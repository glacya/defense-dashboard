"""실행: python -m streamlit run data/scripts/analysis/statistics/e06_bmi_failure_chi_square.py

BMI 그룹과 종목별 미달 여부의 카이제곱 독립성 검정. 선택한 종목은 그룹별 조정표준화잔차(Holm 보정)로
어느 그룹에서 미달이 기대보다 많거나 적은지도 본다(예: 심폐지구력 42 미만).
"""

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm
from statsmodels.stats.multitest import multipletests
import streamlit as st

from data.scripts.analysis.statistics.e02_bmi_descriptive import analyze_bmi, BMI_GROUPS, BMI_DESCRIPTION
from data.scripts.analysis.statistics.e08_event_failure_change import AREAS
from fitness_standards import grade3_standards


def calculate():
    boundaries, _, data, excluded = analyze_bmi()
    standards = grade3_standards()
    standards = standards.loc[standards.sex.eq('M') & standards.age_min.eq(19)
                              & standards.age_max.eq(24)]
    if standards.exercise.duplicated().any():
        raise ValueError('기준표의 종목이 중복되었습니다.')
    standards = standards.set_index('exercise')
    rows, tables = [], {}
    for label, col in AREAS.items():
        if col not in standards.index or standards.loc[col, 'rule'] != 'min_inclusive':
            raise ValueError(f'{col}: 최소값 이상 기준을 확인하세요.')
        cut = float(standards.loc[col, 'min_value'])
        if not np.isfinite(cut):
            raise ValueError(f'{col}: 유효한 기준값이 필요합니다.')
        risk = data[col].lt(cut).astype('boolean').mask(data[col].isna())
        table = pd.DataFrame({'BMI그룹': data['BMI그룹'], '미달': risk}).groupby(
            'BMI그룹', observed=False)['미달'].agg(['count', 'sum']).reindex(BMI_GROUPS)
        table = table.rename(columns={'count': '평가가능수', 'sum': '미달 인원'}).fillna(0).astype(int)
        table['충족 인원'] = table['평가가능수'] - table['미달 인원']
        table['판정불가수'] = data.groupby('BMI그룹', observed=False).size().reindex(BMI_GROUPS) - table['평가가능수']
        table['미달률(%)'] = table['미달 인원']/table['평가가능수'].replace(0, np.nan)*100
        observed = table.loc[table['평가가능수'].gt(0), ['미달 인원', '충족 인원']]
        row = {'종목': label, '미달 기준값': cut, 'χ²': np.nan, '자유도': np.nan,
               'p값': np.nan, "Cramér's V": np.nan, '최소 기대빈도': np.nan,
               '기대빈도 5 미만 비율(%)': np.nan, '상태': '검정 불가: 두 그룹 이상과 미달·충족 모두 필요'}
        if len(observed) >= 2 and observed.sum().gt(0).all():
            stat, p, dof, expected = chi2_contingency(observed.to_numpy(), correction=False)
            row.update({'χ²': stat, '자유도': dof, 'p값': p,
                        "Cramér's V": np.sqrt(stat/observed.to_numpy().sum()),
                        '최소 기대빈도': expected.min(),
                        '기대빈도 5 미만 비율(%)': (expected < 5).mean()*100,
                        '상태': '희소 셀: 점근 p값 해석 주의' if expected.min() < 1 or (expected < 5).mean() > .2 else '검정 가능'})
        rows.append(row)
        tables[label] = table
    results = pd.DataFrame(rows)
    valid = results['p값'].notna()
    results['Holm 보정 p값'] = np.nan
    if valid.any():
        results.loc[valid, 'Holm 보정 p값'] = multipletests(results.loc[valid, 'p값'], method='holm')[1]
    return results, tables, boundaries, excluded


def adjusted_residuals(observed):
    """그룹별 미달 칸의 조정표준화잔차와 Holm 보정 p값(전체 카이제곱 검정과는 별개의 사후 탐색).

    조정표준화잔차 = (관측−기대)/√[기대×(1−행 비율)×(1−열 비율)]
    """
    observed = observed.loc[observed.sum(axis=1).gt(0)]
    n = observed.to_numpy().sum()
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / n
    row_ratio = observed.sum(axis=1).to_numpy() / n
    fail_ratio = observed['미달'].sum() / n
    z = (observed['미달'].to_numpy() - expected[:, 0]) / np.sqrt(
        expected[:, 0] * (1 - row_ratio) * (1 - fail_ratio))
    raw_p = 2 * norm.sf(np.abs(z))
    return pd.DataFrame({
        '미달률(%)': observed['미달'] / observed.sum(axis=1) * 100,
        '기대 미달 인원': expected[:, 0],
        '조정표준화잔차': z,
        '보정 전 p값': raw_p,
        'Holm 보정 p값': multipletests(raw_p, method='holm')[1],
    }, index=observed.index)


