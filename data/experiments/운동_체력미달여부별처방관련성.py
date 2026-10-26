"""실행: python -m streamlit run data/experiments/운동_체력미달여부별처방관련성.py"""
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from scipy.stats import chi2_contingency, fisher_exact
from statsmodels.stats.multitest import multipletests

from 분석_연령별 import analyze_age
from 운동_처방현황분석 import DATA_DIR, load_catalog
from 운동_체력미달정보생성 import generate, DEFICIT_PATH, OUTPUT_DIR

AREAS = {'근력': 'STRENGTH', '근지구력': 'ENDURANCE', '심폐지구력': 'CARDIO', '유연성': 'FLEXIBILITY'}
STANDARD = Path(__file__).resolve().parents[2]/'data/definitions/grade3_male_19_24.csv'


def calculate():
    # 원자료와 기준표로 별도 파일을 갱신한 후, 저장된 미달정보를 읽어 분석한다.
    generate()
    first = pd.read_csv(DEFICIT_PATH, dtype={'SOLDIER_ID': 'string', 'MESURE_ID': 'Int64',
                       **{f'{label}_미달여부': 'boolean' for label in AREAS}})
    first['MESURE_ID'] = pd.to_numeric(first['MESURE_ID'], errors='raise').astype('Int64')
    if first.MESURE_ID.isna().any() or first.MESURE_ID.duplicated().any():
        raise ValueError('첫 측정의 측정번호가 결측 또는 중복입니다.')
    catalog = load_catalog()
    records = pd.read_csv(DATA_DIR/'KS_NFA_PRESCRIPTION.csv', dtype='string')
    records['MESURE_ID'] = pd.to_numeric(records['MESURE_ID'], errors='raise').astype('Int64')
    if records[['PRESCRIPTION_ID', 'MESURE_ID', 'PRESCRIPTION_TYPE_ID']].isna().any().any():
        raise ValueError('처방 식별자에 결측이 있습니다.')
    if records.PRESCRIPTION_ID.duplicated().any():
        raise ValueError('처방식별번호 중복입니다.')
    joined = records.merge(catalog, on='PRESCRIPTION_TYPE_ID', how='left', validate='many_to_one', indicator=True)
    if not joined['_merge'].eq('both').all():
        raise ValueError('운동명 목록에 없는 처방번호가 있습니다.')
    # 첫 측정을 먼저 고른 후 기록 유무로 제외한다. 이후 측정으로 대체하지 않는다.
    excluded = int((~first.MESURE_ID.isin(joined.MESURE_ID)).sum())
    first = first.loc[first.MESURE_ID.isin(joined.MESURE_ID)].set_index('MESURE_ID')
    if first.empty:
        raise ValueError('첫 측정에 처방 기록이 있는 대상자가 없습니다.')
    selected = joined.loc[joined.MESURE_ID.isin(first.index)]
    membership = selected.groupby('PRESCRIPTION')['MESURE_ID'].agg(set).to_dict()
    lists = selected.groupby('MESURE_ID')['PRESCRIPTION'].agg(lambda v: ', '.join(sorted(set(v))))
    linked = first.copy()
    linked['운동처방목록'] = linked.index.map(lists)
    linked.reset_index().to_csv(OUTPUT_DIR/'장병별_미달정보_운동처방연결.csv', index=False, encoding='utf-8-sig')
    rows = []
    for label, col in AREAS.items():
        valid = first.loc[first[f'{label}_미달여부'].notna()]
        fail = valid[f'{label}_미달여부'].astype(bool)
        for exercise in catalog.PRESCRIPTION.unique():
            prescribed = valid.index.isin(membership.get(exercise, set()))
            a = int((fail & prescribed).sum())
            b = int((fail & ~prescribed).sum())
            c = int((~fail & prescribed).sum())
            d = int((~fail & ~prescribed).sum())
            observed = np.array([[a, b], [c, d]])
            row = {'체력요소': label, '운동명': exercise, '평가인원': len(valid),
                   '미달_처방있음': a, '미달_처방없음': b, '충족_처방있음': c, '충족_처방없음': d,
                   '운동처방인원': a+c, '미달집단_처방률(%)': a/(a+b)*100 if a+b else np.nan,
                   '충족집단_처방률(%)': c/(c+d)*100 if c+d else np.nan,
                   '검정방법': '검정 불가', 'χ²': np.nan, 'p값': np.nan,
                   '최소기대빈도': np.nan, 'Phi_방향포함': np.nan}
            if (observed.sum(axis=0)>0).all() and (observed.sum(axis=1)>0).all():
                stat, p, _, expected = chi2_contingency(observed, correction=False)
                method = '카이제곱'
                if (expected < 5).any():
                    _, p = fisher_exact(observed, alternative='two-sided')
                    method = 'Fisher 정확검정'
                phi = (a*d-b*c)/np.sqrt(float((a+b)*(c+d)*(a+c)*(b+d)))
                row.update({'검정방법': method, 'χ²': stat, 'p값': p,
                            '최소기대빈도': expected.min(), 'Phi_방향포함': phi})
            rows.append(row)
    result = pd.DataFrame(rows)
    result['처방률차이_미달-충족(%p)'] = result['미달집단_처방률(%)']-result['충족집단_처방률(%)']
    result['Holm 보정 p값'] = np.nan
    valid = result['p값'].notna()
    if valid.any():
        result.loc[valid, 'Holm 보정 p값'] = multipletests(result.loc[valid, 'p값'], method='holm')[1]
    result.to_csv(OUTPUT_DIR/'체력미달_운동처방관련성분석.csv', index=False, encoding='utf-8-sig')
    return result, first, excluded


