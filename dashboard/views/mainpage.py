"""대시보드 홈: 체력·부상·후속조치 현황을 native Streamlit으로 표시합니다."""

import html
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.common.charts import CHART_CONTINUOUS_SCALE, CHART_PALETTE, show_plotly
from dashboard.common.formatting import FITNESS_ITEM_LABELS, GRADE_LABELS
from dashboard.common.widgets import PieChartWidget, RadarChartWidget
from dashboard.py import queries
from dashboard.py.followup_probability import FOLLOWUP_THRESHOLD
from dashboard.py.management_store import load_completion_counts

PALETTE = list(CHART_PALETTE)
FITNESS_LEVELS = ["1등급", "2등급", "3등급", "4등급"]
REGION_GEOJSON_PATH = Path(__file__).resolve().parents[1] / "assets" / "geojson" / "korea_provinces.geojson"
# 지도는 9개 도 단위로 그립니다. 특별시·광역시·특별자치시는 둘러싼 도에 편입합니다.
# (경도 최소, 경도 최대, 위도 최소, 위도 최대) — 서로 겹치지 않는 도식 지도용 사각형
PROVINCE_BOXES = {
    "경기": (126.4, 127.7, 36.9, 38.0),
    "강원": (127.7, 129.2, 36.9, 38.5),
    "충남": (125.9, 127.3, 35.95, 36.9),
    "충북": (127.3, 128.4, 35.7, 36.9),
    "경북": (128.4, 129.6, 35.7, 36.9),
    "전북": (126.3, 127.3, 35.0, 35.95),
    "경남": (127.3, 129.3, 34.7, 35.7),
    "전남": (125.9, 127.3, 34.2, 35.0),
    "제주": (126.1, 126.9, 33.1, 33.65),
}
# REGION_NAME에 키워드가 포함되면 해당 도로 묶습니다. 위에서부터 먼저 맞는 항목을 사용하므로 순서를 바꾸지 마세요.
# 정식 명칭(경기도, 서울특별시 …)과 줄임말(경기, 서울 …)을 모두 처리합니다.
PROVINCE_KEYWORDS = (
    ("전남광주", "전남"),  # 전남광주통합특별시: '광주'보다 먼저 확인
    ("서울", "경기"), ("인천", "경기"), ("경기", "경기"),
    ("강원", "강원"),
    ("충청북", "충북"), ("충북", "충북"),
    ("충청남", "충남"), ("충남", "충남"), ("대전", "충남"), ("세종", "충남"),
    ("전라북", "전북"), ("전북", "전북"),
    ("전라남", "전남"), ("전남", "전남"), ("광주", "전남"),
    ("경상북", "경북"), ("경북", "경북"), ("대구", "경북"),
    ("경상남", "경남"), ("경남", "경남"), ("부산", "경남"), ("울산", "경남"),
    ("제주", "제주"),
)


class MainPieChart(PieChartWidget):
    """메인 대시보드에서 사용하는 파이차트 위젯."""


class MainRadarChart(RadarChartWidget):
    """메인 대시보드에서 사용하는 개인 운동유형 위젯."""


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
        ("인천", "인천광역시"), ("광주", "광주광역시"), ("대전", "대전광역시"),
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


@st.cache_data
def _region_geojson() -> dict:
    """dashboard/assets/geojson의 실제 시·도 경계를 읽습니다."""
    if not REGION_GEOJSON_PATH.exists():
        raise FileNotFoundError(f"GeoJSON 파일을 찾을 수 없습니다: {REGION_GEOJSON_PATH}")
    with REGION_GEOJSON_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _rate(completed: int, denominator: int, records: int, empty_label: str) -> str:
    if denominator == 0:
        return "대상 없음"
    if records == 0:
        return empty_label
    return f"{completed / denominator * 100:.1f}%"


