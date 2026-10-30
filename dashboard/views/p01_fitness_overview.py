"""1번 화면: 분석 결과 기반 전체 장병 체력 현황입니다."""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.common.charts import CHART_PALETTE, GRADE_COLORS, apply_chart_layout, show_plotly
from dashboard.common.formatting import filter_signature
from dashboard.main_data import load_main_data
from dashboard.py.fitness_overview_data import load_overview, summarize_by_group

EVENT_ORDER = ['근력','근지구력','심폐지구력','유연성']
GRADE_ORDER = ['1등급', '2등급', '3등급', '3등급 미만', '판정 불가']
GRADE_PALETTE = [
    GRADE_COLORS["1등급"],
    "#38BDF8",
    "#2563EB",
    "#DC5C6A",
    "#94A3B8",
]


def _combine_rounds(rounds: pd.DataFrame) -> pd.DataFrame:
    """조직별 집계를 합쳐 전체 지표를 회차별로 계산합니다."""
    count_columns = [
        "전체장병수", "측정인원", "판정가능인원", "판정불완전인원",
        "미달인원", "관리대상인원",
    ]
    combined = rounds.groupby("회차", as_index=False)[count_columns].sum()
    denominator = combined["판정가능인원"]
    combined["미달률"] = combined["미달인원"].div(denominator.where(denominator.gt(0))).mul(100)
    return combined


def _combine_events(events: pd.DataFrame) -> pd.DataFrame:
    """조직별 종목 집계를 인원 기준으로 합쳐 비율을 다시 계산합니다."""
    count_columns = [
        "유효측정인원", "판정가능인원", "판정불가인원", "미달인원",
        "1등급인원", "2등급인원", "3등급인원",
    ]
    rows = []
    for (number, event, unit), groups in events.groupby(
        ["회차", "종목", "단위"], sort=True
    ):
        row = {
            "회차": number,
            "종목": event,
            "단위": unit,
            **groups[count_columns].sum().to_dict(),
        }
        valid = int(row["판정가능인원"])
        row["미달률"] = row["미달인원"] / valid * 100 if valid else float("nan")

        measured = groups.loc[groups["유효측정인원"].gt(0)]
        measured_count = int(measured["유효측정인원"].sum())
        if measured_count:
            mean = (
                measured["평균"] * measured["유효측정인원"]
            ).sum() / measured_count
            within_variance = (
                (measured["유효측정인원"] - 1).clip(lower=0)
                * measured["표준편차"].fillna(0).pow(2)
            ).sum()
            between_variance = (
                measured["유효측정인원"] * (measured["평균"] - mean).pow(2)
            ).sum()
            row["평균"] = mean
            row["표준편차"] = (
                ((within_variance + between_variance) / (measured_count - 1)) ** 0.5
                if measured_count > 1 else float("nan")
            )
        else:
            row["평균"] = float("nan")
            row["표준편차"] = float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def _change_comparison_page(page_key: str, offset: int, page_count: int) -> None:
    """비교 페이지를 갱신해 Streamlit 재실행부터 새 페이지를 표시합니다."""
    current_page = int(st.session_state.get(page_key, 0))
    st.session_state[page_key] = min(max(current_page + offset, 0), page_count - 1)


