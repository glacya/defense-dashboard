"""streamlit run data/experiments/연령별미달여부_카이제곱.py"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from statsmodels.stats.multitest import multipletests
import streamlit as st
import altair as alt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 분석_연령별 import analyze_age
from 종목별체력미달자_회차별변화율 import STANDARD_PATH, AREAS, CARDIO_COLS


def calculate():
    df = analyze_age(return_first=True)
    std = pd.read_csv(STANDARD_PATH)
    std = std.loc[std.sex.eq('M') & std.age_min.eq(19) & std.age_max.eq(24)].set_index('exercise')
    risks = {}
    for col in ['STRENGTH', 'ENDURANCE', 'FLEXIBILITY'] + CARDIO_COLS:
        if std.loc[col, 'rule'] != 'min_inclusive':
            raise ValueError(f'{col}: 기준표 판정 방식 확인 필요')
        risks[col] = df[col].lt(float(std.loc[col, 'min_value'])).astype('boolean').mask(df[col].isna())
    summaries, tables = [], {}
    for label, col in AREAS.items():
        r = risks[col]
        table = pd.DataFrame({'연령': df.AGE, '미달': r}).groupby('연령')['미달'].agg(['count', 'sum']).reindex(range(19, 25), fill_value=0)
        table = table.rename(columns={'count': '평가가능수', 'sum': '미달 인원'}).astype(int)
        table['충족 인원'] = table['평가가능수'] - table['미달 인원']
        table['판정불가수'] = df.groupby('AGE').size().reindex(range(19, 25), fill_value=0) - table['평가가능수']
        table['미달률(%)'] = table['미달 인원'] / table['평가가능수'].replace(0, np.nan) * 100
        observed = table.loc[table['평가가능수'].gt(0), ['미달 인원', '충족 인원']]
        result = {'종목': label, 'χ²': np.nan, '자유도': np.nan, 'p값': np.nan,
                  "Cramér's V": np.nan, '최소 기대빈도': np.nan, '기대빈도 5 미만 비율(%)': np.nan,
                  '상태': '검정 불가: 두 연령 이상과 미달·충족 모두 필요'}
        if len(observed) >= 2 and observed.sum().gt(0).all():
            stat, p, dof, expected = chi2_contingency(observed.to_numpy(), correction=False)
            result.update({'χ²': stat, '자유도': dof, 'p값': p,
                           "Cramér's V": np.sqrt(stat / observed.to_numpy().sum()),
                           '최소 기대빈도': expected.min(),
                           '기대빈도 5 미만 비율(%)': (expected < 5).mean() * 100,
                           '상태': '희소 셀: 점근 p값 해석 주의' if expected.min() < 1 or (expected < 5).mean() > .2 else '검정 가능'})
        summaries.append(result)
        tables[label] = table
    results = pd.DataFrame(summaries)
    valid = results['p값'].notna()
    results['Holm 보정 p값'] = np.nan
    results.loc[valid, 'Holm 보정 p값'] = multipletests(results.loc[valid, 'p값'], method='holm')[1]
    return results, tables


def show_interpretation(results):
    st.subheader('검정 결과 해석')
    for _, row in results.iterrows():
        p = row['Holm 보정 p값']
        if pd.isna(p):
            st.write(f"**{row['종목']}**: 검정할 수 없습니다. {row['상태']}")
            continue
        conclusion = ('귀무가설을 기각합니다. 연령과 해당 종목의 미달 여부가 관련되어 있다는 통계적 근거가 있습니다.'
                      if p < .05 else '귀무가설을 기각하지 못합니다. 연령과 해당 종목의 미달 여부가 관련되어 있다는 통계적 근거가 충분하지 않습니다.')
        effect = row["Cramér's V"]
        st.write(f"**{row['종목']}** — Holm 보정 p={p:.4f}: {conclusion} "
                 f"관련성 크기 Cramér’s V={effect:.4f}.")
        if row['상태'] != '검정 가능':
            st.warning(f"{row['종목']}: {row['상태']}. p값을 신중하게 해석하세요.")
    st.caption('귀무가설을 기각하지 못했다는 것은 독립임을 증명하거나 귀무가설을 채택했다는 뜻이 아닙니다. 유의하더라도 어느 연령끼리 다른지, 연령이 미달의 원인인지는 이 검정만으로 알 수 없습니다. V가 0에 가까우면 관련성이 약하며, 실제 비율 차이도 함께 보고 판단합니다.')
    with st.expander('결과표 지표 읽는 방법'):
        st.markdown('''
- **χ²**: 관측빈도와 기대빈도의 차이를 종합한 통계량입니다. 기대빈도는 `행 합계 × 열 합계 ÷ 전체 인원`입니다.
- **자유도**: `(유효 연령 집단 수−1) × (판정 범주 수−1)`입니다. 6개 연령과 미달·충족이면 5입니다.
- **p값**: 귀무가설과 검정 가정이 성립할 때, 관측한 통계량 이상으로 극단적인 결과가 나올 확률입니다. 귀무가설이 참일 확률은 아닙니다.
- **Cramér’s V**: 연령과 미달 여부의 관련성 크기입니다. 0~1 범위이며, p값과 달리 관련성이 얼마나 큰지를 나타냅니다.
- **기대빈도 진단**: 기대빈도 1 미만인 칸이 있거나 5 미만인 칸이 20%를 넘으면 점근 카이제곱 근사의 신뢰성을 점검합니다. 이는 흔히 사용하는 진단 기준입니다.
- **Holm 보정 p값**: 여러 종목을 함께 검정하는 점을 반영한 값입니다. 이 화면에서는 보정 p값 < 0.05를 유의성 판단 기준으로 사용합니다.
''')
    with st.expander('왜 보정하나요? — Holm 보정의 이유와 원리', expanded=True):
        st.write('네 종목을 각각 5% 유의수준으로 검정하면, 실제로 모든 귀무가설이 참이어도 하나 이상을 잘못 기각할 가능성이 커집니다. 독립적인 네 검정이라는 예시에서는 1−0.95⁴ ≈ 18.55%입니다. 실제 종목들은 서로 관련될 수 있으므로 이 수치는 설명용 예시입니다.')
        st.write('Holm 보정은 여러 검정 중 하나 이상을 잘못 기각할 확률(가족단위 제1종 오류율)을 5% 이하로 통제하는 절차입니다. 검정 간 독립성을 요구하지 않습니다. 여기서는 계산 가능한 네 종목의 검정을 하나의 가족으로 묶습니다.')
        ranked = results.loc[results['p값'].notna(), ['종목', 'p값', 'Holm 보정 p값']].sort_values('p값').reset_index(drop=True)
        m = len(ranked)
        if m:
            ranked.insert(0, '순위 i', range(1, m + 1))
            ranked['곱하는 수 m−i+1'] = np.arange(m, 0, -1)
            ranked['순차 비교 기준 α/(m−i+1)'] = .05 / ranked['곱하는 수 m−i+1']
            ranked['원 p값 × (m−i+1)'] = ranked['p값'] * ranked['곱하는 수 m−i+1']
            st.dataframe(ranked, hide_index=True)
        st.markdown('''
1. 원래 p값을 작은 순서로 정렬합니다.
2. 네 검정이면 차례로 **0.05/4, 0.05/3, 0.05/2, 0.05**와 비교합니다.
3. 가장 작은 p값부터 기준을 통과하는 동안 기각합니다. 처음 통과하지 못한 지점부터 나머지도 기각하지 않습니다.
4. 같은 판단을 보정 p값으로 표현할 수도 있습니다. 정렬된 p값에 **4, 3, 2, 1**을 곱하고, 앞 순위까지의 최댓값을 취한 뒤 1을 넘으면 1로 제한합니다. 이 보정 p값을 0.05와 비교합니다.
''')
        st.caption('단순히 모든 p값에 4를 곱하는 Bonferroni 보정보다 덜 보수적이면서 가족단위 오류율을 통제합니다. 보정은 인원·미달률·χ²를 바꾸지 않고 여러 검정의 유의성 판단을 조정합니다.')


def main():
    st.set_page_config(page_title='카이제곱', layout='wide')
    st.title('연령과 종목별 미달 여부 · 카이제곱 독립성 검정')
    st.caption('장병별 첫 측정 당시 19~24세 · 전처리에서 선정된 3회 측정 대상자의 첫 측정 사용 · 남성 기준 적용')
    st.markdown('**귀무가설(H₀): 연령과 해당 종목의 미달 여부는 독립이다.**')
    st.markdown('**대립가설(H₁): 연령과 해당 종목의 미달 여부는 독립이 아니다(관련이 있다).**')
    st.caption('각 종목을 따로 검정합니다. 독립이라면 해당 종목의 미달 비율은 연령에 관계없이 같습니다.')
    try:
        results, tables = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.dataframe(results, hide_index=True)
    st.caption('유의수준 0.05에서 네 종목에 Holm 보정을 적용합니다. 보정 p값 < 0.05이면 귀무가설을 기각하고, 그 외에는 기각하지 못합니다.')
    show_interpretation(results)
    label = st.selectbox('종목', list(tables))
    st.write(f'선택 종목의 H₀: 연령과 {label} 미달 여부는 독립이다.')
    st.write(f'선택 종목의 H₁: 연령과 {label} 미달 여부는 독립이 아니다.')
    table = tables[label]
    st.subheader(f'{label} · 범주 × 범주 교차표')
    st.caption('행 범주: 19~24세 연령 · 열 범주: 미달·충족. 각 장병의 첫 측정을 한 번만 집계합니다.')
    observed = table[['미달 인원', '충족 인원']].rename(
        columns={'미달 인원': '미달', '충족 인원': '충족'})
    observed.index.name = '연령 ＼ 판정'
    st.markdown('**관측빈도: 실제 장병 수(명)**')
    st.dataframe(observed)
    n = observed.to_numpy().sum()
    if n > 0:
        expected = pd.DataFrame(np.outer(observed.sum(axis=1), observed.sum(axis=0)) / n,
                                index=observed.index, columns=observed.columns)
        st.markdown('**기대빈도: 연령과 미달 여부가 독립일 때 예상 장병 수(명)**')
        st.caption('각 칸의 기대빈도 = 해당 연령 평가 인원 × 해당 판정 전체 인원 ÷ 전체 평가 인원')
        st.dataframe(expected, column_config={
            c: st.column_config.NumberColumn(format='%.2f') for c in expected.columns})
        denominator = observed.sum(axis=1).replace(0, np.nan)
        percentages = observed.div(denominator, axis=0).mul(100)
        expected_percentages = expected.div(denominator, axis=0).mul(100)
        st.markdown('**연령별 관측 비율·기대 비율(%)**')
        proportions = pd.DataFrame({
            '미달 관측(%)': percentages['미달'], '미달 기대(%)': expected_percentages['미달'],
            '충족 관측(%)': percentages['충족'], '충족 기대(%)': expected_percentages['충족']})
        st.dataframe(proportions, column_config={
            c: st.column_config.NumberColumn(format='%.2f%%') for c in proportions.columns})
        st.subheader(f'{label} · 표의 숫자로 이해하는 결과')
        valid_rates = table.loc[table['평가가능수'].gt(0), '미달률(%)']
        overall_rate = observed['미달'].sum() / n * 100
        st.write(f'전체 평가 장병 {int(n):,}명 중 {int(observed["미달"].sum()):,}명이 미달하여 전체 미달률은 **{overall_rate:.2f}%**입니다. 연령과 미달 여부가 독립이라는 가정 아래에서는 각 연령의 기대 미달률도 이 값과 같습니다.')
        explanations = []
        for age, rate in valid_rates.items():
            difference = rate - overall_rate
            explanations.append({
                '연령': f'{age}세', '평가 인원': int(table.loc[age, '평가가능수']),
                '미달 인원': int(observed.loc[age, '미달']), '관측 미달률(%)': rate,
                '기대 미달률(%)': overall_rate, '관측−기대(%p)': difference,
                '수치 해석': f'기대보다 {abs(difference):.2f}%p ' + ('높음' if difference > 0 else '낮음' if difference < 0 else '같음')})
        st.dataframe(pd.DataFrame(explanations), hide_index=True, column_config={
            c: st.column_config.NumberColumn(format='%.2f')
            for c in ['관측 미달률(%)', '기대 미달률(%)', '관측−기대(%p)']})
        if len(valid_rates) >= 2:
            youngest = valid_rates.index.min()
            lo_age, hi_age = valid_rates.idxmin(), valid_rates.idxmax()
            st.write(f'가장 낮은 미달률은 **{lo_age}세 {valid_rates.loc[lo_age]:.2f}%**, 가장 높은 미달률은 **{hi_age}세 {valid_rates.loc[hi_age]:.2f}%**로 차이는 **{valid_rates.max() - valid_rates.min():.2f}%p**입니다. 이는 각 집단을 100명으로 맞춰 생각했을 때의 미달 인원 차이에 해당합니다.')
            changes_by_age = valid_rates.sort_index().diff().dropna()
            if changes_by_age.gt(0).any() and changes_by_age.lt(0).any():
                st.write('연령순 미달률이 올라가기도 하고 내려가기도 하므로, 이 표에서 나이가 많을수록 미달률이 일관되게 높아지는 모습은 보이지 않습니다.')
            if label == '유연성' and 19 in valid_rates.index:
                others = valid_rates.drop(index=19)
                if len(others) and others.min() > valid_rates.loc[19]:
                    st.write(f'유연성은 **19세 {valid_rates.loc[19]:.2f}%**가 나머지 연령보다 낮고, 나머지는 **{others.min():.2f}~{others.max():.2f}%** 사이입니다. 따라서 표에서 두드러지는 모습은 19세의 상대적으로 낮은 미달률이며, 연령 증가에 따른 꾸준한 악화는 아닙니다.')
            selected_result = results.loc[results['종목'].eq(label)].iloc[0]
            adjusted_p = selected_result['Holm 보정 p값']
            effect_size = selected_result["Cramér's V"]
            if pd.notna(adjusted_p):
                st.write(f'**검정과 연결:** Holm 보정 p값은 {adjusted_p:.4f}, Cramér’s V는 {effect_size:.4f}입니다. ' +
                         ('귀무가설을 기각하지만, 유의하다는 사실만으로 관련성이 크다고 볼 수는 없습니다.' if adjusted_p < .05 else '귀무가설을 기각하지 못하며, 위의 수치 차이만으로 관련성을 확정할 수는 없습니다.'))
        st.caption('관측−기대 차이는 설명용이며 각 연령의 차이가 개별적으로 유의하다는 뜻은 아닙니다. 표본이 크면 작은 차이도 검출될 수 있으므로 관련성 크기와 실제 차이를 함께 봅니다. 어느 연령끼리 다른지는 보정된 사후 비교가 필요합니다. 서로 다른 장병의 첫 측정을 비교한 것이므로 개인이 나이를 먹으며 체력이 변한 결과나 연령의 인과효과로 해석할 수 없습니다.')
        st.subheader('연령별 미달·충족 구성비')
        plot = observed.reset_index().rename(columns={'연령 ＼ 판정': '연령'}).melt(
            id_vars='연령', var_name='판정', value_name='인원')
        plot['비율(%)'] = plot['인원'] / plot['연령'].map(observed.sum(axis=1)) * 100
        bars = alt.Chart(plot).mark_bar().encode(
            x=alt.X('연령:O', title='연령(세)'),
            y=alt.Y('비율(%):Q', stack='zero', scale=alt.Scale(domain=[0, 100]), title='구성비(%)'),
            color=alt.Color('판정:N', scale=alt.Scale(domain=['미달', '충족'], range=['#dc6b45', '#5b9bb5'])),
            order=alt.Order('판정:N', sort='descending'),
            tooltip=['연령:O', '판정:N', '인원:Q', alt.Tooltip('비율(%):Q', format='.2f')])
        st.altair_chart(bars)
        st.caption('연령별 인원 차이를 제외하고 구성비를 비교합니다. 마우스를 올리면 실제 인원과 비율을 볼 수 있습니다.')

        st.subheader('관측빈도와 기대빈도 비교')
        comparison = observed.add_prefix('관측_').join(expected.add_prefix('기대_')).reset_index()
        comparison = comparison.rename(columns={'연령 ＼ 판정': '연령'})
        comparison = comparison.melt(id_vars='연령', var_name='구분', value_name='인원')
        comparison[['유형', '판정']] = comparison['구분'].str.split('_', expand=True)
        compare_chart = alt.Chart(comparison).mark_bar().encode(
            x=alt.X('연령:O', title='연령(세)'), xOffset='유형:N',
            y=alt.Y('인원:Q', title='인원(명)'),
            color=alt.Color('유형:N', scale=alt.Scale(domain=['관측', '기대'], range=['#4679ac', '#b4c5d6'])),
            tooltip=['연령:O', '판정:N', '유형:N', alt.Tooltip('인원:Q', format='.2f')]
        ).facet(column=alt.Column('판정:N', title=None))
        st.altair_chart(compare_chart)

        st.subheader('어느 범주가 기대에서 벗어났는가?')
        residuals = (observed - expected).div(np.sqrt(expected.where(expected.gt(0))))
        heat = residuals.reset_index().rename(columns={'연령 ＼ 판정': '연령'}).melt(
            id_vars='연령', var_name='판정', value_name='Pearson 잔차')
        heat = heat.merge(plot[['연령', '판정', '인원']], on=['연령', '판정'])
        cells = alt.Chart(heat).encode(
            x=alt.X('판정:N', title='판정 범주'), y=alt.Y('연령:O', title='연령(세)'),
            tooltip=['연령:O', '판정:N', '인원:Q', alt.Tooltip('Pearson 잔차:Q', format='.2f')])
        limit = max(1., float(np.nanmax(np.abs(residuals.to_numpy())))) if residuals.notna().any().any() else 1.
        rectangles = cells.mark_rect().encode(color=alt.Color(
            'Pearson 잔차:Q', scale=alt.Scale(domain=[-limit, limit], scheme='redblue', reverse=True),
            title='Pearson 잔차'))
        labels = cells.mark_text(color='black').encode(text=alt.Text('Pearson 잔차:Q', format='.2f'))
        st.altair_chart(rectangles + labels)
        st.caption('Pearson 잔차 = (관측빈도−기대빈도)/√기대빈도. 양수는 기대보다 많음, 음수는 적음을 뜻합니다. 잔차 제곱의 합이 χ²입니다. 이 히트맵은 탐색용이며 개별 셀·연령 간 유의성을 확정하는 사후검정은 아닙니다.')
        st.caption('검정에는 위 관측빈도(인원수)를 사용합니다. 비율표는 해석용이며, 기대 비율은 전체 평가 인원의 미달·충족 구성비이므로 연령별로 같습니다. 평가 인원이 0인 연령은 검정에서 제외됩니다.')
        st.download_button('관측·기대빈도 CSV',
                           observed.add_prefix('관측_').join(expected.add_prefix('기대_')).to_csv().encode('utf-8-sig'),
                           file_name=f'{label}_카이제곱_교차표.csv', mime='text/csv')
    st.markdown('**연령별 평가 인원 및 판정불가 현황**')
    st.dataframe(table)
    st.bar_chart(table[['미달률(%)']].rename(index=lambda age: f'{age}세'), y_label='미달률(%)')
    st.caption('결측은 충족으로 처리하지 않습니다. 심폐는 통합 CARDIO(VO₂max) 값이 42 미만이면 미달로 판정합니다. 같은 기준값이면 충족입니다.')
    st.info('단일 부대 장병 표본의 첫 측정을 분석합니다. 다른 부대나 전체 장병으로 일반화하는 데에는 제한이 있으며, 관련성이 연령의 인과효과를 뜻하지는 않습니다.')
    for name, frame in [('검정결과', results), ('연령별미달집계', table.reset_index())]:
        st.download_button(f'{name} CSV', frame.to_csv(index=False).encode('utf-8-sig'), file_name=f'카이제곱_{name}.csv', mime='text/csv')


if __name__ == '__main__':
    main()
