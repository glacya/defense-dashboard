"""streamlit run data/experiments/아노바_bmi.py"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import f_oneway, levene, tukey_hsd
import streamlit as st
import altair as alt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 분석_연령별 import METRICS
from 분석_bmi별 import analyze_bmi, BMI_GROUPS, BMI_DESCRIPTION
from statistics_compat import welch_anova, games_howell
CARDIO_COLS = ['CARDIO']

METRICS = {**METRICS, 'CARDIO': '심폐지구력(VO₂max, mL/kg/min)'}
EXERCISES = ['STRENGTH', 'ENDURANCE', 'FLEXIBILITY', 'CARDIO']


def calculate():
    boundaries, _, df, excluded = analyze_bmi()
    rows, tables = [], {}
    for col in EXERCISES:
        groups = [df.loc[df['BMI그룹'].eq(group), col].dropna().to_numpy() for group in BMI_GROUPS]
        table = df.groupby('BMI그룹', observed=False)[col].agg(['count', 'mean', 'std']).reindex(BMI_GROUPS)
        table.columns = ['유효 인원', '평균', '표준편차']
        table['유효 인원'] = table['유효 인원'].fillna(0).astype(int)
        table['결측 인원'] = df.groupby('BMI그룹', observed=False).size().reindex(BMI_GROUPS) - table['유효 인원']
        tables[col] = table
        row = {'항목': METRICS[col], 'F(일반)': np.nan, 'p값(일반)': np.nan,
               'F(Welch)': np.nan, 'p값(Welch)': np.nan, 'Levene p값': np.nan,
               '적용 검정': '검정 불가', '적용 p값': np.nan, '사후검정 방법': '해당 없음',
               'η²': np.nan, '상태': '검정 불가: 모든 BMI 그룹에서 유효 인원 2명 이상 및 양의 분산 필요'}
        if all(len(g) >= 2 for g in groups) and all(np.var(g, ddof=1) > 0 for g in groups):
            f, p = f_oneway(*groups)
            wf, wp = welch_anova(*groups)
            _, lp = levene(*groups, center='median')
            combined = np.concatenate(groups)
            ss_total = ((combined - combined.mean()) ** 2).sum()
            ss_between = sum(len(g) * (g.mean() - combined.mean()) ** 2 for g in groups)
            row.update({'F(일반)': f, 'p값(일반)': p, 'F(Welch)': wf, 'p값(Welch)': wp,
                        '적용 검정': 'Welch ANOVA' if lp < .05 else '일반 ANOVA',
                        '적용 p값': wp if lp < .05 else p,
                        '사후검정 방법': 'Games–Howell' if lp < .05 else 'Tukey HSD',
                        'Levene p값': lp, 'η²': ss_between / ss_total, '상태': '검정 가능'})
        rows.append(row)
    results = pd.DataFrame(rows)
    return results, tables, boundaries, df, excluded


def posthoc(data, metric, method='Games–Howell'):
    """선택한 방법으로 BMI 세 그룹의 평균을 사후비교한다."""
    samples = [data.loc[data['BMI그룹'].eq(group), metric].dropna().to_numpy()
               for group in BMI_GROUPS]
    if any(len(g) < 2 for g in samples):
        raise ValueError('사후검정에는 각 BMI 그룹의 유효 인원이 최소 2명 필요합니다.')
    if method == 'Tukey HSD':
        result = tukey_hsd(*samples)
        ci = result.confidence_interval(confidence_level=.95)
    elif method == 'Games–Howell':
        result = games_howell(samples)
        ci = result
    else:
        raise ValueError(f'지원하지 않는 사후검정: {method}')
    rows = []
    for i, j in [(0, 1), (0, 2), (1, 2)]:
        p = float(result.pvalue[i, j])
        difference = float(result.statistic[i, j])
        rows.append({'그룹 A': BMI_GROUPS[i], '그룹 B': BMI_GROUPS[j],
                     'A 인원': len(samples[i]), 'B 인원': len(samples[j]),
                     'A 평균': samples[i].mean(), 'B 평균': samples[j].mean(),
                     '평균차(A−B)': difference, '95% CI 하한': ci.low[i, j],
                     '95% CI 상한': ci.high[i, j], '사후검정': method, '보정 p값': p,
                     '판정': '차이 유의' if p < .05 else '기각 못함'})
    return pd.DataFrame(rows)


def main():
    st.set_page_config(page_title='아노바 BMI', layout='wide')
    st.title('BMI 그룹별 실제 체력 측정값 평균 · ANOVA')
    st.info(BMI_DESCRIPTION)
    st.subheader('분산 가정에 따른 ANOVA와 사후검정')
    st.table(pd.DataFrame([
        {'비교 집단 수': '3개 이상', '분산 가정': '등분산 가정',
         '평균 비교 방법': '일반 일원분산분석(F검정)',
         '검정 통계량 공식': 'F = [SSB / (k−1)] / [SSW / (N−k)]', '사후검정': 'Tukey HSD'},
        {'비교 집단 수': '3개 이상', '분산 가정': '이분산 허용',
         '평균 비교 방법': 'Welch 일원분산분석',
         '검정 통계량 공식': 'Fw = Q / [1 + 2(k−2)T / (k²−1)]', '사후검정': 'Games–Howell'},
    ]))
    with st.expander('ANOVA 공식과 기호 설명'):
        st.markdown('**일반 ANOVA: 집단 사이 변동을 집단 내부 변동으로 나눕니다.**')
        st.latex(r'F=\frac{SSB/(k-1)}{SSW/(N-k)},\qquad F\sim F_{k-1,\,N-k}\ \text{under }H_0')
        st.latex(r'SSB=\sum_{i=1}^{k}n_i(\bar{x}_i-\bar{x})^2,\qquad SSW=\sum_{i=1}^{k}\sum_{j=1}^{n_i}(x_{ij}-\bar{x}_i)^2')
        st.markdown('**Welch ANOVA: 표본 수와 분산으로 가중치를 정하고, 이분산에 맞춰 통계량과 자유도를 조정합니다.**')
        st.latex(r'w_i=\frac{n_i}{s_i^2},\quad W=\sum_iw_i,\quad \bar{x}_w=\frac{\sum_i w_i\bar{x}_i}{W}')
        st.latex(r'Q=\frac{\sum_i w_i(\bar{x}_i-\bar{x}_w)^2}{k-1},\qquad T=\sum_i\frac{(1-w_i/W)^2}{n_i-1}')
        st.latex(r'F_W=\frac{Q}{1+\frac{2(k-2)}{k^2-1}T},\qquad \nu_1=k-1,\quad \nu_2=\frac{k^2-1}{3T}')
        st.markdown('`k`는 집단 수(현재 3), `nᵢ`는 각 집단의 유효 인원, `N=Σnᵢ`는 전체 유효 인원입니다. '
                    '`x̄ᵢ`는 집단 평균, `x̄`는 전체 평균, `sᵢ²`는 집단의 표본분산입니다. '
                    '`xᵢⱼ`는 i번째 집단의 j번째 장병 측정값입니다. '
                    '`SSB`는 집단 간 제곱합, `SSW`는 집단 내 제곱합입니다.')
        st.caption('p값은 귀무가설 아래 F분포의 오른쪽 꼬리확률로 계산합니다. 일반 ANOVA는 자유도 k−1, N−k를 사용하며 Welch는 조정된 자유도 ν₁, ν₂를 사용한 근사 검정입니다. 적용 p값 < 0.05이면 귀무가설을 기각합니다.')
    st.caption('이 화면은 BMI 낮음·보통·높음의 세 집단을 비교합니다. 사후검정은 전체 평균 검정이 유의한 경우 수행하며, 위 표는 이 코드에서 사용하는 방법입니다.')
    st.caption('일원분산분석은 BMI 그룹이라는 한 요인에 따라 세 집단의 평균이 같은지 검정합니다. 유의한 경우 사후검정으로 어느 그룹끼리 다른지 확인합니다.')
    st.caption('심폐는 통합 CARDIO(VO₂max) 측정값을 직접 비교합니다.')
    st.write('귀무가설: 세 BMI 그룹의 해당 체력 측정값 평균은 모두 같다. 대립가설: 적어도 한 BMI 그룹의 평균이 다르다.')
    try:
        results, tables, boundaries, data, excluded = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.subheader('BMI 구간 및 분석 대상')
    st.caption(f'첫 측정 BMI의 33.3·66.7 백분위수로 나눕니다. 저체중·정상·비만 같은 의학적 분류가 아닙니다. 같은 BMI는 같은 그룹에 배정하여 인원이 정확히 같지 않을 수 있습니다. BMI 결측·0 이하 제외: {excluded:,}명.')
    st.dataframe(boundaries, hide_index=True)
    st.subheader('종목별 ANOVA 결과')
    st.dataframe(results, hide_index=True, column_config={
        c: st.column_config.NumberColumn(format='%.3e') for c in results.columns if 'p값' in c})
    st.caption('종목별 Levene p값이 0.05 이상이면 일반 ANOVA, 미만이면 Welch를 적용합니다. 적용 p값으로 판단하며 종목 간 Holm 보정은 적용하지 않습니다. η²는 일반 ANOVA의 참고용 효과크기입니다.')
    st.subheader('종목별 검정 결과 해석')
    effect_summary = results[['항목', 'η²']].copy()
    effect_summary['그룹 간 평균 차이에 해당하는 변동 비중(%)'] = effect_summary['η²'] * 100
    st.markdown('**유의성과 차이의 크기는 구분해서 봅니다.** 적용 p값으로 평균 차이의 유의성을, η²로 그룹 간 차이 크기를 확인합니다.')
    st.dataframe(effect_summary.sort_values('η²', ascending=False), hide_index=True,
                 column_config={'그룹 간 평균 차이에 해당하는 변동 비중(%)':
                                st.column_config.NumberColumn(format='%.2f%%')})
    valid_effects = results.dropna(subset=['η²']).sort_values('η²', ascending=False)
    if not valid_effects.empty:
        largest = valid_effects.iloc[0]
        smallest = valid_effects.iloc[-1]
        st.write(f"현재 결과에서 그룹 간 평균 차이의 효과크기는 **{largest['항목']}**이 가장 크고 "
                 f"(η²={largest['η²']:.4f}, 변동의 약 {largest['η²'] * 100:.2f}%), "
                 f"**{smallest['항목']}**이 가장 작습니다 "
                 f"(η²={smallest['η²']:.4f}, 약 {smallest['η²'] * 100:.2f}%). "
                 '이는 서로 다른 측정항목에서 관찰한 차이의 크기를 비교한 것이며, BMI가 그만큼의 변화를 일으켰다는 뜻은 아닙니다.')
    heterogeneous = results.loc[results['Levene p값'].lt(.05), '항목'].tolist()
    if heterogeneous:
        st.write('**Welch 결과를 우선 보는 이유:** ' + ', '.join(heterogeneous) +
                 '에서 Levene p값이 0.05 미만으로, BMI 그룹 간 분산이 같다는 가정을 의심할 근거가 있습니다. Welch ANOVA는 이런 분산 차이와 불균형 인원에 대응합니다.')
    st.caption('p값의 1.301e−9 표기는 1.301×10⁻⁹을 뜻합니다. 0.000e+0은 p값이 매우 작아 수치 계산 한계로 0으로 표시된 것으로, 확률이 수학적으로 정확히 0이라는 뜻이 아닙니다. 표본이 크면 작은 차이도 유의할 수 있으므로 효과크기·실제 평균 차이를 함께 해석합니다.')
    for _, result in results.iterrows():
        adjusted = result['적용 p값']
        if pd.isna(adjusted):
            st.write(f"**{result['항목']}**: {result['상태']}")
            continue
        decision = ('귀무가설을 기각합니다. 적어도 한 BMI 그룹의 평균이 다르다는 통계적 근거가 있습니다.'
                    if adjusted < .05 else '귀무가설을 기각하지 못합니다. BMI 그룹 간 평균 차이의 통계적 근거가 충분하지 않습니다.')
        st.write(f"**{result['항목']}** — {result['적용 검정']} p={adjusted:.3e}: {decision} "
                 f"일반 ANOVA의 η²={result['η²']:.4f}.")
    with st.expander('검정 지표와 해석 방법'):
        st.markdown('''
- **Welch ANOVA**는 그룹별 분산과 인원이 달라도 평균 차이를 검정할 수 있도록 조정한 방법입니다.
- **방법 선택**: Levene p값이 0.05 이상이면 일반 ANOVA, 미만이면 Welch를 적용합니다. 등분산이 증명되는 것은 아니며, 이는 이 화면에서 정한 선택 규칙입니다.
- **판정**: 적용 p값 < 0.05이면 귀무가설을 기각합니다. 유의한 경우 일반 ANOVA는 Tukey HSD, Welch는 Games–Howell 사후검정을 합니다.
- **Levene p값**이 0.05 미만이면 분산이 같다는 가정을 의심할 근거가 있습니다. 0.05 이상이어도 분산이 같다고 증명한 것은 아닙니다.
- **η²**는 전체 측정값 변동 중 BMI 그룹 간 평균 차이에 해당하는 비중입니다. 예를 들어 0.10은 10%이며, 인과적으로 설명한 비율은 아닙니다. 여기서는 일반 ANOVA로 계산한 효과크기입니다.
- 유의하지 않다고 평균이 같다고 증명한 것은 아닙니다. 유의하더라도 차이의 크기·개인별 분포·실무적 의미를 함께 확인해야 합니다.
''')
    metric = st.selectbox('측정 항목', EXERCISES, format_func=lambda c: METRICS[c])
    table = tables[metric]
    st.dataframe(table)
    st.bar_chart(table[['평균']], y_label=METRICS[metric])
    distribution = data[['BMI그룹', metric]].dropna().rename(columns={metric: '측정값'})
    st.altair_chart(alt.Chart(distribution).mark_boxplot(extent=1.5).encode(
        x=alt.X('BMI그룹:N', sort=BMI_GROUPS, title='BMI 그룹'),
        y=alt.Y('측정값:Q', title=METRICS[metric])))
    st.caption('상자그림은 중앙값·사분위 범위와 극단값을 보여줍니다. 평균 차이와 함께 분포도 확인하세요.')
    row = results.loc[results['항목'].eq(METRICS[metric])].iloc[0]
    p = row['적용 p값']
    if pd.notna(p):
        st.write(f"{row['적용 검정']} p값: {p:.6g}. " + ('적어도 한 BMI 그룹의 평균에 차이가 있다는 통계적 근거가 있습니다. 어느 그룹끼리 다른지 확인하려면 사후검정이 필요합니다.' if p < .05 else 'BMI 그룹별 평균 차이를 뒷받침하는 통계적 근거가 충분하지 않습니다.'))
    st.subheader('선택 항목 · 표의 값으로 해석')
    usable = table.loc[table['유효 인원'].gt(0), '평균'].dropna()
    if len(usable):
        for group in BMI_GROUPS:
            values = table.loc[group]
            if values['유효 인원'] > 0:
                st.write(f"**BMI {group}**: 유효 인원 {int(values['유효 인원']):,}명, "
                         f"평균 {values['평균']:.2f}, 표준편차 {values['표준편차']:.2f}.")
        if len(usable) >= 2:
            highest, lowest = usable.idxmax(), usable.idxmin()
            gap = usable.max() - usable.min()
            unit = METRICS[metric]
            st.write(f'평균이 가장 높은 그룹은 **{highest}({usable.max():.2f})**, 가장 낮은 그룹은 **{lowest}({usable.min():.2f})**입니다. 평균 차이는 **{gap:.2f}**({unit})입니다. 이는 기술통계 비교이며 두 그룹 간 유의성을 확정한 결과는 아닙니다.')
        if metric == 'CARDIO':
            st.write('심폐 평균은 VO₂max(mL/kg/min)입니다. 42 미만을 미달로 판정하며, 평균과 개인별 미달률은 구분합니다.')
        else:
            st.caption('이 항목은 측정값이 높을수록 높은 수행 수준을 나타내지만, 관찰된 차이가 BMI 때문에 발생했다고 단정할 수는 없습니다.')
    st.subheader('어느 BMI 그룹끼리 다른가? · 종목별 사후검정')
    if pd.notna(p) and p < .05:
        method = row['사후검정 방법']
        st.caption(f"{row['적용 검정']} 결과에 따라 {method}를 적용합니다.")
        pairs = posthoc(data, metric, method)
        st.markdown('**사후검정 결과를 쉽게 읽으면**')
        readable = []
        for _, pair in pairs.iterrows():
            a, b = pair['그룹 A'], pair['그룹 B']
            difference = pair['평균차(A−B)']
            significant = pair['보정 p값'] < .05
            higher, lower = (a, b) if difference > 0 else (b, a)
            explanation = (
                f'BMI {higher} 그룹의 평균이 {lower} 그룹보다 {abs(difference):.2f} 높습니다.'
                if significant else
                '평균값은 다를 수 있지만, 두 그룹의 평균이 다르다고 판단할 근거가 충분하지 않습니다.'
            )
            readable.append({'비교': f'{a} ↔ {b}',
                             '평균(A / B)': f"{pair['A 평균']:.2f} / {pair['B 평균']:.2f}",
                             '통계적 판단': '유의한 차이 있음' if significant else '유의한 차이 확인 못함',
                             '쉬운 해석': explanation})
        readable = pd.DataFrame(readable)
        st.dataframe(readable, hide_index=True, width='stretch')
        st.caption(f'위 평균과 평균 차이의 단위: {METRICS[metric]}. 여기서 높고 낮음은 BMI가 아니라 체력 측정값의 크기를 뜻합니다.')
        # p값의 크기가 아닌 절대 평균차로 가장 큰 차이를 찾는다.
        largest_gap = pairs.loc[pairs['평균차(A−B)'].abs().idxmax()]
        gap_unit = '%p' if metric == 'STRENGTH' else ('회' if metric == 'ENDURANCE' else
                   'cm' if metric == 'FLEXIBILITY' else 'mL/kg/min')
        gap = abs(largest_gap['평균차(A−B)'])
        st.markdown('**평균 차이가 가장 큰 그룹 쌍**')
        st.write(f"BMI **{largest_gap['그룹 A']} ↔ {largest_gap['그룹 B']}**의 평균 차이가 "
                 f"**{gap:.3f} {gap_unit}**로 세 비교 중 가장 큽니다. "
                 f"(A−B의 95% 신뢰구간: {largest_gap['95% CI 하한']:.3f}~"
                 f"{largest_gap['95% CI 상한']:.3f} {gap_unit})")
        if largest_gap['보정 p값'] < .05:
            st.write(f"이 차이는 통계적으로도 유의합니다(보정 p={largest_gap['보정 p값']:.3e}).")
        else:
            st.write(f"관측 평균 차이는 가장 크지만 통계적으로 유의하지는 않습니다(보정 p={largest_gap['보정 p값']:.3e}).")
        st.caption('차이가 가장 큰지는 평균차의 절댓값으로, 통계적 유의성은 보정 p값으로 판단합니다. 이 비교는 선택한 종목 안에서의 비교입니다.')
        significant_pairs = pairs.loc[pairs['보정 p값'].lt(.05)]
        if len(significant_pairs) == 3:
            order = table['평균'].sort_values(ascending=False).index.tolist()
            st.success('세 그룹은 모든 쌍에서 유의한 차이가 있습니다. 평균이 높은 순서는 '
                       + ' > '.join(f'BMI {g}' for g in order) + '입니다.')
        elif significant_pairs.empty:
            st.info('전체 ANOVA는 유의하지만, 사후검정에서 어느 두 그룹이 다른지는 확인되지 않았습니다. 전체 검정과 쌍별 검정은 판단 기준이 달라 이런 결과가 가능합니다.')
        else:
            st.info(f'세 쌍 중 {len(significant_pairs)}쌍에서 유의한 차이가 확인됐습니다. 나머지 쌍이 같다는 것을 증명한 것은 아닙니다.')
        with st.expander('사후검정 표 읽는 방법', expanded=True):
            st.markdown('''
- **보정 p값 < 0.05**: 해당 두 BMI 그룹의 평균에 차이가 있다는 통계적 근거가 있습니다.
- **보정 p값 ≥ 0.05**: 두 평균의 차이를 확인할 근거가 충분하지 않습니다. 두 그룹이 같다고 확정하지 않습니다.
- **평균차(A−B)**: 양수이면 A의 평균이 높고, 음수이면 B의 평균이 높습니다.
- **95% 신뢰구간**: 평균 차이의 불확실성을 나타냅니다. 0을 포함하지 않으면 유의한 차이로 판단합니다. 개인 측정값의 95% 범위가 아닙니다.
- **보정의 의미**: 낮음–보통, 낮음–높음, 보통–높음 세 비교에서 우연히 유의하다고 판단할 오류를 조절합니다. 이 단계에서는 사후검정의 보정 p값을 사용합니다.
- **해석 범위**: 평균 차이는 BMI가 원인이라는 뜻이나 모든 개인에게 같은 차이가 있다는 뜻은 아닙니다.
''')
        st.download_button('선택 종목 사후검정 쉬운 해석 CSV', readable.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'아노바_bmi_{metric}_사후검정해석.csv', mime='text/csv')
        st.markdown('**사후검정 상세 수치**')
        st.dataframe(pairs, hide_index=True, column_config={
            '보정 p값': st.column_config.NumberColumn(format='%.3e')})
        for _, pair in pairs.iterrows():
            a, b = pair['그룹 A'], pair['그룹 B']
            difference = pair['평균차(A−B)']
            if pair['보정 p값'] < .05:
                direction = '높습니다' if difference > 0 else '낮습니다'
                st.write(f"**{a} vs {b}: 유의한 차이.** {a} 그룹 평균이 {b}보다 "
                         f"{abs(difference):.3f} {direction} "
                         f"(95% CI: {pair['95% CI 하한']:.3f}~{pair['95% CI 상한']:.3f}, "
                         f"보정 p={pair['보정 p값']:.3e}).")
            else:
                st.write(f'**{a} vs {b}:** 평균 차이에 대한 통계적 근거가 충분하지 않습니다.')
        st.caption('평균차·95% 동시 신뢰구간은 A−B 기준입니다. Tukey는 등분산을 가정하고 인원이 다르면 Tukey–Kramer를 적용합니다. Games–Howell은 이분산에 대응합니다. 각 종목 내 세 쌍의 비교에 대한 보정이 포함됩니다.')
        st.download_button('선택 종목 사후검정 CSV', pairs.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'아노바_bmi_{metric}_{method}.csv', mime='text/csv')
    else:
        st.info('선택 종목은 적용 ANOVA가 유의하지 않거나 검정 불가하여 사후검정을 수행하지 않습니다.')
    st.caption('Levene 검정은 중앙값 기준 분산 동질성 진단입니다. 장병 간 독립성·극단값·분포도 확인해야 합니다. 유의한 ANOVA만으로 어느 BMI 그룹끼리 다른지는 알 수 없으며 별도 사후검정이 필요합니다.')
    st.info('단일 부대 표본의 연관성 분석이며 나이·근육량 등 다른 요인을 보정하지 않았습니다. BMI의 인과효과나 예측 성능을 의미하지 않습니다. 상대악력은 체중으로 정규화된 지표이므로 BMI와의 관련성 해석에 체중의 공통 영향을 고려하세요.')
    for name, frame in [('검정결과', results), ('BMI그룹별평균', table.reset_index()), ('BMI구간', boundaries)]:
        st.download_button(f'{name} CSV', frame.to_csv(index=False).encode('utf-8-sig'), file_name=f'아노바_bmi_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
