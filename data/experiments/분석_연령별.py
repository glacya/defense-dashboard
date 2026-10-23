"""실행: streamlit run data/experiments/연령별분석.py

원본 processed 데이터에서 3회 측정 여부와 관계없이 장병별 첫 측정을 분석한다.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parents[2] / 'data/processed/KS_NFA_PROCESSED.csv'
METRICS = {
    'STRENGTH': '상대악력(%)', 'ENDURANCE': '교차윗몸일으키기(회)',
    'FLEXIBILITY': '앉아윗몸앞으로굽히기(cm)',
    'CARDIO': '심폐지구력(VO₂max, mL/kg/min)',
    'HEIGHT': '키(cm)', 'WEIGHT': '체중(kg)', 'BMI': 'BMI', 'BODY_FAT_PERCENTAGE': '체지방률(%)',
}


def analyze_age(return_first=False):
    df = pd.read_csv(DATA_PATH, dtype={'SOLDIER_ID': 'string'}, low_memory=False)
    required = {'SOLDIER_ID', 'AGE', 'MESURE_DE'} | set(METRICS)
    if required - set(df.columns):
        raise ValueError(f'필수 컬럼 없음: {sorted(required - set(df.columns))}')
    source_rows = len(df)
    df = df.loc[df.SOLDIER_ID.notna() & df.SOLDIER_ID.str.strip().ne('')].copy()
    df['_date'] = pd.to_datetime(
        df.MESURE_DE.astype('string').str.replace(r'\.0$', '', regex=True),
        format='%Y%m%d', errors='coerce')
    if df['_date'].isna().any():
        raise ValueError('측정일이 없거나 날짜 형식이 잘못된 기록이 있습니다. 첫 측정 순서를 확인해주세요.')
    df['_order'] = range(len(df))
    # 전체 기록 중 첫 측정을 먼저 선택하고, 그 당시 나이가 19~24세인지 확인한다.
    first = df.sort_values(['SOLDIER_ID', '_date', '_order']).drop_duplicates('SOLDIER_ID').copy()
    for col in ['AGE'] + list(METRICS):
        first[col] = pd.to_numeric(first[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
    first = first.loc[first.AGE.isin(range(19, 25))].copy()
    first['AGE'] = first.AGE.astype(int)
    if first.empty:
        raise ValueError('첫 측정 당시 19~24세인 장병이 없습니다.')
    if return_first:
        return first.drop(columns=['_date', '_order'])
    population = first.groupby('AGE').size().reindex(range(19, 25), fill_value=0)
    people = population.rename('장병 수').rename_axis('연령').reset_index()
    people['구성비(%)'] = people['장병 수'] / len(first) * 100
    rows = []
    for age in range(19, 25):
        group = first.loc[first.AGE.eq(age)]
        for col, label in METRICS.items():
            values = group[col]
            rows.append({'연령': age, '항목': label, '컬럼': col, '장병 수': len(group),
                         '유효 측정 인원': int(values.count()), '결측 인원': int(values.isna().sum()),
                         '평균': values.mean(), '표준편차': values.std(ddof=1)})
    return people, pd.DataFrame(rows), source_rows


def main():
    st.set_page_config(page_title='연령별분석', layout='wide')
    st.title('19~24세 연령별 인원 및 체력 기술통계')
    st.caption('KS_NFA_PROCESSED.csv 직접 사용 · 장병별 날짜순 첫 측정 · 전처리에서 선정된 3회 측정 대상자의 첫 측정 사용')
    try:
        people, stats, source_rows = analyze_age()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.caption('동일 측정일은 원본 행 순서로 첫 기록을 정합니다. 첫 측정 당시 나이가 19~24세인 장병만 포함합니다.')
    left, right = st.columns(2)
    left.metric('원본 측정 기록', f'{source_rows:,}건')
    right.metric('분석 대상 고유 장병', f"{people['장병 수'].sum():,}명")
    st.subheader('연령별 장병 수')
    chart_people = people.assign(연령=people['연령'].astype(str) + '세').set_index('연령')
    st.bar_chart(chart_people[['장병 수']], y_label='장병 수(명)')
    st.dataframe(people, hide_index=True, column_config={
        '구성비(%)': st.column_config.NumberColumn(format='%.2f%%')})
    st.subheader('항목별 평균·표준편차')
    metric = st.selectbox('분석 항목', list(METRICS), format_func=lambda col: METRICS[col])
    selected = stats.loc[stats['컬럼'].eq(metric)].drop(columns=['컬럼', '항목'])
    st.dataframe(selected, hide_index=True, column_config={
        '평균': st.column_config.NumberColumn(format='%.2f'),
        '표준편차': st.column_config.NumberColumn(format='%.2f')})
    means = selected.assign(연령=selected['연령'].astype(str) + '세').set_index('연령')
    st.bar_chart(means[['평균']], y_label=METRICS[metric])
    st.caption('평균·표준편차는 항목별 결측값을 제외하고 계산합니다. 표준편차는 표본 표준편차(ddof=1)이며 유효 인원이 2명 미만이면 표시하지 않습니다. 심폐는 전처리에서 통합된 CARDIO(VO₂max)를 사용합니다.')
    with st.expander('전체 항목 집계'):
        st.dataframe(stats.drop(columns='컬럼'), hide_index=True)
    st.download_button('연령별 인원 CSV 다운로드', people.to_csv(index=False).encode('utf-8-sig'),
                       file_name='연령별_인원.csv', mime='text/csv')
    st.download_button('연령별 평균·표준편차 CSV 다운로드', stats.to_csv(index=False).encode('utf-8-sig'),
                       file_name='연령별_기술통계.csv', mime='text/csv')


if __name__ == '__main__':
    main()
