"""실행: python -m streamlit run data/experiments/t검정_단일표본_심폐기준비교.py"""
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from scipy.stats import ttest_1samp, t

from 분석_연령별 import analyze_age


def calculate(reference=42.0):
    data = analyze_age(return_first=True)
    values = data.CARDIO.replace([np.inf, -np.inf], np.nan).dropna()
    n = len(values)
    if n < 2 or values.std(ddof=1) <= 0:
        raise ValueError('유효 인원 2명 이상과 양의 분산이 필요합니다.')
    test = ttest_1samp(values, popmean=reference, alternative='two-sided')
    mean, sd = values.mean(), values.std(ddof=1)
    margin = t.ppf(.975, n-1)*sd/np.sqrt(n)
    row = {'유효인원': n, '결측제외인원': len(data)-n, '기준평균': reference,
           '표본평균': mean, '표본표준편차': sd, '평균차_표본-기준': mean-reference,
           't값': test.statistic, '자유도': n-1, '양측p값': test.pvalue,
           '평균95%CI하한': mean-margin, '평균95%CI상한': mean+margin,
           'Cohen_d': (mean-reference)/sd}
    return pd.DataFrame([row]), values


def main():
    st.set_page_config(page_title='단일표본 t검정', layout='wide')
    st.title('단일표본 t검정 · 심폐 평균과 기준값 비교')
    st.caption('첫 측정 당시 19~24세 · 장병별 날짜순 첫 측정 · CARDIO(VO₂max, mL/kg/min)')
    reference = st.number_input('비교할 기준평균', value=42.0, step=0.1)
    st.write(f'H₀: 모집단 심폐 평균 = {reference:g} / H₁: 모집단 심폐 평균 ≠ {reference:g} (양측검정)')
    try:
        result, values = calculate(reference)
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    row = result.iloc[0]
    a, b, c = st.columns(3)
    a.metric('표본 평균', f"{row['표본평균']:.2f}")
    b.metric('기준과 평균 차이', f"{row['평균차_표본-기준']:+.2f}")
    c.metric('양측 p값', f"{row['양측p값']:.3e}")
    st.dataframe(result, hide_index=True)
    chart = alt.Chart(pd.DataFrame({'측정값': values})).mark_bar(color='#4389bd').encode(
        x=alt.X('측정값:Q', bin=alt.Bin(maxbins=30), title='심폐 VO₂max'), y=alt.Y('count():Q', title='인원'))
    rule = alt.Chart(pd.DataFrame({'기준': [reference]})).mark_rule(color='#e67e35', strokeWidth=3).encode(x='기준:Q')
    st.altair_chart(chart+rule)
    st.caption('주황선은 비교 기준입니다. 개인 측정값의 분포와 모집단 평균 검정은 구분합니다.')
    st.subheader('결과 해석')
    direction = '높습니다' if row['평균차_표본-기준'] > 0 else '낮습니다' if row['평균차_표본-기준'] < 0 else '같습니다'
    st.write(f"표본 평균은 기준보다 {abs(row['평균차_표본-기준']):.2f} {direction} "
             f"모집단 평균의 95% 신뢰구간은 {row['평균95%CI하한']:.2f}~{row['평균95%CI상한']:.2f}입니다.")
    st.write('양측 p<0.05이므로 귀무가설을 기각합니다. 모집단 평균이 기준과 다르다는 근거가 있습니다.' if row['양측p값'] < .05
             else '귀무가설을 기각하지 못합니다. 평균이 기준과 다르다는 근거가 충분하지 않으며 같다고 증명한 것은 아닙니다.')
    st.latex(r't=\frac{\bar{x}-\mu_0}{s/\sqrt{n}},\qquad df=n-1')
    st.info('42는 개인 심폐 미달 판정의 경계값을 평균 비교의 기준으로 사용한 것입니다. 평균이 42보다 높아도 모든 장병이 충족한다는 뜻은 아닙니다. 독립 관측과 평균의 표본분포 가정을 전제로 하며, 전처리로 선정한 표본의 대표성은 별도 검토가 필요합니다.')
    st.caption('유의수준 0.05, 양측검정입니다. 기준값을 여러 번 바꿔 유의한 결과만 고르면 탐색적 분석이 되므로 보고 시 명시하세요.')
    st.download_button('단일표본 t검정 CSV', result.to_csv(index=False).encode('utf-8-sig'), file_name='단일표본_t검정_심폐.csv', mime='text/csv')


if __name__ == '__main__':
    main()
