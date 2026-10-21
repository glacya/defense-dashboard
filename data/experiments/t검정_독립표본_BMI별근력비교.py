"""실행: python -m streamlit run data/experiments/t검정_독립표본_BMI별근력비교.py"""
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from scipy.stats import levene, ttest_ind, t

from 분석_bmi별 import analyze_bmi


def calculate():
    boundaries, _, data, excluded = analyze_bmi()
    a = data.loc[data['BMI그룹'].eq('낮음'), 'STRENGTH'].dropna().to_numpy()
    b = data.loc[data['BMI그룹'].eq('높음'), 'STRENGTH'].dropna().to_numpy()
    if min(len(a), len(b)) < 2 or min(np.var(a, ddof=1), np.var(b, ddof=1)) <= 0:
        raise ValueError('각 그룹 최소 2명과 양의 분산이 필요합니다.')
    _, lp = levene(a, b, center='median')
    equal = lp >= .05
    test = ttest_ind(a, b, equal_var=equal, alternative='two-sided')
    n1, n2 = len(a), len(b)
    v1, v2 = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled = ((n1-1)*v1+(n2-1)*v2)/(n1+n2-2)
    se = np.sqrt(pooled*(1/n1+1/n2)) if equal else np.sqrt(v1/n1+v2/n2)
    df = n1+n2-2 if equal else (v1/n1+v2/n2)**2/((v1/n1)**2/(n1-1)+(v2/n2)**2/(n2-1))
    diff = a.mean()-b.mean()
    margin = t.ppf(.975, df)*se
    result = pd.DataFrame([{'적용검정': 'Student t검정' if equal else 'Welch t검정',
                            'Levene_p값': lp, '낮음인원': n1, '높음인원': n2,
                            '낮음평균': a.mean(), '높음평균': b.mean(), '평균차_낮음-높음(%p)': diff,
                            't값': test.statistic, '자유도': df, '양측p값': test.pvalue,
                            '평균차95%CI하한': diff-margin, '평균차95%CI상한': diff+margin}])
    return result, boundaries, data, excluded


def main():
    st.set_page_config(page_title='독립표본 t검정', layout='wide')
    st.title('독립표본 t검정 · BMI 낮음 vs 높음의 근력')
    st.write('H₀: 두 BMI 집단의 모집단 상대악력 평균이 같다. H₁: 두 평균이 다르다 (양측검정).')
    try:
        result, boundaries, data, excluded = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.dataframe(boundaries, hide_index=True)
    st.caption(f'첫 측정 BMI 삼분위의 낮음·높음만 비교하며 중간 집단은 제외합니다. 의학적 분류가 아닙니다. BMI 결측·0 이하 제외 {excluded}명. 장병별 첫 측정으로 두 집단의 사람이 겹치지 않습니다.')
    row = result.iloc[0]
    st.info(f"Levene p={row['Levene_p값']:.3e}: 이 화면의 선택 규칙에 따라 {row['적용검정']}을 적용합니다. p≥0.05이면 등분산 Student, p<0.05이면 Welch입니다. Levene 비유의성이 등분산의 증명은 아닙니다.")
    left, middle, right = st.columns(3)
    left.metric('적용 검정', row['적용검정'])
    middle.metric('양측 p값', f"{row['양측p값']:.3e}")
    right.metric('유의수준 0.05 기준', '귀무가설 기각' if row['양측p값'] < .05 else '기각 못함')
    st.caption('e−185는 ×10⁻¹⁸⁵를 뜻합니다. p값이 매우 작아 일반 소수점 표시에서는 0.000으로 보일 수 있으므로 지수 표기합니다. Levene p값은 등분산 진단용이며 평균 차이의 양측 p값과 구분하세요.')
    st.dataframe(result, hide_index=True, column_config={
        '양측p값': st.column_config.NumberColumn('평균 차이 검정 p값(양측)', format='%.3e'),
        'Levene_p값': st.column_config.NumberColumn('등분산 검정 p값(Levene)', format='%.3e')})
    displayed = data.loc[data['BMI그룹'].isin(['낮음', '높음'])].dropna(subset=['STRENGTH'])
    st.altair_chart(alt.Chart(displayed).mark_boxplot(extent=1.5).encode(
        x=alt.X('BMI그룹:N', sort=['낮음', '높음']), y=alt.Y('STRENGTH:Q', title='상대악력(%)')))
    st.subheader('표본 결과와 모집단 평균에 대한 추론')
    direction = '높습니다' if row['평균차_낮음-높음(%p)'] > 0 else '낮습니다'
    st.write(f"**표본에서 관찰한 결과:** BMI 낮음 집단의 표본 평균 {row['낮음평균']:.2f}%, 높음 집단의 표본 평균 {row['높음평균']:.2f}%로, "
             f"낮음 집단이 {abs(row['평균차_낮음-높음(%p)']):.2f}%p {direction} "
             '이는 현재 표본에서 계산한 수치입니다.')
    st.write(f"**양측 p값 = {row['양측p값']:.3e}**. " +
             ('p<0.05이므로 두 집단의 모집단 평균이 같다는 귀무가설을 기각합니다. 검정 가정 아래 BMI 낮음·높음 집단의 모집단 상대악력 평균이 다르다는 통계적 근거가 있습니다.' if row['양측p값'] < .05
              else '두 집단의 모집단 평균이 같다는 귀무가설을 기각하지 못합니다. 모집단 평균 차이를 확인할 근거가 충분하지 않으며, 두 모집단 평균이 같다고 증명한 것은 아닙니다.'))
    st.write(f"**모집단 평균 차이의 추정:** 낮음−높음의 95% 신뢰구간은 "
             f"**{row['평균차95%CI하한']:.2f}~{row['평균차95%CI상한']:.2f}%p**입니다. "
             '개인별 근력 차이의 범위가 아니라 두 집단 모집단 평균 차이에 대한 구간 추정입니다.')
    st.caption('95% 신뢰수준은 같은 표집·계산 절차를 반복하면 만들어진 구간의 약 95%가 실제 모집단 평균 차이를 포함한다는 의미입니다.')
    st.info('일반화 범위: 이 표본은 국민체력100 자료 중 남성 19~24세와 전처리·반복 측정 선정 조건을 충족한 대상자입니다. 전체 장병을 무작위로 뽑은 표본으로 확인된 것은 아니므로, 전체 장병 모집단에 같은 차이가 있다고 단정할 수 없습니다. 모집단 추론은 표본의 대표성과 검정 가정이 뒷받침되는 범위에서 해석합니다.')
    st.info('기존 BMI ANOVA·사후검정과 질문이 겹치는 두 집단 비교 실습입니다. 기존 결과를 확인한 뒤 선정한 비교이므로 탐색적 분석으로 보고합니다. BMI가 근력을 변화시켰다는 인과결론은 아니며 상대악력과 BMI에 체중이 공통 관여합니다.')
    st.caption('유의수준 0.05, 양측검정. 반복 측정·대응표본 t검정이 아닙니다. 개인 간 독립성·분포·극단값 및 표본 대표성도 검토해야 합니다.')
    st.download_button('독립표본 t검정 CSV', result.to_csv(index=False, float_format='%.6e').encode('utf-8-sig'), file_name='독립표본_t검정_BMI근력.csv', mime='text/csv')


if __name__ == '__main__':
    main()
