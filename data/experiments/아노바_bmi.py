"""streamlit run data/experiments/아노바_bmi.py"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import f_oneway, levene, tukey_hsd
from statsmodels.stats.multitest import multipletests
import streamlit as st
import altair as alt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 연령별분석 import analyze_age, METRICS
CARDIO_COLS = ['TRAD', 'STEP', '20M_RUN']

METRICS = {**METRICS, 'CARDIO': '심폐지구력(Z점수)'}
EXERCISES = ['REL_GRIP', 'CROSS_UP', 'SIT_REACH', 'CARDIO']
BMI_GROUPS = ['낮음', '중간', '높음']


def calculate():
    df = analyze_age(return_first=True)
    excluded = int((df.BMI.isna() | df.BMI.le(0)).sum())
    df = df.loc[df.BMI.notna() & df.BMI.gt(0)].copy()
    df['CARDIO'] = np.nan
    df['심폐검사'] = pd.Series(pd.NA, index=df.index, dtype='string')
    one = df[CARDIO_COLS].notna().sum(axis=1).eq(1)
    for method in CARDIO_COLS:
        selected = one & df[method].notna()
        values = df.loc[selected, method]
        sd = values.std(ddof=1)
        # BMI 그룹별이 아니라, 분석 대상 전체의 검사별 평균·표준편차를 사용한다.
        if len(values) >= 2 and pd.notna(sd) and sd > 0:
            df.loc[selected, 'CARDIO'] = (values - values.mean()) / sd
        df.loc[selected, '심폐검사'] = method
    low, high = df.BMI.quantile([1 / 3, 2 / 3]).to_numpy()
    if not np.isfinite([low, high]).all() or low >= high:
        raise ValueError('BMI 삼분위 경계를 만들 수 없습니다.')
    df['BMI그룹'] = pd.cut(df.BMI, [-np.inf, low, high, np.inf], labels=BMI_GROUPS)
    boundaries = pd.DataFrame({'BMI그룹': BMI_GROUPS,
                               '구간': [f'BMI ≤ {low:.6g}', f'{low:.6g} < BMI ≤ {high:.6g}', f'BMI > {high:.6g}'],
                               '장병 수': df.groupby('BMI그룹', observed=False).size().reindex(BMI_GROUPS).to_numpy()})
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
               'η²': np.nan, '상태': '검정 불가: 모든 BMI 그룹에서 유효 인원 2명 이상 및 양의 분산 필요'}
        if all(len(g) >= 2 for g in groups) and all(np.var(g, ddof=1) > 0 for g in groups):
            f, p = f_oneway(*groups)
            wf, wp = f_oneway(*groups, equal_var=False)
            _, lp = levene(*groups, center='median')
            combined = np.concatenate(groups)
            ss_total = ((combined - combined.mean()) ** 2).sum()
            ss_between = sum(len(g) * (g.mean() - combined.mean()) ** 2 for g in groups)
            row.update({'F(일반)': f, 'p값(일반)': p, 'F(Welch)': wf, 'p값(Welch)': wp,
                        'Levene p값': lp, 'η²': ss_between / ss_total, '상태': '검정 가능'})
        rows.append(row)
    results = pd.DataFrame(rows)
    for kind in ['일반', 'Welch']:
        valid = results[f'p값({kind})'].notna()
        results[f'Holm p값({kind})'] = np.nan
        results.loc[valid, f'Holm p값({kind})'] = multipletests(results.loc[valid, f'p값({kind})'], method='holm')[1]
    return results, tables, boundaries, df, excluded


def posthoc(data, metric):
    """한 종목 내 세 쌍의 비교를 동시에 보정한 Games–Howell 결과."""
    samples = [data.loc[data['BMI그룹'].eq(group), metric].dropna().to_numpy()
               for group in BMI_GROUPS]
    result = tukey_hsd(*samples, equal_var=False)
    ci = result.confidence_interval(confidence_level=.95)
    rows = []
    for i, j in [(0, 1), (0, 2), (1, 2)]:
        p = float(result.pvalue[i, j])
        difference = float(result.statistic[i, j])
        rows.append({'그룹 A': BMI_GROUPS[i], '그룹 B': BMI_GROUPS[j],
                     'A 인원': len(samples[i]), 'B 인원': len(samples[j]),
                     'A 평균': samples[i].mean(), 'B 평균': samples[j].mean(),
                     '평균차(A−B)': difference, '95% CI 하한': ci.low[i, j],
                     '95% CI 상한': ci.high[i, j], 'Games–Howell 보정 p값': p,
                     '판정': '차이 유의' if p < .05 else '기각 못함'})
    return pd.DataFrame(rows)


def main():
    st.set_page_config(page_title='아노바 BMI', layout='wide')
    st.title('BMI 그룹별 실제 체력 측정값 평균 · ANOVA')
    st.caption('장병별 첫 측정 당시 19~24세 · 3회 측정 조건 없음 · 심폐는 검사별 Z점수로 통합')
    st.caption('심폐 Z점수 = (측정값−해당 검사 평균)÷해당 검사 표본 표준편차. BMI가 유효한 분석 장병 전체에서 검사별로 표준화하며, BMI 그룹 안에서 따로 표준화하지 않습니다. 검사값이 정확히 하나인 기록만 사용합니다. 표준편차를 계산할 수 없거나 0인 검사는 심폐 분석에서 제외합니다.')
    st.info('Z=0은 해당 검사 평균, +1은 평균보다 1표준편차 높음, −1은 1표준편차 낮음입니다. 3등급 기준과 무관합니다. 검사 내 상대적 위치를 합친 탐색 지표로, 검사 간 생리적 능력의 동등성을 보장하지는 않습니다.')
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
    st.caption('집단 크기·분산 차이에 대비해 Welch ANOVA를 주 분석으로 함께 제공합니다. 각 방법별 네 항목 p값에 Holm 보정을 적용합니다. η²는 일반 ANOVA의 평균 차이 효과크기입니다.')
    st.subheader('종목별 검정 결과 해석')
    effect_summary = results[['항목', 'η²']].copy()
    effect_summary['그룹 간 평균 차이에 해당하는 변동 비중(%)'] = effect_summary['η²'] * 100
    st.markdown('**유의성과 차이의 크기는 구분해서 봅니다.** 맨 오른쪽 Welch Holm 보정 p값으로 전체 평균 차이의 유의성을, η²로 일반 ANOVA에서의 그룹 간 차이 크기를 확인합니다.')
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
        adjusted = result['Holm p값(Welch)']
        if pd.isna(adjusted):
            st.write(f"**{result['항목']}**: {result['상태']}")
            continue
        decision = ('귀무가설을 기각합니다. 적어도 한 BMI 그룹의 평균이 다르다는 통계적 근거가 있습니다.'
                    if adjusted < .05 else '귀무가설을 기각하지 못합니다. BMI 그룹 간 평균 차이의 통계적 근거가 충분하지 않습니다.')
        st.write(f"**{result['항목']}** — Welch Holm 보정 p={adjusted:.3e}: {decision} "
                 f"일반 ANOVA의 η²={result['η²']:.4f}.")
    with st.expander('검정 지표와 해석 방법'):
        st.markdown('''
- **Welch ANOVA**는 그룹별 분산과 인원이 달라도 평균 차이를 검정할 수 있도록 조정한 방법입니다.
- **Holm 보정 p값**은 네 항목을 함께 검정할 때 우연한 유의 결과가 늘어나는 문제를 조정합니다. 보정 p값 < 0.05를 판단 기준으로 사용합니다.
- **Levene p값**이 0.05 미만이면 분산이 같다는 가정을 의심할 근거가 있습니다. 0.05 이상이어도 분산이 같다고 증명한 것은 아닙니다.
- **η²**는 전체 측정값 변동 중 BMI 그룹 간 평균 차이에 해당하는 비중입니다. 예를 들어 0.10은 10%이며, 인과적으로 설명한 비율은 아닙니다. 여기서는 일반 ANOVA로 계산한 효과크기입니다.
- 유의하지 않다고 평균이 같다고 증명한 것은 아닙니다. 유의하더라도 차이의 크기·개인별 분포·실무적 의미를 함께 확인해야 합니다.
''')
    metric = st.selectbox('측정 항목', EXERCISES, format_func=lambda c: METRICS[c])
    table = tables[metric]
    if metric == 'CARDIO':
        reference = data.groupby('심폐검사').apply(
            lambda g: pd.Series({'인원': len(g),
                                  '원점수 평균': g[g.name].mean(),
                                  '원점수 표준편차': g[g.name].std(ddof=1)}), include_groups=False)
        st.caption('Z점수 계산에 사용한 검사별 원점수 통계')
        st.dataframe(reference)
        st.caption('검사 구성 확인: 각 BMI 그룹에서 어떤 심폐 검사를 받았는지 표시합니다.')
        st.dataframe(pd.crosstab(data['BMI그룹'], data['심폐검사']).reindex(BMI_GROUPS, fill_value=0))
    st.dataframe(table)
    st.bar_chart(table[['평균']], y_label=METRICS[metric])
    distribution = data[['BMI그룹', metric]].dropna().rename(columns={metric: '측정값'})
    st.altair_chart(alt.Chart(distribution).mark_boxplot(extent=1.5).encode(
        x=alt.X('BMI그룹:N', sort=BMI_GROUPS, title='BMI 그룹'),
        y=alt.Y('측정값:Q', title=METRICS[metric])))
    st.caption('상자그림은 중앙값·사분위 범위와 극단값을 보여줍니다. 평균 차이와 함께 분포도 확인하세요.')
    row = results.loc[results['항목'].eq(METRICS[metric])].iloc[0]
    p = row['Holm p값(Welch)']
    if pd.notna(p):
        st.write(f"Welch 검정 Holm 보정 p값: {p:.6g}. " + ('적어도 한 BMI 그룹의 평균에 차이가 있다는 통계적 근거가 있습니다. 어느 그룹끼리 다른지 확인하려면 사후검정이 필요합니다.' if p < .05 else 'BMI 그룹별 평균 차이를 뒷받침하는 통계적 근거가 충분하지 않습니다.'))
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
            unit = 'Z점수 단위' if metric == 'CARDIO' else METRICS[metric]
            st.write(f'평균이 가장 높은 그룹은 **{highest}({usable.max():.2f})**, 가장 낮은 그룹은 **{lowest}({usable.min():.2f})**입니다. 평균 차이는 **{gap:.2f}**({unit})입니다. 이는 기술통계 비교이며 두 그룹 간 유의성을 확정한 결과는 아닙니다.')
        if metric == 'CARDIO':
            st.write('심폐 평균 Z점수가 양수이면 해당 검사 참여자 평균보다 높은 상대적 수준, 음수이면 낮은 상대적 수준입니다. 예를 들어 평균 Z=−0.50은 평균적으로 자기 검사 평균보다 0.5표준편차 낮은 위치입니다. 미달률이나 3등급 충족 여부를 뜻하지 않습니다.')
        else:
            st.caption('이 항목은 측정값이 높을수록 높은 수행 수준을 나타내지만, 관찰된 차이가 BMI 때문에 발생했다고 단정할 수는 없습니다.')
    st.subheader('어느 BMI 그룹끼리 다른가? · Games–Howell 사후검정')
    if pd.notna(p) and p < .05:
        pairs = posthoc(data, metric)
        st.dataframe(pairs, hide_index=True, column_config={
            'Games–Howell 보정 p값': st.column_config.NumberColumn(format='%.3e')})
        for _, pair in pairs.iterrows():
            a, b = pair['그룹 A'], pair['그룹 B']
            difference = pair['평균차(A−B)']
            if pair['Games–Howell 보정 p값'] < .05:
                direction = '높습니다' if difference > 0 else '낮습니다'
                st.write(f"**{a} vs {b}: 유의한 차이.** {a} 그룹 평균이 {b}보다 "
                         f"{abs(difference):.3f} {direction} "
                         f"(95% CI: {pair['95% CI 하한']:.3f}~{pair['95% CI 상한']:.3f}, "
                         f"보정 p={pair['Games–Howell 보정 p값']:.3e}).")
            else:
                st.write(f'**{a} vs {b}:** 평균 차이에 대한 통계적 근거가 충분하지 않습니다.')
        st.caption('평균차·신뢰구간은 A−B 기준입니다. Games–Howell은 이분산·불균형 인원에 대응하며 한 종목 내 세 쌍의 다중비교를 반영합니다. 위 Holm 보정은 네 종목의 전체 검정에 대한 별도 보정입니다. 이 사후 결과는 종목 내 가족 기준이며 네 종목의 모든 쌍을 통합 보정한 결과는 아닙니다.')
        st.download_button('선택 종목 사후검정 CSV', pairs.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'아노바_bmi_{metric}_GamesHowell.csv', mime='text/csv')
    else:
        st.info('선택 종목은 Holm 보정된 전체 Welch 검정이 유의하지 않거나 검정 불가하여 사후검정을 수행하지 않습니다.')
    st.caption('Levene 검정은 중앙값 기준 분산 동질성 진단입니다. 장병 간 독립성·극단값·분포도 확인해야 합니다. 유의한 ANOVA만으로 어느 BMI 그룹끼리 다른지는 알 수 없으며 별도 사후검정이 필요합니다.')
    st.info('단일 부대 표본의 연관성 분석이며 나이·근육량 등 다른 요인을 보정하지 않았습니다. BMI의 인과효과나 예측 성능을 의미하지 않습니다. 상대악력은 체중으로 정규화된 지표이므로 BMI와의 관련성 해석에 체중의 공통 영향을 고려하세요.')
    for name, frame in [('검정결과', results), ('BMI그룹별평균', table.reset_index()), ('BMI구간', boundaries)]:
        st.download_button(f'{name} CSV', frame.to_csv(index=False).encode('utf-8-sig'), file_name=f'아노바_bmi_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
