"""6번 화면: 전체 부상·종목별 등급 비교·개인 부상 이력입니다."""

import math
from html import escape

import altair as alt
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.py.injury_overview_data import filter_injuries_by_personnel, load_injury_overview
from dashboard.py.fitness_judgment import EVENTS, GRADE_LABELS
from dashboard.common.filters import render_personnel_cards
from dashboard.common.formatting import filter_signature

INJURY_LABELS = {
    'INJURY_ID': '부상 식별자',
    'SOLDIER_ID': '장병 식별자',
    'SOLDIER_NAME': '장병 이름',
    'UNIT_NAME': '부대',
    'RANK_NAME': '계급',
    'INJURY_CATEGORY': '부상 대분류',
    'INJURY_LOCATION': '부상 부위',
    'PREVENTABILITY': '예방 가능 여부',
    'SEVERITY': '심각도',
}
GROUP_MODAL_COLUMNS = [
    'INJURY_ID', 'SOLDIER_ID', 'SOLDIER_NAME', 'UNIT_NAME', 'RANK_NAME',
    'INJURY_LOCATION', 'PREVENTABILITY', 'SEVERITY',
]

SEVERITY_COLORS = {'경증': '#0F766E', '중등증': '#0891B2', '중증': '#2563EB', '(미상)': '#94A3B8'}
GROUP_COLUMNS = {'지역별': 'REGION_NAME', '부대별': 'UNIT_NAME', '계급별': 'RANK_NAME'}


def _style_injury_chart(chart):
    chart.update_layout(
        template='plotly_white',
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(color='#182B40'),
        legend=dict(font=dict(color='#182B40')),
        hoverlabel=dict(bgcolor='#FFFFFF', font=dict(color='#182B40')),
        margin=dict(l=12, r=20, t=24, b=12),
    )
    chart.update_traces(textfont_color='#182B40')
    chart.update_xaxes(
        tickfont_color='#182B40',
        title_font_color='#182B40',
        gridcolor='#E2E8F0',
        linecolor='#CBD5E1',
    )
    chart.update_yaxes(
        tickfont_color='#182B40',
        title_font_color='#182B40',
        gridcolor='#E2E8F0',
        linecolor='#CBD5E1',
    )
    return chart


