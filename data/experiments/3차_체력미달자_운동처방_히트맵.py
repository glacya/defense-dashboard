"""3차 측정 당시 종목별 미달자의 운동처방률. --export로 CSV 저장."""
from pathlib import Path
import argparse

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from 분석_연령별 import analyze_age
from 운동_처방현황분석 import load_catalog

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/processed'
OUTPUT = ROOT / 'data/experiments/results/3차_체력미달자_운동처방_히트맵'
AREAS = {'근력': 'STRENGTH', '근지구력': 'ENDURANCE',
         '심폐지구력': 'CARDIO', '유연성': 'FLEXIBILITY'}


def calculate():
    """첫 측정 19~24세 표본의 날짜순 세 번째 측정과 당시 처방을 연결한다."""
    cohort = analyze_age(return_first=True).SOLDIER_ID
    measures = pd.read_csv(DATA / 'KS_NFA_PROCESSED.csv',
                           dtype={'SOLDIER_ID': 'string', 'MESURE_ID': 'Int64'})
    if measures[['SOLDIER_ID', 'MESURE_ID']].isna().any().any() or measures.MESURE_ID.duplicated().any():
        raise ValueError('측정 식별자에 결측 또는 중복이 있습니다.')
    measures['_date'] = pd.to_datetime(measures.MESURE_DE.astype('string').str.replace(
        r'\.0$', '', regex=True), format='%Y%m%d', errors='raise')
    measures = measures.loc[measures.SOLDIER_ID.isin(cohort)].copy()
    measures['_order'] = range(len(measures))
    measures = measures.sort_values(['SOLDIER_ID', '_date', '_order'])
    measures['회차'] = measures.groupby('SOLDIER_ID').cumcount() + 1
    third = measures.loc[measures['회차'].eq(3)].copy()
    if third.empty:
        raise ValueError('분석 가능한 3차 측정이 없습니다.')
    records = pd.read_csv(DATA / 'KS_NFA_PRESCRIPTION.csv',
                          dtype={'MESURE_ID': 'Int64', 'PRESCRIPTION_TYPE_ID': 'string'})
    if records[['MESURE_ID', 'PRESCRIPTION_TYPE_ID']].isna().any().any():
        raise ValueError('처방 연결 식별자에 결측이 있습니다.')
    catalog = load_catalog()
    joined = records.merge(catalog, on='PRESCRIPTION_TYPE_ID', how='left', validate='many_to_one')
    if joined.PRESCRIPTION.isna().any():
        raise ValueError('운동 목록에 없는 처방유형이 있습니다.')
    linked = joined.loc[joined.MESURE_ID.isin(third.MESURE_ID),
                        ['MESURE_ID', 'PRESCRIPTION']].drop_duplicates()
    people = third.loc[third.MESURE_ID.isin(linked.MESURE_ID)].copy()
    if people.empty:
        raise ValueError('3차 측정에 연결되는 운동처방이 없습니다.')
    standards = pd.read_csv(ROOT / 'data/definitions/grade3_male_19_24.csv')
    standards = standards.loc[standards.sex.eq('M') & standards.age_min.eq(19) & standards.age_max.eq(24)]
    if standards.exercise.duplicated().any():
        raise ValueError('기준표에 종목이 중복되어 있습니다.')
    standards = standards.set_index('exercise')
    membership = linked.groupby('PRESCRIPTION').MESURE_ID.agg(set).to_dict()
    rows = []
    for label, col in AREAS.items():
        if col not in standards.index or standards.loc[col, 'rule'] != 'min_inclusive':
            raise ValueError(f'{label}: 미달 판정 기준을 확인하세요.')
        cut = float(standards.loc[col, 'min_value'])
        if not np.isfinite(cut):
            raise ValueError(f'{label}: 기준값이 유효하지 않습니다.')
        values = pd.to_numeric(people[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
        fail_ids = set(people.loc[values.lt(cut), 'MESURE_ID'])
        for exercise in catalog.PRESCRIPTION.unique():
            prescribed = membership.get(exercise, set())
            count = len(fail_ids & prescribed)
            rows.append({'운동명': exercise, '체력종목': label, '미달기준값': cut,
                         '평가가능인원': int(values.notna().sum()), '판정불가인원': int(values.isna().sum()),
                         '미달인원': len(fail_ids), '미달자중처방인원': count,
                         '미달자내처방률(%)': count / len(fail_ids) * 100 if fail_ids else np.nan,
                         '전체처방인원': len(prescribed)})
    summary = {'3차측정인원': len(third), '처방기록있는인원': len(people),
               '처방기록없음제외': len(third) - len(people), '3차측정없음': len(cohort) - len(third)}
    return pd.DataFrame(rows), summary


def main():
    st.set_page_config(page_title='3차 체력 미달자 운동처방', layout='wide')
    st.title('3차 체력 미달자의 운동처방 현황')
    st.caption('장병별 날짜순 세 번째 측정과 그 측정 당시의 처방을 연결합니다. 이후 회차가 있어도 3차를 사용합니다.')
    try:
        result, summary = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    for column, (label, value) in zip(st.columns(4), summary.items()):
        column.metric(label, f'{value:,}명')
    st.info('색은 해당 종목 미달자 중 해당 운동을 처방받은 비율입니다. '
            '예: 심폐 미달자 100명 중 달리기 처방 40명 → 40%. 운동 수행률이나 체력 개선률이 아닙니다.')
    st.caption('첫 측정 당시 19~24세 표본 · 남성 19~24세 3등급 기준 미만=미달 · '
               '처방 기록 없는 3차 측정은 제외 · 같은 측정·운동 중복 제거 · 종목 결측은 해당 분모에서 제외')
    ranking = result[['운동명', '전체처방인원']].drop_duplicates().sort_values(
        ['전체처방인원', '운동명'], ascending=[False, True])
    mode = st.radio('표시할 운동', ['처방 인원 상위 운동', '직접 선택'], horizontal=True)
    if mode == '직접 선택':
        defaults = [name for name in ['달리기', '발목 돌리기'] if name in set(ranking.운동명)]
        names = st.multiselect('운동 검색·선택', ranking.운동명.tolist(), default=defaults)
    else:
        count = st.slider('상위 운동 수', 5, 50, 20, 5)
        names = ranking.loc[ranking.전체처방인원.gt(0)].head(count).운동명.tolist()
    view = result.loc[result.운동명.isin(names)].copy()
    if view.empty:
        st.info('표시할 운동을 선택하세요.')
    else:
        view['셀표시'] = view.apply(lambda row: (
            f"{row['미달자내처방률(%)']:.2f}% ({row['미달자중처방인원']}/{row['미달인원']})"
            if row['미달인원'] else '미달자 없음'), axis=1)
        base = alt.Chart(view).encode(
            x=alt.X('체력종목:N', sort=list(AREAS), title=None),
            y=alt.Y('운동명:N', sort=names, title=None),
            tooltip=['운동명:N', '체력종목:N', '미달인원:Q', '미달자중처방인원:Q',
                     alt.Tooltip('미달자내처방률(%):Q', format='.2f'), '전체처방인원:Q'])
        chart = base.mark_rect().encode(color=alt.Color(
            '미달자내처방률(%):Q', scale=alt.Scale(domain=[0, 100], scheme='blues'), title='처방률(%)'))
        text = base.mark_text(fontSize=12).encode(text='셀표시:N', color=alt.condition(
            alt.datum['미달자내처방률(%)'] >= 55, alt.value('white'), alt.value('#172b4d')))
        st.altair_chart((chart + text).properties(height=max(150, len(names) * 38)), width='stretch')
        st.caption('셀: 처방률% (해당 운동 처방 인원/해당 종목 미달 인원). 여러 종목 미달자는 각 열에 포함됩니다. '
                   '미달자 0명인 종목의 비율은 계산하지 않습니다. 처방 인원이 적은 운동은 함께 확인하세요.')
        st.dataframe(view.drop(columns='셀표시'), hide_index=True)
    st.download_button('전체 운동 집계 CSV 다운로드', result.to_csv(index=False).encode('utf-8-sig'),
                       file_name='3차_체력미달자_운동처방률.csv', mime='text/csv')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', action='store_true', help='화면 없이 전체 집계 CSV 저장')
    args = parser.parse_args()
    if args.export:
        frame, info = calculate()
        OUTPUT.mkdir(parents=True, exist_ok=True)
        frame.to_csv(OUTPUT / '3차_체력미달자_운동처방률.csv', index=False, encoding='utf-8-sig')
        print(info)
        print(f'저장 완료: {OUTPUT}')
    else:
        main()
