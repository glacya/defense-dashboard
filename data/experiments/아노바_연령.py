"""streamlit run data/experiments/아노바.py"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import f_oneway, levene
from statsmodels.stats.multitest import multipletests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 연령별분석 import analyze_age, METRICS

EXERCISES = ['REL_GRIP', 'CROSS_UP', 'SIT_REACH', 'TRAD', 'STEP', '20M_RUN']


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
               'F(Welch)': np.nan, 'p값(Welch)': np.nan, 'Levene p값': np.nan,
               'η²': np.nan, '상태': '검정 불가: 모든 연령에서 유효 인원 2명 이상 필요'}
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
    return results, tables


def main():
    st.set_page_config(page_title='아노바', layout='wide')
    st.title('연령별 실제 체력 측정값 평균 · ANOVA')
    st.caption('장병별 첫 측정 당시 19~24세 · 3회 측정 조건 없음 · 심폐는 검사별 분리')
    st.write('귀무가설: 여섯 연령 집단의 평균이 모두 같다. 대립가설: 적어도 한 연령 집단의 평균이 다르다.')
    try:
        results, tables = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.dataframe(results, hide_index=True)
    st.caption('집단 크기·분산 차이에 대비해 Welch ANOVA를 주 분석으로 함께 제공합니다. 각 방법별 여섯 항목 p값에 Holm 보정을 적용합니다. η²는 일반 ANOVA의 평균 차이 효과크기입니다.')
    metric = st.selectbox('측정 항목', EXERCISES, format_func=lambda c: METRICS[c])
    table = tables[metric]
    st.dataframe(table)
    st.bar_chart(table[['평균']].rename(index=lambda age: f'{age}세'), y_label=METRICS[metric])
    row = results.loc[results['항목'].eq(METRICS[metric])].iloc[0]
    p = row['Holm p값(Welch)']
    if pd.notna(p):
        st.write(f"Welch 검정 Holm 보정 p값: {p:.6g}. " + ('적어도 한 연령의 평균에 차이가 있다는 통계적 근거가 있습니다.' if p < .05 else '연령별 평균 차이를 뒷받침하는 통계적 근거가 충분하지 않습니다.'))
    st.caption('Levene 검정은 중앙값 기준 분산 동질성 진단입니다. 장병 간 독립성·극단값·분포도 확인해야 합니다. 유의한 ANOVA만으로 어느 연령끼리 다른지는 알 수 없으며 별도 사후검정이 필요합니다.')
    st.info('모집단 전체를 분석한다면 평균 차이와 효과크기를 우선 해석하세요. 통계적 유의성은 실무적 중요성이나 연령의 인과효과를 의미하지 않습니다.')
    for name, frame in [('검정결과', results), ('연령별평균', table.reset_index())]:
        st.download_button(f'{name} CSV', frame.to_csv(index=False).encode('utf-8-sig'), file_name=f'아노바_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
