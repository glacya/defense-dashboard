"""실행: python -m streamlit run data/experiments/bmi별분석.py

장병별 첫 측정을 BMI 고정 구간으로 나눠 인원과 항목별 기술통계를 비교한다.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 분석_연령별 import analyze_age, METRICS, DATA_PATH

BMI_GROUPS = ['낮음', '보통', '높음']
BMI_BINS = [0, 18.5, 25, np.inf]
BMI_DESCRIPTION = '대한비만학회 성인 BMI 기준을 통합한 분석용 3그룹: 낮음=저체중(BMI<18.5), 보통=정상·비만전단계(18.5≤BMI<25), 높음=1·2·3단계 비만(BMI≥25). 보통에는 비만전단계가 포함되므로 정상체중만을 뜻하지 않습니다.'
BMI_SOURCE = 'https://general.kosso.or.kr/html/user/core/view/reaction/main/kosso/inc/data/guideline2022_vol8.pdf'


def analyze_bmi():
    # 연령별분석과 동일한 대상자·날짜순 첫 측정·결측 처리를 재사용한다.
    first = analyze_age(return_first=True)
    excluded = int((first.BMI.isna() | first.BMI.le(0)).sum())
    first = first.loc[first.BMI.notna() & first.BMI.gt(0)].copy()
    if first.empty:
        raise ValueError('분석 가능한 BMI가 없습니다.')
    first['BMI그룹'] = pd.cut(first.BMI, BMI_BINS, labels=BMI_GROUPS, right=False)
    counts = first.groupby('BMI그룹', observed=False).size().reindex(BMI_GROUPS)
    people = pd.DataFrame({'BMI그룹': BMI_GROUPS,
                           '구간': ['BMI < 18.5', '18.5 ≤ BMI < 25', 'BMI ≥ 25'],
                           '장병 수': counts.to_numpy()})
    people['구성비(%)'] = people['장병 수']/len(first)*100
    rows = []
    for label in BMI_GROUPS:
        group = first.loc[first['BMI그룹'].eq(label)]
        for col, name in METRICS.items():
            values = group[col]
            rows.append({'BMI그룹': label, '항목': name, '컬럼': col, '장병 수': len(group),
                         '유효 측정 인원': int(values.count()), '결측 인원': int(values.isna().sum()),
                         '평균': values.mean(), '표준편차': values.std(ddof=1)})
    return people, pd.DataFrame(rows), first, excluded


def main():
    st.set_page_config(page_title='BMI별분석', layout='wide')
    st.title('BMI 그룹별 인원 및 체력 기술통계')
    st.caption('KS_NFA_PROCESSED.csv · 첫 측정 당시 19~24세 · 장병별 날짜순 첫 측정 사용')
    try:
        people, stats, first, excluded = analyze_bmi()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.info(BMI_DESCRIPTION)
    st.caption(f'분류 근거: {BMI_SOURCE}')
    st.caption('전처리에서 선정된 대상자 안에서 분석합니다. 같은 날짜는 원본 행 순서로 첫 측정을 정하며, BMI 결측·0 이하 값은 제외합니다.')
    left, right = st.columns(2)
    left.metric('분석 대상 고유 장병', f'{len(first):,}명')
    right.metric('BMI 판정불가 제외', f'{excluded:,}명')
    st.subheader('BMI 그룹별 장병 수와 구간')
    st.bar_chart(people.set_index('BMI그룹')[['장병 수']], y_label='장병 수(명)')
    st.dataframe(people, hide_index=True, column_config={
        '구성비(%)': st.column_config.NumberColumn(format='%.2f%%')})
    st.subheader('항목별 평균·표준편차')
    metric = st.selectbox('분석 항목', list(METRICS), format_func=lambda c: METRICS[c])
    selected = stats.loc[stats['컬럼'].eq(metric)].drop(columns=['컬럼', '항목'])
    st.dataframe(selected, hide_index=True, column_config={
        '평균': st.column_config.NumberColumn(format='%.2f'),
        '표준편차': st.column_config.NumberColumn(format='%.2f')})
    st.bar_chart(selected.set_index('BMI그룹')[['평균']], y_label=METRICS[metric])
    st.caption('평균·표준편차는 항목별 결측을 제외해 계산합니다. 표준편차는 표본 기준(ddof=1)이며 유효 인원이 2명 미만이면 공란입니다. 심폐는 통합 CARDIO(VO₂max) 값입니다.')
    st.caption('이 화면은 기술통계입니다. 평균 차이가 통계적으로 유의한지는 아노바_bmi.py의 검정·사후검정 결과로 확인하세요.')
    with st.expander('전체 항목 집계'):
        st.dataframe(stats.drop(columns='컬럼'), hide_index=True)
    for label, frame, name in [('BMI별 인원', people, '인원'), ('BMI별 평균·표준편차', stats, '기술통계')]:
        st.download_button(f'{label} CSV 다운로드', frame.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'bmi별_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
