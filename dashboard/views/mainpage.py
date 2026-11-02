"""대시보드 홈: 체력·부상·후속조치 현황을 native Streamlit으로 표시합니다."""

import html
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy.exc import SQLAlchemyError

from dashboard.common.charts import (
    CHART_PALETTE,
    FITNESS_DEVIATION_SCALE,
    LIGHT_TEXT,
    MUTED_TEXT,
    NAVY_BORDER,
    make_choropleth,
)
from dashboard.common.formatting import FITNESS_ITEM_LABELS
from dashboard.common.chart_widgets import PieChartWidget, RadarChartWidget
from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS
from dashboard.py.followup_probability import FOLLOWUP_THRESHOLD
from dashboard.py.management_store import load_completion_counts
from dashboard.py.personal_exercise_recommendations import load_recommendation

PALETTE = list(CHART_PALETTE)
FITNESS_LEVELS = ["1등급", "2등급", "3등급", "4등급"]
# 시·도 경계는 Streamlit 정적 파일(dashboard/static, .streamlit/config.toml의 enableStaticServing)로 제공한다.
# figure에는 URL만 넣고 브라우저의 plotly.js가 파일을 직접 받아 재사용하므로, 다시 그릴 때마다
# 수 MB의 경계 좌표를 서버에서 만들고 직렬화하지 않는다.
REGION_GEOJSON_PATH = Path(__file__).resolve().parents[1] / "static" / "korea_provinces.geojson"
REGION_GEOJSON_URL = "app/static/korea_provinces.geojson?v=2"


def _unit_table(units: pd.DataFrame) -> pd.DataFrame:
    """지역·부대별 집계(queries.load_home_units)에 미달률·충족률을 붙입니다."""
    unit = units.rename(columns={"TOTAL": "인원", "FAILED": "미달"})
    unit["미달률"] = unit["미달"] / unit["인원"].clip(lower=1) * 100
    unit["충족률"] = 100 - unit["미달률"]
    return unit


def _province_of(region_name: str) -> str | None:
    """원본 지역명을 GeoJSON의 시·도 이름으로 정규화합니다."""
    name = str(region_name)
    province_keywords = (
        ("전남광주", "전라남도"),
        ("서울", "서울특별시"), ("부산", "부산광역시"), ("대구", "대구광역시"),
        ("인천", "인천광역시"), ("광주", "전라남도"), ("대전", "대전광역시"),
        ("울산", "울산광역시"), ("세종", "세종특별자치시"), ("경기", "경기도"),
        ("강원", "강원도"), ("충청북", "충청북도"), ("충북", "충청북도"),
        ("충청남", "충청남도"), ("충남", "충청남도"), ("전라북", "전라북도"),
        ("전북", "전라북도"), ("전라남", "전라남도"), ("전남", "전라남도"),
        ("경상북", "경상북도"), ("경북", "경상북도"), ("경상남", "경상남도"),
        ("경남", "경상남도"), ("제주", "제주특별자치도"),
    )
    for keyword, province in province_keywords:
        if keyword in name:
            return province
    return None


def _rate(completed: int, denominator: int, records: int, empty_label: str) -> str:
    if denominator == 0:
        return "대상 없음"
    if records == 0:
        return empty_label
    return f"{completed / denominator * 100:.1f}%"


def _fitness_deviation_band(deviation: float) -> int:
    """전체 충족률 대비 편차를 5개 색상 구간(단위: %p)으로 나눕니다."""
    if deviation <= -5:
        return 0
    if deviation < -2.5:
        return 1
    if deviation < 2.5:
        return 2
    if deviation < 5:
        return 3
    return 4