def _render_injury_distributions(injuries: pd.DataFrame, people: pd.DataFrame) -> None:
    """필터된 부상 기록으로 부위·심각도·조직별 그래프를 표시합니다."""
    left, right = st.columns(2)
    chart_injuries = injuries.assign(
        INJURY_LOCATION=injuries['INJURY_LOCATION'].fillna('(미상)'),
        SEVERITY=injuries['SEVERITY'].astype('string').str.strip().fillna('(미상)'),
    )
    chart_scope_signature = filter_signature(tuple(injuries['INJURY_ID']))
    location_counts = (
        chart_injuries.groupby('INJURY_LOCATION', dropna=False)
        .size()
        .rename('건수')
        .reset_index()
        .rename(columns={'INJURY_LOCATION': '부위'})
        .sort_values('건수', ascending=False)
    )
    with left, st.container(border=True):
        st.subheader('부위별 부상 건수')
        chart = px.bar(
            location_counts,
            x='부위',
            y='건수',
            text='건수',
            custom_data=['부위'],
            color_discrete_sequence=['#0F766E'],
        )
        chart.update_traces(
            textposition='outside',
            textfont=dict(color='#18324B', size=12),
            cliponaxis=False,
        )
        chart.update_layout(
            margin=dict(l=48, r=20, t=24, b=76),
            yaxis=dict(rangemode='tozero', range=[0, location_counts['건수'].max() * 1.16]),
            xaxis=dict(tickangle=-25, automargin=True),
        )
        location_event = st.plotly_chart(
            _style_injury_chart(chart), width='stretch', theme=None,
            key=f'injury_location_distribution_{chart_scope_signature}',
            on_select=_activate_location_chart, selection_mode='points',
        )

    severity_counts = (
        chart_injuries.groupby('SEVERITY', dropna=False)
        .size()
        .rename('건수')
        .reset_index()
        .rename(columns={'SEVERITY': '심각도'})
    )
    severity_order = [*SEVERITY_COLORS]
    severity_order.extend(sorted(set(severity_counts['심각도']) - set(severity_order)))
    severity_sort = {value: index for index, value in enumerate(severity_order)}
    severity_counts['_정렬순서'] = severity_counts['심각도'].map(severity_sort)
    severity_counts = severity_counts.sort_values('_정렬순서').reset_index(drop=True)
    severity_counts['색상'] = severity_counts['심각도'].map(SEVERITY_COLORS).fillna('#94A3B8')
    severity_counts['비율'] = severity_counts['건수'] / severity_counts['건수'].sum() * 100
    severity_counts['_시작각'] = (
        severity_counts['건수'].cumsum() - severity_counts['건수']
    ) / severity_counts['건수'].sum() * math.tau
    severity_counts['_끝각'] = (
        severity_counts['건수'].cumsum() / severity_counts['건수'].sum() * math.tau
    )
    severity_counts['중심각'] = (
        severity_counts['건수'].cumsum() - severity_counts['건수'] / 2
    ) / severity_counts['건수'].sum() * math.tau
    severity_counts['표시'] = severity_counts.apply(
        lambda row: f"{row['심각도']}\n{row['비율']:.1f}%", axis=1,
    )
    with right, st.container(border=True):
        st.subheader('심각도별 부상 건수 비율')
        severity_selection = alt.selection_point(
            name='severity_click', fields=['심각도'], on='click', clear='dblclick', toggle=False,
        )
        legend_items = ''.join(
            '<span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;">'
            f'<i style="display:inline-block;width:11px;height:11px;border-radius:50%;background:{SEVERITY_COLORS.get(value, "#94A3B8")};"></i>'
            f'{escape(str(value))}</span>'
            for value in severity_order
        )
        st.markdown(
            '<div style="display:flex;justify-content:flex-end;flex-wrap:wrap;gap:12px;'
            'margin:0 8px 4px;color:#18324B;font-size:13px;">'
            f'<strong>심각도</strong>{legend_items}</div>',
            unsafe_allow_html=True,
        )
        donut = (
            alt.Chart(severity_counts)
            .mark_arc(innerRadius=68, outerRadius=205, stroke='#FFFFFF', strokeWidth=2)
            .encode(
                theta=alt.Theta(
                    '_시작각:Q',
                    scale=alt.Scale(domain=[0, math.tau], range=[0, math.tau]),
                    stack=None,
                ),
                theta2=alt.Theta2('_끝각:Q'),
                color=alt.Color('색상:N', scale=None, legend=None),
                tooltip=[
                    alt.Tooltip('심각도:N', title='심각도'),
                    alt.Tooltip('건수:Q', title='건수', format=','),
                    alt.Tooltip('비율:Q', title='비율', format='.1f'),
                ],
            )
            .add_params(severity_selection)
            .properties(height=450)
        )
        labels = (
            alt.Chart(severity_counts)
            .mark_text(
                radius=137,
                fontSize=14,
                fontWeight='bold',
                color='#FFFFFF',
                align='center',
                baseline='middle',
                lineBreak='\n',
            )
            .encode(
                theta=alt.Theta(
                    '중심각:Q',
                    scale=alt.Scale(domain=[0, math.tau], range=[0, math.tau]),
                    stack=None,
                ),
                text=alt.Text('표시:N'),
                tooltip=alt.Tooltip('비율:Q', title='비율', format='.1f'),
            )
        )
        severity_event = st.altair_chart(
            donut + labels,
            width='stretch',
            theme=None,
            key=f'injury_severity_distribution_{chart_scope_signature}',
            on_select=_activate_severity_chart,
        )

    active_chart = st.session_state.get('injury_chart_active_selection')
    modal_dismissed = st.session_state.get('injury_chart_modal_dismissed', False)
    location = _selected_chart_category(location_event, '부위') if active_chart == 'location' else None
    if location is not None:
        matching = chart_injuries.loc[chart_injuries['INJURY_LOCATION'].eq(location)]
        signature = filter_signature('location', chart_scope_signature, location, tuple(matching['INJURY_ID']))
        if not modal_dismissed and st.session_state.get('injury_chart_modal_dismissed_signature') != signature:
            named_records = matching.merge(
                people[['SOLDIER_ID', 'SOLDIER_NAME']],
                on='SOLDIER_ID', how='left', validate='many_to_one',
            )
            _show_injury_group_modal(f'부위: {location}', named_records, signature, chart_modal=True)

    severity = (
        _selected_altair_category(severity_event, 'severity_click', '심각도')
        if active_chart == 'severity' else None
    )
    if severity is not None:
        matching = chart_injuries.loc[chart_injuries['SEVERITY'].eq(severity)]
        signature = filter_signature('severity', chart_scope_signature, severity, tuple(matching['INJURY_ID']))
        if not modal_dismissed and st.session_state.get('injury_chart_modal_dismissed_signature') != signature:
            named_records = matching.merge(
                people[['SOLDIER_ID', 'SOLDIER_NAME']],
                on='SOLDIER_ID', how='left', validate='many_to_one',
            )
            _show_injury_group_modal(f'심각도: {severity}', named_records, signature, chart_modal=True)

    group_label = st.selectbox('부상 건수 비교 기준', list(GROUP_COLUMNS), key='injury_group_by')
    group_column = GROUP_COLUMNS[group_label]
    group_label_name = group_label.removesuffix('별')
    grouped_counts = (
        injuries.groupby(group_column, dropna=False)
        .size()
        .rename('부상 건수')
        .reset_index()
        .rename(columns={group_column: group_label_name})
        .sort_values('부상 건수', ascending=True)
    )
    with st.container(border=True):
        st.subheader(f'{group_label} 부상 건수')
        chart = px.bar(
            grouped_counts,
            x='부상 건수',
            y=group_label_name,
            orientation='h',
            text='부상 건수',
            color_discrete_sequence=['#2563EB'],
        )
        st.plotly_chart(_style_injury_chart(chart), width='stretch', theme=None)
    st.caption('분포 그래프는 부상 건수 기준입니다. 같은 장병의 반복 부상도 각각 포함됩니다.')


