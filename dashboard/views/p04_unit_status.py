"""부대 현황: 지역·부대별 인원, 미달 확률, BMI 분포를 확인합니다."""

from types import SimpleNamespace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pandas.io.formats.style import Styler
from sqlalchemy.exc import SQLAlchemyError

from dashboard.common.filters import render_personnel_cards
from dashboard.common.charts import (
    BMI_COLORS, LIGHT_TEXT, NAVY_BORDER, NAVY_SURFACE, MUTED_TEXT,
)
from dashboard.common.formatting import BMI_CATEGORY_ORDER, classify_bmi, filter_signature
from dashboard.common.table_widgets import render_dataframe
from dashboard.common.chart_widgets import PieChartWidget, RadarChartWidget
from dashboard.common.widgets import render_soldier_details
from dashboard.db import DEFAULT_TTL
from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS
from dashboard.py.followup_probability import RISK_LEVELS, RISK_RANGES, classify_probabilities

RISK_COLORS = {
    "안전": "#2F9E59",
    "경계1등급": "#EACB22",
    "경계2등급": "#E88932",
    "경계3등급": "#C92836",
}
RISK_BAND_FILLS = {
    "안전": "rgba(47, 158, 89, 0.08)",
    "경계1등급": "rgba(234, 203, 34, 0.10)",
    "경계2등급": "rgba(232, 137, 50, 0.09)",
    "경계3등급": "rgba(201, 40, 54, 0.08)",
}
RISK_DISTRIBUTION_HEIGHT = 540


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_population() -> pd.DataFrame:
    """장병별 최신 측정(DB)을 화면이 쓰는 모양으로 바꿉니다(MESURE_ID 정수, 측정일 날짜, BMI 구간)."""
    rows = queries.load_unit_latest()
    rows = rows.assign(
        SOLDIER_ID=rows["SOLDIER_ID"].astype(str),
        MESURE_ID=pd.to_numeric(rows["MESURE_ID"]).astype("int64"),
        MESURE_DE=pd.to_datetime(rows["MESURE_DE"], format="%Y%m%d"),
    )
    rows["BMI구간"] = classify_bmi(rows["BMI"])
    rows["RISK_LEVEL"] = pd.NA
    probability_rows = rows.loc[rows["FAILURE_PROBABILITY"].notna(), ["SOLDIER_ID", "FAILURE_PROBABILITY"]]
    classified = classify_probabilities(probability_rows)
    rows.loc[classified.index, "RISK_LEVEL"] = classified["RISK_LEVEL"]
    return rows


def _render_unit_filters(population: pd.DataFrame):
    """도 단위 지역·지역별 부대 카드 필터를 표시합니다."""
    st.caption("도 단위 지역 카드를 선택하면 해당 지역의 부대가 표시됩니다. 부대 선택이 없으면 선택 지역의 전체 부대를 포함합니다.")
    selection = render_personnel_cards(population, "unit", show_ranks=False)
    st.caption(f"조회 조건 · 장병별 최신 측정 · 현재 조회 {selection.scoped.SOLDIER_ID.nunique():,}명 / 전체 {population.SOLDIER_ID.nunique():,}명")
    return SimpleNamespace(regions=selection.regions, units=selection.units, scoped=selection.scoped)


def clear_bmi_chart_selection() -> None:
    st.session_state["bmi_chart_selected_category"] = None
    st.session_state["bmi_chart_selection_key"] = None
    st.session_state["bmi_chart_dismissed_selection_key"] = None


def select_bmi_category(group_name: str, category: str, context: str) -> None:
    st.session_state["bmi_chart_selection_key"] = (group_name, category, context)
    st.session_state["bmi_chart_dismissed_selection_key"] = None
    st.session_state["bmi_chart_selected_category"] = category


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