def _render_kpis(total: int, injury_total: int) -> None:
    try:
        non_safe = queries.load_non_safe_count(FOLLOWUP_THRESHOLD)
        risk_value = f"{non_safe / max(total, 1) * 100:.1f}%"
        risk_detail = f"{non_safe:,}명 · 안전 제외"
    except (ValueError, KeyError, SQLAlchemyError):
        non_safe = 0
        risk_value = "기록 없음"
        risk_detail = "미달 확률 자료 확인 필요"
    try:
        # 기록 테이블이 아직 없으면(SQLAlchemyError) 완료율만 비워 두고 홈 화면은 계속 보여 준다.
        counts = load_completion_counts(FOLLOWUP_THRESHOLD)
    except (ValueError, SQLAlchemyError):
        counts = dict.fromkeys(["fitness_records", "fitness_completed", "injury_records", "injury_completed"], 0)
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
        "<div class='home-readiness-banner__title'>전투준비태세 종합 현황</div>"
        "<div class='home-readiness-banner__description'>준비된 오늘, 더 안전한 내일입니다.</div>"
        "</div>"
        "<div class='home-readiness-banner__cards'>"
        + "".join(cards)
        + "</div></section>",
        unsafe_allow_html=True,
    )


def _render_fitness_variance(unit: pd.DataFrame) -> None:
    with st.container(border=True, height=455):
        st.subheader("부대·지역별 체력 편차")
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
        chart = px.choropleth(
            region,
            geojson=_region_geojson(),
            locations="지역",
            featureidkey="properties.name",
            color="충족률",
            hover_name="지역",
            hover_data={"충족률": ":.1f", "인원": ":,", "포함지역": True},
            color_continuous_scale=list(CHART_CONTINUOUS_SCALE),
            range_color=(0, 100),
            labels={"충족률": "체력 충족률(%)", "인원": "인원(명)", "포함지역": "포함 지역"},
        )
        chart.update_traces(marker=dict(line=dict(width=1, color="#FFFFFF")))
        chart.update_geos(
            fitbounds="locations", visible=False, bgcolor="#EAF2F9",
            projection_type="mercator", showcountries=False,
        )
        chart.update_layout(height=360, margin=dict(t=8, b=8, l=4, r=4),
                            coloraxis_colorbar=dict(title="충족률(%)"))
        selection = st.plotly_chart(
            chart,
            width="stretch",
            key="home-region-map",
            on_select="rerun",
            selection_mode="points",
            config={"displayModeBar": False},
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
) -> None:
    MainPieChart(
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
    ).render()
    return

    st.subheader(title)
    palette = colors or PALETTE
    labels = data[names].astype(str).tolist()
    color_map = {label: palette[index % len(palette)] for index, label in enumerate(labels)}
    figure = px.pie(data, names=names, values="인원", hole=0.55, color=names,
                    color_discrete_map=color_map)
    figure.update_traces(textinfo="none")
    figure.update_layout(height=330, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
    st.plotly_chart(figure, width="stretch")
    if show_legend:
        total = max(float(data["인원"].sum()), 1.0)
        legend = []
        for index, row in data.reset_index(drop=True).iterrows():
            label = str(row[names])
            count = int(row["인원"])
            percent = count / total * 100
            color = color_map[label]
            legend.append(
                f"<div style='display:flex;justify-content:space-between;gap:8px;line-height:1.7'>"
                f"<span><span style='display:inline-block;width:10px;height:10px;background:{color};"
                f"border-radius:2px;margin-right:6px'></span>{html.escape(label)}</span>"
                f"<span>{count:,}명 ({percent:.1f}%)</span></div>"
            )
        st.markdown("<div style='font-size:.78rem'>" + "".join(legend) + "</div>", unsafe_allow_html=True)


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


def _render_people_grade(unit: pd.DataFrame, selected_region: str | None) -> None:
    with st.container(border=True, height="content"):
        summaries = _precompute_scope_summaries(unit)
        region_units = unit.copy()
        region_units["지역"] = region_units["REGION_NAME"].map(_province_of)
        visible_units = sorted(
            region_units.loc[region_units["지역"].eq(selected_region), "UNIT_NAME"].dropna().unique()
        ) if selected_region else []

        selected_unit = st.session_state.get("home_selected_unit")
        if selected_region and selected_unit not in visible_units:
            selected_unit = None
            st.session_state["home_selected_unit"] = None

        if selected_region:
            st.subheader(selected_region)
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

        summary = summaries.get(summary_key, summaries["전체"])
        total = summary["total"]
        grade_columns = st.columns(2)
        with grade_columns[0]:
            _pie(
                summary["grades"],
                "등급",
                "체력수준 등급 비율",
                colors=["#2563EB", "#14B8A6", "#F59E0B", "#F15B70"],
                show_legend=True,
                height=220,
                legend_position="bottom",
                title_size="0.9rem",
                center_text=f"{total:,}<br>명",
            )
        with grade_columns[1]:
            under = summary["under"]
            under_ratio = pd.DataFrame({"구분": ["2개 이상 미달", "기준 충족"], "인원": [under, max(total - under, 0)]})
            _pie(
                under_ratio,
                "구분",
                "2개 이상 미달 비율",
                colors=[CHART_PALETTE[4], CHART_PALETTE[2]],
                show_legend=True,
                height=220,
                legend_position="bottom",
                title_size="0.9rem",
                center_text=f"{total:,}<br>명",
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
            )


def _render_exercise_type(types: pd.DataFrame) -> tuple[int, int] | None:
    with st.container(border=True, height="content"):
        st.subheader("운동유형")
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
        MainRadarChart(
            labels=list(FITNESS_ITEM_LABELS.values()),
            values=[float(profile[event]) for event in FITNESS_ITEM_LABELS],
            height=270,
        ).render()
    return selected_grade, selected_cluster


def _render_recommendations(types: pd.DataFrame, selected_type: tuple[int, int] | None) -> None:
    with st.container(border=True, height="content"):
        st.subheader("운동추천리스트")
        if selected_type is None:
            st.info("운동 유형을 선택하면 해당 유형의 추천 운동이 표시됩니다.")
            return
        grade, cluster = selected_type
        selected_name = types.loc[
            types["AVERAGE_PERCENTILE_GRADE"].eq(grade) & types["CLUSTER"].eq(cluster), "TYPE_NAME"
        ].iloc[0]
        st.caption(selected_name)
        recommendations = queries.load_home_type_prescriptions(grade, cluster)
        if recommendations.empty:
            st.info("선택한 유형에 연결된 추천 운동 기록이 없습니다.")
            return
        recommendation_columns = st.columns(2)
        for index, row in enumerate(recommendations.itertuples()):
            with recommendation_columns[index % 2]:
                st.markdown(f"**{row.EXERCISE}**")
                st.caption(f"해당 유형 처방 {int(row.PRESCRIPTIONS):,}건")


def render_home_overview(units: pd.DataFrame) -> None:
    unit = _unit_table(units)
    total = int(unit["인원"].sum())
    injuries = queries.load_home_injuries()
    types = queries.load_fitness_types()
    _render_kpis(total, injuries["injuries"])
    overview_columns = st.columns(3)
    with overview_columns[0]:
        selected_region = _render_fitness_variance(unit)
        selected_type = _render_exercise_type(types)
    with overview_columns[1]:
        _render_people_grade(unit, selected_region)
        _render_recommendations(types, selected_type)
    with overview_columns[2]:
        _render_injuries(injuries, total)


def render() -> None:
    try:
        units = queries.load_home_units()
    except (ValueError, SQLAlchemyError) as error:
        st.error(f"대시보드 데이터를 불러오지 못했습니다: {error}")
        st.info("DB 접속 정보와 데이터 적재(data/scripts/setup_database.py)를 확인하세요.")
        st.stop()
    if units.empty:
        st.info("현재 조건에 해당하는 장병이 없습니다.")
        st.stop()
    render_home_overview(units)
    st.caption("이 화면의 데이터는 개인 진단이나 의학적 판단을 대체하지 않습니다.")