def _clear_injury_modal_dismissal() -> None:
    st.session_state['injury_modal_dismissed_signature'] = None


def _dismiss_injury_modal(signature: str) -> None:
    st.session_state['injury_modal_dismissed_signature'] = signature


def _activate_injury_chart(chart_name: str) -> None:
    st.session_state['injury_chart_active_selection'] = chart_name
    st.session_state['injury_chart_modal_dismissed'] = False
    st.session_state['injury_chart_modal_dismissed_signature'] = None


def _activate_location_chart() -> None:
    _activate_injury_chart('location')


def _activate_severity_chart() -> None:
    _activate_injury_chart('severity')


def _dismiss_injury_chart_modal(signature: str) -> None:
    st.session_state['injury_chart_modal_dismissed'] = True
    st.session_state['injury_chart_modal_dismissed_signature'] = signature


def _selected_chart_category(event, column: str) -> str | None:
    """Return the category value from the first selected Plotly point."""
    points = event.selection.points
    if not points:
        return None
    point = points[0]
    custom_data = point.get('customdata')
    if custom_data:
        return str(custom_data[0])
    fallback_key = 'label' if column == '심각도' else 'x'
    value = point.get(fallback_key)
    return str(value) if value is not None else None


def _selected_altair_category(event, selection_name: str, field: str) -> str | None:
    selected = event.selection.get(selection_name, [])
    if isinstance(selected, dict):
        value = selected.get(field)
    elif isinstance(selected, list) and selected:
        value = selected[-1].get(field) if isinstance(selected[-1], dict) else None
    else:
        value = None
    return str(value) if value is not None else None


