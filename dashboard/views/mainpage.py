"""대시보드 홈: 체력·부상·후속조치 현황을 native Streamlit으로 표시합니다."""

import html
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.charts import CHART_CONTINUOUS_SCALE, CHART_PALETTE, show_plotly
from dashboard.common.filters import render_filters
from dashboard.common.formatting import FITNESS_ITEM_LABELS, GRADE_LABELS, add_deficiency_flags
from dashboard.common.widgets import PieChartWidget, RadarChartWidget
from dashboard.main_data import load_main_data
from dashboard.py.followup_probability import load_probabilities
from dashboard.py.management_store import load_records

PALETTE = list(CHART_PALETTE)
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


def _metrics(filters, measurements: pd.DataFrame):
    latest = add_deficiency_flags(filters.scoped)
    total = int(latest["SOLDIER_ID"].nunique())
    under = int(latest.loc[latest["체력미달"], "SOLDIER_ID"].nunique())
    managed = int(latest.loc[latest["관리대상"], "SOLDIER_ID"].nunique())
    return latest, total, under, managed, int(measurements["MESURE_DE"].nunique())


def _unit_table(latest: pd.DataFrame) -> pd.DataFrame:
    unit = latest.groupby(["REGION_NAME", "UNIT_NAME"]).agg(
        인원=("SOLDIER_ID", "nunique"), 미달=("체력미달", "sum")
    ).reset_index()
    unit["미달"] = unit["미달"].astype(int)
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


def _completion_rate(records: pd.DataFrame, ids: set[str], denominator: int) -> str:
    if denominator == 0 or records.empty:
        return "기록 없음"
    scoped = records.loc[records["SOLDIER_ID"].isin(ids) & records["STATUS"].ne("취소")]
    completed = scoped.loc[scoped["STATUS"].eq("완료"), "SOLDIER_ID"].nunique()
    return f"{completed / denominator * 100:.1f}%"


def _injury_completion_rate(records: pd.DataFrame, injury_ids: set[str], denominator: int) -> str:
    if denominator == 0 or records.empty:
        return "기록 없음"
    scoped = records.loc[records["INJURY_ID"].isin(injury_ids)]
    completed = scoped.loc[scoped["RECOVERY_STATUS"].eq("회복 확인"), "INJURY_ID"].nunique()
    return f"{completed / denominator * 100:.1f}%"


def _non_safe_count(soldier_ids: set[str]) -> int:
    """다음 체력검정 미달 확률이 안전(30% 미만)이 아닌 장병 수를 계산합니다."""
    probabilities = load_probabilities()
    scoped = probabilities.loc[probabilities["SOLDIER_ID"].isin(soldier_ids)]
    return int(scoped.loc[scoped["RISK_LEVEL"].ne("안전"), "SOLDIER_ID"].nunique())


