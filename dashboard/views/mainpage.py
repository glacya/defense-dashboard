"""대시보드 홈: 바로가기 링크, 전체 현황 요약, 장병 목록을 보여 줍니다."""

from math import ceil

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.charts import (
    ALERT_COLOR, BLUE_ACCENT, CYAN_ACCENT, FITNESS_ITEM_COLORS, GRADE_COLORS, OK_COLOR, WARN_COLOR,
    apply_dark_layout, show_plotly,
)
from dashboard.common.filters import render_filters
from dashboard.common.formatting import (
    BMI_CATEGORY_ORDER, FITNESS_ITEM_LABELS, NAV_STATE_KEY, GRADE_LABELS,
    add_deficiency_flags, add_measurement_rounds, filter_signature, period_mask,
)
from dashboard.common.widgets import reset_soldier_detail_dismissal, show_soldier_detail_dialog
from dashboard.main_data import load_main_data
from data.scripts.fitness_standards import GRADE_CUTS

HOME_TITLE = "대시보드 홈"


def _render_page_links() -> None:
    """다른 페이지로 가는 바로가기 링크를 4개씩 배치합니다."""
    links = [item for item in st.session_state.get(NAV_STATE_KEY, []) if item[0] != HOME_TITLE]
    if not links:
        return
    with st.container(border=True):
        st.markdown("**바로가기**")
        for start in range(0, len(links), 4):
            row = links[start:start + 4]
            for column, (title, icon, page) in zip(st.columns(4), row):
                with column:
                    st.page_link(page, label=title, icon=icon)