def _style_summary_table(summary: pd.DataFrame, group_label: str) -> Styler:
    """요약 표를 대시보드 차트 팔레트와 의미별 색상으로 강조합니다."""
    return (
        summary.style
        .set_table_styles([
            {
                "selector": "th",
                "props": [
                    ("background-color", "#193B60"),
                    ("color", "#FFFFFF"),
                    ("font-weight", "700"),
                    ("border-bottom", "3px solid #2C65B7"),
                    ("padding", "0.65rem 0.75rem"),
                    ("text-align", "center"),
                ],
            },
            {
                "selector": "td",
                "props": [
                    ("border-bottom", "1px solid #DFE6ED"),
                    ("padding", "0.55rem 0.75rem"),
                    ("color", "#182B40"),
                    ("text-align", "left"),
                    ("vertical-align", "middle"),
                ],
            },
            {
                "selector": "tbody tr:nth-child(even) td",
                "props": [("background-color", "#F8FAFC")],
            },
        ])
        .set_properties(
            subset=[group_label],
            **{
                "background-color": "#ECF3FC",
                "color": "#193B60",
                "font-weight": "700",
                "border-left": "3px solid #2C65B7",
            },
        )
        .set_properties(
            subset=["전체 장병 수"],
            **{"background-color": "#EFF6FF", "color": "#2563EB", "font-weight": "700"},
        )
        .set_properties(
            subset=["정상 BMI 인원"],
            **{"background-color": "#EAF6F4", "color": "#0F766E", "font-weight": "700"},
        )
        .bar(
            subset=["정상 BMI 비율(%)"],
            color="rgba(20, 184, 166, 0.28)",
            vmin=0,
            vmax=100,
            props="color: #0F766E; font-weight: 700;",
        )
        .set_properties(
            subset=["과체중·비만 인원"],
            **{"background-color": "#FAF4E9", "color": "#D97706", "font-weight": "700"},
        )
        .set_properties(
            subset=["저체중 인원"],
            **{"background-color": "#FDECEF", "color": "#DC5C6A", "font-weight": "700"},
        )
    )


def _bmi_distribution_figure(distribution: pd.DataFrame, total: int) -> go.Figure:
    """BMI 구간 분포를 공통 입체 도넛 차트로 만듭니다."""
    return PieChartWidget(
        data=distribution,
        names="BMI 구간",
        values="인원",
        colors=[BMI_COLORS[category] for category in distribution["BMI 구간"]],
        center_text=f"{total:,}<br>명",
        height=340,
        show_percent=True,
    ).build_figure()


def _risk_counts(scoped: pd.DataFrame) -> pd.Series:
    """현재 지역·부대 필터 안에서 확률 등급별 장병 수를 계산합니다."""
    people_with_probability = scoped.loc[scoped["RISK_LEVEL"].isin(RISK_LEVELS)]
    return (
        people_with_probability.groupby("RISK_LEVEL")["SOLDIER_ID"]
        .nunique()
        .reindex(RISK_LEVELS, fill_value=0)
    )


def _risk_distribution_figure(scoped: pd.DataFrame) -> go.Figure:
    """BMI와 미달 확률의 실제 값을 축으로 사용하는 위험 등급 산점도를 만듭니다."""
    figure = go.Figure()
    shapes = []
    probability_bands = [
        (0.0, 0.3, "안전"),
        (0.3, 0.5, "경계1등급"),
        (0.5, 0.7, "경계2등급"),
        (0.7, 1.0, "경계3등급"),
    ]
    for lower, upper, level in probability_bands:
        shapes.append({
            "type": "rect",
            "xref": "paper",
            "yref": "y",
            "x0": 0,
            "x1": 1,
            "y0": lower,
            "y1": upper,
            "line": {"width": 0},
            "fillcolor": RISK_BAND_FILLS[level],
            "layer": "below",
        })
    for threshold in (0.3, 0.5, 0.7):
        shapes.append({
            "type": "line",
            "xref": "paper",
            "yref": "y",
            "x0": 0,
            "x1": 1,
            "y0": threshold,
            "y1": threshold,
            "line": {"color": NAVY_BORDER, "width": 1, "dash": "dash"},
            "layer": "above",
        })

    chart_population = scoped.loc[
        scoped["RISK_LEVEL"].isin(RISK_LEVELS)
        & scoped["BMI"].notna()
        & scoped["FAILURE_PROBABILITY"].notna()
    ]
    for level in RISK_LEVELS:
        soldiers = chart_population.loc[chart_population["RISK_LEVEL"].eq(level)].sort_values(
            "SOLDIER_ID",
            kind="stable",
        )
        if soldiers.empty:
            continue
        figure.add_trace(go.Scatter(
            x=soldiers["BMI"],
            y=soldiers["FAILURE_PROBABILITY"],
            mode="markers",
            name=level,
            marker={
                "color": RISK_COLORS[level],
                "size": 8,
                "opacity": 0.82,
                "line": {"color": "#FFFFFF", "width": 1},
            },
            customdata=soldiers[["SOLDIER_NAME", "UNIT_NAME"]].to_numpy(),
            hovertemplate=(
                f"{level}<br>%{{customdata[0]}} · %{{customdata[1]}}"
                "<br>BMI %{x:.1f}<br>미달 확률 %{y:.1%}<extra></extra>"
            ),
        ))

    figure.update_layout(
        height=RISK_DISTRIBUTION_HEIGHT,
        margin={"t": 12, "b": 42, "l": 58, "r": 12},
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 10},
        },
        template="plotly_white",
        plot_bgcolor=NAVY_SURFACE,
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": LIGHT_TEXT},
        shapes=shapes,
        xaxis={
            "title": {"text": "BMI", "standoff": 8},
            "showgrid": True,
            "gridcolor": NAVY_BORDER,
            "zeroline": False,
            "fixedrange": True,
        },
        yaxis={
            "title": {"text": "다음 측정 미달 확률", "standoff": 8},
            "tickmode": "array",
            "tickvals": [0, 0.3, 0.5, 0.7, 1],
            "ticktext": ["0%", "30%", "50%", "70%", "100%"],
            "range": [0, 1],
            "showgrid": False,
            "fixedrange": True,
        },
    )
    return figure


