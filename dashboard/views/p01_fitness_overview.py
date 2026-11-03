"""1번 화면: 분석 결과 기반 전체 장병 체력 현황입니다."""

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.common.charts import (
    CHART_PALETTE,
    apply_chart_layout,
    make_bar,
    make_line,
    show_plotly,
)
from dashboard.common.filters import render_personnel_cards
from dashboard.common.formatting import filter_signature, format_timestamp
from dashboard.common.overview_widgets import render_metric_cards, render_paged_plotly_chart
from dashboard.common.table_widgets import render_dataframe
from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS
from dashboard.py.fitness_overview_data import combine_events, combine_rounds, load_group_summary, load_overview

_combine_rounds = combine_rounds
_combine_events = combine_events

EVENT_ORDER = ['근력','근지구력','심폐지구력','유연성']
GRADE_ORDER = ['1등급', '2등급', '3등급', '3등급 미만']
GRADE_PALETTE = [
    "#14B8A6",
    "#7DD3FC",
    "#3B82F6",
    "#F87171",
]




def _change_comparison_page(page_key: str, offset: int, page_count: int) -> None:
    """비교 페이지를 갱신해 Streamlit 재실행부터 새 페이지를 표시합니다."""
    current_page = int(st.session_state.get(page_key, 0))
    st.session_state[page_key] = min(max(current_page + offset, 0), page_count - 1)