def render_home_overview(filters, measurements: pd.DataFrame) -> None:
    scoped = filters.scoped
    latest = add_deficiency_flags(scoped)
    total_count = latest["SOLDIER_ID"].nunique()
    underperformers = latest.loc[latest["체력미달"], "SOLDIER_ID"].nunique()
    managed = latest.loc[latest["관리대상"], "SOLDIER_ID"].nunique()
    underperform_rate = underperformers / max(total_count, 1) * 100
    managed_rate = managed / max(total_count, 1) * 100

    st.subheader("전체 현황")
    st.caption("현재 조건의 장병별 최신 측정과 선택 기간의 전체 측정 회차를 함께 집계합니다.")
    cards = [
        ("전체 장병", f"{total_count:,}명", "기준 인원", "total"),
        ("측정 회차", f"{measurements.loc[period_mask(measurements['MESURE_DE'], filters.date_start, filters.date_end), 'MESURE_DE'].nunique():,}회", "선택 기간 전체", "normal"),
        ("체력 미달", f"{underperformers:,}명", f"전체의 {underperform_rate:.1f}%", "risk"),
        ("관리 대상", f"{managed:,}명", f"전체의 {managed_rate:.1f}%", "underweight"),
    ]
    for column, (label, value, detail, style) in zip(st.columns(4), cards):
        with column:
            with st.container(border=True, key=f"overview-card-{style}"):
                st.metric(label, value)
                st.caption(detail)

    scoped_history = measurements.loc[
        period_mask(measurements["MESURE_DE"], filters.date_start, filters.date_end)
        & measurements["REGION_NAME"].isin(filters.regions)
        & measurements["UNIT_NAME"].isin(filters.units)
        & measurements["RANK_NAME"].isin(filters.ranks)
    ].copy()
    scoped_history = add_measurement_rounds(scoped_history)
    round_summary = (
        scoped_history.groupby("측정회차", as_index=False)
        .agg(측정인원=("SOLDIER_ID", "nunique"), 측정건수=("MESURE_ID", "count"))
        .sort_values("측정회차")
    )
    round_deficiency = (
        add_deficiency_flags(scoped_history).groupby("측정회차", as_index=False)
        .agg(
            미달인원=("체력미달", "sum"),
            판정가능인원=("체력판정가능", "sum"),
            관리대상=("관리대상", "sum"),
        )
    )
    round_summary = round_summary.merge(round_deficiency, on="측정회차", how="left")
    recent = set(round_summary["측정회차"].sort_values().tail(3))
    round_summary = round_summary.loc[round_summary["측정회차"].isin(recent)].copy()
    round_summary["회차"] = round_summary["측정회차"].astype(int).map(lambda v: f"{v}회차")
    round_summary["미달비율"] = (
        round_summary["미달인원"] / round_summary["판정가능인원"].clip(lower=1) * 100
    )

    chart_columns = st.columns([1.15, 0.85])
    with chart_columns[0]:
        st.markdown("**회차별 측정 인원 및 미달 인원**")
        if round_summary.empty:
            st.info("선택한 조건의 측정 회차가 없습니다.")
        else:
            figure = go.Figure()
            figure.add_trace(go.Bar(name="측정인원", x=round_summary["회차"], y=round_summary["측정인원"], marker_color=BLUE_ACCENT))
            figure.add_trace(go.Bar(name="미달인원", x=round_summary["회차"], y=round_summary["미달인원"], marker_color=ALERT_COLOR))
            figure.add_trace(go.Scatter(
                name="미달비율", x=round_summary["회차"], y=round_summary["미달비율"],
                yaxis="y2", mode="lines+markers", line=dict(color=WARN_COLOR, width=3),
                hovertemplate="미달 비율: %{y:.1f}%<extra></extra>",
            ))
            apply_dark_layout(
                figure, 330, barmode="group", xaxis_title=None, yaxis_title="인원",
                yaxis2=dict(title="미달 비율(%)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.12, x=0),
            )
            show_plotly(figure)

    with chart_columns[1]:
        st.markdown("**현재 체력 판정**")
        status = pd.DataFrame({"판정": ["기준 충족", "체력 미달"], "인원": [total_count - underperformers, underperformers]})
        figure = px.pie(status, names="판정", values="인원", hole=0.62, color="판정",
                        color_discrete_map={"기준 충족": OK_COLOR, "체력 미달": ALERT_COLOR})
        apply_dark_layout(figure, 310, showlegend=False)
        figure.update_traces(textinfo="label+percent", textfont_color="#EFF5FB")
        show_plotly(figure)

    st.markdown("**종목별 미달 현황**")
    item_summary = pd.DataFrame([
        {"종목": label, "미달 인원": int(latest[f"미달_{column}"].sum()),
         "미달 비율": int(latest[f"미달_{column}"].sum()) / max(total_count, 1) * 100}
        for column, label in FITNESS_ITEM_LABELS.items()
    ]).sort_values("미달 인원", ascending=True)
    figure = px.bar(item_summary, x="미달 인원", y="종목", orientation="h", text="미달 인원",
                    color="종목", color_discrete_map=FITNESS_ITEM_COLORS, hover_data={"미달 비율": ":.1f"})
    apply_dark_layout(figure, 270, showlegend=False, xaxis_title="미달 인원", yaxis_title=None)
    figure.update_traces(texttemplate="%{x:,}명", textposition="outside")
    show_plotly(figure)

    stat_columns = st.columns(2)
    with stat_columns[0]:
        st.markdown("**종목별 평균 측정값**")
        average = pd.DataFrame([
            {"종목": label, "평균값": float(pd.to_numeric(latest[column], errors="coerce").mean())}
            for column, label in FITNESS_ITEM_LABELS.items()
        ]).sort_values("평균값")
        figure = px.bar(average, x="평균값", y="종목", orientation="h", text="평균값",
                        color="종목", color_discrete_map=FITNESS_ITEM_COLORS)
        apply_dark_layout(figure, 275, showlegend=False, xaxis_title="평균 측정값", yaxis_title=None)
        figure.update_traces(texttemplate="%{x:.1f}", textposition="outside")
        show_plotly(figure)
    with stat_columns[1]:
        st.markdown("**종목별 등급 분포**")
        show_plotly(_grade_distribution_figure(latest, 275))

    with st.expander("판정 기준 보기"):
        st.caption("체력 미달은 3등급 하한 미만, 관리 대상은 체력 4종목 또는 BMI·체지방률 정상 범위 이탈로 계산합니다.")
        standards = pd.DataFrame([
            {"항목": FITNESS_ITEM_LABELS[column], "미달 기준": f"{GRADE_CUTS[column][3]:g} 미만"}
            for column in FITNESS_ITEM_LABELS
        ] + [
            {"항목": "BMI", "미달 기준": "18.5 미만 또는 25.0 이상"},
            {"항목": "체지방률", "미달 기준": "7.0 이하 또는 27.0 이상"},
        ])
        st.dataframe(standards, hide_index=True, width="stretch")


def _grade_distribution_figure(latest: pd.DataFrame, height: int):
    rows = []
    for column, label in FITNESS_ITEM_LABELS.items():
        counts = latest[f"등급_{column}"].value_counts()
        rows.extend({"종목": label, "등급": grade, "인원": int(counts.get(grade, 0))} for grade in GRADE_LABELS)
    figure = px.bar(pd.DataFrame(rows), x="종목", y="인원", color="등급", barmode="stack",
                    category_orders={"등급": list(GRADE_LABELS)}, color_discrete_map=GRADE_COLORS)
    apply_dark_layout(figure, height, xaxis_title=None, yaxis_title="인원")
    return figure


def render_personnel_list(filters, measurements: pd.DataFrame, injuries: pd.DataFrame) -> None:
    st.subheader("장병 목록")
    st.caption("장병 목록의 왼쪽 선택 칸을 누르면 상세 신체정보가 열립니다.")
    search_query = st.text_input("군번·이름 검색", placeholder="군번 또는 이름을 입력하세요", key="home_search").strip()

    list_data = filters.scoped.loc[filters.scoped["BMI구간"].isin(filters.bmi)].copy()
    if search_query:
        matches = (
            list_data["SOLDIER_ID"].str.contains(search_query, case=False, regex=False, na=False)
            | list_data["SOLDIER_NAME"].str.contains(search_query, case=False, regex=False, na=False)
        )
        list_data = list_data.loc[matches]

    sort_options = {
        "측정일": "MESURE_DE", "군번": "SOLDIER_ID", "이름": "SOLDIER_NAME", "계급": "RANK_NAME",
        "지역": "REGION_NAME", "부대": "UNIT_NAME", "나이": "AGE", "BMI": "BMI", "체지방률": "BODY_FAT_PERCENTAGE",
    }
    controls = st.columns([1.2, 1, 1, 2])
    with controls[0]:
        sort_label = st.selectbox("정렬 기준", options=list(sort_options), key="home_sort")
    with controls[1]:
        sort_direction = st.selectbox("정렬 순서", options=["내림차순", "오름차순"], key="home_direction")
    with controls[2]:
        page_size = st.selectbox("페이지당 인원", options=[10, 20, 50, 100], index=1, key="home_page_size")
    with controls[3]:
        st.caption("표의 열 제목을 클릭해도 정렬할 수 있습니다.")

    list_data = list_data.sort_values(
        sort_options[sort_label], ascending=sort_direction == "오름차순", kind="stable"
    ).reset_index(drop=True)
    total_rows = len(list_data)
    page_count = max(1, ceil(total_rows / page_size))

    signature = filter_signature(
        tuple(filters.regions), tuple(filters.units), tuple(filters.ranks), filters.age_range,
        filters.date_start, filters.date_end, tuple(filters.bmi), search_query,
        sort_label, sort_direction, page_size,
    )
    if st.session_state.get("home_table_signature") != signature:
        st.session_state["home_table_signature"] = signature
        st.session_state["home_page"] = 1
    current_page = min(max(st.session_state.get("home_page", 1), 1), page_count)
    st.session_state["home_page"] = current_page

    page_start = (current_page - 1) * page_size
    page_data = list_data.iloc[page_start:page_start + page_size].copy()

    nav = st.columns([1, 2, 1])
    with nav[0]:
        if st.button("← 이전", disabled=current_page <= 1 or total_rows == 0, width="stretch", key="home_prev"):
            st.session_state["home_page"] = current_page - 1
            st.rerun()
    with nav[1]:
        st.markdown(
            f"<div style='text-align:center;padding-top:0.45rem'>"
            f"{total_rows:,}명 · {current_page} / {page_count} 페이지</div>",
            unsafe_allow_html=True,
        )
    with nav[2]:
        if st.button("다음 →", disabled=current_page >= page_count or total_rows == 0, width="stretch", key="home_next"):
            st.session_state["home_page"] = current_page + 1
            st.rerun()

    if page_data.empty:
        st.info("검색어와 선택된 조건에 해당하는 장병이 없습니다.")
        return

    table = page_data[[
        "SOLDIER_ID", "SOLDIER_NAME", "REGION_NAME", "UNIT_NAME", "RANK_NAME",
        "AGE", "MESURE_DE", "BMI", "BMI구간", "BODY_FAT_PERCENTAGE",
    ]].rename(columns={
        "SOLDIER_ID": "군번", "SOLDIER_NAME": "이름", "REGION_NAME": "지역", "UNIT_NAME": "부대",
        "RANK_NAME": "계급", "AGE": "나이", "MESURE_DE": "측정일", "BMI구간": "BMI 구간",
        "BODY_FAT_PERCENTAGE": "체지방률(%)",
    })
    event = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        on_select=reset_soldier_detail_dismissal,
        selection_mode="single-row",
        key=f"home_table_{current_page}_{filter_signature(signature, current_page)}",
        column_config={
            "나이": st.column_config.NumberColumn(format="%d세"),
            "측정일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "BMI": st.column_config.NumberColumn(format="%.1f"),
            "체지방률(%)": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    selected_rows = event.selection.rows
    if selected_rows and 0 <= selected_rows[0] < len(page_data):
        soldier = page_data.iloc[selected_rows[0]]
        st.session_state["selected_soldier_id"] = soldier["SOLDIER_ID"]
        if st.session_state.get("soldier_detail_dismissed_id") != soldier["SOLDIER_ID"]:
            show_soldier_detail_dialog(soldier, measurements, injuries)


def render() -> None:
    st.title("🪖 장병 체력 현황")
    st.caption(f"{HOME_TITLE} · 지역·부대별 신체 현황을 확인하고 장병의 최근 측정 정보를 살펴봅니다.")
    try:
        measurements, injuries = load_main_data()
    except (FileNotFoundError, ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        st.error(f"대시보드 데이터를 불러오지 못했습니다: {error}")
        st.info("먼저 프로젝트 루트에서 데이터 파이프라인의 합성 단계를 실행해 장병 명단과 최종 측정 데이터를 생성하세요.")
        st.stop()

    _render_page_links()
    filters = render_filters(measurements, prefix="home", show_bmi=True)
    if filters.scoped.empty:
        st.info("현재 필터 조건에 해당하는 장병이 없습니다.")
        st.stop()

    render_home_overview(filters, measurements)
    render_personnel_list(filters, measurements, injuries)
    st.divider()
    st.caption(
        "BMI 구간은 일반적인 성인 기준(저체중 <18.5, 정상 18.5–25, 과체중 25–30, 비만 ≥30)으로 표시합니다. "
        "이 화면의 데이터는 개인 진단이나 의학적 판단을 대체하지 않습니다."
    )