def _risk_soldier_table(soldiers: pd.DataFrame) -> pd.DataFrame:
    """확률 등급별 장병 명단과 CSV 내보내기 표를 만듭니다."""
    columns = [
        "SOLDIER_ID", "SOLDIER_NAME", "REGION_NAME", "UNIT_NAME", "RANK_NAME",
        "MESURE_DE", "BMI", "BODY_FAT_PERCENTAGE", "FAILURE_PROBABILITY", "RISK_LEVEL",
    ]
    table = soldiers[columns].rename(columns={
        "SOLDIER_ID": "군번",
        "SOLDIER_NAME": "이름",
        "REGION_NAME": "지역",
        "UNIT_NAME": "부대",
        "RANK_NAME": "계급",
        "MESURE_DE": "측정일",
        "BMI": "BMI",
        "BODY_FAT_PERCENTAGE": "체지방률(%)",
        "FAILURE_PROBABILITY": "미달 확률(%)",
        "RISK_LEVEL": "확률 등급",
    })
    table["측정일"] = pd.to_datetime(table["측정일"], errors="coerce").dt.strftime("%Y-%m-%d")
    table["미달 확률(%)"] = (pd.to_numeric(table["미달 확률(%)"]) * 100).round(1)
    return table


def _select_risk_level(level: str, context: str) -> None:
    """선택한 확률 등급을 토글해 명단 표시를 갱신합니다."""
    selected = st.session_state.get("unit_risk_level_selection")
    current = (level, context)
    st.session_state["unit_risk_level_selection"] = None if selected == current else current


