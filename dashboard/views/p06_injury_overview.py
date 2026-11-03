"""6번 화면: 전체 부상·종목별 등급 비교·개인 부상 이력입니다."""

from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.py import queries
from dashboard.py.injury_overview_data import injury_grade_table, injury_metadata, injury_people
from dashboard.py.fitness_judgment import EVENTS, GRADE_LABELS
from dashboard.common.filters import render_personnel_cards
from dashboard.common.formatting import filter_signature, format_timestamp
from dashboard.common.charts import NAVY_BORDER, apply_chart_layout, make_bar
from dashboard.common.chart_widgets import PieChartWidget
from dashboard.common.overview_widgets import render_metric_cards
from dashboard.common.table_widgets import render_dataframe

INJURY_LABELS = {
    'INJURY_ID': '부상 식별자',
    'SOLDIER_ID': '군번',
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

SEVERITY_COLORS = {'경증': '#0F766E', '중등증': '#0891B2', '중증': '#2563EB', '미상': '#94A3B8'}
GROUP_COLUMNS = {'지역별': 'REGION_NAME', '부대별': 'UNIT_NAME', '계급별': 'RANK_NAME'}


def _style_injury_chart(chart):
    apply_chart_layout(
        chart,
        height=450,
        margin=dict(l=12, r=20, t=24, b=12),
        xaxis=dict(linecolor=NAVY_BORDER),
        yaxis=dict(linecolor=NAVY_BORDER),
    )
    return chart


def _render_injury_distributions(
    distribution: pd.DataFrame, units: list[tuple[str, str]], ranks: list[str],
) -> None:
    """필터를 건 부상 건수 집계(queries.load_injury_distribution)로 부위·심각도·조직별 그래프를 표시합니다.

    막대·조각을 클릭하면 그때만 해당 부상 기록을 같은 필터로 조회합니다(queries.load_injury_records).
    """
    left, right = st.columns(2)
    chart_scope_signature = filter_signature(tuple(units), tuple(ranks))
    location_counts = (
        queries.distribution_counts(distribution, 'INJURY_LOCATION')
        .rename(columns={'INJURY_LOCATION': '부위', 'INJURIES': '건수'})
        .sort_values('건수', ascending=False)
    )
    location_counts['부위'] = location_counts['부위'].replace('미지정', '미상')
    with left, st.container(border=True):
        st.subheader('부위별 부상 건수')
        chart = make_bar(
            location_counts,
            x='부위',
            y='건수',
            text='건수',
            custom_data=['부위'],
            color_discrete_sequence=['#0F766E'],
        )
        chart.update_traces(
            textposition='top center',
            textfont=dict(color='#18324B', size=12),
            cliponaxis=False,
            selector={'mode': 'text'},
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
        queries.distribution_counts(distribution, 'SEVERITY')
        .rename(columns={'SEVERITY': '심각도', 'INJURIES': '건수'})
        .sort_values('심각도', kind='stable')
    )
    severity_counts['심각도'] = severity_counts['심각도'].replace({'(미상)': '미상', '미지정': '미상'})
    severity_order = [*SEVERITY_COLORS]
    severity_order.extend(sorted(set(severity_counts['심각도']) - set(severity_order)))
    severity_sort = {value: index for index, value in enumerate(severity_order)}
    severity_counts['_정렬순서'] = severity_counts['심각도'].map(severity_sort)
    severity_counts = severity_counts.sort_values('_정렬순서').reset_index(drop=True)
    severity_counts['색상'] = severity_counts['심각도'].map(SEVERITY_COLORS).fillna('#94A3B8')
    severity_counts['비율'] = severity_counts['건수'] / severity_counts['건수'].sum() * 100
    with right, st.container(border=True):
        st.subheader('심각도별 부상 건수 비율')
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
        severity_figure = PieChartWidget(
            data=severity_counts,
            names='심각도',
            values='건수',
            colors=severity_counts['색상'].tolist(),
            center_text=f"{int(severity_counts['건수'].sum()):,}건",
            height=450,
            show_percent=True,
        ).build_figure()
        severity_event = st.plotly_chart(
            severity_figure,
            width='stretch',
            theme=None,
            config={'displayModeBar': False},
            key=f'injury_severity_distribution_{chart_scope_signature}',
            on_select=_activate_severity_chart,
            selection_mode='points',
        )

    active_chart = st.session_state.get('injury_chart_active_selection')
    modal_dismissed = st.session_state.get('injury_chart_modal_dismissed', False)
    location = _selected_chart_category(location_event, '부위') if active_chart == 'location' else None
    if location is not None:
        signature = filter_signature('location', chart_scope_signature, location)
        if not modal_dismissed and st.session_state.get('injury_chart_modal_dismissed_signature') != signature:
            records = queries.load_injury_records(units, ranks, location=location)
            _show_injury_group_modal(f'부위: {location}', records, signature, chart_modal=True)

    severity = _selected_chart_category(severity_event, '심각도') if active_chart == 'severity' else None
    if severity is not None:
        signature = filter_signature('severity', chart_scope_signature, severity)
        if not modal_dismissed and st.session_state.get('injury_chart_modal_dismissed_signature') != signature:
            records = queries.load_injury_records(units, ranks, severity=severity)
            _show_injury_group_modal(f'심각도: {severity}', records, signature, chart_modal=True)

    group_label = st.selectbox('부상 건수 비교 기준', list(GROUP_COLUMNS), key='injury_group_by')
    group_column = GROUP_COLUMNS[group_label]
    group_label_name = group_label.removesuffix('별')
    grouped_counts = (
        queries.distribution_counts(distribution, group_column)
        .rename(columns={group_column: group_label_name, 'INJURIES': '부상 건수'})
        .sort_values([group_label_name], kind='stable')
        .sort_values('부상 건수', ascending=True, kind='stable')
    )
    with st.container(border=True):
        st.subheader(f'{group_label} 부상 건수')
        chart = make_bar(
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
        render_dataframe(records, hide_index=True, width='stretch')
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
            render_dataframe(injuries, hide_index=True, width='stretch')
            st.download_button(
                '개인 부상 기록 CSV',
                injuries.to_csv(index=False).encode('utf-8-sig'),
                f'{person.SOLDIER_ID}_부상이력.csv',
                'text/csv',
                width='stretch',
            )
        st.caption('발생일·회복 상태·운동 제한 항목은 원본에 없어 표시하지 않습니다.')

    _modal()


def render() -> None:
    """부상 기록 전체를 기준으로 현황과 개인 기록을 표시합니다."""
    st.caption('장병 체력관리 / 06')
    st.title('부상 현황')
    st.write('부상 인원과 건수를 구분하고, 체력등급에 따른 분포와 개인별 기록을 확인합니다.')
    try:
        summary=queries.load_injury_summary()
        people=injury_people()
    except (ValueError,KeyError,SQLAlchemyError) as error:
        st.error(f'자료를 확인해 주세요: {error}');st.stop()
    st.info('합성 부상 자료 · 발생일이 없어 전체 보유 기록을 집계합니다. 최신 체력등급과의 비교이며 실제 부상 위험을 입증하는 결과가 아닙니다.')
    total=int(summary.TOTAL_SOLDIERS)
    injured=int(summary.INJURED_SOLDIERS)
    values=[f'{total:,}명',f'{injured:,}명',f'{int(summary.INJURIES):,}건',
            f'{injured/total*100:.1f}%' if total else '해당 없음',f'{int(summary.REPEATED_SOLDIERS):,}명']
    render_metric_cards(
        list(zip(
            ['total', 'injured', 'injuries', 'injured_rate', 'repeated'],
            ['전체 장병 수','부상 기록 보유 인원','부상 건수','부상자 비율','2건 이상 부상 기록'],
            values,
        )),
        container_key=None,
        key_prefix='injury_overview_card',
        clickable=False,
        clickable_keys=set(),
        scope_signature='',
        help_text='',
    )
    st.caption('전체 장병 명단이 분모입니다. 한 장병에게 부상이 여러 건 있어도 부상 인원은 1명입니다.')
    overall,comparison,individual=st.tabs(['전체 부상 분포','체력등급별 비교','개인별 부상 이력'])
    with overall:
        if int(summary.INJURIES)==0:
            st.info('부상 기록이 없습니다.')
        else:
            st.caption('지역·부대·계급 카드 선택은 아래 분포 그래프에 적용됩니다. 상단 요약 지표는 전체 자료 기준입니다.')
            selection = render_personnel_cards(people, 'injury')
            distribution = queries.load_injury_distribution(selection.units, selection.ranks)
            filtered_total = queries.distribution_counts(distribution, None)
            st.caption(f'선택 조건에 해당하는 부상 기록 {filtered_total:,}건')
            if filtered_total == 0:
                st.info('선택한 지역·부대·계급 조건에 해당하는 부상 기록이 없습니다.')
            else:
                _render_injury_distributions(distribution, selection.units, selection.ranks)
    with comparison:
        event=st.selectbox('비교할 체력 종목',list(EVENTS),format_func=lambda key:EVENTS[key][0])
        grade_table=injury_grade_table().loc[lambda table: table['종목'].eq(EVENTS[event][0])]
        left,right=st.columns(2)
        with left:
            chart=make_bar(grade_table,x='등급',y='부상자비율',text='부상자비율',
                category_orders={'등급':list(GRADE_LABELS.values())},hover_data=['전체인원','부상인원','부상건수'],color_discrete_sequence=['#2563eb'])
            chart.update_traces(
                texttemplate='%{text:.1f}%',
                selector={'mode': 'text'},
            )
            chart.update_layout(yaxis_range=[0,100],yaxis_title='부상자 비율 (%)',title='최신 종목 등급별 부상자 비율')
            st.plotly_chart(_style_injury_chart(chart),width='stretch',theme=None)
        with right:
            render_dataframe(grade_table.drop(columns='종목'),hide_index=True,width='stretch',
                column_config={'부상자비율':st.column_config.NumberColumn(format='%.1f%%')})
        st.caption('분모: 각 등급의 전체 장병 수. 0명인 등급의 비율은 계산하지 않습니다. 종합등급이 아닌 종목별 등급이며 판정 불가 집단도 별도 표시합니다.')
        st.download_button('등급별 부상 집계 다운로드(CSV)',grade_table.to_csv(index=False).encode('utf-8-sig'),'체력등급별_부상현황.csv','text/csv')
    with individual:
        left,right=st.columns(2)
        search=left.text_input('이름 또는 군번으로 검색')
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
        display=shown[cols].rename(columns={'SOLDIER_ID':'군번','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속','INJURY_COUNT':'부상 건수'})
        st.caption(f'조회 결과 {len(shown):,}명 · 신상 정보는 합성 자료입니다.')
        table_key = f"injury_personnel_table_{filter_signature(tuple(shown['SOLDIER_ID']))}"
        table_event = render_dataframe(
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
                    records = queries.load_soldier_injuries(person.SOLDIER_ID).rename(columns=INJURY_LABELS)
                    if not records.empty:
                        records['예방 가능 여부'] = records['예방 가능 여부'].map({'Y': '가능', 'N': '불가능'}).fillna('정보 없음')
                    _show_injury_history_modal(person, records, modal_signature)
    with st.expander('집계 기준·자료 출처'):
        metadata=injury_metadata()
        st.write('장병 명단 전체와, 보유한 부상 기록을 집계합니다.')
        st.write('부상자 비율은 (부상 기록이 1건 이상 있는 장병 수) / (집단 전체 인원)을 백분율로 나타낸 것입니다.')
        st.write('부상 발생일이 없어 기간별 집계는 하지 않습니다.')
        st.write('부상 기록 데이터는 BMI와 심폐지구력을 기반으로 부상 발생률을 추정한 뒤 합성하였습니다. 이에 등급별 차이를 실제 부상 위험이나 인과관계로 해석하지 않았습니다.')
        st.caption('분석 생성일: '+format_timestamp(metadata['생성일시']))
