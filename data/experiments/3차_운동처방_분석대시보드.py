"""실행: python -m streamlit run data/experiments/3차_운동처방_분석대시보드.py"""
import importlib

import altair as alt
import pandas as pd
import streamlit as st

analysis = importlib.import_module('3차_체력미달_운동처방_상관분석')
AREAS = list(analysis.AREAS)


def bars(data, value, title, color=None):
    """운동별 가로 막대. 표시된 값은 툴팁으로 확인한다."""
    chart = alt.Chart(data).mark_bar().encode(
        y=alt.Y('운동명:N', sort='-x', title=None, axis=alt.Axis(labelLimit=300)),
        x=alt.X(f'{value}:Q', title=title),
        tooltip=['운동명:N', alt.Tooltip(f'{value}:Q', format='.3f')])
    if color:
        chart = chart.encode(color=color)
    st.altair_chart(chart.properties(height=max(220, data.운동명.nunique()*28)), width='stretch')


def heatmap(data, value, title, names, signed=False):
    scale = alt.Scale(domain=[-1, 1], scheme='redblue', reverse=True) if signed else alt.Scale(domain=[0, 100], scheme='blues')
    shown = data.copy()
    shown['셀표시'] = shown.apply(lambda r: (
        f'{r[value]:+.3f}' if signed else f'{r[value]:.1f}%') + (' *' if signed and r['관련성확인'] else '')
        if pd.notna(r[value]) else '계산 불가', axis=1)
    base = alt.Chart(shown).encode(
        x=alt.X('체력종목:N', sort=AREAS, title=None),
        y=alt.Y('운동명:N', sort=names, title=None, axis=alt.Axis(labelLimit=300)),
        tooltip=['운동명:N', '체력종목:N', alt.Tooltip(f'{value}:Q', format='.3f'),
                 '미달인원:Q', '미달자중처방인원:Q', '전체처방인원:Q',
                 alt.Tooltip('Holm보정p값:Q', format='.3e')])
    cutoff = .55 if signed else 55
    chart = base.mark_rect().encode(color=alt.Color(f'{value}:Q', scale=scale, title=title))
    text = base.mark_text().encode(text='셀표시:N', color=alt.condition(
        abs(alt.datum[value]) > cutoff, alt.value('white'), alt.value('black')))
    st.altair_chart((chart+text).properties(height=max(160, len(names)*33)), width='stretch')