def render() -> None:
    """전체 지표·종목 통계·등급 분포·회차별 추이를 표시합니다."""
    st.caption('장병 체력관리 / 01')
    st.title('전체 체력 현황')
    st.write('부대의 체력 수준과 미달 추이를 확인합니다.')
    try:
        rounds, events, metadata = load_overview()
    except FileNotFoundError:
        st.warning('전체 현황 분석 결과가 없습니다. 먼저 아래 명령을 실행해 주세요.')
        st.code('python -m data.scripts.analysis.analysis2.fitness_overview', language='powershell')
        st.stop()
    except (ValueError, KeyError, pd.errors.EmptyDataError, json.JSONDecodeError) as error:
        st.error(f'분석 결과를 확인해 주세요: {error}')
        st.stop()
    if rounds.empty:
        st.info('표시할 분석 자료가 없습니다.')
        st.stop()
    st.sidebar.header('조회 범위')
    level = st.sidebar.radio('분석 기준', ['전체', '지역별', '부대별'], horizontal=True)
    group_label = '지역' if level == '지역별' else '부대' if level == '부대별' else '구분'
    comparison_rounds = pd.DataFrame()
    comparison_events = pd.DataFrame()
    if level != '전체':
        try:
            measurements, _ = load_main_data()
            group_column = 'REGION_NAME' if level == '지역별' else 'UNIT_NAME'
            comparison_rounds, comparison_events = summarize_by_group(measurements, group_column)
        except (FileNotFoundError, ValueError, KeyError, pd.errors.ParserError) as error:
            st.error(f'{level} 체력 현황을 계산하지 못했습니다: {error}')
            st.stop()
        all_comparison_rounds = comparison_rounds
        all_comparison_events = comparison_events
        groups = sorted(comparison_rounds['그룹'].unique().tolist())
        selected_group = st.sidebar.selectbox(
            f'{group_label} 선택',
            ['전체 비교', *groups],
        )
        if selected_group != '전체 비교':
            comparison_rounds = comparison_rounds.loc[
                comparison_rounds['그룹'].eq(selected_group)
            ]
            comparison_events = comparison_events.loc[
                comparison_events['그룹'].eq(selected_group)
            ]
        scope = _combine_rounds(comparison_rounds)
        scoped_events = _combine_events(comparison_events)
    else:
        scope = rounds
        scoped_events = events
    choices = sorted(scope['회차'].unique())
    number = st.sidebar.selectbox('측정 회차', choices, index=len(choices)-1, format_func=lambda n:f'{n}차')
    scope_caption = (
        f'{level} · 장병의 현재 소속 기준으로 묶어 회차별로 집계합니다.'
        if level != '전체' else
        '전체 장병 기준으로 조회합니다. 전체 장병 수는 명단 기준이며, 회차별 측정 인원은 달라질 수 있습니다.'
    )
    st.sidebar.caption(scope_caption)
    row = scope.loc[scope['회차'].eq(number)].iloc[0]
    selected = scoped_events.loc[scoped_events['회차'].eq(number)]
    title_scope = f'{level} · {selected_group}' if level != '전체' else '전체 장병'
    st.subheader(f'{title_scope} · {number}차')
    metrics = [('전체 장병 수',f'{int(row["전체장병수"]):,}명'), ('측정 인원',f'{int(row["측정인원"]):,}명'),
        ('미달 인원',f'{int(row["미달인원"]):,}명'), ('미달 비율',f'{row["미달률"]:.1f}%' if pd.notna(row['미달률']) else '판정 불가'),
        ('집중관리 대상',f'{int(row["관리대상인원"]):,}명')]
    for column,(label,value) in zip(st.columns(5), metrics):
        column.metric(label,value,border=True)
    st.caption(f'4종목 판정 가능 {int(row["판정가능인원"]):,}명 · 판정 불완전 {int(row["판정불완전인원"]):,}명. 전체 미달률은 4종목 모두 판정 가능한 인원 중 1종목 이상 미달 비율입니다.')
    if row['측정인원']==0:
        st.info('선택한 조건에서 측정한 장병이 없습니다.')
    left,right=st.columns(2)
    with left,st.container(border=True):
        st.subheader('종목별 미달률')
        chart=px.bar(selected,x='종목',y='미달률',text='미달률',category_orders={'종목':EVENT_ORDER},
            hover_data=['미달인원','판정가능인원'],color_discrete_sequence=[CHART_PALETTE[0]])
        chart.update_traces(texttemplate='%{text:.1f}%')
        chart.update_layout(yaxis_title='미달률 (%)',yaxis_range=[0,100],showlegend=False)
        apply_chart_layout(chart)
        show_plotly(chart)
    with right,st.container(border=True):
        st.subheader('종목별 등급 분포')
        grade_columns=['1등급인원','2등급인원','3등급인원','미달인원','판정불가인원']
        distribution=selected.melt(id_vars=['종목'],value_vars=grade_columns,var_name='등급',value_name='인원')
        distribution['등급']=distribution['등급'].replace({'1등급인원':'1등급','2등급인원':'2등급','3등급인원':'3등급','미달인원':'3등급 미만','판정불가인원':'판정 불가'})
        chart=px.bar(distribution,x='종목',y='인원',color='등급',barmode='stack',category_orders={'종목':EVENT_ORDER,'등급':GRADE_ORDER},
            color_discrete_sequence=GRADE_PALETTE)
        apply_chart_layout(chart)
        show_plotly(chart)
    if level != '전체':
        compare = all_comparison_rounds.loc[all_comparison_rounds['회차'].eq(number)].copy()
        compare = compare.sort_values('미달률', ascending=False, na_position='last', kind='stable')
        compare_events = all_comparison_events.loc[all_comparison_events['회차'].eq(number)]
        st.subheader(f'{group_label}별 미달률 비교')
        st.caption('전체 미달률과 4개 종목별 미달률을 함께 표시합니다. 전체 미달률이 높은 순서로 5개씩 볼 수 있습니다.')
        group_names = compare['그룹'].tolist()
        page_size = 5
        page_count = max(1, (len(group_names) + page_size - 1) // page_size)
        page_key = f"fitness_comparison_page_{filter_signature(level, selected_group, number, tuple(group_names))}"
        page = min(max(int(st.session_state.get(page_key, 0)), 0), page_count - 1)
        start = page * page_size
        visible_groups = group_names[start:start + page_size]
        visible_overall = compare.loc[compare['그룹'].isin(visible_groups), ['그룹', '미달률']].copy()
        visible_overall['비교 항목'] = '전체'
        visible_events = compare_events.loc[compare_events['그룹'].isin(visible_groups),
                                            ['그룹', '종목', '미달률']].rename(columns={'종목': '비교 항목'})
        chart_data = pd.concat([visible_overall, visible_events], ignore_index=True)
        chart = px.bar(
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
            xaxis_title=group_label, yaxis_title='미달률 (%)', yaxis_range=[0, 100],
            xaxis={'tickangle': -25, 'automargin': True},
            legend={'orientation': 'h', 'y': 1.12, 'x': 0},
        )
        apply_chart_layout(chart, height=430, margin={'l': 55, 'r': 24, 't': 70, 'b': 90})
        previous_col, chart_col, next_col = st.columns([1, 14, 1], vertical_alignment='center')
        previous_col.button(
            '← 이전', disabled=page == 0, key=f'{page_key}_previous',
            on_click=_change_comparison_page, args=(page_key, -1, page_count),
        )
        with chart_col:
            st.caption(f'{page + 1} / {page_count}')
            show_plotly(chart)
        next_col.button(
            '다음 →', disabled=page >= page_count - 1, key=f'{page_key}_next',
            on_click=_change_comparison_page, args=(page_key, 1, page_count),
        )
        visible_compare = compare.loc[compare['그룹'].isin(visible_groups)]
        st.dataframe(
            visible_compare.rename(columns={'그룹': group_label}),
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
    st.subheader('종목별 측정 수준')
    st.caption('단위가 다른 종목의 평균은 하나의 축에서 비교하지 않습니다. 평균은 유효 측정값 기준이며, 등급 판정은 연령 기준까지 적용합니다.')
    for col,event in zip(st.columns(4),EVENT_ORDER):
        record=selected.loc[selected['종목'].eq(event)].iloc[0]
        value=f'{record["평균"]:.2f} {record["단위"]}' if pd.notna(record['평균']) else '측정 없음'
        col.metric(event,value,border=True)
    st.subheader('회차별 변화')
    tab1,tab2=st.tabs(['측정·미달 인원','종목별 미달률'])
    with tab1:
        counts=scope.melt(id_vars=['회차'],value_vars=['측정인원','미달인원','관리대상인원'],var_name='구분',value_name='인원')
        chart=px.bar(counts,x='회차',y='인원',color='구분',barmode='group',
                     color_discrete_sequence=list(CHART_PALETTE))
        apply_chart_layout(chart)
        show_plotly(chart)
    with tab2:
        compare_groups = level != '전체' and selected_group == '전체 비교'
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
            selected_groups = st.sidebar.multiselect(
                f'{group_label} 선택 · 미달률 추이',
                options=available_groups,
                default=available_groups,
                key=f'fitness_trend_groups_{filter_signature(level, selected_group)}',
                help='선택한 그룹을 최신 회차 미달률 순으로 5개씩 나눠 봅니다.',
            )
            trend_page_size = 5
            trend_page_count = max(1, (len(selected_groups) + trend_page_size - 1) // trend_page_size)
            trend_page_key = f"fitness_trend_page_{filter_signature(level, tuple(selected_groups))}"
            trend_page = min(max(int(st.session_state.get(trend_page_key, 0)), 0), trend_page_count - 1)
            trend_start = trend_page * trend_page_size
            visible_trend_groups = selected_groups[trend_start:trend_start + trend_page_size]
            trend = trend.loc[trend['그룹'].isin(visible_trend_groups)]
            st.caption(f'선택한 {group_label} {len(selected_groups)}개 · 범례를 클릭하면 선을 숨기거나 다시 표시할 수 있습니다.')

        event_tabs = st.tabs(EVENT_ORDER)
        for event, event_tab in zip(EVENT_ORDER, event_tabs):
            with event_tab:
                event_trend = trend.loc[trend['종목'].eq(event)]
                if compare_groups and not selected_groups:
                    st.info(f'추이를 볼 {group_label}을 선택하세요.')
                    continue
                if event_trend.empty:
                    st.info('선택한 조건에 표시할 미달률 자료가 없습니다.')
                    continue
                if compare_groups:
                    chart = px.line(
                        event_trend, x='회차', y='미달률', color='그룹', line_group='그룹',
                        markers=True,
                        labels={'그룹': group_label, '회차': '회차', '미달률': '미달률 (%)',
                                '미달인원': '미달 인원', '판정가능인원': '판정 가능 인원'},
                        hover_data={'그룹': True, '회차': True, '미달률': ':.1f',
                                    '미달인원': ':,d', '판정가능인원': ':,d'},
                    )
                    chart.update_traces(line={'width': 2}, marker={'size': 7})
                else:
                    chart = px.line(
                        event_trend, x='회차', y='미달률', markers=True,
                        labels={'회차': '회차', '미달률': '미달률 (%)',
                                '미달인원': '미달 인원', '판정가능인원': '판정 가능 인원'},
                        hover_data={'회차': True, '미달률': ':.1f',
                                    '미달인원': ':,d', '판정가능인원': ':,d'},
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
                    previous_col, chart_col, next_col = st.columns(
                        [1, 14, 1], vertical_alignment='center'
                    )
                    previous_col.button(
                        '← 이전', disabled=trend_page == 0,
                        key=f'{trend_page_key}_{event}_previous',
                        on_click=_change_comparison_page,
                        args=(trend_page_key, -1, trend_page_count),
                    )
                    with chart_col:
                        st.caption(
                            f'추이 그룹 {trend_page + 1} / {trend_page_count} · '
                            f'{len(visible_trend_groups)}개 표시'
                        )
                        show_plotly(chart)
                    next_col.button(
                        '다음 →', disabled=trend_page >= trend_page_count - 1,
                        key=f'{trend_page_key}_{event}_next',
                        on_click=_change_comparison_page,
                        args=(trend_page_key, 1, trend_page_count),
                    )
                else:
                    show_plotly(chart)
    st.caption('회차는 개인별 날짜순 측정 순서입니다. 같은 달력 기간을 뜻하지 않으며, 회차별 측정·판정 가능 인원을 함께 확인하세요.')
    with st.expander('집계표 및 CSV 다운로드'):
        st.dataframe(scope,hide_index=True,width='stretch')
        st.dataframe(selected.drop(columns=['회차']),hide_index=True,width='stretch')
        st.download_button('회차별 집계 다운로드',scope.to_csv(index=False).encode('utf-8-sig'),'회차별_체력현황.csv','text/csv')
        st.download_button('선택 회차 종목별 집계 다운로드',selected.to_csv(index=False).encode('utf-8-sig'),'종목별_체력현황.csv','text/csv')
    with st.expander('자료·판정·관리 대상 기준'):
        st.write(metadata['기준'])
        st.write(metadata['표본'])
        st.write('집중관리 대상: '+metadata['관리대상'])
        st.caption('1차에는 악화·3회 지속 미달을 판정하지 않으며, 2차에는 3회 지속 미달을 판정하지 않습니다. 부상 위험 예측과 구분합니다.')
        if level == '전체':
            st.write(metadata['집계범위'])
        else:
            group_label = '지역' if level == '지역별' else '부대'
            st.write(
                f'현재 화면 집계범위: 장병의 현재 소속 정보({group_label})를 기준으로 회차별 집계합니다.'
            )
            st.caption(f'원본 전체 분석 집계범위: {metadata["집계범위"]}')
        st.write(f'측정 기간: {metadata["측정시작"]} ~ {metadata["측정종료"]}')
        st.caption('분석 생성일: '+metadata['생성일시'])
        st.dataframe(pd.DataFrame(metadata['등급기준']).T.rename(columns={'1':'1등급 하한','2':'2등급 하한','3':'3등급 하한'}))
