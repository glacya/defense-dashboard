"""대시보드 홈: 체력·부상·후속조치 현황을 native Streamlit으로 표시합니다."""

import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.filters import render_filters
from dashboard.common.formatting import FITNESS_ITEM_LABELS, GRADE_LABELS, NAV_STATE_KEY, add_deficiency_flags
from dashboard.main_data import load_main_data
from dashboard.py.management_store import load_records

HOME_TITLE = "대시보드 홈"
PALETTE = ["#2589FF", "#16C79A", "#F2A93B", "#F15B70", "#6E7F95"]
REGION_COORDS = {
    "서울": (37.5665, 126.9780), "부산": (35.1796, 129.0756), "대구": (35.8714, 128.6014),
    "인천": (37.4563, 126.7052), "광주": (35.1595, 126.8526), "대전": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114), "세종": (36.4800, 127.2890), "경기": (37.2750, 127.0095),
    "강원": (37.8228, 128.1555), "충북": (36.8000, 127.7000), "충남": (36.5184, 126.8000),
    "전북": (35.7175, 127.1530), "전남": (34.8679, 126.9910), "경북": (36.4919, 128.8889),
    "경남": (35.4606, 128.2132), "제주": (33.4996, 126.5312),
}


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
        st.caption("지역별 체력 충족률을 표시합니다. 낮을수록 빨강, 정상 수준은 초록, 높을수록 파랑입니다.")
        region = unit.assign(충족인원=unit["충족률"] * unit["인원"]).groupby("REGION_NAME", as_index=False).agg(
            인원=("인원", "sum"), 충족인원=("충족인원", "sum")
        )
        region["충족률"] = region["충족인원"] / region["인원"].clip(lower=1) * 100
        region["위도"] = region["REGION_NAME"].map(lambda name: next((v[0] for k, v in REGION_COORDS.items() if k in name), None))
        region["경도"] = region["REGION_NAME"].map(lambda name: next((v[1] for k, v in REGION_COORDS.items() if k in name), None))
        region = region.dropna(subset=["위도", "경도"])
        chart = px.scatter_geo(
            region, lat="위도", lon="경도", size="인원", color="충족률", text="REGION_NAME",
            hover_name="REGION_NAME", hover_data={"충족률": ":.1f", "인원": ":,", "위도": False, "경도": False},
            color_continuous_scale=[(0.0, "#F15B70"), (0.5, "#16C79A"), (1.0, "#2589FF")],
            range_color=(0, 100), labels={"충족률": "체력 충족률(%)", "인원": "인원(명)"},
        )
        chart.update_traces(marker=dict(line=dict(width=1, color="#EFF5FB"), sizemin=8), textposition="top center")
        chart.update_geos(
            projection_type="mercator", showland=True, landcolor="#10243A", showocean=True,
            oceancolor="#071321", showcountries=True, countrycolor="#244666",
            lonaxis_range=[124, 130], lataxis_range=[33, 39],
        )
        chart.update_layout(height=470, margin=dict(t=20, b=20, l=10, r=10), coloraxis_colorbar=dict(title="충족률(%)"))
        st.plotly_chart(chart, width="stretch")
        st.dataframe(region[["REGION_NAME", "인원", "충족률"]].sort_values("충족률").rename(columns={
            "REGION_NAME": "지역", "인원": "인원(명)", "충족률": "체력 충족률(%)",
        }), hide_index=True, width="stretch")


def _pie(data: pd.DataFrame, names: str, title: str, colors=None, show_legend: bool = False) -> None:
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
            labels = rates["종목"].tolist()
            values = rates["충족률"].tolist()
            figure = go.Figure(go.Scatterpolar(
                r=values + [values[0]],
                theta=labels + [labels[0]],
                fill="toself",
                line=dict(color="#2589FF", width=2),
                fillcolor="rgba(37, 137, 255, 0.25)",
                name="현재 조건",
            ))
            figure.update_layout(
                height=360,
                margin=dict(t=25, b=20, l=35, r=35),
                showlegend=False,
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%"),
                    angularaxis=dict(direction="clockwise"),
                ),
            )
            st.plotly_chart(figure, width="stretch")
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
    _render_fitness_variance(unit)
    people_columns = st.columns(2)
    with people_columns[0]:
        _render_people_grade(latest)
    with people_columns[1]:
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