def _fitness_mean_figure(round_means: pd.DataFrame) -> go.Figure | None:
    """가장 최근 회차의 종목별 평균을 단위별 축을 가진 막대 차트로 만듭니다."""
    event_codes = list(EVENTS)
    if round_means.empty or not {"ROUND", "MEASURED", *event_codes}.issubset(round_means.columns):
        return None
    available = round_means.dropna(subset=["ROUND"]).sort_values("ROUND")
    if available.empty:
        return None

    latest = available.iloc[-1]
    figure = make_subplots(rows=1, cols=4, horizontal_spacing=0.08)
    for index, (event, (label, unit)) in enumerate(EVENTS.items()):
        value = pd.to_numeric(latest[event], errors="coerce")
        has_value = pd.notna(value)
        value = float(value) if has_value else 0.0
        column = index + 1
        figure.add_trace(
            go.Bar(
                x=[label],
                y=[value],
                marker_color=CHART_PALETTE[index % len(CHART_PALETTE)],
                width=0.58,
                text=[f"{value:,.1f}" if has_value else "자료 없음"],
                textposition="outside",
                textfont=dict(size=9),
                cliponaxis=False,
                hovertemplate=(
                    f"{label} 평균: %{{y:,.1f}} {unit}<extra></extra>"
                    if has_value
                    else "표시할 평균 자료가 없습니다.<extra></extra>"
                ),
            ),
            row=1,
            col=column,
        )
        figure.update_xaxes(
            showgrid=False,
            showticklabels=True,
            tickfont=dict(size=9, color=LIGHT_TEXT),
            tickvals=[label],
            ticktext=[
                {
                    "근력": "근력<br>(%)",
                    "근지구력": "근지구<br>력<br>(회)",
                    "심폐지구력": "심폐<br>지구력<br>(mL/kg/min)",
                    "유연성": "유연성<br>(cm)",
                }[label]
            ],
            ticks="",
            fixedrange=True,
            row=1,
            col=column,
        )
        figure.update_yaxes(
            range=[0, max(value * 1.4, 1)] if has_value else [0, 1],
            visible=False,
            fixedrange=True,
            row=1,
            col=column,
        )

    figure.update_layout(
        height=270,
        margin=dict(l=8, r=8, t=35, b=46),
        bargap=0.42,
        showlegend=False,
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=LIGHT_TEXT),
    )
    return figure


def _render_fitness_means(round_means: pd.DataFrame) -> None:
    st.markdown("#### 종목별 체력 평균")
    chart = _fitness_mean_figure(round_means)
    if chart is None:
        st.info("표시할 회차별 체력 평균 자료가 없습니다.")
        return
    latest = round_means.dropna(subset=["ROUND"]).sort_values("ROUND").iloc[-1]
    st.caption(f"{int(latest['ROUND'])}차 측정 · 유효 측정 {int(latest['MEASURED']):,}명")
    st.plotly_chart(
        chart,
        width="stretch",
        key="home-fitness-event-means",
        config={"displayModeBar": False},
    )


def _render_kpis(
    total: int,
    injury_total: int,
    non_safe_count: int | None,
    completion_counts: dict[str, int] | None,
) -> None:
    if non_safe_count is None:
        non_safe = 0
        risk_value = "기록 없음"
        risk_detail = "미달 확률 자료 확인 필요"
        st.warning("체력 위험인원 자료를 불러오지 못했습니다.")
    else:
        non_safe = non_safe_count
        risk_value = f"{non_safe / max(total, 1) * 100:.1f}%"
        risk_detail = f"{non_safe:,}명 · 안전 제외"

    if completion_counts is None:
        counts = dict.fromkeys(["fitness_records", "fitness_completed", "injury_records", "injury_completed"], 0)
        st.warning("후속조치 완료율 자료를 불러오지 못했습니다.")
    else:
        counts = completion_counts
    fitness_completion = (_rate(counts["fitness_completed"], non_safe, counts["fitness_records"], "기록 없음")
                          if non_safe else "기록 없음")
    fitness_detail = f'경계1~3등급 {non_safe:,}명 기준 · 안전 제외' if non_safe else "미달 확률 자료 확인 필요"
    injury_completion = _rate(counts["injury_completed"], injury_total, counts["injury_records"], "0.0%")
    values = [
        ("체력 후속조치 완료율", fitness_completion, fitness_detail),
        ("부상 후속조치 완료율", injury_completion, "부상별 최신 후속조치 완료 상태 기준"),
        ("체력관리 위험인원 비율", risk_value, risk_detail),
    ]
    cards = []
    card_colors = ["#F15B70", "#16C79A", "#2589FF"]
    for (label, value, detail), color in zip(values, card_colors):
        cards.append(
            f"<article class='home-readiness-card' style='--card-accent:{color}'>"
            f"<div class='home-readiness-card__label'>{html.escape(label)}</div>"
            f"<div class='home-readiness-card__value'>{html.escape(value)}</div>"
            f"<div class='home-readiness-card__detail'>{html.escape(detail)}</div>"
            "</article>"
        )
    st.markdown(
        "<section class='home-readiness-banner'>"
        "<div class='home-readiness-banner__copy'>"
        "<div class='home-readiness-banner__eyebrow'>DEFENSE READINESS</div>"
        "<div class='home-readiness-banner__title'>전투체력·부상 관리 종합 현황</div>"
        "<div class='home-readiness-banner__description'>준비된 오늘, 더 안전한 내일입니다.</div>"
        "</div>"
        "<div class='home-readiness-banner__cards'>"
        + "".join(cards)
        + "</div></section>",
        unsafe_allow_html=True,
    )