def main():
    st.set_page_config(page_title='운동 체력미달별 처방 관련성', layout='wide')
    st.title('부족한 체력요소와 운동처방의 관계')
    st.caption('체력이 부족한 사람에게 어떤 운동이 더 자주 처방됐는지 확인합니다. 주황색은 미달 집단, 파란색은 충족 집단입니다.')
    st.info('장병별 첫 측정의 체력 상태와 그 측정에 기록된 운동처방을 비교합니다. 처방 기록이 없는 첫 측정은 제외합니다. 특정 운동의 ‘처방 없음’은 다른 운동의 처방 기록은 있지만 해당 운동은 기록되지 않았다는 뜻입니다.')
    try:
        result, people, excluded = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    a, b = st.columns(2)
    a.metric('처방 기록 있는 첫 측정 장병', f'{len(people):,}명')
    b.metric('첫 측정 처방 기록 없음 제외', f'{excluded:,}명')
    st.caption('실행 시 별도 미달정보 CSV를 갱신한 뒤 해당 파일을 읽어 처방과 연결합니다. 결과는 data/experiments/results/운동_체력미달별처방관련성/에 저장합니다.')
    with st.expander('별도 생성한 미달정보와 처방 연결 자료'):
        deficit = pd.read_csv(DEFICIT_PATH, dtype={'SOLDIER_ID': 'string'})
        st.dataframe(deficit, hide_index=True)
        st.download_button('첫 측정 미달정보 CSV', DEFICIT_PATH.read_bytes(), file_name=DEFICIT_PATH.name, mime='text/csv')
        linked_path = OUTPUT_DIR/'장병별_미달정보_운동처방연결.csv'
        st.dataframe(pd.read_csv(linked_path, dtype={'SOLDIER_ID': 'string'}), hide_index=True)
        st.download_button('미달정보·운동처방 연결 CSV', linked_path.read_bytes(), file_name=linked_path.name, mime='text/csv')
    with st.expander('분석에 사용한 데이터·변수·방법', expanded=False):
        st.table(pd.DataFrame([
            {'구분': '측정 자료', '내용': 'KS_NFA_PROCESSED.csv: SOLDIER_ID, MESURE_ID, AGE, MESURE_DE, 체력 4종목'},
            {'구분': '별도 미달정보', '내용': '장병별_첫측정_체력미달정보.csv: 측정값·종목별 기준값·미달 여부를 저장한 후 재입력'},
            {'구분': '처방 자료', '내용': 'KS_NFA_PRESCRIPTION.csv: MESURE_ID, PRESCRIPTION_TYPE_ID, PRESCRIPTION_ID'},
            {'구분': '운동명 자료', '내용': 'KS_NFA_PRESCRIPTION_DETAIL.csv: PRESCRIPTION_TYPE_ID, PRESCRIPTION'},
            {'구분': '연결 기준', '내용': '측정번호로 체력·처방 연결, 처방유형번호로 운동명 연결. 운동명 기준으로 처방 유무 집계'},
            {'구분': '분석 단위', '내용': '장병별 날짜순 첫 측정 1건. 같은 장병의 반복 측정을 독립 표본처럼 합치지 않음'},
            {'구분': '대상·제외', '내용': f'첫 측정 당시 19~24세, 처방 기록 있는 {len(people):,}명. 첫 측정 처방 기록 없는 {excluded:,}명 제외'},
            {'구분': '변수 1', '내용': '체력요소별 미달 여부: 기준 미만=미달, 이상=충족. 종목 결측은 해당 분석에서 제외'},
            {'구분': '변수 2', '내용': '운동별 처방 여부: 해당 운동 기록 있음=1, 다른 운동 기록은 있으나 해당 운동은 없음=0'},
            {'구분': '검정', '내용': '체력 미달/충족 × 처방 있음/없음의 2×2 교차표. Pearson 카이제곱, 기대빈도 5 미만이면 Fisher'},
            {'구분': '관련성 크기', '내용': 'Phi(φ): −1~1. 양수는 미달 집단에서 처방이 더 흔함, 음수는 충족 집단에서 더 흔함'},
            {'구분': '다중검정', '내용': '모든 체력요소×운동의 계산 가능한 p값에 Holm 보정. 보정 p<0.05로 판단'},
        ]))
        st.caption(f'전체 조합 {len(result):,}개 중 계산 가능한 검정 {result["p값"].notna().sum():,}개. 유의한 결과 {result["Holm 보정 p값"].lt(.05).sum():,}개. 처방 여부는 기록 기준이며 실제 운동 수행 여부는 아닙니다.')
        st.latex(r'\phi=\frac{ad-bc}{\sqrt{(a+b)(c+d)(a+c)(b+d)}}')
        st.caption('a=미달·처방있음, b=미달·처방없음, c=충족·처방있음, d=충족·처방없음. 두 이진변수의 Phi는 0/1로 코딩한 Pearson 상관계수와 같습니다. 연속 체력값의 상관분석과는 구분합니다.')
    st.caption('체력 미달 기준: 근력 51.8, 근지구력 42, 심폐 VO₂max 42, 유연성 6.1 미만. 종목 결측은 해당 검정에서 제외합니다.')
    label = st.selectbox('① 확인할 부족 체력요소', list(AREAS))
    min_count = st.number_input('표에 표시할 최소 운동 처방 인원', min_value=0, value=10, step=5)
    view = result.loc[result.체력요소.eq(label) & result.운동처방인원.ge(min_count)].sort_values('Holm 보정 p값')
    st.subheader(f'{label}이 부족한 사람에게 어떤 운동을 처방했을까?')
    group_data = result.loc[result.체력요소.eq(label)].iloc[0]
    fail_n = int(group_data['미달_처방있음']+group_data['미달_처방없음'])
    pass_n = int(group_data['충족_처방있음']+group_data['충족_처방없음'])
    a, b, c = st.columns(3)
    a.metric(f'{label} 미달 집단', f'{fail_n:,}명')
    b.metric(f'{label} 충족 집단', f'{pass_n:,}명')
    c.metric('보정 후 관련성이 확인된 운동', f'{view["Holm 보정 p값"].lt(.05).sum():,}개', help='현재 최소 처방 인원 조건에 해당하는 운동 중 Holm 보정 p<0.05인 운동 수')
    mode = st.radio('② 비교할 운동', ['미달 집단에 자주 처방된 운동', '두 집단의 처방률 차이가 큰 운동'], horizontal=True)
    count = st.slider('③ 비교할 상위 운동 수', 5, 25, 10, 5)
    overview = view.dropna(subset=['미달집단_처방률(%)', '충족집단_처방률(%)']).copy()
    if mode == '미달 집단에 자주 처방된 운동':
        overview = overview.nlargest(count, '미달집단_처방률(%)')
    else:
        overview = overview.assign(차이절댓값=overview['처방률차이_미달-충족(%p)'].abs()).nlargest(count, '차이절댓값')
    if not overview.empty:
        order = overview.운동명.tolist()
        comparison = overview.melt(id_vars=['운동명'],
            value_vars=['미달집단_처방률(%)', '충족집단_처방률(%)'], var_name='집단', value_name='처방률(%)')
        comparison['집단'] = comparison['집단'].map({'미달집단_처방률(%)': f'{label} 미달', '충족집단_처방률(%)': f'{label} 충족'})
        chart = alt.Chart(comparison).encode(
            y=alt.Y('운동명:N', sort=order, title=None),
            yOffset=alt.YOffset('집단:N', sort=[f'{label} 미달', f'{label} 충족']),
            x=alt.X('처방률(%):Q', title='각 집단에서 해당 운동을 처방받은 비율(%)', scale=alt.Scale(domain=[0, 100])),
            color=alt.Color('집단:N', scale=alt.Scale(domain=[f'{label} 미달', f'{label} 충족'], range=['#e67e35', '#4389bd']), title=None),
            tooltip=['운동명:N', '집단:N', alt.Tooltip('처방률(%):Q', format='.1f')])
        st.altair_chart((chart.mark_bar(size=11) + chart.mark_text(align='left', dx=4, color='#263238').encode(
            text=alt.Text('처방률(%):Q', format='.1f'))).properties(height=max(280, len(order)*45)))
        st.caption('주황 막대가 더 길면 미달 집단에 더 흔한 처방입니다. 집단별 인원수가 달라 횟수 대신 비율로 비교합니다. 막대 길이의 차이만으로 통계적 유의성을 판단하지 않습니다.')
        readable = overview[['운동명', '미달집단_처방률(%)', '충족집단_처방률(%)', '처방률차이_미달-충족(%p)']].copy()
        readable.columns = ['운동명', '미달 집단 처방률(%)', '충족 집단 처방률(%)', '처방률 차이(%p)']
        readable['관련성 확인'] = np.where(overview['Holm 보정 p값'].lt(.05), '확인됨', '근거 부족 또는 검정 불가')
        readable['관측된 경향'] = np.where(overview['처방률차이_미달-충족(%p)'].gt(0), '미달 집단에 더 흔함',
                                      np.where(overview['처방률차이_미달-충족(%p)'].lt(0), '충족 집단에 더 흔함', '두 집단 동일'))
        st.dataframe(readable, hide_index=True, column_config={
            col: st.column_config.NumberColumn(format='%.1f') for col in readable.columns if '%' in col})
        strongest = overview.loc[overview['처방률차이_미달-충족(%p)'].abs().idxmax()]
        direction = '높습니다' if strongest['처방률차이_미달-충족(%p)'] > 0 else '낮습니다' if strongest['처방률차이_미달-충족(%p)'] < 0 else '같습니다'
        st.write(f"**화면에 표시한 운동 중 차이가 가장 큰 것은 ‘{strongest['운동명']}’입니다.** "
                 f"미달 집단 처방률 {strongest['미달집단_처방률(%)']:.1f}%, 충족 집단 {strongest['충족집단_처방률(%)']:.1f}%로, "
                 f"미달 집단이 {abs(strongest['처방률차이_미달-충족(%p)']):.1f}%p {direction}")
        st.caption('이 비교는 해당 체력요소를 보완하려는 처방 경향을 살펴보는 것입니다. 운동이 그 요소에 적합한지, 실제 수행 후 개선됐는지를 입증하지 않습니다.')
    else:
        st.info('현재 조건에 해당하는 비교 자료가 없습니다.')
    st.divider()
    st.subheader('관련성 통계 자세히 보기')
    st.subheader('체력요소 × 운동처방 관련성 히트맵')
    top_n = st.slider('시각화할 운동 수', 5, 40, 15, 5)
    eligible = result.loc[result.운동처방인원.ge(min_count) & result['Phi_방향포함'].notna()].copy()
    ranking = eligible.assign(관련성절댓값=eligible['Phi_방향포함'].abs()).groupby('운동명')['관련성절댓값'].max().nlargest(top_n)
    heat = eligible.loc[eligible.운동명.isin(ranking.index)].copy()
    heat['유의성'] = np.where(heat['Holm 보정 p값'].lt(.05), '유의', '유의하지 않음')
    if not heat.empty:
        cells = alt.Chart(heat).encode(
            x=alt.X('체력요소:N', sort=list(AREAS)),
            y=alt.Y('운동명:N', sort=ranking.index.tolist()),
            tooltip=['체력요소:N', '운동명:N', alt.Tooltip('Phi_방향포함:Q', format='.3f'),
                     alt.Tooltip('Holm 보정 p값:Q', format='.3e'), '유의성:N', '운동처방인원:Q'])
        st.altair_chart(cells.mark_rect().encode(color=alt.Color(
            'Phi_방향포함:Q', scale=alt.Scale(domain=[-1, 1], scheme='redblue', reverse=True), title='Phi(φ)'))
            + cells.mark_text(color='black').encode(text=alt.Text('Phi_방향포함:Q', format='.2f')))
        st.caption('전체 체력요소에서 |Phi|가 큰 운동을 우선 표시합니다. 양수는 미달 집단에 더 흔한 처방, 음수는 충족 집단에 더 흔한 처방입니다. 색의 진하기는 관련성 크기이며 유의 여부는 마우스를 올려 확인하세요. 빈 칸은 표시 인원 조건 미충족 또는 검정 불가입니다.')
    st.subheader(f'{label} · 미달 집단과 충족 집단의 처방률 비교')
    scatter = view.dropna(subset=['Phi_방향포함', '미달집단_처방률(%)', '충족집단_처방률(%)']).copy()
    scatter['유의성'] = np.where(scatter['Holm 보정 p값'].lt(.05), '유의', '유의하지 않음')
    if not scatter.empty:
        dots = alt.Chart(scatter).mark_circle().encode(
            x=alt.X('충족집단_처방률(%):Q', scale=alt.Scale(domain=[0, 100])),
            y=alt.Y('미달집단_처방률(%):Q', scale=alt.Scale(domain=[0, 100])),
            size=alt.Size('운동처방인원:Q', title='처방 인원'), color='유의성:N',
            tooltip=['운동명:N', alt.Tooltip('미달집단_처방률(%):Q', format='.2f'),
                     alt.Tooltip('충족집단_처방률(%):Q', format='.2f'), alt.Tooltip('Holm 보정 p값:Q', format='.3e')])
        diagonal = alt.Chart(pd.DataFrame({'x': [0, 100], 'y': [0, 100]})).mark_line(strokeDash=[5, 5], color='gray').encode(x='x:Q', y='y:Q')
        st.altair_chart(diagonal+dots)
        st.caption('점 하나가 운동 하나입니다. 대각선 위는 미달 집단에서 더 자주 처방, 아래는 충족 집단에서 더 자주 처방되는 운동입니다. 점 크기는 처방 인원이며 색은 보정 p값에 따른 유의성입니다.')
        ranked = scatter.assign(관련성절댓값=scatter['Phi_방향포함'].abs()).nlargest(top_n, '관련성절댓값')
        st.subheader(f'{label} · 관련성 크기 상위 운동')
        st.altair_chart(alt.Chart(ranked).mark_bar().encode(
            x=alt.X('Phi_방향포함:Q', title='Phi(φ)'),
            y=alt.Y('운동명:N', sort=ranked.운동명.tolist()), color='유의성:N',
            tooltip=['운동명:N', alt.Tooltip('Phi_방향포함:Q', format='.3f'), alt.Tooltip('Holm 보정 p값:Q', format='.3e')]))
    st.subheader('관련성 분석 상세표')
    st.dataframe(view, hide_index=True)
    st.caption('모든 체력요소×운동의 계산 가능한 검정 전체에 Holm 보정을 적용합니다. 인원 필터는 표시만 바꾸며 보정 범위는 바꾸지 않습니다. 희소한 교차표(기대빈도 5 미만)는 Fisher 정확검정을 사용합니다.')
    options = view.운동명.tolist()
    if options:
        exercise = st.selectbox('상세 운동', options)
        row = view.loc[view.운동명.eq(exercise)].iloc[0]
        table = pd.DataFrame({'처방 있음': [row['미달_처방있음'], row['충족_처방있음']],
                              '처방 없음': [row['미달_처방없음'], row['충족_처방없음']]}, index=['미달', '충족']).astype(int)
        st.subheader(f'{label} × {exercise}')
        st.dataframe(table)
        st.bar_chart(table.div(table.sum(axis=1).replace(0, np.nan), axis=0)*100, stack=True, y_label='처방 구성비(%)')
        st.write(f"미달 집단 처방률 **{row['미달집단_처방률(%)']:.2f}%**, 충족 집단 **{row['충족집단_처방률(%)']:.2f}%**, 차이 **{row['처방률차이_미달-충족(%p)']:.2f}%p**입니다.")
        p = row['Holm 보정 p값']
        if pd.notna(p):
            decision = '관련성이 있다는 통계적 근거가 있습니다.' if p < .05 else '관련성을 확인할 근거가 충분하지 않습니다.'
            st.write(f"{row['검정방법']}, Holm 보정 p={p:.3e}: {decision}")
            st.caption(f"Phi={row['Phi_방향포함']:.3f}. 양수는 미달 집단에서 해당 운동 처방이 더 흔함을 뜻하며, 음수는 반대입니다. χ²는 보정 없는 Pearson 통계량이고, Fisher 사용 시 p값은 정확검정 결과입니다.")
        else:
            st.info('집단 또는 처방 여부에 변동이 없어 검정할 수 없습니다.')
    else:
        st.info('표시 조건을 만족하는 운동이 없습니다. 최소 인원을 낮춰 보세요.')
    st.divider()
    st.subheader('분석 해석 · 주목해서 볼 점')
    st.caption(f'아래 해석은 선택한 {label}과 최소 처방 인원 {min_count}명 조건에 해당하는 모든 운동을 기준으로 합니다. 그래프의 상위 운동 수와는 무관합니다.')
    interpretable = view.dropna(subset=['Phi_방향포함', 'Holm 보정 p값']).copy()
    significant = interpretable.loc[interpretable['Holm 보정 p값'].lt(.05)]
    positive = significant.loc[significant['처방률차이_미달-충족(%p)'].gt(0)]
    negative = significant.loc[significant['처방률차이_미달-충족(%p)'].lt(0)]
    st.markdown('**1. 부족한 체력요소에 따라 처방이 달라졌는가?**')
    if interpretable.empty:
        st.info('현재 표시 조건에서 관련성을 검정할 수 있는 운동이 없습니다. 인원 조건과 교차표를 확인하세요.')
    else:
        st.write(f'검정 가능한 운동 **{len(interpretable):,}개** 중 보정 후 관련성이 확인된 운동은 '
                 f'**{len(significant):,}개**입니다. 이 중 **{len(positive):,}개**는 미달 집단에서, '
                 f'**{len(negative):,}개**는 충족 집단에서 더 자주 처방됐습니다.')
        if significant.empty:
            st.info('현재 조건에서는 보정 후 관련성이 확인된 운동이 없습니다. 개별 처방률 차이는 관찰되더라도 체력 미달 여부에 따라 처방이 달라졌다고 단정하기 어렵습니다. 관련성이 전혀 없다고 증명한 것은 아닙니다.')
        st.markdown('**2. 미달 집단에 더 자주 처방된 운동을 먼저 확인하세요.**')
        if not positive.empty:
            highlighted = positive.nlargest(3, '처방률차이_미달-충족(%p)')
            for _, item in highlighted.iterrows():
                st.write(f"- **{item['운동명']}**: 미달 집단 {item['미달집단_처방률(%)']:.1f}%, "
                         f"충족 집단 {item['충족집단_처방률(%)']:.1f}% → "
                         f"미달 집단에서 **{item['처방률차이_미달-충족(%p)']:.1f}%p 더 높음** "
                         f"(φ={item['Phi_방향포함']:.3f}, 보정 p={item['Holm 보정 p값']:.3e}).")
            st.caption('해당 미달 상태와 함께 더 흔히 기록된 처방입니다. 부족한 요소를 보완하려는 처방 경향과 부합할 수 있지만 운동 목적의 분류·처방 사유를 확인해야 합니다.')
        else:
            st.write('미달 집단에서 더 흔하면서 보정 후 유의한 운동은 현재 조건에서 확인되지 않았습니다.')
        st.markdown('**3. 유의성보다 관련성의 크기도 함께 보세요.**')
        strongest = interpretable.loc[interpretable['Phi_방향포함'].abs().idxmax()]
        st.write(f"현재 조건에서 |φ|가 가장 큰 운동은 **{strongest['운동명']}**이며 "
                 f"φ=**{strongest['Phi_방향포함']:.3f}**, 보정 p=**{strongest['Holm 보정 p값']:.3e}**입니다. "
                 'φ가 0에 가까우면 미달 여부와 처방 여부의 연결은 약합니다. p값이 작아도 관련성이 크다는 뜻은 아닙니다.')
        if not negative.empty:
            item = negative.loc[negative['처방률차이_미달-충족(%p)'].idxmin()]
            st.write(f"**반대 방향도 확인:** {item['운동명']}은 충족 집단에서 "
                     f"{abs(item['처방률차이_미달-충족(%p)']):.1f}%p 더 흔하며 보정 후 유의합니다. "
                     '이는 처방 오류를 뜻하지 않습니다. 유지·향상 목적이나 다른 체력요소·대상자 특성이 작용했을 수 있습니다.')
    st.markdown('**4. 이 결과로 말할 수 있는 것과 다음 확인 사항**')
    st.write('이 결과는 첫 측정 당시 체력 미달 여부와 기록된 운동처방의 관련성입니다. 처방 뒤 실제 수행 여부나 체력 개선을 분석한 결과는 아닙니다. 관련성이 약해도 처방이 부적절하거나 운동 효과가 없다고 해석하지 않습니다.')
    st.write('같은 체력요소를 보완하는 운동이 여러 종류로 나뉘면 개별 운동과의 관련성이 약하게 나타날 수 있습니다. 다음 단계는 근거 있는 운동군 분류를 정한 뒤, 해당 보완 운동군을 하나라도 처방받은 비율을 비교하는 것입니다.')
    st.caption('처방 기록 없는 첫 측정은 제외한 집단의 결과입니다. 다른 대상자 전체로 일반화하거나, 연령·BMI 등 다른 요인과 무관한 효과로 해석할 수 없습니다. 상위 운동을 결과에 따라 골라 강조한 해석은 탐색적입니다.')
    st.warning('이 분석은 처방의 관련성만 확인합니다. 운동 수행·효과 분석이 아니며, 미달 상태에 따라 처방이 선택됐을 가능성이 있습니다. 연령·BMI 등 다른 요인은 보정하지 않았습니다.')
    st.download_button('전체 관련성 분석 CSV', result.to_csv(index=False).encode('utf-8-sig'),
                       file_name='운동_체력미달별처방관련성.csv', mime='text/csv')


if __name__ == '__main__':
    main()
