"""부대 현황: 지역·부대별 BMI 구성, 계급별 평균 BMI, 체지방률을 비교합니다."""

import altair as alt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.charts import (
    BMI_COLORS, LIGHT_TEXT, NAVY_BACKGROUND, NAVY_BORDER, NAVY_SURFACE, MUTED_TEXT,
    RANK_BAR_COLOR, WARN_COLOR, apply_dark_layout, show_plotly, style_altair,
)
from dashboard.common.filters import render_filters
from dashboard.common.formatting import BMI_CATEGORY_ORDER, RANK_ORDER, filter_signature
from dashboard.common.widgets import render_soldier_details
from dashboard.main_data import load_main_data
from dashboard.py.followup_fitness_types import load_fitness_types
from dashboard.py.personal_fitness_profile import load_personal_profile
from dashboard.py.fitness_judgment import EVENTS


def clear_bmi_chart_selection() -> None:
    st.session_state["bmi_chart_selected_category"] = None
    st.session_state["bmi_chart_selection_key"] = None
    st.session_state["bmi_chart_dismissed_selection_key"] = None


def select_bmi_category(group_name: str, category: str, context: str) -> None:
    st.session_state["bmi_chart_selection_key"] = (group_name, category, context)
    st.session_state["bmi_chart_dismissed_selection_key"] = None
    st.session_state["bmi_chart_selected_category"] = category
    st.session_state["bmi_count_button_clicked"] = True