def _render_fitness_variance(unit: pd.DataFrame) -> None:
    with st.container(border=True, height="content"):
        st.subheader("지역별 체력 기준 충족률 편차")
        st.caption("전체 장병 기준 충족률과의 차이(%p)를 2.5%p 간격으로 색상 구분합니다.")
        unit = unit.assign(
            지역=unit["REGION_NAME"].map(_province_of),
            충족인원=unit["충족률"] / 100 * unit["인원"],
        )
        unmapped = sorted(unit.loc[unit["지역"].isna(), "REGION_NAME"].astype(str).unique())
        if unmapped:
            st.warning(f"시·도 경계에 매칭되지 않은 지역이 있어 지도에서 제외했습니다: {', '.join(unmapped)}")
            unit = unit.dropna(subset=["지역"])
        if unit.empty:
            st.info("지도에 표시할 지역 데이터가 없습니다.")
            return
        region = unit.groupby("지역", as_index=False).agg(
            인원=("인원", "sum"),
            충족인원=("충족인원", "sum"),
            포함지역=("REGION_NAME", lambda names: "·".join(sorted(set(map(str, names))))),
        )
        region["충족률"] = region["충족인원"] / region["인원"].clip(lower=1) * 100
        overall_rate = region["충족인원"].sum() / max(region["인원"].sum(), 1) * 100
        region["편차"] = region["충족률"] - overall_rate
        region["편차구간"] = region["편차"].map(_fitness_deviation_band)
        if not REGION_GEOJSON_PATH.exists():
            st.warning(f"시·도 경계 파일을 찾을 수 없습니다: {REGION_GEOJSON_PATH}")
            return None
        chart = make_choropleth(
            region,
            geojson=REGION_GEOJSON_URL,
            locations="지역",
            featureidkey="properties.name",
            color="편차구간",
            hover_name="지역",
            hover_data={
                "편차구간": False,
                "편차": ":+.1f",
                "충족률": ":.1f",
                "인원": ":,",
                "포함지역": True,
            },
            color_continuous_scale=list(FITNESS_DEVIATION_SCALE),
            range_color=(0, 4),
            labels={
                "편차": "전체 대비 편차(%p)",
                "충족률": "체력 기준 충족률(%)",
                "인원": "인원(명)",
                "포함지역": "포함 지역",
            },
        )
        chart.update_traces(marker=dict(line=dict(width=1.25, color="#FFFFFF")))
        chart.update_geos(
            fitbounds="locations",
            visible=False,
            bgcolor="rgba(0,0,0,0)",
            projection_type="mercator",
            showcountries=False,
            showcoastlines=False,
            domain=dict(x=[0, 0.92], y=[0, 1]),
        )
        chart.update_layout(
            height=600,
            margin=dict(t=4, b=4, l=4, r=36),
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=LIGHT_TEXT),
            hoverlabel=dict(
                bgcolor="#FFFFFF",
                bordercolor=NAVY_BORDER,
                font=dict(color=LIGHT_TEXT, size=12),
            ),
            coloraxis_colorbar=dict(
                title=dict(text="편차(%p)", side="top"),
                orientation="v",
                x=0.935,
                xanchor="left",
                y=0.5,
                yanchor="middle",
                len=0.5,
                thickness=6,
                outlinewidth=0,
                tickvals=[0, 1, 2, 3, 4],
                ticktext=["≤−5", "−5~−2.5", "−2.5~+2.5", "+2.5~+5", "≥+5"],
                tickfont=dict(size=8, color=MUTED_TEXT),
                title_font=dict(size=9, color=LIGHT_TEXT),
            ),
            dragmode=False,
        )  # 지도 드래그 이동 막기(클릭 선택은 유지)
        selection = st.plotly_chart(
            chart,
            width="stretch",
            key="home-region-map",
            on_select="rerun",
            selection_mode="points",
            config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
        )
        points = getattr(getattr(selection, "selection", None), "points", [])
        if points:
            selected = points[0].get("location")
            if selected is None:
                customdata = points[0].get("customdata", [])
                selected = customdata[0] if customdata else None
            if selected in set(region["지역"]):
                if st.session_state.get("home_selected_region") != selected:
                    st.session_state["home_selected_region"] = selected
                    st.session_state["home_selected_unit"] = None
                    st.session_state["home_unit_page"] = 0
                return selected
        stored_region = st.session_state.get("home_selected_region")
        if stored_region not in set(region["지역"]):
            st.session_state["home_selected_region"] = None
            st.session_state["home_selected_unit"] = None
            st.session_state["home_unit_page"] = 0
            return None
        return stored_region