def _render_risk_probability_panel(scoped: pd.DataFrame, filters) -> None:
    """현재 선택된 장병의 미달 확률 분포, 등급별 선택 카드와 CSV 명단을 표시합니다."""
    st.divider()
    st.subheader("미달 확률별 장병 현황")
    st.caption(
        "현재 지역·부대 선택을 적용합니다. 안전은 30% 미만이며, 30%·50%·70%부터 각각 경계1·2·3등급입니다. "
        "분포를 확인한 뒤 가운데 등급을 선택하면 해당 장병 명단이 표시됩니다."
    )

    counts = _risk_counts(scoped)
    predicted_count = int(counts.sum())
    missing_count = int(scoped.loc[scoped["RISK_LEVEL"].isna(), "SOLDIER_ID"].nunique())
    context = filter_signature(
        tuple(filters.regions),
        tuple(filters.units),
        tuple(scoped["SOLDIER_ID"].astype(str)),
    )

    selection = st.session_state.get("unit_risk_level_selection")
    if not (isinstance(selection, tuple) and len(selection) == 2 and selection[1] == context):
        selection = None
        st.session_state["unit_risk_level_selection"] = None

    distribution_column, grade_column, roster_column = st.columns(
        [1.2, 0.3, 1.45],
        gap="small",
        vertical_alignment="top",
        wrap=False,
    )
    with distribution_column:
        with st.container(border=True):
            st.markdown("**1. 확률별 분포**")
            st.plotly_chart(
                _risk_distribution_figure(scoped),
                width="stretch",
                key=f"unit_risk_distribution_{context}",
                config={"displayModeBar": False},
            )
            st.caption(
                "점 하나는 장병 한 명입니다. 가로축은 최신 측정 BMI, 세로축은 다음 측정 미달 확률입니다. "
                "배경 구간은 30%·50%·70% 기준으로 나뉘며, 점에 마우스를 올리면 상세값을 확인할 수 있습니다."
            )

    with grade_column:
        st.markdown(
            """
            <style>
                div[class*="st-key-unit-risk-grade-"] button {
                    aspect-ratio: 1 / 1;
                    height: auto;
                    min-height: 0;
                    width: 100%;
                    padding: 0.4rem;
                    border-radius: 12px;
                }
                div[class*="st-key-unit-risk-grade-"] button * {
                    color: inherit !important;
                }
                div[class*="st-key-unit-risk-grade-"] button:hover {
                    filter: brightness(.97);
                }
                div[class*="st-key-unit-risk-grade-"][class*="-selected-"] button {
                    border-width: 3px;
                    box-shadow: 0 0 0 2px currentColor;
                }
                div[class*="st-key-unit-risk-grade-0-"] button {
                    background: #edf8f0; border-color: #2f9e59; color: #176638;
                }
                div[class*="st-key-unit-risk-grade-1-"] button {
                    background: #fffbea; border-color: #eacb22; color: #76640b;
                }
                div[class*="st-key-unit-risk-grade-2-"] button {
                    background: #fff5eb; border-color: #e88932; color: #914d13;
                }
                div[class*="st-key-unit-risk-grade-3-"] button {
                    background: #fff0f1; border-color: #c92836; color: #8d1d27;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
        for level, interval in reversed(list(zip(RISK_LEVELS, RISK_RANGES))):
            index = RISK_LEVELS.index(level)
            is_selected = selection == (level, context)
            st.button(
                f'{"✓ " if is_selected else ""}**{level} · {int(counts[level]):,}명**  \n{interval}',
                key=f"unit-risk-grade-{index}-{'selected' if is_selected else 'idle'}-{context}",
                width="stretch",
                disabled=counts[level] == 0,
                on_click=_select_risk_level,
                args=(level, context),
            )

    with roster_column:
        if selection is None:
            st.markdown("**3. 선택 등급 장병 명단**")
            st.caption("가운데 등급 카드를 선택하면 명단과 CSV 다운로드가 표시됩니다.")
        else:
            level = selection[0]
            soldiers = scoped.loc[scoped["RISK_LEVEL"].eq(level)].sort_values(
                ["FAILURE_PROBABILITY", "UNIT_NAME", "RANK_NAME", "SOLDIER_NAME"],
                ascending=[False, True, True, True],
                kind="stable",
            )
            table = _risk_soldier_table(soldiers)
            st.markdown(f"**3. {level} 명단 · {len(table):,}명**")
            st.dataframe(
                table,
                hide_index=True,
                height=RISK_DISTRIBUTION_HEIGHT,
                width="stretch",
                column_config={
                    "BMI": st.column_config.NumberColumn(format="%.1f"),
                    "체지방률(%)": st.column_config.NumberColumn(format="%.1f"),
                    "미달 확률(%)": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            st.download_button(
                "CSV 다운로드",
                data=table.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"미달확률_{level}_장병명단.csv",
                mime="text/csv",
                key=f"unit_risk_csv_{context}_{level}",
            )

    if missing_count:
        st.caption(f"미달 확률 자료가 없는 장병 {missing_count:,}명은 등급 집계에서 제외했습니다.")
    if predicted_count == 0:
        st.info("현재 선택 범위에 미달 확률 자료가 있는 장병이 없습니다.")


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
            event = render_dataframe(
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
    classification = soldier  # 목록 행에 그 측정의 체력유형(등급·군집·유형명)이 들어 있다.
    if pd.isna(classification.TYPE_NAME):
        st.info("선택 측정의 체력유형 분류 정보가 없습니다.")
        return

    st.markdown(f"**{classification.TYPE_NAME}**")
    st.caption(
        f"평균 백분위 {int(classification.AVERAGE_PERCENTILE_GRADE)}등급 · "
        f"군집 {int(classification.CLUSTER)} · 측정일 {soldier['MESURE_DE']:%Y-%m-%d} 기준"
    )
    try:
        personal_profile, cluster_profile, member_count = queries.load_measurement_profile(soldier["MESURE_ID"])
    except (ValueError, KeyError, SQLAlchemyError) as error:
        st.info(f"체력유형 비교 차트를 표시할 수 없습니다: {error}")
        return

    axes = [EVENTS[event][0] for event in personal_profile.index]
    radar = RadarChartWidget(
        labels=axes,
        values=[
            [float(value) if pd.notna(value) else None for value in personal_profile],
            [float(value) if pd.notna(value) else None for value in cluster_profile],
        ],
        name=["선택 장병", "같은 체력유형 평균"],
        line_color=["#2563eb", "#ea580c"],
        fill_color=["rgba(37, 99, 235, 0.18)", "rgba(234, 88, 12, 0.18)"],
        height=310,
    )
    st.plotly_chart(radar.build_figure(), width="stretch", key=f"unit_soldier_fitness_type_{soldier['MESURE_ID']}",
                    config={"displayModeBar": False})
    st.caption(
        f"바깥쪽일수록 종목 백분위가 높습니다. 같은 체력유형의 전체 회차 측정 "
        f"{member_count:,}건 평균이며 선택 측정도 포함합니다. 백분위는 전체 측정 기준입니다."
    )


def _render_summary(scoped: pd.DataFrame) -> str:
    level = st.segmented_control("요약 기준", options=["지역별", "부대별"], default="지역별",
                                 key="unit_summary_level", on_change=clear_bmi_chart_selection)
    group_column = "REGION_NAME" if level == "지역별" else "UNIT_NAME"
    group_label = "지역" if level == "지역별" else "부대"
    summary = summarize_groups(scoped, group_column).rename(columns={group_column: group_label})
    render_dataframe(
        _style_summary_table(summary, group_label),
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
    analysis_level = st.segmented_control("요약 기준", options=["지역별", "부대별"], default="지역별",
                                          key="unit_analysis_level", on_change=clear_bmi_chart_selection)
    group_column = "REGION_NAME" if analysis_level == "지역별" else "UNIT_NAME"
    label = "지역" if analysis_level == "지역별" else "부대"
    groups = sorted(scoped[group_column].dropna().unique().tolist())
    group_name = st.selectbox(f"상세 분석 {label}", options=groups, key="unit_selected_group")
    group = scoped.loc[scoped[group_column].eq(group_name)]
    context = filter_signature(summary_level, analysis_level, group_name,
                               tuple(filters.regions), tuple(filters.units))

    chart_columns = st.columns([1.35, 1])
    with chart_columns[0]:
        st.markdown(f"**{group_name} · BMI 구간별 인원**")
        distribution = (group["BMI구간"].value_counts().reindex(BMI_CATEGORY_ORDER, fill_value=0)
                        .rename_axis("BMI 구간").reset_index(name="인원"))
        distribution["비율(%)"] = distribution["인원"] / max(len(group), 1) * 100
        st.plotly_chart(
            _bmi_distribution_figure(distribution, len(group)),
            width="stretch",
            key=f"unit_donut_{filter_signature(analysis_level, group_name, context)}",
            config={"displayModeBar": False},
        )

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

    selected_category = st.session_state.get("bmi_chart_selected_category")
    current_key = (group_name, selected_category, context)
    if (analysis_level == "부대별" and selected_category in BMI_CATEGORY_ORDER
            and st.session_state.get("bmi_chart_selection_key") == current_key):
        members = group.loc[group["BMI구간"].eq(selected_category)].sort_values(["UNIT_NAME", "RANK_NAME", "SOLDIER_NAME"])
        show_bmi_soldiers_panel(group_name, selected_category, members)


def render() -> None:
    st.title("부대 현황")
    st.caption("지역·부대별 인원 현황, 미달 확률 등급 및 BMI 구간별 장병 분포를 확인합니다.")
    try:
        population = _load_population()
    except (ValueError, SQLAlchemyError) as error:
        st.error(f"부대 현황 데이터를 불러오지 못했습니다: {error}")
        st.stop()

    filters = _render_unit_filters(population)
    if filters.scoped.empty:
        st.info("선택한 지역·부대 조건에 해당하는 장병이 없습니다.")
        st.stop()

    summary_tab, analysis_tab = st.tabs(["지역·부대별 인원 요약", "BMI 별 요약"])
    with summary_tab:
        summary_level = _render_summary(filters.scoped)
        _render_risk_probability_panel(filters.scoped, filters)
    with analysis_tab:
        _render_analysis(filters.scoped, filters, summary_level)