def main():
    st.set_page_config(page_title='BMI별 미달 여부 카이제곱', layout='wide')
    st.title('BMI 그룹과 종목별 미달 여부 · 카이제곱 독립성 검정')
    st.caption('최종 전처리 대상자의 날짜순 첫 측정 · 첫 측정 당시 19~24세 · 남성 기준')
    st.markdown('**H₀: BMI 그룹과 해당 종목의 미달 여부는 독립이다.**\n\n**H₁: BMI 그룹과 해당 종목의 미달 여부는 관련이 있다.**')
    try:
        results, tables, boundaries, excluded = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.subheader('BMI 구간과 대상 인원')
    st.info(BMI_DESCRIPTION)
    st.dataframe(boundaries, hide_index=True)
    st.caption(f'BMI 결측·0 이하 제외: {excluded:,}명. 장병당 첫 측정 1건만 사용합니다.')
    st.subheader('종목별 검정 결과')
    st.dataframe(results, hide_index=True, column_config={
        c: st.column_config.NumberColumn(format='%.3e') for c in ['p값', 'Holm 보정 p값']})
    st.caption('연령별 카이제곱과 동일하게 네 종목의 검정에 Holm 보정을 적용합니다. Holm 보정 p값 < 0.05이면 귀무가설을 기각합니다.')
    for _, row in results.iterrows():
        p = row['Holm 보정 p값']
        if pd.isna(p):
            st.write(f"**{row['종목']}**: {row['상태']}")
            continue
        text = 'BMI 그룹과 미달 여부가 관련 있다는 근거가 있습니다.' if p < .05 else 'BMI 그룹과 미달 여부의 관련성을 확인할 근거가 충분하지 않습니다.'
        effect = row["Cramér's V"]
        st.write(f"**{row['종목']}**: {text} (보정 p={p:.3e}, Cramér’s V={effect:.3f})")
        if row['상태'] != '검정 가능':
            st.warning(f"{row['종목']}: {row['상태']}")
    label = st.selectbox('종목', list(tables))
    table = tables[label]
    observed = table[['미달 인원', '충족 인원']].rename(columns={'미달 인원': '미달', '충족 인원': '충족'})
    st.subheader(f'{label} · 관측빈도(명)')
    st.dataframe(observed)
    n = observed.to_numpy().sum()
    if n > 0:
        expected = pd.DataFrame(np.outer(observed.sum(axis=1), observed.sum(axis=0))/n,
                                index=observed.index, columns=observed.columns)
        st.subheader('기대빈도(명)')
        st.caption('BMI 그룹과 미달 여부가 독립이라면 예상되는 인원입니다. 각 칸 = 행 합계 × 열 합계 ÷ 전체 인원.')
        st.dataframe(expected)
        rates = observed.div(observed.sum(axis=1).replace(0, np.nan), axis=0)*100
        st.subheader('BMI 그룹별 미달·충족 비율(%)')
        st.bar_chart(rates, stack=True, y_label='구성비(%)')
        st.dataframe(table)
        valid_rates = table.loc[table['평가가능수'].gt(0), '미달률(%)']
        if len(valid_rates) >= 2:
            lo, hi = valid_rates.idxmin(), valid_rates.idxmax()
            st.write(f'관측 미달률은 BMI **{hi}** 그룹이 **{valid_rates.loc[hi]:.2f}%**로 가장 높고, '
                     f'**{lo}** 그룹이 **{valid_rates.loc[lo]:.2f}%**로 가장 낮습니다. 차이는 **{valid_rates.max()-valid_rates.min():.2f}%p**입니다.')
        residuals = (observed-expected)/np.sqrt(expected.where(expected.gt(0)))
        with st.expander('Pearson 잔차 및 검정 해석'):
            st.dataframe(residuals)
            st.write('잔차=(관측−기대)/√기대. 양수는 기대보다 많고 음수는 적다는 뜻입니다. 잔차 제곱의 합이 χ²입니다. 잔차는 탐색용이며 개별 그룹의 유의성을 판정하는 사후검정은 아닙니다.')
            st.write('자유도=(유효 BMI 그룹 수−1)×(판정 범주 수−1)로 세 그룹·두 판정이면 2입니다. Cramér’s V는 관련성 크기입니다. 전체 검정이 유의해도 모든 그룹 쌍이 다르다는 뜻은 아닙니다.')
        st.subheader(f'{label} · 그룹별 조정표준화잔차')
        adjusted = adjusted_residuals(observed)
        st.dataframe(adjusted, column_config={
            c: st.column_config.NumberColumn(format='%.3e') for c in ['보정 전 p값', 'Holm 보정 p값']})
        st.caption('양수는 기대보다 미달자가 많고 음수는 적다는 뜻입니다. ±1.96은 보정 전 참고 기준이며, 최종 판단은 세 그룹의 Holm 보정 p값 < 0.05입니다. 전체 검정이 유의하지 않으면 참고용으로만 봅니다.')
        for group, row in adjusted.iterrows():
            if row['Holm 보정 p값'] < .05:
                direction = '많음' if row['조정표준화잔차'] > 0 else '적음'
                st.write(f'- {group}: 미달 인원이 기대보다 유의하게 {direction}')
            else:
                st.write(f'- {group}: 보정 후 유의한 차이 없음')
        st.download_button('관측·기대빈도 CSV', observed.add_prefix('관측_').join(expected.add_prefix('기대_')).to_csv().encode('utf-8-sig'),
                           file_name=f'bmi_{AREAS[label]}_chi_square_crosstab.csv', mime='text/csv')
    st.caption('측정값이 종목별 기준 미만이면 미달, 기준값과 같으면 충족입니다. 심폐 CARDIO 기준은 42이며 결측은 평가에서 제외합니다.')
    st.info('이 검정은 체력 평균이 아닌 미달·충족 비율의 관련성을 확인합니다. BMI의 인과효과나 개인 통과확률을 의미하지 않습니다.')
    for name, frame in [('검정결과', results), ('BMI별미달집계', table.reset_index()), ('BMI구간', boundaries)]:
        st.download_button(f'{name} CSV', frame.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'bmi_chi_square_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