def _pie(
    data: pd.DataFrame,
    names: str,
    title: str,
    colors=None,
    show_legend: bool = False,
    center_text: str | None = None,
    height: int = 160,
    legend_position: str = "left",
    title_size: str | None = None,
    show_percent: bool = True,
    *,
    key: str,
) -> None:
    PieChartWidget(
        data=data,
        names=names,
        title=title,
        colors=colors,
        show_legend=show_legend,
        center_text=center_text,
        height=height,
        legend_position=legend_position,
        title_size=title_size,
        show_percent=show_percent,
        key=key,
    ).render()
    return


def _scope_summary(units: pd.DataFrame) -> dict:
    """부대 집계 행들을 더해 인원, 체력 수준(4종목 중 가장 낮은 등급) 분포, 2종목 이상 미달 인원을 만듭니다."""
    counts = [int(units[f"LEVEL_{level}"].sum()) for level in range(1, 5)]
    return {
        "total": int(units["인원"].sum()),
        "grades": pd.DataFrame({"등급": FITNESS_LEVELS, "인원": counts}),
        "under": int(units["MULTIPLE_FAILED"].sum()),
    }


def _precompute_scope_summaries(unit: pd.DataFrame) -> dict[str, dict]:
    """전체·지역(시·도)·부대 요약을 부대 집계(약 20행)에서 미리 만들어 둡니다."""
    prepared = unit.assign(_지역=unit["REGION_NAME"].map(_province_of))
    summaries = {"전체": _scope_summary(prepared)}
    for region_name, region_data in prepared.dropna(subset=["_지역"]).groupby("_지역"):
        summaries[f"지역::{region_name}"] = _scope_summary(region_data)
        for unit_name, unit_data in region_data.groupby("UNIT_NAME"):
            summaries[f"부대::{region_name}::{unit_name}"] = _scope_summary(unit_data)
    return summaries


def _comparison_scopes(
    summaries: dict[str, dict],
    selected_region: str | None,
    selected_unit: str | None,
) -> tuple[tuple[str, dict], tuple[str, dict]] | None:
    if selected_region is None:
        return None

    province = summaries.get(f"지역::{selected_region}")
    if province is None:
        return None
    if selected_unit:
        selected = summaries.get(f"부대::{selected_region}::{selected_unit}")
        if selected is None:
            return None
        return (selected_region, province), (selected_unit, selected)
    return (selected_region, province), ("전국", summaries["전체"])


def _default_selected_unit(selected_unit: str | None, visible_units: list[str]) -> str | None:
    if selected_unit in visible_units:
        return selected_unit
    return visible_units[0] if len(visible_units) == 1 else None


def _render_grade_pie(summary: dict, title: str, height: int, key: str) -> None:
    _pie(
        summary["grades"],
        "등급",
        title,
        colors=["#2563EB", "#14B8A6", "#F59E0B", "#F15B70"],
        show_legend=True,
        height=height,
        legend_position="bottom",
        title_size="0.82rem",
        center_text=f'{summary["total"]:,}<br>명',
        key=key,
    )


