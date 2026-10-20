"""실행: streamlit run data/experiments/종목별체력미달자변화률2with장병.py

CSV 저장만: python data/experiments/종목별체력미달자변화률2with장병.py --export
남성 19~24세 기준 적용. 원본에 성별이 없으므로 남성 표본임을 전제로 한다.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / 'data/processed/KS_NFA_PROCESSED.csv'
STANDARD_PATH = ROOT / 'data/definitions/grade3_male_19_24.csv'
OUTPUT_DIR = ROOT / 'data/experiments/results/종목별체력미달자변화률2with장병'
CARDIO_COLS = ['TRAD', 'STEP', '20M_RUN']
MEASURES = ['REL_GRIP', 'CROSS_UP', 'SIT_REACH'] + CARDIO_COLS
AREAS = {'근력': 'REL_GRIP', '근지구력': 'CROSS_UP',
         '심폐지구력': 'cardio', '유연성': 'SIT_REACH'}


def analyze(complete_only=True):
    """날짜순 첫 3회를 사용하고, 종목별로 같은 장병 집단을 비교한다."""
    df = pd.read_csv(DATA_PATH, dtype={'M_CODE': 'string'}, low_memory=False)
    required = ['M_CODE', 'AGE', 'MESURE_DE'] + MEASURES
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f'필수 컬럼 없음: {sorted(missing)}')
    standards = pd.read_csv(STANDARD_PATH)
    standards = standards.loc[
        standards.sex.eq('M') & standards.age_min.eq(19) & standards.age_max.eq(24)
    ].copy()
    if standards.exercise.duplicated().any():
        raise ValueError('기준표의 종목이 중복되어 있습니다.')
    std = standards.set_index('exercise')
    for col in MEASURES:
        if col not in std.index or std.loc[col, 'rule'] != 'min_inclusive':
            raise ValueError(f'{col}: 최소값 이상 기준을 확인하세요.')
        if pd.isna(std.loc[col, 'min_value']):
            raise ValueError(f'{col}: 기준값이 없습니다.')
    for col in ['AGE'] + MEASURES:
        df[col] = pd.to_numeric(df[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
    df = df.loc[df.AGE.between(19, 24) & df.M_CODE.notna()
                & df.M_CODE.str.strip().ne('')].copy()
    # 날짜를 모르는 행을 제거하면 이후 측정이 앞 회차로 바뀌므로 오류로 안내한다.
    df['_date'] = pd.to_datetime(
        df.MESURE_DE.astype('string').str.replace(r'\.0$', '', regex=True),
        format='%Y%m%d', errors='coerce')
    if df['_date'].isna().any():
        raise ValueError('MESURE_DE에 해석할 수 없는 날짜가 있습니다.')
    df['_order'] = range(len(df))
    df = df.sort_values(['M_CODE', '_date', '_order'])
    df = df.loc[df.groupby('M_CODE').M_CODE.transform('size').ge(3)].copy()
    df['회차'] = df.groupby('M_CODE').cumcount() + 1
    df = df.loc[df['회차'].le(3)].copy()
    if df.empty:
        raise ValueError('19~24세 중 3회 이상 측정한 대상자가 없습니다.')
    for col in MEASURES:
        df[f'{col}_미달'] = (df[col] < float(std.loc[col, 'min_value'])).astype('boolean').mask(df[col].isna())
    df['심폐측정값수'] = df[CARDIO_COLS].notna().sum(axis=1)
    df['심폐검사'] = pd.Series(pd.NA, index=df.index, dtype='string')
    df['cardio_미달'] = pd.Series(pd.NA, index=df.index, dtype='boolean')
    for col in CARDIO_COLS:
        chosen = df['심폐측정값수'].eq(1) & df[col].notna()
        df.loc[chosen, '심폐검사'] = col
        df.loc[chosen, 'cardio_미달'] = df.loc[chosen, f'{col}_미달']
    rows, changes = [], []
    for label, col in AREAS.items():
        risk = f'{col}_미달'
        complete = df.groupby('M_CODE')[risk].count().eq(3)
        target = df.loc[df.M_CODE.isin(complete[complete].index)] if complete_only else df
        counts = []
        for round_no in (1, 2, 3):
            values = target.loc[target['회차'].eq(round_no), risk]
            fail, valid = int(values.sum()), int(values.notna().sum())
            counts.append(fail)
            rows.append({'종목': label, '회차': f'{round_no}차', '대상자수': len(values),
                         '평가가능수': valid, '판정불가수': int(values.isna().sum()),
                         '미달자수': fail, '미달률(%)': fail / valid * 100 if valid else np.nan,
                         '3회완전측정제외수': int((~complete).sum()) if complete_only else 0})
        for before, after in ((1, 2), (2, 3), (1, 3)):
            a, b = counts[before - 1], counts[after - 1]
            changes.append({'종목': label, '비교': f'{before}차→{after}차',
                            '기준미달자수': a, '비교미달자수': b, '증감인원': b - a,
                            '변동률(%)': (b - a) / a * 100 if a else np.nan})
    return pd.DataFrame(rows), pd.DataFrame(changes), df.drop(columns=['_date', '_order']), standards


def main():
    st.set_page_config(page_title='종목별 체력 미달자 변화', layout='wide')
    st.title('종목별 1·2·3차 체력 미달자 변화')
    st.caption('남성 19~24세 3등급 기준 · MESURE_DE 날짜순 첫 3회 (같은 날짜는 원본 행 순서)')
    st.info('원본에 성별 컬럼이 없어 남성 표본을 전제로 합니다. 19~24세 측정 기록이 3회 이상인 장병을 분석합니다.')
    complete_only = st.checkbox('종목별 3회 모두 판정 가능한 동일 장병만 비교', value=True)
    try:
        summary, changes, detail, standards = analyze(complete_only)
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.metric('3회 이상 측정 장병', f'{detail.M_CODE.nunique():,}명')
    st.caption('미달 = 측정값 < 3등급 최소값. 기준값과 같으면 충족. 심폐는 TRAD·STEP·20M_RUN 중 값이 정확히 1개인 검사를 사용합니다. 결측·복수 심폐값은 판정불가입니다.')
    with st.expander('적용 기준표'):
        st.dataframe(standards.loc[standards.exercise.isin(MEASURES)], hide_index=True)
    st.subheader('종목별 미달 장병 수')
    counts = summary.pivot(index='종목', columns='회차', values='미달자수').reindex(
        index=list(AREAS), columns=['1차', '2차', '3차'])
    st.caption('막대를 클릭하면 해당 종목·회차의 미달 장병 정보를 아래에서 확인할 수 있습니다.')
    selection = alt.selection_point(name='soldier_bar', fields=['종목', '회차'],
                                    on='click', toggle=False, clear='dblclick')
    chart = alt.Chart(summary).mark_bar().encode(
        x=alt.X('종목:N', sort=list(AREAS)),
        xOffset=alt.XOffset('회차:N', sort=['1차', '2차', '3차']),
        y=alt.Y('미달자수:Q', title='미달 장병 수(명)'),
        color=alt.Color('회차:N', sort=['1차', '2차', '3차']),
        opacity=alt.condition(selection, alt.value(1), alt.value(0.35)),
        tooltip=['종목:N', '회차:N', '미달자수:Q', '평가가능수:Q']
    ).add_params(selection)
    event = st.altair_chart(chart, key='soldier_count_chart', on_select='rerun',
                            selection_mode='soldier_bar')
    selected = event.selection.get('soldier_bar', [])
    if selected:
        show_soldiers(detail, selected[0], complete_only)
    else:
        st.info('조회할 종목의 1차·2차·3차 막대를 클릭하세요. 그래프를 두 번 클릭하면 선택이 해제됩니다.')
    st.dataframe(counts, width='stretch')
    st.subheader('종목별 측정 회차에 따른 변화')
    for start in (0, 2):
        for container, label in zip(st.columns(2), list(AREAS)[start:start + 2]):
            with container:
                st.markdown(f'**{label}**')
                trend = counts.loc[label].rename('미달자수').rename_axis('회차').to_frame()
                st.line_chart(trend, y_label='미달 장병 수(명)')
    st.dataframe(summary, hide_index=True)
    st.subheader('미달자 수 변동률')
    st.caption('(비교 회차 미달자 수 − 기준 회차 미달자 수) / 기준 회차 미달자 수 × 100. 음수는 감소, 양수는 증가입니다. 기준 인원이 0명이면 계산하지 않습니다.')
    st.bar_chart(changes.pivot(index='종목', columns='비교', values='변동률(%)')
                 .reindex(index=list(AREAS), columns=['1차→2차', '2차→3차', '1차→3차']),
                 stack=False, y_label='변동률(%)')
    st.dataframe(changes, hide_index=True)
    if not complete_only:
        st.warning('회차별 평가가능 인원이 다르면 미달자 수 변동에 결측의 영향이 포함됩니다.')
    for label, frame, name in [('종목별 집계', summary, 'summary'), ('변동률', changes, 'changes'),
                                ('회차별 상세 판정', detail, 'detail')]:
        st.download_button(f'{label} CSV 다운로드', frame.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'fitness_by_sport_{name}.csv', mime='text/csv')


def show_soldiers(detail, selected, complete_only):
    """선택된 막대 집계와 동일한 조건으로 미달 장병만 조회한다."""
    label, round_label = selected.get('종목'), selected.get('회차')
    if label not in AREAS or round_label not in ['1차', '2차', '3차']:
        return
    risk = f'{AREAS[label]}_미달'
    target = detail
    if complete_only:
        complete = detail.groupby('M_CODE')[risk].count().eq(3)
        target = detail.loc[detail.M_CODE.isin(complete[complete].index)]
    soldiers = target.loc[target['회차'].eq(int(round_label[0]))
                          & target[risk].fillna(False)].copy()
    st.subheader(f'{label} · {round_label} 미달 장병 정보')
    st.metric('선택한 미달 장병', f'{len(soldiers):,}명')
    st.caption('M_CODE는 원본 장병 식별자입니다. 측정값과 원본의 장병 정보를 함께 표시합니다.')
    first = ['M_CODE', 'AGE', 'MESURE_DE', '회차']
    measures = CARDIO_COLS + ['심폐검사'] if label == '심폐지구력' else [AREAS[label]]
    columns = first + measures + [c for c in soldiers.columns if c not in first + measures]
    soldiers = soldiers[columns]
    st.dataframe(soldiers, hide_index=True, width='stretch')
    st.download_button('선택한 미달 장병 CSV 다운로드',
                       soldiers.to_csv(index=False).encode('utf-8-sig'),
                       file_name=f'{label}_{round_label}_미달장병.csv', mime='text/csv',
                       key='selected_soldiers_download')


if __name__ == '__main__':
    if '--export' in sys.argv:
        summary, changes, detail, _ = analyze()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, frame in [('summary', summary), ('changes', changes), ('detail', detail)]:
            frame.to_csv(OUTPUT_DIR / f'fitness_by_sport_{name}.csv', index=False, encoding='utf-8-sig')
        print(summary.to_string(index=False))
        print(changes.to_string(index=False))
        print(f'저장 위치: {OUTPUT_DIR}')
    else:
        main()
