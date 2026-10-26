"""실행: python -m streamlit run data/experiments/미달종목별_운동처방_탐색대시보드.py"""
import importlib

import altair as alt
import pandas as pd
import streamlit as st

analysis = importlib.import_module('3차_체력미달_운동처방_상관분석')
AREAS = list(analysis.AREAS)


def select_candidates(result, area, minimum=10, significant=True):
    """같은 종목의 충족자보다 처방률이 높은 운동만 선택한다."""
    selected = result.loc[result.체력종목.eq(area) & result.Phi.gt(0)
                          & result.전체처방인원.ge(minimum)].copy()
    if significant:
        selected = selected.loc[selected.관련성확인]
    return selected.sort_values(['Phi', '전체처방인원'], ascending=False)


def comparison_chart(data):
    long = data.melt(id_vars='운동명', value_vars=['미달자내처방률(%)', '충족자내처방률(%)'],
                     var_name='집단', value_name='처방률(%)')
    long['집단'] = long['집단'].map({'미달자내처방률(%)': '미달자', '충족자내처방률(%)': '충족자'})
    return alt.Chart(long).mark_bar().encode(
        y=alt.Y('운동명:N', sort=data.운동명.tolist(), title=None, axis=alt.Axis(labelLimit=300)),
        yOffset=alt.YOffset('집단:N', sort=['미달자', '충족자']),
        x=alt.X('처방률(%):Q', scale=alt.Scale(domain=[0, 100]), title='집단 내 처방률(%)'),
        color=alt.Color('집단:N', scale=alt.Scale(domain=['미달자', '충족자'], range=['#e67e35', '#4389bd'])),
        tooltip=['운동명:N', '집단:N', alt.Tooltip('처방률(%):Q', format='.2f')]
    ).properties(height=max(160, len(data)*48))