def summarize_groups(data: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """지역 또는 부대별 인원과 BMI 구간별 집계를 계산합니다."""
    columns = [group_column, "전체 장병 수", "정상 BMI 인원", "정상 BMI 비율(%)", "과체중·비만 인원", "저체중 인원"]
    if data.empty:
        return pd.DataFrame(columns=columns)
    summary = (
        data.assign(
            _normal=data["BMI구간"].eq("정상"),
            _overweight_obese=data["BMI구간"].isin(["과체중", "비만"]),
            _underweight=data["BMI구간"].eq("저체중"),
        )
        .groupby(group_column, dropna=False)
        .agg(**{
            "전체 장병 수": ("SOLDIER_ID", "nunique"),
            "정상 BMI 인원": ("_normal", "sum"),
            "과체중·비만 인원": ("_overweight_obese", "sum"),
            "저체중 인원": ("_underweight", "sum"),
        })
        .reset_index()
    )
    for column in ["정상 BMI 인원", "과체중·비만 인원", "저체중 인원"]:
        summary[column] = summary[column].astype(int)
    summary["정상 BMI 비율(%)"] = (summary["정상 BMI 인원"] / summary["전체 장병 수"] * 100).round(1)
    return summary.sort_values(["전체 장병 수", group_column], ascending=[False, True], kind="stable").reset_index(drop=True)


def show_bmi_soldiers_panel(group_name: str, category: str, soldiers: pd.DataFrame) -> None:
    """선택한 부대와 BMI 구간의 장병 목록을 모달로 표시합니다."""

    @st.dialog(f"{group_name} · BMI 구간별 장병", width="large")
    def _panel() -> None:
        st.markdown(f"**{category} · {len(soldiers):,}명** (현재 조건 적용)")
        if soldiers.empty:
            st.info("현재 조건에 해당하는 장병이 없습니다.")
        else:
            table = soldiers[["SOLDIER_ID", "SOLDIER_NAME", "REGION_NAME", "UNIT_NAME", "RANK_NAME", "AGE", "MESURE_DE", "BMI", "BODY_FAT_PERCENTAGE"]].rename(columns={
                "SOLDIER_ID": "군번", "SOLDIER_NAME": "이름", "REGION_NAME": "지역", "UNIT_NAME": "부대",
                "RANK_NAME": "계급", "AGE": "나이", "MESURE_DE": "측정일", "BODY_FAT_PERCENTAGE": "체지방률(%)",
            })
            st.caption("목록 왼쪽 선택 칸을 누르면 상세 신체정보가 아래에 표시됩니다.")
            event = st.dataframe(
                table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                key=f"unit_bmi_table_{filter_signature(category, tuple(soldiers['SOLDIER_ID']))}",
                column_config={
                    "나이": st.column_config.NumberColumn(format="%d세"),
                    "측정일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    "BMI": st.column_config.NumberColumn(format="%.1f"),
                    "체지방률(%)": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            rows = event.selection.rows
            if rows and 0 <= rows[0] < len(soldiers):
                st.divider()
                soldier = soldiers.iloc[rows[0]]
                details_column, fitness_type_column = st.columns([1.15, 1], gap="medium")
                with details_column:
                    render_soldier_details(soldier)
                with fitness_type_column:
                    render_soldier_fitness_type(soldier)
        if st.button("닫기", width="stretch", type="primary"):
            st.session_state["bmi_chart_selected_category"] = None
            st.session_state["bmi_chart_dismissed_selection_key"] = st.session_state.get("bmi_chart_selection_key")
            st.rerun()

    _panel()


def render_soldier_fitness_type(soldier: pd.Series) -> None:
    """선택 장병의 체력유형과 개인 상세 화면과 같은 백분위 레이더를 표시합니다."""
    st.subheader("체력유형")
    try:
        classified, _ = load_fitness_types(
            pd.DataFrame([{
                "SOLDIER_ID": soldier["SOLDIER_ID"],
                "MESURE_ID": soldier["MESURE_ID"],
            }])
        )
    except (OSError, ValueError, KeyError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        st.info(f"체력유형 자료를 확인할 수 없습니다: {error}")
        return

    classification = classified.iloc[0]
    if pd.isna(classification.TYPE_NAME):
        st.info("선택 측정의 체력유형 분류 정보가 없습니다.")
        return

    st.markdown(f"**{classification.TYPE_NAME}**")
    st.caption(
        f"평균 백분위 {int(classification.AVERAGE_PERCENTILE_GRADE)}등급 · "
        f"군집 {int(classification.CLUSTER)} · 측정일 {soldier['MESURE_DE']:%Y-%m-%d} 기준"
    )
    try:
        personal_profile, cluster_profile, member_count = load_personal_profile(soldier["MESURE_ID"])
    except (OSError, ValueError, KeyError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        st.info(f"체력유형 비교 차트를 표시할 수 없습니다: {error}")
        return

    axes = [EVENTS[event][0] for event in personal_profile.index]
    radar = go.Figure()
    for name, values, color in [
        ("선택 장병", personal_profile, "#2563eb"),
        ("같은 체력유형 평균", cluster_profile, "#ea580c"),
    ]:
        scores = [float(value) if pd.notna(value) else None for value in values]
        radar.add_trace(go.Scatterpolar(
            r=scores + scores[:1], theta=axes + axes[:1],
            mode="lines+markers", name=name,
            line={"color": color, "width": 3},
            hovertemplate="%{theta}<br>백분위 %{r:.1f}<extra>%{fullData.name}</extra>",
        ))
    radar.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100], "dtick": 20},
               "angularaxis": {"direction": "clockwise"}, "gridshape": "linear"},
        height=310, margin={"t": 20, "b": 35, "l": 35, "r": 35},
        legend={"orientation": "h", "y": -0.08, "x": 0.5, "xanchor": "center", "font": {"size": 10}},
    )
    st.plotly_chart(radar, width="stretch", key=f"unit_soldier_fitness_type_{soldier['MESURE_ID']}",
                    config={"displayModeBar": False})
    st.caption(
        f"바깥쪽일수록 종목 백분위가 높습니다. 같은 체력유형의 전체 회차 측정 "
        f"{member_count:,}건 평균이며 선택 측정도 포함합니다. 백분위는 전체 측정 기준입니다."
    )


def _render_summary(scoped: pd.DataFrame) -> str:
    level = st.segmented_control("요약 기준", options=["지역별", "부대별"], default="지역별",
                                 key="unit_summary_level", on_change=clear_bmi_chart_selection)
    group_column = "REGION_NAME" if level == "지역별" else "UNIT_NAME"
    summary = summarize_groups(scoped, group_column)
    st.dataframe(
        summary.rename(columns={group_column: "지역" if level == "지역별" else "부대"}),
        hide_index=True,
        width="stretch",
        column_config={
            "전체 장병 수": st.column_config.NumberColumn(format="%d명"),
            "정상 BMI 인원": st.column_config.NumberColumn(format="%d명"),
            "정상 BMI 비율(%)": st.column_config.NumberColumn(format="%.1f"),
            "과체중·비만 인원": st.column_config.NumberColumn(format="%d명"),
            "저체중 인원": st.column_config.NumberColumn(format="%d명"),
        },
    )
    st.caption("정상 BMI 비율은 해당 지역·부대 전체 장병 중 정상 BMI 인원의 비율입니다.")
    return level


def _render_analysis(scoped: pd.DataFrame, filters, summary_level: str) -> None:
    analysis_level = st.segmented_control("차트 분석 단위", options=["지역별", "부대별"], default="지역별",
                                          key="unit_analysis_level", on_change=clear_bmi_chart_selection)
    group_column = "REGION_NAME" if analysis_level == "지역별" else "UNIT_NAME"
    label = "지역" if analysis_level == "지역별" else "부대"
    groups = sorted(scoped[group_column].dropna().unique().tolist())
    group_name = st.selectbox(f"상세 분석 {label}", options=groups, key="unit_selected_group")
    group = scoped.loc[scoped[group_column].eq(group_name)]
    context = filter_signature(summary_level, analysis_level, group_name, tuple(filters.regions),
                               tuple(filters.units), tuple(filters.ranks), filters.age_range,
                               filters.date_start, filters.date_end)

    chart_columns = st.columns([1.35, 1])
    with chart_columns[0]:
        st.markdown(f"**{group_name} · BMI 구간별 인원**")
        distribution = (group["BMI구간"].value_counts().reindex(BMI_CATEGORY_ORDER, fill_value=0)
                        .rename_axis("BMI 구간").reset_index(name="인원"))
        distribution["비율(%)"] = distribution["인원"] / max(len(group), 1) * 100
        selection = alt.selection_point(name="bmi_slice", fields=["BMI 구간"], on="click", toggle=False, clear="dblclick")
        donut = (
            alt.Chart(distribution)
            .mark_arc(innerRadius=78, outerRadius=125, stroke=NAVY_BACKGROUND, strokeWidth=3, cursor="pointer")
            .encode(
                theta=alt.Theta("인원:Q"),
                color=alt.Color("BMI 구간:N", scale=alt.Scale(domain=list(BMI_CATEGORY_ORDER),
                                range=[BMI_COLORS[c] for c in BMI_CATEGORY_ORDER]), legend=None),
                opacity=alt.condition(selection, alt.value(1), alt.value(0.85)),
                tooltip=[alt.Tooltip("BMI 구간:N"), alt.Tooltip("인원:Q", format=",d"), alt.Tooltip("비율(%):Q", format=".1f")],
            )
            .add_params(selection)
        )
        total = alt.Chart(pd.DataFrame({"label": [f"{len(group):,}명"]})).mark_text(
            color=LIGHT_TEXT, fontSize=22, fontWeight="bold").encode(text="label:N")
        event = st.altair_chart(
            style_altair(alt.layer(donut, total), 340), width="stretch",
            key=f"unit_donut_{filter_signature(analysis_level, group_name, context)}",
            on_select="rerun", selection_mode="bmi_slice",
        )
        points = event.selection.get("bmi_slice", [])
        clicked_button = st.session_state.pop("bmi_count_button_clicked", False)
        if analysis_level == "부대별" and points and not clicked_button:
            category = points[-1].get("BMI 구간")
            if category in BMI_CATEGORY_ORDER:
                key = (group_name, category, context)
                st.session_state["bmi_chart_selection_key"] = key
                if st.session_state.get("bmi_chart_dismissed_selection_key") != key:
                    st.session_state["bmi_chart_selected_category"] = category

    with chart_columns[1]:
        st.markdown("**구간별 인원**")
        for _, row in distribution.iterrows():
            category = str(row["BMI 구간"])
            count = int(row["인원"])
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;
                    padding:0.65rem 0.8rem;margin:0.35rem 0;border:1px solid {NAVY_BORDER};
                    border-radius:0.55rem;background:{NAVY_SURFACE};">
                    <span style="display:flex;align-items:center;gap:0.55rem;color:{LIGHT_TEXT};">
                        <span style="width:0.7rem;height:0.7rem;border-radius:50%;background:{BMI_COLORS[category]};display:inline-block;"></span>
                        <strong>{category}</strong>
                    </span>
                    <span style="color:{LIGHT_TEXT};white-space:nowrap;">
                        {count:,}명 <span style="color:{MUTED_TEXT};">({row['비율(%)']:.1f}%)</span>
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if analysis_level == "부대별":
                st.button(
                    f"{count:,}명 보기",
                    key=f"unit_count_{filter_signature(group_name, category, context)}",
                    width="stretch",
                    on_click=select_bmi_category,
                    args=(group_name, category, context),
                )

    rank_average = group.groupby("RANK_NAME", as_index=False).agg(평균_BMI=("BMI", "mean"), 인원=("SOLDIER_ID", "nunique"))
    rank_average["RANK_NAME"] = pd.Categorical(rank_average["RANK_NAME"], categories=RANK_ORDER, ordered=True)
    rank_average = rank_average.sort_values("RANK_NAME")
    st.markdown(f"**{group_name} · 계급별 평균 BMI**")
    rank_figure = px.bar(rank_average, x="RANK_NAME", y="평균_BMI", text="평균_BMI",
                         color_discrete_sequence=[RANK_BAR_COLOR], hover_data={"인원": True, "평균_BMI": ":.2f"},
                         labels={"RANK_NAME": "계급", "평균_BMI": "평균 BMI", "인원": "장병 수"})
    rank_figure.update_traces(texttemplate="%{y:.1f}", textposition="outside")
    apply_dark_layout(rank_figure, 360, showlegend=False, xaxis_title=None, yaxis_title="평균 BMI", yaxis_rangemode="tozero")
    show_plotly(rank_figure)

    st.markdown(f"**현재 조건 · {label}별 평균 체지방률**")
    body_fat = (scoped.groupby(group_column, as_index=False)
                .agg(평균_체지방률=("BODY_FAT_PERCENTAGE", "mean"), 인원=("SOLDIER_ID", "nunique"))
                .sort_values("평균_체지방률", ascending=True))
    body_fat_figure = px.bar(body_fat, x="평균_체지방률", y=group_column, orientation="h", text="평균_체지방률",
                             hover_data={"인원": True, "평균_체지방률": ":.1f"},
                             labels={group_column: label, "평균_체지방률": "평균 체지방률(%)", "인원": "장병 수"},
                             color_discrete_sequence=[WARN_COLOR])
    body_fat_figure.update_traces(texttemplate="%{x:.1f}%", textposition="outside")
    apply_dark_layout(body_fat_figure, max(300, min(620, 36 * len(body_fat) + 100)),
                      margin=dict(l=8, r=40, t=8, b=8), xaxis_title="평균 체지방률(%)", yaxis_title=None)
    show_plotly(body_fat_figure)

    selected_category = st.session_state.get("bmi_chart_selected_category")
    current_key = (group_name, selected_category, context)
    if (analysis_level == "부대별" and selected_category in BMI_CATEGORY_ORDER
            and st.session_state.get("bmi_chart_selection_key") == current_key):
        members = group.loc[group["BMI구간"].eq(selected_category)].sort_values(["UNIT_NAME", "RANK_NAME", "SOLDIER_NAME"])
        show_bmi_soldiers_panel(group_name, selected_category, members)


def render() -> None:
    st.title("🪖 부대 현황")
    st.caption("지역·부대별 BMI 구성과 체지방률을 비교하고, 구간별 장병 명단을 확인합니다.")
    try:
        measurements, _ = load_main_data()
    except (FileNotFoundError, ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        st.error(f"부대 현황 데이터를 불러오지 못했습니다: {error}")
        st.stop()

    filters = render_filters(measurements, prefix="unit")
    if filters.scoped.empty:
        st.info("현재 필터 조건에 해당하는 장병이 없습니다.")
        st.stop()

    summary_tab, analysis_tab = st.tabs(["지역·부대별 요약", "신체정보 분석"])
    with summary_tab:
        summary_level = _render_summary(filters.scoped)
    with analysis_tab:
        _render_analysis(filters.scoped, filters, summary_level)
