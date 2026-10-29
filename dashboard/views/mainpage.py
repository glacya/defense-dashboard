"""대시보드 홈: 체력·부상·후속조치 현황을 native Streamlit으로 표시합니다."""

import html
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.filters import render_filters
from dashboard.common.formatting import FITNESS_ITEM_LABELS, GRADE_LABELS, NAV_STATE_KEY, add_deficiency_flags
from dashboard.common.widgets import PieChartWidget, RadarChartWidget
from dashboard.main_data import load_main_data
from dashboard.py.management_store import load_records

HOME_TITLE = "대시보드 홈"
PALETTE = ["#2589FF", "#16C79A", "#F2A93B", "#F15B70", "#6E7F95"]
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


def _render_page_links() -> None:
    links = [item for item in st.session_state.get(NAV_STATE_KEY, []) if item[0] != HOME_TITLE]
    if not links:
        return
    with st.container(border=True):
        st.markdown("**바로가기**")
        for start in range(0, len(links), 4):
            for column, (title, icon, page) in zip(st.columns(4), links[start:start + 4]):
                with column:
                    st.page_link(page, label=title, icon=icon)


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


def _render_kpis(total: int, managed: int, latest: pd.DataFrame, injuries: pd.DataFrame) -> None:
    ids = set(latest["SOLDIER_ID"])
    scoped_injuries = injuries.loc[injuries["SOLDIER_ID"].isin(ids)]
    followups = load_records("followup_records")
    injury_followups = load_records("injury_followup")
    values = [
        ("체력 후속조치 완료율", _completion_rate(followups, ids, managed), "관리 대상 기준"),
        ("부상 후속조치 완료율", _injury_completion_rate(injury_followups, set(scoped_injuries["INJURY_ID"]), len(scoped_injuries)), "부상 건수 기준"),
        ("체력관리 위험인원 비율", f"{managed / max(total, 1) * 100:.1f}%", f"{managed:,}명"),
    ]
    for column, (label, value, detail) in zip(st.columns(3), values):
        with column:
            with st.container(border=True):
                st.metric(label, value)
                st.caption(detail)


def _render_fitness_variance(unit: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("부대·지역별 체력 편차")
        st.caption(
            "전체 평균 대비 편차입니다. 평균 근처는 초록, 평균보다 낮으면 빨강, 높으면 파랑입니다. "
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
        overall_rate = region["충족인원"].sum() / max(region["인원"].sum(), 1) * 100
        region["편차"] = region["충족률"] - overall_rate
        max_deviation = max(float(region["편차"].abs().max()), 1.0)
        chart = px.choropleth(
            region,
            geojson=_region_geojson(),
            locations="지역",
            featureidkey="properties.name",
            color="편차",
            hover_name="지역",
            hover_data={"편차": ":+.1f", "충족률": ":.1f", "인원": ":,", "포함지역": True},
            color_continuous_scale=[(0.0, "#F15B70"), (0.5, "#16C79A"), (1.0, "#2589FF")],
            range_color=(-max_deviation, max_deviation),
            labels={"편차": "전체 평균 대비 편차(%p)", "충족률": "지역 충족률(%)", "인원": "인원(명)", "포함지역": "포함 지역"},
        )
        chart.update_geos(
            fitbounds="locations", visible=False, bgcolor="#071321",
            projection_type="mercator", showcountries=False,
        )
        chart.update_layout(height=470, margin=dict(t=10, b=10, l=0, r=0),
                            coloraxis_colorbar=dict(title="평균 대비 편차(%p)"))
        st.plotly_chart(chart, width="stretch")


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


def _render_people_grade(latest: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("전체 장병 정보")
        people = latest.drop_duplicates("SOLDIER_ID")
        total = len(people)
        st.metric("전체 장병 수", f"{total:,}명", border=True)
        rows = [{"등급": grade, "인원": sum(
            int((latest[f"등급_{column}"] == grade).sum()) for column in FITNESS_ITEM_LABELS
        )} for grade in GRADE_LABELS]
        _pie(pd.DataFrame(rows), "등급", "전체 등급 비율")


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
            _pie(ratio, "구분", "미달 인원 비율", colors=["#F15B70", "#16C79A"], show_legend=True)


def render_home_overview(filters, measurements: pd.DataFrame, injuries: pd.DataFrame) -> None:
    latest, total, under, managed, _ = _metrics(filters, measurements)
    unit = _unit_table(latest)
    _render_kpis(total, managed, latest, injuries)
    overview_columns = st.columns([2, 1])
    with overview_columns[0]:
        _render_fitness_variance(unit)
    with overview_columns[1]:
        _render_people_grade(latest)
    _render_injuries(injuries, set(latest["SOLDIER_ID"]))
    _render_exercise_and_shortlist(latest)


def render() -> None:
    st.caption("장병 체력관리 / 홈")
    st.title("대시보드 홈")
    st.write("부대별 체력·부상 현황과 후속조치 진행 상황을 확인합니다.")
    try:
        measurements, injuries = load_main_data()
    except (FileNotFoundError, ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        st.error(f"대시보드 데이터를 불러오지 못했습니다: {error}")
        st.info("먼저 프로젝트 루트에서 데이터 파이프라인의 합성 단계를 실행해 장병 명단과 최종 측정 데이터를 생성하세요.")
        st.stop()

    _render_page_links()
    filters = render_filters(measurements, prefix="home", show_bmi=False, show_date=False, show_controls=False)
    if filters.scoped.empty:
        st.info("현재 필터 조건에 해당하는 장병이 없습니다.")
        st.stop()
    render_home_overview(filters, measurements, injuries)
    st.caption("이 화면의 데이터는 개인 진단이나 의학적 판단을 대체하지 않습니다.")