def _people_for_metric(
    metric: str,
    round_number: int,
    unit_name: str,
    soldier_ids: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """부대 카드에 해당하는 장병(전체는 장병별 최신 회차, 나머지는 선택 회차의 판정 행)을 돌려줍니다."""
    judged = queries.load_unit_judgments(unit_name)
    if soldier_ids is not None:
        judged = judged.loc[judged['SOLDIER_ID'].isin(soldier_ids)]
    if metric == 'total':
        # 회차 순으로 정렬돼 있으므로 마지막 행이 최신 측정이다(측정이 없는 장병은 판정 칸이 빈 1행).
        return judged.drop_duplicates('SOLDIER_ID', keep='last')
    current = judged.loc[judged['ROUND'].eq(round_number)]
    if metric == 'measured':
        return current
    if metric == 'deficient':
        return current.loc[current['FAIL_COUNT'].ge(1)]
    if metric == 'managed':
        return current.loc[current['MANAGED'].astype(bool)]
    raise ValueError(f'지원하지 않는 카드 구분입니다: {metric}')


def _round_change_chart(scope: pd.DataFrame):
    counts = scope.melt(
        id_vars=['회차'],
        value_vars=['측정인원', '미달인원', '관리대상인원'],
        var_name='구분',
        value_name='인원',
    )
    counts['회차 표시'] = counts['회차'].map(lambda value: f'{int(value)}차')
    round_order = [f'{int(value)}차' for value in sorted(scope['회차'].unique())]
    chart = make_bar(
        counts,
        x='회차 표시',
        y='인원',
        color='구분',
        barmode='group',
        category_orders={'회차 표시': round_order},
        color_discrete_sequence=list(CHART_PALETTE),
        labels={'회차 표시': '측정 회차', '인원': '인원'},
    )
    apply_chart_layout(chart, height=300)
    return chart


def _show_metric_people(title: str, people: pd.DataFrame, signature: str) -> None:
    display = people.copy()

    def failed_events(row: pd.Series) -> str:
        if pd.isna(row['ROUND']):
            return '측정 없음'
        failed = [
            label for event, (label, _) in EVENTS.items()
            if pd.notna(row[f'{event}_GRADE']) and row[f'{event}_GRADE'] == 0
        ]
        return ', '.join(failed) if failed else '없음'

    display['미달 종목'] = display.apply(failed_events, axis=1)
    table = display.reindex(columns=[
        'SOLDIER_ID', 'SOLDIER_NAME', 'RANK_NAME', 'AGE', '미달 종목', 'MANAGED',
    ]).rename(columns={
        'SOLDIER_ID': '군번', 'SOLDIER_NAME': '이름', 'RANK_NAME': '계급',
        'AGE': '나이', 'MANAGED': '집중관리 대상',
    })

    @st.dialog(title, width='large')
    def _modal() -> None:
        st.caption(f'해당 장병 {len(table):,}명')
        if table.empty:
            st.info('해당 조건의 장병이 없습니다.')
        else:
            render_dataframe(
                table, hide_index=True, width='stretch',
                column_config={'집중관리 대상': st.column_config.CheckboxColumn()},
            )
            st.download_button(
                '장병 명단 CSV', table.to_csv(index=False).encode('utf-8-sig'),
                f'{signature}_장병명단.csv', 'text/csv', width='stretch',
            )

    _modal()


def render() -> None:
    """전체 지표·종목 통계·등급 분포·회차별 추이를 표시합니다."""
    # st.caption('장병 체력관리 / 01')
    st.title('전체 체력 현황')
    st.write('선택한 조회 범위의 체력 수준과 미달 추이를 확인합니다.')
    try:
        roster = queries.load_roster()
    except (ValueError, KeyError, SQLAlchemyError) as error:
        st.error(f'장병 명단을 불러오지 못했습니다: {error}')
        st.stop()
    selection = render_personnel_cards(roster, 'fitness_overview')
    if selection.scoped.empty:
        st.info('선택한 지역·부대·계급 조건에 해당하는 장병이 없습니다.')
        st.stop()

    selected_soldier_ids = tuple(selection.scoped['SOLDIER_ID'].astype(str))
    soldier_ids = (
        selected_soldier_ids
        if len(selection.scoped) != len(roster)
        else None
    )
    try:
        rounds, events, metadata = load_overview(soldier_ids)
        all_comparison_rounds = pd.DataFrame()
        all_comparison_events = pd.DataFrame()
        if soldier_ids is not None:
            all_comparison_rounds, all_comparison_events = load_group_summary(
                'UNIT_NAME',
                soldier_ids,
            )
    except (ValueError, KeyError, SQLAlchemyError) as error:
        st.error(f'분석 결과를 확인해 주세요: {error}')
        st.stop()
    if rounds.empty:
        st.info('선택한 조건에 표시할 분석 자료가 없습니다.')
        st.stop()
    choices = sorted(rounds['회차'].unique())
    number = st.radio(
        '측정 회차',
        choices,
        index=len(choices) - 1,
        horizontal=True,
        format_func=lambda value: f'{value}차',
        key='fitness_overview_round',
    )
    scope = rounds
    scoped_events = events
    selected_units = st.session_state.get('fitness_overview_card_units', [])
    unit_selected = len(selected_units) == 1
    selected_unit = selected_units[0][1] if unit_selected else None
    row = scope.loc[scope['회차'].eq(number)].iloc[0]
    selected = scoped_events.loc[scoped_events['회차'].eq(number)]
    title_scope = '선택한 조회 범위' if soldier_ids is not None else '전체 장병'
    st.subheader(f'{title_scope} · {number}차')
    st.caption(
        f'조회 범위: 지역·부대·계급 기본 필터 · '
        f'{selection.scoped.SOLDIER_ID.nunique():,}명'
        if soldier_ids is not None else
        f'조회 범위: 전체 장병 · {len(roster):,}명'
    )
    scope_signature = filter_signature(
        tuple(selected_soldier_ids) if soldier_ids is not None else 'all',
        number,
    )
    metrics = [
        ('total', '전체 장병 수', f'{int(row["전체장병수"]):,}명'),
        ('measured', '측정 인원', f'{int(row["측정인원"]):,}명'),
        ('deficient', '미달 인원', f'{int(row["미달인원"]):,}명'),
        ('managed', '집중관리 대상', f'{int(row["관리대상인원"]):,}명'),
        ('rate', '미달 비율', f'{row["미달률"]:.1f}%' if pd.notna(row['미달률']) else '판정 불가'),
    ]
    clicked_metric = render_metric_cards(
        metrics,
        container_key='fitness-overview-summary-cards',
        key_prefix='fitness_overview_card',
        clickable=unit_selected,
        clickable_keys={'total', 'measured', 'deficient', 'managed'},
        scope_signature=scope_signature,
        help_text='카드에 해당하는 장병 명단 보기',
    )
    if unit_selected:
        st.caption('부대를 선택한 상태에서 네 가지 요약 카드를 클릭하면 해당 장병 명단을 확인할 수 있습니다.')
    if clicked_metric:
        people = _people_for_metric(
            clicked_metric,
            int(number),
            selected_unit,
            selected_soldier_ids if soldier_ids is not None else None,
        )
        metric_label = next(label for key, label, _ in metrics if key == clicked_metric)
        modal_title = f'{selected_unit} · {number}차 · {metric_label}'
        if clicked_metric == 'total':
            modal_title = f'{selected_unit} · 전체 장병 수'
        _show_metric_people(modal_title, people, f'{scope_signature}_{clicked_metric}')
    st.caption('전체 미달률은 측정 인원 중 1종목 이상 미달한 인원의 비율입니다.')
    if row['측정인원']==0:
        st.info('선택한 조건에서 측정한 장병이 없습니다.')
    left,right=st.columns(2)
    with left,st.container(border=True):
        st.subheader('종목별 미달률')
        chart=make_bar(
            selected, x='종목', y='미달률', text='미달률', color='종목',
            category_orders={'종목': EVENT_ORDER},
            hover_data=['미달인원', '측정인원'],
            color_discrete_sequence=list(CHART_PALETTE),
        )
        chart.update_traces(
            texttemplate='%{text:.1f}%',
            textposition='top center',
            cliponaxis=False,
            selector={'mode': 'text'},
        )
        visible_rates = selected['미달률'].dropna()
        if visible_rates.empty:
            yaxis_range = [0, 100]
        else:
            rate_min, rate_max = float(visible_rates.min()), float(visible_rates.max())
            padding = max((rate_max - rate_min) * 0.35, 2.0)
            yaxis_range = [max(0.0, rate_min - padding), min(100.0, rate_max + padding)]
            if yaxis_range[0] == yaxis_range[1]:
                yaxis_range = [max(0.0, rate_min - 2.0), min(100.0, rate_max + 2.0)]
        chart.update_layout(
            yaxis_title='미달률 (%)', yaxis_range=yaxis_range, showlegend=False,
            xaxis={'categoryorder': 'array', 'categoryarray': EVENT_ORDER},
        )
        apply_chart_layout(chart, height=300, margin={'l': 55, 'r': 20, 't': 32, 'b': 45})
        st.caption('선택 회차의 미달률 범위를 확대해 막대 간 차이를 표시합니다.')
        show_plotly(chart)
    with right,st.container(border=True):
        st.subheader('종목별 등급 분포')
        grade_columns=['1등급인원','2등급인원','3등급인원','미달인원']
        distribution=selected.melt(id_vars=['종목'],value_vars=grade_columns,var_name='등급',value_name='인원')
        distribution['등급']=distribution['등급'].replace({'1등급인원':'1등급','2등급인원':'2등급','3등급인원':'3등급','미달인원':'3등급 미만'})
        chart=make_bar(distribution,x='종목',y='인원',color='등급',barmode='stack',category_orders={'종목':EVENT_ORDER,'등급':GRADE_ORDER},
            color_discrete_sequence=GRADE_PALETTE)
        apply_chart_layout(chart, height=300)
        show_plotly(chart)
    st.subheader('종목별 측정 수준')
    st.caption('단위가 다른 종목의 평균은 하나의 축에서 비교하지 않습니다. 평균은 유효 측정값 기준이며, 등급 판정은 연령 기준까지 적용합니다.')
    for col,event in zip(st.columns(4),EVENT_ORDER):
        record=selected.loc[selected['종목'].eq(event)].iloc[0]
        value=f'{record["평균"]:.2f} {record["단위"]}' if pd.notna(record['평균']) else '측정 없음'
        col.metric(event,value,border=True)
    st.subheader('회차별 변화')
    tab1,tab2=st.tabs(['측정·미달 인원','종목별 미달률'])
    with tab1:
        show_plotly(_round_change_chart(scope))
    with tab2:
        compare_groups = (
            soldier_ids is not None
            and not all_comparison_rounds.empty
            and all_comparison_rounds['그룹'].nunique() > 1
        )
        group_label = '부대'
        trend = all_comparison_events.copy() if compare_groups else scoped_events.copy()
        selected_groups = []
        trend_page = 0
        trend_page_count = 1
        if compare_groups:
            latest_round = all_comparison_rounds['회차'].max()
            ranked_groups = (
                all_comparison_rounds.loc[all_comparison_rounds['회차'].eq(latest_round)]
                .sort_values('미달률', ascending=False, na_position='last')['그룹']
                .drop_duplicates().tolist()
            )
            available_groups = [
                *ranked_groups,
                *sorted(set(trend['그룹'].dropna()) - set(ranked_groups)),
            ]
            selected_groups = available_groups
            trend_page_size = 5
            trend_page_count = max(1, (len(selected_groups) + trend_page_size - 1) // trend_page_size)
            trend_page_key = (
                f"fitness_trend_page_{filter_signature(scope_signature, tuple(selected_groups))}"
            )
            trend_page = min(max(int(st.session_state.get(trend_page_key, 0)), 0), trend_page_count - 1)
            trend_start = trend_page * trend_page_size
            visible_trend_groups = selected_groups[trend_start:trend_start + trend_page_size]
            trend = trend.loc[trend['그룹'].isin(visible_trend_groups)]
            st.caption(f'선택한 {group_label} {len(selected_groups)}개 · 범례를 클릭하면 선을 숨기거나 다시 표시할 수 있습니다.')

        event_tabs = st.tabs(EVENT_ORDER)
        for event, event_tab in zip(EVENT_ORDER, event_tabs):
            with event_tab:
                event_trend = trend.loc[trend['종목'].eq(event)]
                if event_trend.empty:
                    st.info('선택한 조건에 표시할 미달률 자료가 없습니다.')
                    continue
                if compare_groups:
                    chart = make_line(
                        event_trend, x='회차', y='미달률', color='그룹', line_group='그룹',
                        markers=True,
                        labels={'그룹': group_label, '회차': '회차', '미달률': '미달률 (%)',
                                '미달인원': '미달 인원', '측정인원': '측정 인원'},
                        hover_data={'그룹': True, '회차': True, '미달률': ':.1f',
                                    '미달인원': ':,d', '측정인원': ':,d'},
                    )
                    chart.update_traces(line={'width': 2}, marker={'size': 7})
                else:
                    chart = make_line(
                        event_trend, x='회차', y='미달률', markers=True,
                        labels={'회차': '회차', '미달률': '미달률 (%)',
                                '미달인원': '미달 인원', '측정인원': '측정 인원'},
                        hover_data={'회차': True, '미달률': ':.1f',
                                    '미달인원': ':,d', '측정인원': ':,d'},
                    )
                    chart.update_traces(line={'width': 3}, marker={'size': 8})
                visible_rates = event_trend['미달률'].dropna()
                if visible_rates.empty:
                    yaxis_range = [0, 100]
                else:
                    rate_min = float(visible_rates.min())
                    rate_max = float(visible_rates.max())
                    padding = max((rate_max - rate_min) * 0.15, 1.0)
                    yaxis_range = [
                        max(0.0, rate_min - padding),
                        min(100.0, rate_max + padding),
                    ]
                    if yaxis_range[0] == yaxis_range[1]:
                        yaxis_range = [max(0.0, rate_min - 1.0), min(100.0, rate_max + 1.0)]
                chart.update_layout(
                    title=f'{event} 미달률 추이',
                    xaxis_title='측정 회차', yaxis_title='미달률 (%)',
                    yaxis_range=yaxis_range, xaxis_dtick=1, hovermode='closest',
                    legend={'title': group_label, 'itemclick': 'toggle', 'itemdoubleclick': 'toggleothers'},
                )
                apply_chart_layout(chart, height=430, margin={'l': 55, 'r': 24, 't': 55, 'b': 45})
                if compare_groups:
                    render_paged_plotly_chart(
                        chart,
                        page=trend_page,
                        page_count=trend_page_count,
                        page_key=f'{trend_page_key}_{event}',
                        caption=(
                            f'추이 그룹 {trend_page + 1} / {trend_page_count} · '
                            f'{len(visible_trend_groups)}개 표시'
                        ),
                        on_page_change=_change_comparison_page,
                    )
                else:
                    show_plotly(chart)
    st.caption('회차는 개인별 날짜순 측정 순서입니다. 같은 달력 기간을 뜻하지 않으며, 3회 이상 측정 인원의 데이터로 전체 지표와 다를 수 있습니다.')
    with st.expander('집계표 및 CSV 다운로드'):
        render_dataframe(scope,hide_index=True,width='stretch')
        render_dataframe(selected.drop(columns=['회차']),hide_index=True,width='stretch')
        st.download_button('회차별 집계 다운로드',scope.to_csv(index=False).encode('utf-8-sig'),'회차별_체력현황.csv','text/csv')
        st.download_button('선택 회차 종목별 집계 다운로드',selected.to_csv(index=False).encode('utf-8-sig'),'종목별_체력현황.csv','text/csv')
    with st.expander('자료·판정·관리 대상 기준'):
        st.write('측정 당시의 데이터에 국민체력100의 19~24세 남성 등급표를 적용하여 판정합니다.')
        st.write('''
집중 관리 대상은 다음 조건 중 하나 이상 해당되는 인원입니다.
- BMI가 25 이상이면서 근력 또는 심폐지구력이 3등급 미만인 인원
- 선택한 회차들 중 미달 회차가 2개 이상인 인원
- 1회차 측정에 비해 미달 종목 수가 늘어난 인원
- 동일 종목에서 3회 연속 미달한 인원
''')
        st.write('전체 장병 기준으로 부대를 구분하지 않고 표기했습니다.')
        st.caption('현재 집계에는 위 지역·부대·계급 카드 필터가 적용됩니다.')
        st.write(f'측정 기간: {metadata["측정시작"]} ~ {metadata["측정종료"]}')
        st.caption('분석 생성일: '+format_timestamp(metadata['생성일시']))
        # 근지구력은 횟수라 정수, 나머지 종목은 소수 첫째 자리까지 표기한다.
        standards = pd.DataFrame([
            {'종목': f'{EVENTS[event][0]}({EVENTS[event][1]})',
             **{f'{level}등급 하한': f'{value:.0f}' if event == 'ENDURANCE' else f'{value:.1f}'
                for level, value in metadata['등급기준'][event].items()}}
            for event in EVENTS
        ])
        # 종목 이름이 '심폐지구력(mL/kg/min)'처럼 길어 잘리지 않도록 열 폭을 넓힌다.
        render_dataframe(standards, hide_index=True,
                         column_config={'종목': st.column_config.TextColumn(width='medium')})
    if (
        soldier_ids is not None
        and not all_comparison_rounds.empty
        and all_comparison_rounds['그룹'].nunique() > 1
    ):
        compare = all_comparison_rounds.loc[all_comparison_rounds['회차'].eq(number)].copy()
        compare = compare.sort_values('미달률', ascending=False, na_position='last', kind='stable')
        compare_events = all_comparison_events.loc[all_comparison_events['회차'].eq(number)]
        st.subheader('부대별 미달률 비교')
        st.caption('조회 범위에 포함된 부대를 전체 미달률이 높은 순서로 5개씩 비교합니다.')
        group_names = compare['그룹'].tolist()
        page_size = 5
        page_count = max(1, (len(group_names) + page_size - 1) // page_size)
        page_key = f"fitness_comparison_page_{filter_signature(scope_signature, number, tuple(group_names))}"
        page = min(max(int(st.session_state.get(page_key, 0)), 0), page_count - 1)
        start = page * page_size
        visible_groups = group_names[start:start + page_size]
        visible_overall = compare.loc[compare['그룹'].isin(visible_groups), ['그룹', '미달률']].copy()
        visible_overall['비교 항목'] = '전체'
        visible_events = compare_events.loc[compare_events['그룹'].isin(visible_groups),
                                            ['그룹', '종목', '미달률']].rename(columns={'종목': '비교 항목'})
        chart_data = pd.concat([visible_overall, visible_events], ignore_index=True)
        chart = make_bar(
            chart_data, x='그룹', y='미달률', color='비교 항목', barmode='group',
            category_orders={'그룹': visible_groups, '비교 항목': ['전체', *EVENT_ORDER]},
            color_discrete_sequence=list(CHART_PALETTE),
            hover_data={'미달률': ':.1f'},
        )
        average_rate = compare['미달률'].mean()
        if pd.notna(average_rate):
            chart.add_hline(y=average_rate, line_color='#F59E0B', line_dash='dot', line_width=2)
            chart.add_annotation(
                x=1, y=average_rate, xref='paper', yref='y',
                text=f'전체 평균 {average_rate:.1f}%', showarrow=False,
                xanchor='right', yanchor='bottom', font={'color': '#F59E0B', 'size': 11},
            )
        chart.update_layout(
            xaxis_title='부대', yaxis_title='미달률 (%)', yaxis_range=[0, 100],
            xaxis={'tickangle': -25, 'automargin': True},
            legend={'orientation': 'h', 'y': 1.12, 'x': 0},
        )
        apply_chart_layout(chart, height=430, margin={'l': 55, 'r': 24, 't': 70, 'b': 90})
        render_paged_plotly_chart(
            chart,
            page=page,
            page_count=page_count,
            page_key=page_key,
            caption=f'{page + 1} / {page_count}',
            on_page_change=_change_comparison_page,
        )
        visible_compare = compare.loc[compare['그룹'].isin(visible_groups)]
        render_dataframe(
            visible_compare.rename(columns={'그룹': '부대'}),
            hide_index=True,
            width='stretch',
            column_config={
                '전체장병수': st.column_config.NumberColumn('전체 장병 수', format='%d명'),
                '측정인원': st.column_config.NumberColumn('측정 인원', format='%d명'),
                '미달인원': st.column_config.NumberColumn('미달 인원', format='%d명'),
                '미달률': st.column_config.NumberColumn('미달 비율(%)', format='%.1f'),
                '관리대상인원': st.column_config.NumberColumn('집중관리 대상', format='%d명'),
            },
        )