def _render_multiple_fail_pie(summary: dict, title: str, height: int, key: str) -> None:
    total = summary["total"]
    under_ratio = pd.DataFrame({
        "구분": ["2개 이상 미달", "기준 충족"],
        "인원": [summary["under"], max(total - summary["under"], 0)],
    })
    _pie(
        under_ratio,
        "구분",
        title,
        colors=[CHART_PALETTE[4], CHART_PALETTE[2]],
        show_legend=True,
        height=height,
        legend_position="bottom",
        title_size="0.82rem",
        center_text=f"{total:,}<br>명",
        key=key,
    )


def _render_people_grade(
    unit: pd.DataFrame,
    selected_region: str | None,
    round_means: pd.DataFrame,
) -> None:
    with st.container(border=True, height="content"):
        summaries = _precompute_scope_summaries(unit)
        region_units = unit.copy()
        region_units["지역"] = region_units["REGION_NAME"].map(_province_of)
        visible_units = sorted(
            region_units.loc[region_units["지역"].eq(selected_region), "UNIT_NAME"].dropna().unique()
        ) if selected_region else []

        selected_unit = st.session_state.get("home_selected_unit")
        if selected_region:
            selected_unit = _default_selected_unit(selected_unit, visible_units)
            st.session_state["home_selected_unit"] = selected_unit

        if selected_region:
            st.subheader(selected_region)
            if len(visible_units) == 1:
                st.caption(f"이 지역은 부대가 하나뿐이어서 해당 부대를 자동 선택했습니다: {visible_units[0]}")
            page_size = 4
            page_count = max((len(visible_units) + page_size - 1) // page_size, 1)
            page = min(max(int(st.session_state.get("home_unit_page", 0)), 0), page_count - 1)
            st.session_state["home_unit_page"] = page
            start = page * page_size
            page_units = visible_units[start:start + page_size]
            navigation = st.columns([0.25, 3.5, 0.25])
            with navigation[0]:
                if st.button("‹", key="home-unit-prev", disabled=page == 0):
                    st.session_state["home_unit_page"] = page - 1
                    st.session_state["home_selected_unit"] = None
                    st.rerun()
            with navigation[1]:
                unit_columns = st.columns(max(len(page_units), 1))
                for column, unit_name in zip(unit_columns, page_units):
                    with column:
                        if st.button(
                            unit_name,
                            key=f"home-unit-{selected_region}-{unit_name}",
                            type="primary" if unit_name == selected_unit else "secondary",
                            width="stretch",
                        ):
                            st.session_state["home_selected_unit"] = unit_name
                            st.rerun()
            with navigation[2]:
                if st.button("›", key="home-unit-next", disabled=page >= page_count - 1):
                    st.session_state["home_unit_page"] = page + 1
                    st.session_state["home_selected_unit"] = None
                    st.rerun()
            st.caption(
                f"{selected_unit or selected_region} 기준 · 부대 {start + 1}~{min(start + page_size, len(visible_units))}"
                f" / {len(visible_units)}"
            )
            summary_key = (
                f"부대::{selected_region}::{selected_unit}"
                if selected_unit else f"지역::{selected_region}"
            )
        else:
            st.subheader("전체 장병 정보")
            summary_key = "전체"

        comparison = _comparison_scopes(summaries, selected_region, selected_unit)
        if comparison is None:
            summary = summaries.get(summary_key, summaries["전체"])
            grade_columns = st.columns(2)
            with grade_columns[0]:
                _render_grade_pie(summary, "체력수준 등급 비율", 220, "home-summary-grade")
            with grade_columns[1]:
                _render_multiple_fail_pie(summary, "2개 이상 미달 비율", 220, "home-summary-failure")
            _render_fitness_means(round_means)
            return

        (left_name, left_summary), (right_name, right_summary) = comparison
        st.caption(f"{left_name} · {right_name} 비교")
        grade_columns = st.columns(2)
        with grade_columns[0]:
            _render_grade_pie(left_summary, f"{left_name} 체력수준 등급", 165, "home-compare-grade-left")
        with grade_columns[1]:
            _render_grade_pie(right_summary, f"{right_name} 체력수준 등급", 165, "home-compare-grade-right")
        failure_columns = st.columns(2)
        with failure_columns[0]:
            _render_multiple_fail_pie(
                left_summary, f"{left_name} 2개 이상 미달", 165, "home-compare-failure-left"
            )
        with failure_columns[1]:
            _render_multiple_fail_pie(
                right_summary, f"{right_name} 2개 이상 미달", 165, "home-compare-failure-right"
            )


def _render_injuries(summary: dict, total_soldiers: int) -> None:
    with st.container(border=True, height="content"):
        st.subheader("부상 현황")
        total = max(total_soldiers, 1)
        injured = summary["injured_soldiers"]
        overall = pd.DataFrame({"구분": ["부상", "정상"], "인원": [injured, max(total - injured, 0)]})
        part = summary["locations"].rename(columns={"INJURY_LOCATION": "부상 부위", "INJURIES": "인원"})
        minor = part.loc[part["인원"] < 100, "인원"].sum()
        part = part.loc[part["인원"] >= 100].copy()
        if minor:
            part = pd.concat([part, pd.DataFrame([{"부상 부위": "기타", "인원": int(minor)}])], ignore_index=True)
        severity = summary["severities"].rename(columns={"SEVERITY": "심각도", "INJURIES": "인원"})
        for data, name, title in zip(
            [overall, part, severity],
            ["구분", "부상 부위", "심각도"],
            ["전체 대비 부상 비율", "부상 부위별 비율", "부상 심각도 비율"],
        ):
            _pie(
                data,
                name,
                title,
                show_legend=True,
                center_text=f"{total:,}<br>&#47749;",
                title_size="0.9rem",
                key=f"home-injury-{name}",
            )


def _render_exercise_type(types: pd.DataFrame) -> tuple[int, int] | None:
    with st.container(border=True, height="content"):
        st.subheader("운동 유형")
        selector_columns = st.columns(2)
        with selector_columns[0]:
            selected_grade = st.selectbox(
                "등급",
                [1, 2, 3, 4],
                format_func=lambda value: f"{value}등급",
                key="home-exercise-grade",
            )
        grade_types = types.loc[types["AVERAGE_PERCENTILE_GRADE"].eq(selected_grade)].sort_values("CLUSTER")
        type_options = grade_types["CLUSTER"].astype(int).tolist()
        type_names = dict(zip(grade_types["CLUSTER"].astype(int), grade_types["TYPE_NAME"]))
        with selector_columns[1]:
            selected_cluster = st.selectbox(
                "유형",
                type_options,
                format_func=lambda value: type_names.get(value, f"유형 {value}"),
                key=f"home-exercise-type-{selected_grade}",
            )
        # 백분위는 분석 단계가 전체 측정 안에서 매겨 저장한 값(사용자 결정, 다시 매기지 않음)
        profile = queries.load_home_type_profile(selected_grade, selected_cluster)
        st.caption(type_names.get(selected_cluster, "선택 유형"))
        RadarChartWidget(
            labels=list(FITNESS_ITEM_LABELS.values()),
            values=[float(profile[event]) for event in FITNESS_ITEM_LABELS],
            height=270,
        ).render()
    return selected_grade, selected_cluster


def _render_recommendations(selected_type: tuple[int, int] | None) -> None:
    with st.container(border=True, height="content"):
        st.subheader("운동 추천 리스트")
        if selected_type is None:
            st.info("운동 유형을 선택하면 해당 유형의 추천 운동이 표시됩니다.")
            return
        grade, cluster = selected_type
        try:
            recommendations = load_recommendation(grade, cluster)
        except (OSError,ValueError,KeyError,pd.errors.EmptyDataError,SQLAlchemyError) as error:
            st.info(f'추천 운동 자료를 확인할 수 없습니다: {error}')
            return
        if recommendations.empty:
            st.info("선택한 유형에 연결된 추천 운동 기록이 없습니다.")
            return
        illustrations = {
            '근력': 'strength',
            '근지구력': 'endurance',
            '심폐지구력': 'cardio',
            '유연성': 'flexibility',
        }
        focus = recommendations.sort_values('RECOMMENDATION_RANK').iloc[0].IMPROVEMENT_FOCUS
        image_name = illustrations.get(focus)
        title_columns = st.columns([4, 1], vertical_alignment='center')
        with title_columns[0]:
            st.caption(f'{grade}등급 · {recommendations.TYPE_NAME.iloc[0]}')
        if image_name:
            with title_columns[1]:
                st.image(
                    str(Path(__file__).resolve().parents[1] / 'img' / f'exercise_{image_name}.svg'),
                    caption=f'{focus} 운동 예시',
                    width=90,
                )
        recommendation_columns = st.columns(2)
        for index, row in enumerate(recommendations.itertuples()):
            with recommendation_columns[index % 2]:
                st.markdown(f"**{int(row.RECOMMENDATION_RANK)}. {row.RECOMMENDED_EXERCISE}**")
                st.caption(f"보완 요소: {row.IMPROVEMENT_FOCUS}")


def render_home_overview(
    units: pd.DataFrame,
    injuries: dict,
    types: pd.DataFrame,
    non_safe_count: int | None,
    completion_counts: dict[str, int] | None,
    round_means: pd.DataFrame,
) -> None:
    unit = _unit_table(units)
    total = int(unit["인원"].sum())
    _render_kpis(total, injuries["injuries"], non_safe_count, completion_counts)
    with st.container(key="home-overview-layout"):
        overview_columns = st.columns(3)
        with overview_columns[0]:
            selected_region = _render_fitness_variance(unit)
            selected_type = _render_exercise_type(types)
        with overview_columns[1]:
            _render_people_grade(unit, selected_region, round_means)
            _render_recommendations(selected_type)
        with overview_columns[2]:
            _render_injuries(injuries, total)
            with st.container(border=True,height='content'):
                notice_title,notice_image=st.columns([1,1],vertical_alignment='center')
                with notice_title:
                    st.subheader('알림')
                with notice_image:
                    st.image(str(Path(__file__).resolve().parents[1] / 'img' / 'notification_bell.svg'),width=40)
                st.info('오늘도 체력에 투자하세요. 근육은 적금처럼 쌓이지만, 이자는 땀으로 지급됩니다! 💪')
                st.info("""오늘의 운동: \n
• 팔굽혀펴기(푸시up): 100회 \n
• 윗몸일으키기(시트up): 100회 \n
• 스쿼트: 100회\n
• 달리기(러닝): 매일 10km""")



def _load_home_data() -> tuple[
    pd.DataFrame,
    dict,
    pd.DataFrame,
    int | None,
    dict[str, int] | None,
    pd.DataFrame,
]:
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="dashboard-home") as executor:
        units_future = executor.submit(queries.load_home_units)
        injuries_future = executor.submit(queries.load_home_injuries)
        types_future = executor.submit(queries.load_fitness_types)
        round_means_future = executor.submit(queries.load_round_means)
        non_safe_future = executor.submit(
            _load_optional_non_safe_count,
        )
        completion_future = executor.submit(
            _load_optional_completion_counts,
        )
        return (
            units_future.result(),
            injuries_future.result(),
            types_future.result(),
            non_safe_future.result(),
            completion_future.result(),
            round_means_future.result(),
        )


def render() -> None:
    try:
        units, injuries, types, non_safe_count, completion_counts, round_means = _load_home_data()
    except (ValueError, SQLAlchemyError) as error:
        st.error(f"대시보드 데이터를 불러오지 못했습니다: {error}")
        st.info("DB 접속 정보와 데이터 적재(data/scripts/setup_database.py)를 확인하세요.")
        st.stop()

    if units.empty:
        st.info("현재 조건에 해당하는 장병이 없습니다.")
        st.stop()
    render_home_overview(units, injuries, types, non_safe_count, completion_counts, round_means)
    st.caption("이 화면의 데이터는 개인 진단이나 의학적 판단을 대체하지 않습니다.")


def _load_optional_non_safe_count() -> int | None:
    try:
        return queries.load_non_safe_count(FOLLOWUP_THRESHOLD)
    except (ValueError, KeyError, SQLAlchemyError):
        return None


def _load_optional_completion_counts() -> dict[str, int] | None:
    try:
        # 기록 테이블이 없어도 나머지 홈 화면은 계속 표시합니다.
        return load_completion_counts(FOLLOWUP_THRESHOLD)
    except (ValueError, SQLAlchemyError):
        return None
