"""실행: python -m streamlit run data/experiments/체력측정항목_전체분포분석.py"""
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from 분석_연령별 import analyze_age

METRICS = {'STRENGTH': '근력·상대악력(%)', 'ENDURANCE': '근지구력(회)',
           'CARDIO': '심폐지구력·VO₂max(mL/kg/min)', 'FLEXIBILITY': '유연성(cm)',
           'BMI': 'BMI(kg/m²)', 'BODY_FAT_PERCENTAGE': '체지방률(%)'}
OUTPUT = Path(__file__).resolve().parent/'results/체력측정항목별분포'


def calculate():
    data = analyze_age(return_first=True)
    rows = []
    for col, label in METRICS.items():
        values = data[col].replace([np.inf, -np.inf], np.nan).dropna()
        q1, q3 = values.quantile([.25, .75])
        iqr = q3-q1
        rows.append({'항목': label, '컬럼': col, '전체장병수': len(data), '유효인원': len(values),
                     '결측인원': len(data)-len(values), '평균': values.mean(), '중앙값': values.median(),
                     '표준편차': values.std(ddof=1), '최솟값': values.min(), '1사분위수': q1,
                     '3사분위수': q3, '최댓값': values.max(), '사분위범위_IQR': iqr,
                     '왜도': values.skew(), '1.5IQR밖인원': int(((values<q1-1.5*iqr)|(values>q3+1.5*iqr)).sum())})
    return pd.DataFrame(rows), data


def main():
    st.set_page_config(page_title='체력 측정 항목별 분포', layout='wide')
    st.title('장병 체력수준 · 6개 측정 항목의 전체 분포')
    st.caption('최종 전처리 자료의 장병별 날짜순 첫 측정 · 첫 측정 당시 19~24세 · 남성 기준')
    try:
        summary, data = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT/'6개항목_기술통계.csv', index=False, encoding='utf-8-sig')
    st.metric('분석 대상 고유 장병', f'{len(data):,}명')
    st.info('한 장병당 첫 측정 1건만 사용합니다. 전처리에서 선정된 대상자 안의 분포이며 원본 전체 모집단 분포가 아닙니다. 결측은 항목별로 제외하고 표준편차는 표본 기준(ddof=1)으로 계산합니다.')
    st.subheader('6개 항목 기술통계 요약')
    st.dataframe(summary.drop(columns='컬럼'), hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format='%.2f')
                                for c in ['평균', '중앙값', '표준편차', '최솟값', '1사분위수', '3사분위수', '최댓값', '사분위범위_IQR', '왜도']})
    bins = st.slider('히스토그램 최대 구간 수', 10, 60, 30, 5)
    st.subheader('전체 항목 히스토그램')
    for start in (0, 2, 4):
        for container, col in zip(st.columns(2), list(METRICS)[start:start+2]):
            with container:
                st.markdown(f'**{METRICS[col]}**')
                values = data[[col]].dropna().rename(columns={col: '측정값'})
                if values.empty:
                    st.info('유효 측정값 없음')
                    continue
                hist = alt.Chart(values).mark_bar(color='#4389bd').encode(
                    x=alt.X('측정값:Q', bin=alt.Bin(maxbins=bins), title=METRICS[col]),
                    y=alt.Y('count():Q', title='장병 수(명)'),
                    tooltip=[alt.Tooltip('측정값:Q', bin=True), alt.Tooltip('count():Q', title='인원')])
                st.altair_chart(hist.properties(height=220))
    st.subheader('선택 항목 · 박스플롯과 해석')
    col = st.selectbox('측정 항목', list(METRICS), format_func=lambda c: METRICS[c])
    row = summary.loc[summary['컬럼'].eq(col)].iloc[0]
    values = data[[col]].dropna().rename(columns={col: '측정값'})
    if not values.empty:
        st.altair_chart(alt.Chart(values).mark_boxplot(extent=1.5, color='#4389bd').encode(
            x=alt.X('측정값:Q', title=METRICS[col])).properties(height=150))
        st.write(f"평균 **{row['평균']:.2f}**, 중앙값 **{row['중앙값']:.2f}**, 표준편차 **{row['표준편차']:.2f}**입니다. "
                 f"가운데 약 50%의 측정값은 **{row['1사분위수']:.2f}~{row['3사분위수']:.2f}** 사이에 있습니다.")
        st.write(f"측정값 범위는 **{row['최솟값']:.2f}~{row['최댓값']:.2f}**입니다. "
                 f"1.5×IQR 기준 바깥 관측값은 **{int(row['1.5IQR밖인원']):,}명**이며 자동으로 제거하지 않습니다.")
        if pd.notna(row['왜도']):
            direction = '큰 값 쪽으로 꼬리가 긴' if row['왜도'] > 0 else '작은 값 쪽으로 꼬리가 긴' if row['왜도'] < 0 else '왜도가 0인'
            st.caption(f"표본 왜도는 {row['왜도']:.2f}로 {direction} 방향을 나타냅니다. 히스토그램과 함께 보며, 이 값만으로 정규분포 여부를 확정하지 않습니다.")
    with st.expander('통계량·그래프 읽는 방법', expanded=True):
        st.markdown('''
- **평균·중앙값**: 평균은 전체 값의 합/인원이며, 중앙값은 정렬했을 때 가운데 값입니다. 둘의 차이와 분포 모양을 함께 확인합니다.
- **표준편차**: 평균 주변으로 개인별 값이 얼마나 퍼져 있는지 보여줍니다. 표준편차 자체는 신뢰구간이 아닙니다.
- **히스토그램**: 구간별 인원으로 집중 구간·비대칭·여러 봉우리를 확인합니다. 구간 수에 따라 모양이 달라질 수 있습니다.
- **박스플롯**: 상자는 1~3사분위수, 내부 선은 중앙값, 수염은 1.5×IQR 범위 내 관측값까지입니다. 바깥 점은 오류로 확정된 값이 아닙니다.
- 항목마다 단위가 달라 표준편차의 절댓값만으로 서로 다른 종목의 산포를 비교하지 않습니다. 미달률이나 통과확률을 구하는 분석과도 구분됩니다.
''')
    st.download_button('6개 항목 기술통계 CSV', summary.to_csv(index=False).encode('utf-8-sig'),
                       file_name='6개항목_기술통계.csv', mime='text/csv')


if __name__ == '__main__':
    main()