def _show_injury_group_modal(
    title: str, injuries: pd.DataFrame, signature: str, chart_modal: bool = False,
) -> None:
    records = injuries.reindex(columns=GROUP_MODAL_COLUMNS).copy()
    if 'PREVENTABILITY' in records.columns:
        records['PREVENTABILITY'] = records['PREVENTABILITY'].map(
            {'Y': '가능', 'N': '불가능'}
        ).fillna('정보 없음')
    records = records.rename(columns=INJURY_LABELS)

    @st.dialog(
        f'{title} · 해당 부상 기록',
        width='large',
        on_dismiss=(
            (lambda: _dismiss_injury_chart_modal(signature))
            if chart_modal else (lambda: _dismiss_injury_modal(signature))
        ),
    )
    def _modal() -> None:
        people_count = injuries['SOLDIER_ID'].nunique() if 'SOLDIER_ID' in injuries else 0
        st.caption(f'인원 {people_count:,}명 · 부상 기록 {len(injuries):,}건')
        st.dataframe(records, hide_index=True, width='stretch')
        st.download_button(
            '부상 기록 CSV',
            records.to_csv(index=False).encode('utf-8-sig'),
            '선택한_부상_기록.csv',
            'text/csv',
            width='stretch',
        )

    _modal()


def _show_injury_history_modal(person: pd.Series, injuries: pd.DataFrame, signature: str) -> None:
    @st.dialog(
        f'{person.SOLDIER_NAME} · 개인 부상 이력',
        width='large',
        on_dismiss=lambda: _dismiss_injury_modal(signature),
    )
    def _modal() -> None:
        st.markdown(f'**{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}**')
        if injuries.empty:
            st.info('보유 부상 자료에서 해당 장병의 기록이 없습니다.')
        else:
            st.dataframe(injuries, hide_index=True, width='stretch')
            st.download_button(
                '개인 부상 기록 CSV',
                injuries.to_csv(index=False).encode('utf-8-sig'),
                f'{person.SOLDIER_ID}_부상이력.csv',
                'text/csv',
                width='stretch',
            )
        st.caption('발생일·회복 상태·운동 제한 항목은 원본에 없어 표시하지 않습니다.')

    _modal()


