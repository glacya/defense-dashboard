"""streamlit run data/experiments/아노바_연령.py"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import f_oneway, levene, tukey_hsd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 분석_연령별 import analyze_age, METRICS
from statistics_compat import welch_anova, games_howell

EXERCISES = ['STRENGTH', 'ENDURANCE', 'FLEXIBILITY', 'CARDIO']


def calculate():
    df = analyze_age(return_first=True)
    rows, tables = [], {}
    for col in EXERCISES:
        groups = [df.loc[df.AGE.eq(age), col].dropna().to_numpy() for age in range(19, 25)]
        table = df.groupby('AGE')[col].agg(['count', 'mean', 'std']).reindex(range(19, 25))
        table.columns = ['유효 인원', '평균', '표준편차']
        table['유효 인원'] = table['유효 인원'].fillna(0).astype(int)
        tables[col] = table
        row = {'항목': METRICS[col], 'F(일반)': np.nan, 'p값(일반)': np.nan,
               'Levene p값': np.nan, '적용 검정': '검정 불가',
               '적용 F값': np.nan, '적용 p값': np.nan, '사후검정 방법': '해당 없음',
               'η²': np.nan, '상태': '검정 불가: 모든 연령에서 유효 인원 2명 이상 및 양의 분산 필요'}
        if all(len(g) >= 2 for g in groups) and all(np.var(g, ddof=1) > 0 for g in groups):
            f, p = f_oneway(*groups)
            _, lp = levene(*groups, center='median')
            # 종목별 등분산 진단에 따라 평균 검정과 사후검정 방법을 정한다.
            if lp < .05:
                selected_f, selected_p = welch_anova(*groups)
                method, followup = 'Welch ANOVA', 'Games–Howell'
            else:
                selected_f, selected_p = f, p
                method, followup = '일반 ANOVA', 'Tukey HSD'
            combined = np.concatenate(groups)
            ss_total = ((combined - combined.mean()) ** 2).sum()
            ss_between = sum(len(g) * (g.mean() - combined.mean()) ** 2 for g in groups)
            row.update({'F(일반)': f, 'p값(일반)': p,
                        '적용 검정': method, '적용 F값': selected_f, '적용 p값': selected_p,
                        '사후검정 방법': followup,
                        'Levene p값': lp, 'η²': ss_between / ss_total, '상태': '검정 가능'})
        rows.append(row)
    results = pd.DataFrame(rows)
    return results, tables


def interpret_results(results):
    """종목별로 선택한 검정의 p값을 기준으로 해석한다."""
    interpretations = []
    for _, row in results.iterrows():
        p = row['적용 p값']
        if pd.isna(p):
            conclusion = row['상태']
        elif p < .05:
            conclusion = '귀무가설 기각: 적어도 한 연령 집단의 평균이 다르다는 근거가 있습니다. 어느 연령 간 차이인지는 사후검정이 필요합니다.'
        else:
            conclusion = '귀무가설 기각 못함: 연령별 평균 차이의 근거가 충분하지 않습니다. 평균이 같다고 증명한 것은 아닙니다.'
        eta = row['η²']
        effect = (f'표본의 전체 측정값 변동 중 연령 집단 간 평균 차이에 해당하는 비중은 {eta:.2%}입니다.'
                  if pd.notna(eta) else '효과크기 계산 불가')
        lp = row['Levene p값']
        variance = ('등분산 가설 기각: Welch ANOVA를 적용합니다.' if lp < .05
                    else '등분산 가정 유지: 일반 ANOVA를 적용합니다. 등분산이 증명된 것은 아닙니다.') if pd.notna(lp) else '분산 검정 불가'
        interpretations.append({'항목': row['항목'], '적용 검정': row['적용 검정'], '적용 p값': p,
                                '결과 해석': conclusion, '효과크기 해석': effect,
                                '분산 해석': variance})
    return pd.DataFrame(interpretations)


def posthoc(metric, method='Tukey HSD'):
    """본 검정과 같은 표본에 선택된 사후검정을 적용한다."""
    df = analyze_age(return_first=True)
    ages = list(range(19, 25))
    groups = [df.loc[df.AGE.eq(age), metric].dropna().to_numpy() for age in ages]
    if any(len(g) < 2 for g in groups):
        raise ValueError('사후검정은 각 연령에 유효 측정값이 최소 2개 필요합니다.')
    if method == 'Tukey HSD':
        result = tukey_hsd(*groups)
        ci = result.confidence_interval(confidence_level=.95)
    elif method == 'Games–Howell':
        result = games_howell(groups)
        ci = result
    else:
        raise ValueError(f'지원하지 않는 사후검정: {method}')
    rows = []
    for i in range(len(ages)):
        for j in range(i + 1, len(ages)):
            p = float(result.pvalue[i, j])
            rows.append({'연령 A': ages[i], '연령 B': ages[j],
                         'A 인원': len(groups[i]), 'B 인원': len(groups[j]),
                         'A 평균': groups[i].mean(), 'B 평균': groups[j].mean(),
                         '평균차(A−B)': float(result.statistic[i, j]),
                         '95% 동시 CI 하한': float(ci.low[i, j]),
                         '95% 동시 CI 상한': float(ci.high[i, j]),
                         '사후검정': method, '보정 p값': p,
                         '판정': '차이 유의' if p < .05 else '기각 못함'})
    return pd.DataFrame(rows)


def main():
    st.set_page_config(page_title='아노바', layout='wide')
    st.title('연령별 체력 평균 · 종목별 일반/Welch 일원분산분석')
    st.caption('장병별 첫 측정 당시 19~24세 · 전처리에서 선정된 3회 측정 대상자의 첫 측정 사용 · 심폐는 통합 CARDIO(VO₂max) 사용')
    st.write('귀무가설: 여섯 연령 집단의 평균이 모두 같다. 대립가설: 적어도 한 연령 집단의 평균이 다르다.')
    try:
        results, tables = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.dataframe(results, hide_index=True)
    st.caption('종목별 Levene p값이 0.05 미만이면 Welch, 그 외에는 일반 ANOVA를 적용합니다. 결론은 적용 p값으로 판단하며 F(일반)·p값(일반)은 참고값입니다.')
    with st.expander('결과표 읽는 방법', expanded=True):
        st.markdown('''
- **방법 선택**: Levene p값 < 0.05이면 Welch ANOVA, 0.05 이상이면 일반 ANOVA를 사용합니다. 종목마다 별도로 선택합니다.
- **판정 기준**: `적용 p값 < 0.05`이면 평균이 같다는 귀무가설을 기각합니다. 각 종목의 보정 전 p값을 사용하며 종목 사이 Holm 보정은 적용하지 않습니다.
- **일반 일원분산분석**: 요인은 연령 하나이며 19~24세 여섯 집단의 평균을 비교합니다. 장병 간 독립성, 집단 내 오차의 정규성, 집단 간 등분산을 가정합니다.
- **Welch 일원분산분석**: 등분산 가정 없이 연령 집단별 분산·인원 차이를 고려합니다. 독립성 등 다른 가정은 여전히 확인해야 합니다.
- **사후검정**: 적용 p값이 0.05 미만일 때 일반 ANOVA는 Tukey HSD, Welch는 Games–Howell로 연령 15개 쌍을 비교합니다. 사후검정의 보정 p값은 해당 종목 내 여러 쌍의 비교를 고려한 값입니다.
- **F값**: 집단 사이 평균 차이를 집단 내부 변동과 비교한 통계량입니다. F값 하나만으로 유의 여부나 차이의 실무적 크기를 판단하지 않습니다.
- **p값**: 평균이 같다는 가정 아래 관측한 통계량 이상으로 극단적인 결과가 나올 확률입니다. 귀무가설이 참일 확률이나 개인의 통과확률이 아닙니다.
- **Levene p값**: 0.05 미만이면 연령별 분산이 다르다는 근거가 있습니다. 이는 평균 차이를 검정한 결과가 아닙니다.
- **η²(에타제곱)**: 표본 전체 변동 중 연령 집단 간 평균 차이에 해당하는 비중입니다. 예를 들어 0.02는 2%이며, 연령이 체력을 2% 변화시켰다는 인과적 의미는 아닙니다.
- **유효 인원 / 평균 / 표준편차**: 결측을 제외한 장병 수, 측정값의 평균, 개인별 측정값의 퍼짐 정도입니다. 표준편차는 평균의 신뢰구간이 아닙니다.
''')
    interpretations = interpret_results(results)
    st.subheader('종목별 결과 해석')
    st.dataframe(interpretations, hide_index=True)
    st.caption('이 분석은 연령별 측정값 평균을 비교합니다. 미달자 비율이나 3차 통과확률을 검정하는 분석은 아닙니다.')
    metric = st.selectbox('측정 항목', EXERCISES, format_func=lambda c: METRICS[c])
    table = tables[metric]
    st.dataframe(table)
    st.bar_chart(table[['평균']].rename(index=lambda age: f'{age}세'), y_label=METRICS[metric])
    row = results.loc[results['항목'].eq(METRICS[metric])].iloc[0]
    p = row['적용 p값']
    if pd.notna(p):
        st.write(f"{row['적용 검정']} 적용 p값: {p:.6g}. " + ('귀무가설을 기각합니다. 적어도 한 연령의 평균에 차이가 있다는 통계적 근거가 있습니다.' if p < .05 else '귀무가설을 기각하지 못합니다. 연령별 평균 차이를 뒷받침하는 통계적 근거가 충분하지 않습니다.'))
    else:
        st.warning(row['상태'])
    if pd.notna(row['Levene p값']) and row['Levene p값'] < .05:
        st.info('이 종목은 Levene p값이 0.05 미만이므로 Welch ANOVA 결과로 판단합니다.')
    st.subheader('선택 종목의 실제 수치 해석')
    for age, values in table.iterrows():
        n = int(values['유효 인원'])
        if n:
            sd = f"{values['표준편차']:.2f}" if pd.notna(values['표준편차']) else '계산 불가'
            st.write(f"**{age}세**: {n:,}명, 평균 {values['평균']:.2f}, 표준편차 {sd}.")
    means = table.loc[table['유효 인원'].gt(0), '평균'].dropna()
    if len(means) >= 2:
        st.write(f'관측 평균이 가장 높은 연령은 **{means.idxmax()}세({means.max():.2f})**, '
                 f'가장 낮은 연령은 **{means.idxmin()}세({means.min():.2f})**입니다. '
                 f'두 평균 차이는 **{means.max()-means.min():.2f}**입니다. 단위는 선택 종목의 표시 단위와 같습니다.')
        st.caption('최고·최저 평균은 기술통계입니다. 두 연령 간 차이가 통계적으로 유의하다는 뜻은 아닙니다.')
    if pd.notna(row['η²']):
        st.write(f"일반 ANOVA의 η²={row['η²']:.4f}: 표본 전체 변동 중 연령 집단 간 평균 차이 비중은 **{row['η²']:.2%}**입니다.")
    st.caption('Levene 검정은 중앙값 기준 분산 동질성 진단입니다. 장병 간 독립성·극단값·분포도 확인해야 합니다. 유의한 ANOVA만으로 어느 연령끼리 다른지는 알 수 없으며 별도 사후검정이 필요합니다.')
    st.info('모집단 전체를 분석한다면 평균 차이와 효과크기를 우선 해석하세요. 통계적 유의성은 실무적 중요성이나 연령의 인과효과를 의미하지 않습니다.')
    st.caption('전처리로 선정된 장병들의 첫 측정을 연령별로 비교한 결과입니다. 같은 장병이 나이가 들면서 변한 정도를 추적한 결과는 아닙니다.')
    st.subheader('유의한 종목의 연령 간 사후검정')
    st.caption('적용 p값이 0.05 미만인 종목만 진행합니다. 일반 ANOVA → Tukey HSD(인원이 다르면 Tukey–Kramer), Welch → Games–Howell. 각 종목 내 15개 비교에 대한 보정이 포함됩니다.')
    significant = results.loc[results['적용 p값'].lt(.05)]
    if significant.empty:
        st.info('선택된 ANOVA에서 유의한 종목이 없어 사후검정을 진행하지 않습니다.')
    for _, significant_row in significant.iterrows():
        selected_metric = next(c for c in EXERCISES if METRICS[c] == significant_row['항목'])
        st.markdown(f"**{significant_row['항목']}**")
        method = significant_row['사후검정 방법']
        st.caption(f"{significant_row['적용 검정']} 결과에 따라 {method}를 적용합니다.")
        try:
            pairs = posthoc(selected_metric, method)
        except (ValueError, OSError, KeyError) as exc:
            st.error(f'사후검정 계산 불가: {exc}')
            continue
        st.dataframe(pairs, hide_index=True, column_config={
            '보정 p값': st.column_config.NumberColumn(format='%.6f')})
        st.caption('평균차는 A−B입니다. 양수면 A 연령의 평균이 높고, 음수면 B 연령의 평균이 높습니다. 95% 동시 신뢰구간에 0이 포함되지 않으면 유의한 차이로 해석합니다.')
        different = pairs.loc[pairs['보정 p값'].lt(.05)]
        if different.empty:
            st.info('ANOVA 전체 검정은 유의하지만, 사후검정에서 유의한 개별 연령 쌍은 없습니다. 전체 검정과 쌍별 검정은 검정 대상과 판단 기준이 달라 이런 결과가 가능합니다.')
        for _, pair in different.iterrows():
            direction = '높습니다' if pair['평균차(A−B)'] > 0 else '낮습니다'
            st.write(f"**{int(pair['연령 A'])}세 vs {int(pair['연령 B'])}세**: "
                     f"{int(pair['연령 A'])}세 평균이 {int(pair['연령 B'])}세보다 "
                     f"{abs(pair['평균차(A−B)']):.2f} {direction} "
                     f"({method} 보정 p={pair['보정 p값']:.6g}).")
        st.download_button(f"{significant_row['항목']} 사후검정 CSV", pairs.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'아노바_연령_{selected_metric}_{method}.csv', mime='text/csv')
    for name, frame in [('검정결과', results), ('결과해석', interpretations), ('연령별평균', table.reset_index())]:
        st.download_button(f'{name} CSV', frame.to_csv(index=False).encode('utf-8-sig'), file_name=f'아노바_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