def main():
    st.set_page_config(page_title='3차 운동처방 분석 대시보드', layout='wide')
    st.title('3차 운동처방 분석 대시보드')
    st.caption('같은 측정의 체력 상태와 운동처방을 비교합니다. 운동 수행이나 처방 이후 효과를 나타내지 않습니다.')
    try:
        result, summary = analysis.calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    result['처방률차이(%p)'] = result['미달자내처방률(%)'] - result['충족자내처방률(%)']
    st.caption('첫 측정 당시 19~24세 표본의 날짜순 3차 측정 · 기존 남성 19~24세 기준 · '
               '처방 기록 없는 측정 제외 · 종목별 결측 제외 · 같은 측정·운동 중복 제거')
    with st.container(horizontal=True):
        for label, value in summary.items():
            st.metric(label, f'{value:,}명', border=True)
    with st.sidebar:
        st.header('표시 조건')
        area = st.selectbox('체력 종목', AREAS)
        minimum = st.number_input('전체 대상 중 최소 운동 처방 인원', min_value=0, value=10, step=5)
        top = st.slider('상위 운동 수', 5, 40, 15, 5)
        significant = st.checkbox('관련성 비교는 보정 p<0.05만 표시', value=False)
        st.caption('최소 인원·상위 수는 화면 표시 조건입니다. Holm 보정은 전체 검정 기준으로 유지됩니다. '
                   '운동 상세와 자료 점검은 필터와 관계없이 전체 자료를 사용합니다.')
    filtered = result.loc[result.전체처방인원.ge(minimum)].copy()
    related = filtered.loc[filtered.관련성확인] if significant else filtered
    one = filtered.loc[filtered.체력종목.eq(area)]
    relation_one = related.loc[related.체력종목.eq(area)]
    population = result.loc[result.체력종목.eq(area)].iloc[0]
    st.subheader(f'선택 종목: {area}')
    st.caption(f"미달 {int(population['미달인원']):,}명 · 충족 "
               f"{int(population['평가가능인원']-population['미달인원']):,}명. "
               '①~⑥은 선택 종목을 기준으로 표시합니다. ②·③의 다른 열은 비교용이며, ⑦~⑨는 전체 종목을 함께 봅니다.')
    tabs = st.tabs(['① 처방 규모', '② 미달 종목별 처방률', '③ 상관관계 지도',
                    '④ 미달자 집중 처방', '⑤ 미달·충족 비교', '⑥ 처방 빈도와 관련성',
                    '⑦ 운동별 상세', '⑧ 공통 처방 패턴', '⑨ 자료 점검·다운로드'])
    with tabs[0]:
        st.subheader(f'{area} 미달자에게 많이 처방된 운동')
        st.caption('선택 종목의 미달자 중 해당 운동을 처방받은 인원 순위입니다. 한 장병은 여러 운동에 포함될 수 있습니다.')
        ranking = one.loc[one.미달자중처방인원.gt(0)].nlargest(top, '미달자중처방인원')[
            ['운동명', '미달자중처방인원', '미달인원', '미달자내처방률(%)']]
        bars(ranking, '미달자중처방인원', f'{area} 미달자 중 처방 인원(명)')
        st.dataframe(ranking, hide_index=True)
    with tabs[1]:
        st.subheader(f'{area} 미달자 처방률 상위 운동 · 종목 간 비교')
        st.caption('선택 종목의 처방률 순위로 운동을 고릅니다. 각 열의 분모는 해당 종목 미달 인원입니다. '
                   '미달 집단이 겹치거나 공통 처방이 많으면 종목을 바꿔도 상위 운동명은 비슷할 수 있습니다.')
        names = one.nlargest(top, '미달자내처방률(%)').운동명.tolist()
        heatmap(filtered.loc[filtered.운동명.isin(names)], '미달자내처방률(%)', '처방률(%)', names)
        st.dataframe(one.nlargest(top, '미달자내처방률(%)')[
            ['운동명', '미달자중처방인원', '미달인원', '미달자내처방률(%)']], hide_index=True)
    with tabs[2]:
        st.subheader(f'{area} 기준 상관관계 상위 운동 · 종목 간 비교')
        st.caption('양수: 미달자에게 더 흔함 · 음수: 충족자에게 더 흔함 · *: Holm 보정 p<0.05. '
                   '상관 크기와 유의성은 구분해서 읽습니다.')
        names = relation_one.dropna(subset=['Phi']).assign(
            크기=lambda frame: frame.Phi.abs()).nlargest(top, '크기').운동명.tolist()
        heatmap(related.loc[related.운동명.isin(names)], 'Phi', 'φ', names, signed=True)
    with tabs[3]:
        st.subheader(f'{area} 미달자에게 상대적으로 더 자주 처방된 운동')
        st.caption('같은 종목의 충족자와 비교한 양의 φ 순위입니다. 운동 효과의 순위가 아닙니다.')
        positive = relation_one.loc[relation_one.Phi.gt(0)].nlargest(top, 'Phi')
        if positive.empty:
            st.info('현재 조건에 해당하는 양의 관련성 운동이 없습니다.')
        else:
            bars(positive, 'Phi', '파이 상관계수(φ)')
            st.dataframe(positive[['운동명', 'Phi', '전체처방인원', '미달자내처방률(%)',
                                   '충족자내처방률(%)', '처방률차이(%p)', 'Holm보정p값']], hide_index=True)
    with tabs[4]:
        st.subheader(f'{area} 미달자·충족자 처방률 비교')
        st.caption('양수 차이: 미달자 처방률이 높음. 두 집단의 인원수가 달라 비율로 비교합니다.')
        comparison = relation_one.assign(차이절댓값=relation_one['처방률차이(%p)'].abs()).nlargest(top, '차이절댓값')
        long = comparison.melt(id_vars='운동명', value_vars=['미달자내처방률(%)', '충족자내처방률(%)'],
                               var_name='집단', value_name='처방률')
        st.altair_chart(alt.Chart(long).mark_bar().encode(
            y=alt.Y('운동명:N', sort=comparison.운동명.tolist(), axis=alt.Axis(labelLimit=300)),
            yOffset='집단:N', x=alt.X('처방률:Q', scale=alt.Scale(domain=[0,100]), title='처방률(%)'),
            color='집단:N', tooltip=['운동명', '집단', alt.Tooltip('처방률:Q', format='.2f')]
        ).properties(height=max(220,len(comparison)*45)), width='stretch')
    with tabs[5]:
        st.subheader('많이 처방된 운동과 미달 관련성이 큰 운동')
        st.caption('오른쪽: 많이 처방됨 · 위쪽: 미달자에게 상대적으로 더 흔함 · '
                   '아래쪽: 충족자에게 상대적으로 더 흔함. 처방 빈도와 상관계수는 서로 다른 지표입니다.')
        points = relation_one.dropna(subset=['Phi'])
        scatter = alt.Chart(points).mark_circle(size=65).encode(
            x=alt.X('미달자중처방인원:Q', title=f'{area} 미달자 중 처방 인원(명)'),
            y=alt.Y('Phi:Q', title='파이 상관계수(φ)', scale=alt.Scale(domain=[-1,1])),
            color='관련성확인:N', tooltip=['운동명', '미달자중처방인원', '전체처방인원', 'Phi', 'Holm보정p값'])
        zero = alt.Chart(pd.DataFrame({'기준':[0]})).mark_rule(color='gray').encode(y='기준:Q')
        st.altair_chart((scatter+zero).properties(height=400), width='stretch')
    with tabs[6]:
        st.subheader('운동별 처방과 체력 상태 상세')
        options = sorted(result.운동명.unique())
        exercise = st.selectbox('확인할 운동', options, index=options.index('달리기') if '달리기' in options else 0)
        detail = result.loc[result.운동명.eq(exercise)]
        st.dataframe(detail[['체력종목', '전체처방인원', '미달자내처방률(%)', '충족자내처방률(%)',
                             'Phi', 'Holm보정p값', '검정방법']], hide_index=True)
        st.caption('아래 표는 상관계수를 계산한 2×2 교차표의 인원입니다. 종목별 결측 제외로 전체 인원이 달라질 수 있습니다.')
        st.dataframe(detail[['체력종목', '미달_처방있음', '미달_처방없음', '충족_처방있음', '충족_처방없음']], hide_index=True)
    with tabs[7]:
        st.subheader('여러 미달 집단에 공통으로 나타나는 처방')
        st.caption('해당 운동이 몇 개 종목에서 양의 관련성을 보이는지 요약합니다. '
                   '같은 장병이 겹칠 수 있으며 여러 종목을 개선하는 효과를 뜻하지 않습니다.')
        patterns = related.assign(양의관련=related.Phi.gt(0), 양의유의=related.Phi.gt(0)&related.관련성확인).groupby('운동명').agg(
            양의관련종목수=('양의관련', 'sum'), 양의유의종목수=('양의유의', 'sum'),
            최대양의Phi=('Phi', 'max')).reset_index()
        patterns = patterns.loc[patterns.양의관련종목수.gt(0)].sort_values(
            ['양의유의종목수', '양의관련종목수', '최대양의Phi'], ascending=False).head(top)
        st.dataframe(patterns, hide_index=True)
    with tabs[8]:
        st.subheader('분석 범위와 데이터 품질 점검')
        quality = result.groupby('체력종목', sort=False).agg(
            평가가능인원=('평가가능인원','first'), 판정불가인원=('판정불가인원','first'),
            미달인원=('미달인원','first'), 상관계산가능운동수=('Phi','count'),
            보정후유의조합수=('관련성확인','sum')).reset_index()
        st.dataframe(quality, hide_index=True)
        st.caption('처방이 모두 없거나 모두 있는 운동 등 변수가 일정한 경우 상관계수를 계산할 수 없습니다. '
                   '모든 계산 가능한 운동×종목 조합에 Holm 보정을 적용합니다.')
        st.download_button('전체 분석 CSV 다운로드', result.to_csv(index=False).encode('utf-8-sig'),
                           file_name='3차_운동처방_대시보드_전체분석.csv', mime='text/csv')
        st.dataframe(result, hide_index=True)


if __name__ == '__main__':
    main()