def _render_personnel_filter_cards(people: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """지역·부대·계급 카드를 표시하고 조건에 맞는 부상 기록을 반환합니다."""
    selection = render_personnel_cards(people, 'injury')
    filtered_injuries = filter_injuries_by_personnel(
        injuries,
        people,
        regions=selection.regions,
        ranks=selection.ranks,
    )
    return filtered_injuries.loc[selection.unit_mask(filtered_injuries)]


def render() -> None:
    """부상 기록 전체를 기준으로 현황과 개인 기록을 표시합니다."""
    st.caption('장병 체력관리 / 06')
    st.title('부상 현황')
    st.write('부상 인원과 건수를 구분하고, 체력등급에 따른 분포와 개인별 기록을 확인합니다.')
    try:
        people,grades,summary,metadata,injuries=load_injury_overview()
    except FileNotFoundError:
        st.warning('분석 결과 또는 원본 파일이 없습니다. 아래 명령으로 생성하세요.')
        st.code('python -m data.scripts.analysis.analysis2.injury_overview',language='powershell');st.stop()
    except (ValueError,KeyError,pd.errors.EmptyDataError) as error:
        st.error(f'자료를 확인해 주세요: {error}');st.stop()
    if summary.empty:
        st.info('표시할 집계 자료가 없습니다.');st.stop()
    st.info('합성 부상 자료 · 발생일이 없어 전체 보유 기록을 집계합니다. 최신 체력등급과의 비교이며 실제 부상 위험을 입증하는 결과가 아닙니다.')
    row=summary.iloc[0]
    values=[f'{int(row["전체장병수"]):,}명',f'{int(row["부상인원"]):,}명',f'{int(row["부상건수"]):,}건',
            f'{row["부상자비율"]:.1f}%' if pd.notna(row['부상자비율']) else '해당 없음',f'{int(row["반복부상인원"]):,}명']
    for col,label,value in zip(st.columns(5),['전체 장병 수','부상 기록 보유 인원','부상 건수','부상자 비율','2건 이상 부상 기록'],values):
        col.metric(label,value,border=True)
    st.caption('전체 장병 명단이 분모입니다. 한 장병에게 부상이 여러 건 있어도 부상 인원은 1명입니다.')
    overall,comparison,individual=st.tabs(['전체 부상 분포','체력등급별 비교','개인별 부상 이력'])
    with overall:
        if injuries.empty:
            st.info('부상 파일에 기록이 없습니다.')
        else:
            st.caption('지역·부대·계급 카드 선택은 아래 분포 그래프에 적용됩니다. 상단 요약 지표는 전체 자료 기준입니다.')
            filtered_injuries = _render_personnel_filter_cards(people, injuries)
            st.caption(f'선택 조건에 해당하는 부상 기록 {len(filtered_injuries):,}건')
            if filtered_injuries.empty:
                st.info('선택한 지역·부대·계급 조건에 해당하는 부상 기록이 없습니다.')
            else:
                _render_injury_distributions(filtered_injuries, people)
    with comparison:
        event=st.selectbox('비교할 체력 종목',list(EVENTS),format_func=lambda key:EVENTS[key][0])
        grade_table=grades.loc[grades['종목'].eq(EVENTS[event][0])]
        left,right=st.columns(2)
        with left:
            chart=px.bar(grade_table,x='등급',y='부상자비율',text='부상자비율',
                category_orders={'등급':list(GRADE_LABELS.values())},hover_data=['전체인원','부상인원','부상건수'],color_discrete_sequence=['#2563eb'])
            chart.update_traces(texttemplate='%{text:.1f}%')
            chart.update_layout(yaxis_range=[0,100],yaxis_title='부상자 비율 (%)',title='최신 종목 등급별 부상자 비율')
            st.plotly_chart(_style_injury_chart(chart),width='stretch',theme=None)
        with right:
            st.dataframe(grade_table.drop(columns='종목'),hide_index=True,width='stretch',
                column_config={'부상자비율':st.column_config.NumberColumn(format='%.1f%%')})
        st.caption('분모: 각 등급의 전체 장병 수. 0명인 등급의 비율은 계산하지 않습니다. 종합등급이 아닌 종목별 등급이며 판정 불가 집단도 별도 표시합니다.')
        st.download_button('등급별 부상 집계 CSV',grade_table.to_csv(index=False).encode('utf-8-sig'),'체력등급별_부상현황.csv','text/csv')
    with individual:
        left,right=st.columns(2)
        search=left.text_input('이름·장병번호 검색')
        condition=right.selectbox('부상 기록',['전체','기록 있음','2건 이상','기록 없음'])
        shown=people.copy()
        if search:
            shown=shown.loc[shown.SOLDIER_NAME.str.contains(search,regex=False)|shown.SOLDIER_ID.str.contains(search,regex=False)]
        if condition=='기록 있음':
            shown=shown.loc[shown.INJURY_COUNT.gt(0)]
        elif condition=='2건 이상':
            shown=shown.loc[shown.INJURY_COUNT.ge(2)]
        elif condition=='기록 없음':
            shown=shown.loc[shown.INJURY_COUNT.eq(0)]
        cols=['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME','INJURY_COUNT']
        display=shown[cols].rename(columns={'SOLDIER_ID':'장병 식별자','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속','INJURY_COUNT':'부상 건수'})
        st.caption(f'조회 결과 {len(shown):,}명 · 신상 정보는 합성 자료입니다.')
        table_key = f"injury_personnel_table_{filter_signature(tuple(shown['SOLDIER_ID']))}"
        table_event = st.dataframe(
            display,
            hide_index=True,
            width='stretch',
            on_select=_clear_injury_modal_dismissal,
            selection_mode='single-row',
            key=table_key,
        )
        if shown.empty:
            st.info('검색 조건에 해당하는 장병이 없습니다.')
        else:
            selected_rows = table_event.selection.rows
            if selected_rows and 0 <= selected_rows[0] < len(shown):
                person = shown.iloc[selected_rows[0]]
                modal_signature = filter_signature(table_key, person.SOLDIER_ID)
                if st.session_state.get('injury_modal_dismissed_signature') != modal_signature:
                    records = injuries.loc[injuries.SOLDIER_ID.eq(person.SOLDIER_ID)].rename(columns=INJURY_LABELS).copy()
                    if not records.empty:
                        records['예방 가능 여부'] = records['예방 가능 여부'].map({'Y': '가능', 'N': '불가능'}).fillna('정보 없음')
                    _show_injury_history_modal(person, records, modal_signature)
    with st.expander('집계 기준·자료 출처'):
        for key in ['집계범위','등급','기간','합성','중복']:
            st.write(metadata[key])
        st.caption('분석 생성일: '+metadata['생성일시'])