def main():
    st.set_page_config(page_title='미달 종목별 운동처방 탐색', layout='wide')
    st.title('미달 종목별 운동처방 탐색')
    st.caption('3차 측정 당시 미달자가 충족자보다 더 높은 비율로 처방받은 운동을 찾아봅니다.')
    try:
        result, summary = analysis.calculate()
    except (ValueError, KeyError, OSError) as exc:
        st.error(str(exc))
        st.stop()
    result['처방률차이(%p)'] = result['미달자내처방률(%)'] - result['충족자내처방률(%)']
    with st.sidebar:
        st.header('탐색 조건')
        area = st.selectbox('미달 종목', AREAS)
        minimum = st.number_input('최소 전체 처방 인원', min_value=0, value=10, step=5,
                                  help='미달자와 충족자를 합한 해당 운동 처방 인원입니다.')
        significant = st.checkbox('보정 p<0.05인 운동만', value=True)
        top = st.slider('비교할 운동 수', 5, 30, 10, 5)
        order = st.selectbox('순위 기준', ['관련성(φ)', '처방률 차이(%p)', '미달자 처방률(%)'])
    candidates = select_candidates(result, area, minimum, significant)
    sort_key = {'관련성(φ)': 'Phi', '처방률 차이(%p)': '처방률차이(%p)',
                '미달자 처방률(%)': '미달자내처방률(%)'}[order]
    candidates = candidates.sort_values([sort_key, '전체처방인원'], ascending=False)
    population = result.loc[result.체력종목.eq(area)].iloc[0]
    with st.container(horizontal=True):
        st.metric('처방 기록 있는 3차 대상', f"{summary['처방기록있는인원']:,}명", border=True)
        st.metric(f'{area} 미달', f"{int(population['미달인원']):,}명", border=True)
        st.metric(f'{area} 충족', f"{int(population['평가가능인원']-population['미달인원']):,}명", border=True)
        st.metric('조건에 해당하는 운동', f'{len(candidates):,}개', border=True)
    st.info('양의 φ는 미달자에게 상대적으로 더 흔한 처방이라는 뜻입니다. '
            '관련성의 크기와 통계적 유의성은 별개이며, 이 순위는 운동 효과나 추천 순위가 아닙니다.')
    tabs = st.tabs(['종목별 관련 운동', '집단별 처방률 비교', '운동별 근거 확인', '전체 종목 비교·다운로드'])
    with tabs[0]:
        st.subheader(f'{area} 미달자에게 상대적으로 더 자주 처방된 운동')
        if candidates.empty:
            st.info('현재 조건에 해당하는 운동이 없습니다. 최소 인원 또는 유의성 조건을 조정하세요.')
        else:
            shown = candidates.head(top)
            chart = alt.Chart(shown).mark_bar(color='#dd7744').encode(
                y=alt.Y('운동명:N', sort=shown.운동명.tolist(), title=None, axis=alt.Axis(labelLimit=300)),
                x=alt.X(f'{sort_key}:Q', title=order),
                tooltip=['운동명', 'Phi', '미달자내처방률(%)', '충족자내처방률(%)', '전체처방인원', 'Holm보정p값'])
            st.altair_chart(chart.properties(height=max(200,len(shown)*32)), width='stretch')
            table = shown[['운동명', 'Phi', '미달자중처방인원', '미달인원', '미달자내처방률(%)',
                           '충족자내처방률(%)', '처방률차이(%p)', 'Holm보정p값']].copy()
            st.dataframe(table, hide_index=True)
            st.caption('표의 미달자중처방인원/미달인원이 미달자 처방률의 분자·분모입니다. '
                       '한 사람이 여러 운동과 여러 종목에 포함될 수 있습니다.')
    with tabs[1]:
        st.subheader(f'{area} 미달자와 충족자의 처방률 차이')
        if candidates.empty:
            st.info('선택 조건에 해당하는 비교 자료가 없습니다.')
        else:
            st.altair_chart(comparison_chart(candidates.head(top)), width='stretch')
            first = candidates.iloc[0]
            st.write(f"현재 순위의 첫 운동은 **{first['운동명']}**입니다. "
                     f"미달자 처방률 {first['미달자내처방률(%)']:.2f}%, "
                     f"충족자 처방률 {first['충족자내처방률(%)']:.2f}%로 "
                     f"**{first['처방률차이(%p)']:.2f}%p** 차이가 납니다.")
    with tabs[2]:
        st.subheader('운동 하나를 선택해 계산 근거 확인')
        st.caption('이 화면은 필터와 관계없이 모든 운동을 조회할 수 있습니다. 달리기처럼 흔한 운동도 확인해 보세요.')
        options = sorted(result.운동명.unique())
        exercise = st.selectbox('확인할 운동', options, index=options.index('달리기') if '달리기' in options else 0)
        row = result.loc[result.체력종목.eq(area) & result.운동명.eq(exercise)].iloc[0]
        phi = row.Phi
        left, right = st.columns(2)
        left.metric('파이 상관계수(φ)', f'{phi:+.3f}' if pd.notna(phi) else '계산 불가')
        right.metric('보정 p값', f"{row['Holm보정p값']:.3g}" if pd.notna(row['Holm보정p값']) else '계산 불가')
        st.altair_chart(comparison_chart(result.loc[result.체력종목.eq(area) & result.운동명.eq(exercise)]), width='stretch')
        counts = pd.DataFrame({'집단': [f'{area} 미달', f'{area} 충족'],
            '처방 있음': [int(row['미달_처방있음']), int(row['충족_처방있음'])],
            '처방 없음': [int(row['미달_처방없음']), int(row['충족_처방없음'])]})
        st.dataframe(counts, hide_index=True)
        if pd.isna(phi):
            st.info('미달 여부 또는 처방 여부가 모두 같아서 상관계수를 계산할 수 없습니다.')
        else:
            direction = '미달자에게 더 흔한 처방' if phi > 0 else '충족자에게 더 흔한 처방' if phi < 0 else '두 집단의 처방률이 같음'
            evidence = '보정 후 통계적으로 유의함' if row['관련성확인'] else '보정 후 유의한 관련성은 확인되지 않음'
            st.write(f'관측 방향: **{direction}** · {evidence}')
        if row.전체처방인원 < 10:
            st.caption(f"전체 처방 인원이 {int(row.전체처방인원)}명으로 적습니다. 순위나 방향을 일반화하기 어렵습니다.")
        with st.expander('계산 방법'):
            st.write('미달=1·충족=0, 처방 있음=1·없음=0으로 계산한 피어슨 상관계수와 φ는 같습니다.')
            st.latex(r'\phi=\frac{ad-bc}{\sqrt{(a+b)(c+d)(a+c)(b+d)}}')
            st.caption('a=미달·처방 있음, b=미달·처방 없음, c=충족·처방 있음, d=충족·처방 없음. '
                       '기대빈도 5 미만이면 Fisher 검정, 그 외에는 카이제곱 검정. 전체 조합에 Holm 보정.')
    with tabs[3]:
        st.subheader('종목별 관련 운동 요약')
        st.caption('각 종목에서 현재 최소 인원·유의성 조건을 적용한 양의 φ 상위 운동을 보여줍니다. '
                   '순위는 선택한 기준을 따릅니다.')
        overview = []
        for label in AREAS:
            selected = select_candidates(result, label, minimum, significant).sort_values(sort_key, ascending=False)
            overview.append({'체력종목': label, '해당운동수': len(selected),
                             '상위운동': ' / '.join(selected.head(3).운동명) if len(selected) else '해당 없음'})
        st.dataframe(pd.DataFrame(overview), hide_index=True)
        st.download_button('선택 종목·조건의 관련 운동 CSV', candidates.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'{area}_관련운동.csv', mime='text/csv')
        st.download_button('전체 상관분석 CSV', result.to_csv(index=False).encode('utf-8-sig'),
                           file_name='3차_종목별_운동처방_전체분석.csv', mime='text/csv')
        st.write(f"3차 측정 {summary['3차측정인원']:,}명 중 처방 기록 없는 "
                 f"{summary['처방기록없음제외']:,}명 제외. {area} 판정불가 "
                 f"{int(population['판정불가인원']):,}명은 해당 종목 계산에서 제외했습니다.")
        st.caption('첫 측정 당시 19~24세 표본 · 날짜순 세 번째 측정 · 남성 19~24세 기준 미만=미달. '
                   '다른 운동 처방은 있지만 해당 운동 기록이 없으면 처방 없음으로 처리합니다. '
                   '실제 운동 수행 여부와 이후 체력 개선은 이 분석에 포함되지 않습니다.')


if __name__ == '__main__':
    main()
