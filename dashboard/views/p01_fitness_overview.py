"""1번 화면: 분석 결과 기반 전체 장병 체력 현황입니다."""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.common.charts import CHART_PALETTE, GRADE_COLORS, apply_chart_layout, show_plotly
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
        group_label = '지역' if level == '지역별' else '부대'
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
        compare = all_comparison_rounds.loc[all_comparison_rounds['회차'].eq(number)].sort_values(
            '그룹', kind='stable'
        )
        compare_events = all_comparison_events.loc[all_comparison_events['회차'].eq(number)]
        left, right = st.columns(2)
        with left, st.container(border=True):
            st.subheader(f'{group_label}별 전체 미달률 비교')
            chart = px.bar(
                compare,
                x='그룹',
                y='미달률',
                text='미달률',
                hover_data=['미달인원', '판정가능인원', '측정인원'],
                color_discrete_sequence=[CHART_PALETTE[2]],
            )
            chart.update_traces(texttemplate='%{text:.1f}%')
            chart.update_layout(yaxis_title='미달률 (%)', yaxis_range=[0, 100])
            apply_chart_layout(chart)
            show_plotly(chart)
        with right, st.container(border=True):
            st.subheader(f'{group_label}별 종목 미달률 비교')
            chart = px.bar(
                compare_events,
                x='그룹',
                y='미달률',
                color='종목',
                barmode='group',
                category_orders={'종목': EVENT_ORDER},
                color_discrete_sequence=list(CHART_PALETTE),
                hover_data=['미달인원', '판정가능인원'],
            )
            chart.update_layout(yaxis_title='미달률 (%)', yaxis_range=[0, 100])
            apply_chart_layout(chart)
            show_plotly(chart)
        st.dataframe(
            compare.rename(columns={'그룹': group_label}),
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
        if level != '전체' and selected_group == '전체 비교':
            trend=all_comparison_events
            chart=px.line(trend,x='회차',y='미달률',color='그룹',facet_col='종목',markers=True,
                          category_orders={'종목':EVENT_ORDER},hover_data=['미달인원','판정가능인원'])
        else:
            chart=px.line(scoped_events,x='회차',y='미달률',color='종목',markers=True,
                          category_orders={'종목':EVENT_ORDER},hover_data=['미달인원','판정가능인원'])
        chart.update_layout(yaxis_title='미달률 (%)',yaxis_range=[0,100],xaxis_dtick=1)
        apply_chart_layout(chart)
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