def _render_kpis(total: int, managed: int, latest: pd.DataFrame, injuries: pd.DataFrame) -> None:
    ids = set(latest["SOLDIER_ID"])
    scoped_injuries = injuries.loc[injuries["SOLDIER_ID"].isin(ids)]
    followups = load_records("followup_records")
    injury_followups = load_records("injury_followup")
    try:
        non_safe = _non_safe_count(ids)
        risk_value = f"{non_safe / max(total, 1) * 100:.1f}%"
        risk_detail = f"{non_safe:,}명 · 안전 제외"
    except (OSError, ValueError, KeyError, UnicodeDecodeError, pd.errors.ParserError):
        risk_value = "기록 없음"
        risk_detail = "미달 확률 자료 확인 필요"
    values = [
        ("체력 후속조치 완료율", _completion_rate(followups, ids, managed), "관리 대상 기준"),
        ("부상 후속조치 완료율", _injury_completion_rate(injury_followups, set(scoped_injuries["INJURY_ID"]), len(scoped_injuries)), "부상 건수 기준"),
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
    with st.container(border=True):
        st.subheader("부대·지역별 체력 편차")
        st.caption(
            "지역별 체력 충족률을 표시합니다. 낮은 값은 연한 파랑, 높은 값은 짙은 청록·남색으로 구분합니다. "
            "실제 시·도 경계 GeoJSON을 사용합니다."
        )
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
        chart.update_layout(height=470, margin=dict(t=20, b=20, l=10, r=10),
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


def _pie(data: pd.DataFrame, names: str, title: str, colors=None, show_legend: bool = False) -> None:
    MainPieChart(
        data=data,
        names=names,
        title=title,
        colors=colors,
        show_legend=show_legend,
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


def _fitness_level_distribution(data: pd.DataFrame) -> pd.DataFrame:
    """네 종목 중 가장 낮은 등급을 장병별 체력수준(1~4등급)으로 집계합니다."""
    grade_order = ["1등급", "2등급", "3등급", "미달"]
    grade_rank = {grade: index for index, grade in enumerate(grade_order)}
    grade_columns = [f"등급_{column}" for column in FITNESS_ITEM_LABELS]
    levels = data[grade_columns].apply(
        lambda row: max(row.map(grade_rank).tolist()), axis=1
    ).map({index: label for index, label in enumerate(["1등급", "2등급", "3등급", "4등급"])})
    counts = levels.value_counts().reindex(["1등급", "2등급", "3등급", "4등급"], fill_value=0)
    return counts.rename_axis("등급").reset_index(name="인원")


def _two_or_more_deficiencies(data: pd.DataFrame) -> int:
    deficiency_columns = [f"미달_{column}" for column in FITNESS_ITEM_LABELS]
    return int(data[deficiency_columns].sum(axis=1).ge(2).sum())


def _render_people_grade(
    latest: pd.DataFrame,
    unit: pd.DataFrame,
    selected_region: str | None,
) -> None:
    with st.container(border=True):
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
            if selected_unit:
                scoped = latest.loc[
                    latest["UNIT_NAME"].eq(selected_unit)
                    & latest["REGION_NAME"].map(_province_of).eq(selected_region)
                ]
            else:
                scoped = latest.loc[latest["REGION_NAME"].map(_province_of).eq(selected_region)]
        else:
            st.subheader("전체 장병 정보")
            scoped = latest

        total = int(scoped["SOLDIER_ID"].nunique())
        st.metric("대상 장병 수", f"{total:,}명", border=True)
        grade_columns = st.columns(2)
        with grade_columns[0]:
            _pie(_fitness_level_distribution(scoped), "등급", "체력수준 등급 비율")
        with grade_columns[1]:
            under = _two_or_more_deficiencies(scoped)
            under_ratio = pd.DataFrame({"구분": ["2개 이상 미달", "기준 충족"], "인원": [under, max(total - under, 0)]})
            _pie(under_ratio, "구분", "2개 이상 미달 비율", colors=[CHART_PALETTE[4], CHART_PALETTE[2]], show_legend=True)


def _render_injuries(injuries: pd.DataFrame, ids: set[str]) -> None:
    scoped = injuries.loc[injuries["SOLDIER_ID"].isin(ids)]
    with st.container(border=True):
        st.subheader("부상 현황")
        st.caption(f"현재 조건의 부상 {len(scoped):,}건 · 부상 장병 {scoped['SOLDIER_ID'].nunique():,}명")
        total = max(len(ids), 1)
        overall = pd.DataFrame({"구분": ["부상", "정상"], "인원": [scoped["SOLDIER_ID"].nunique(), max(total - scoped["SOLDIER_ID"].nunique(), 0)]})
        part_counts = scoped["INJURY_LOCATION"].value_counts()
        part = part_counts.rename_axis("부상 부위").reset_index(name="인원")
        minor = part.loc[part["인원"] < 100, "인원"].sum()
        part = part.loc[part["인원"] >= 100].copy()
        if minor:
            part = pd.concat([part, pd.DataFrame([{"부상 부위": "기타", "인원": int(minor)}])], ignore_index=True)
        severity = scoped["SEVERITY"].value_counts().rename_axis("심각도").reset_index(name="인원")
        columns = st.columns(3)
        for column, data, name, title in zip(columns, [overall, part, severity], ["구분", "부상 부위", "심각도"],
                                              ["전체 대비 부상 비율", "부상 부위별 비율", "부상 심각도 비율"]):
            with column:
                _pie(data, name, title, show_legend=True)


def _render_exercise_and_shortlist(latest: pd.DataFrame) -> None:
    rates = pd.DataFrame([{"종목": label, "충족률": 100 - latest[f"미달_{column}"].astype(bool).mean() * 100}
                         for column, label in FITNESS_ITEM_LABELS.items()])
    left, middle, right = st.columns(3)
    with left:
        with st.container(border=True):
            st.subheader("개인 운동유형")
            MainRadarChart(
                labels=rates["종목"].tolist(),
                values=rates["충족률"].tolist(),
            ).render()
    with middle:
        with st.container(border=True):
            st.subheader("운동추천리스트")
            for _, row in rates.sort_values("충족률").head(4).iterrows():
                st.markdown(f"**{row['종목']} 보강 운동**")
                st.caption(f"충족률 {row['충족률']:.1f}% · 전문 지도자와 세부 운동을 상의하세요.")
    with right:
        with st.container(border=True):
            under = int(latest["체력미달"].sum())
            total = max(latest["SOLDIER_ID"].nunique(), 1)
            ratio = pd.DataFrame({"구분": ["미달", "기준 충족"], "인원": [under, max(total - under, 0)]})
            _pie(ratio, "구분", "미달 인원 비율", colors=[CHART_PALETTE[4], CHART_PALETTE[2]], show_legend=True)


def render_home_overview(filters, measurements: pd.DataFrame, injuries: pd.DataFrame) -> None:
    latest, total, under, managed, _ = _metrics(filters, measurements)
    unit = _unit_table(latest)
    _render_kpis(total, managed, latest, injuries)
    overview_columns = st.columns([2, 1])
    with overview_columns[0]:
        selected_region = _render_fitness_variance(unit)
    with overview_columns[1]:
        _render_people_grade(latest, unit, selected_region)
    _render_injuries(injuries, set(latest["SOLDIER_ID"]))
    _render_exercise_and_shortlist(latest)


def render() -> None:
    try:
        measurements, injuries = load_main_data()
    except (FileNotFoundError, ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        st.error(f"대시보드 데이터를 불러오지 못했습니다: {error}")
        st.info("먼저 프로젝트 루트에서 데이터 파이프라인의 합성 단계를 실행해 장병 명단과 최종 측정 데이터를 생성하세요.")
        st.stop()

    filters = render_filters(measurements, prefix="home", show_bmi=False, show_date=False, show_controls=False)
    if filters.scoped.empty:
        st.info("현재 필터 조건에 해당하는 장병이 없습니다.")
        st.stop()
    render_home_overview(filters, measurements, injuries)
    st.caption("이 화면의 데이터는 개인 진단이나 의학적 판단을 대체하지 않습니다.")
