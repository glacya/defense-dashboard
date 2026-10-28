"""장병의 최근 체력 측정과 인적 정보를 살펴보는 Streamlit 대시보드."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import PROCESSED_DIR, SYNTHETIC_DIR
from data.scripts.fitness_standards import GRADE_CUTS, RANGE_STANDARDS

PERSONNEL_PATH = SYNTHETIC_DIR / "SOLDIER_PERSONNEL.csv"
FITNESS_PATH = PROCESSED_DIR / "KS_NFA_PROCESSED.csv"
INJURY_PATH = SYNTHETIC_DIR / "SOLDIER_INJURY.csv"

BMI_CATEGORY_ORDER = ("저체중", "정상", "과체중", "비만")
BMI_COLORS = {
    "저체중": "#438DFF",
    "정상": "#16C79A",
    "과체중": "#F2A93B",
    "비만": "#F15B70",
}
NAVY_BACKGROUND = "#071321"
NAVY_SURFACE = "#10243A"
NAVY_BORDER = "#244666"
LIGHT_TEXT = "#EFF5FB"
MUTED_TEXT = "#C6D3E0"
CYAN_ACCENT = "#25C6D8"
BLUE_ACCENT = "#2589FF"
RANK_CHART_COLORS = ("#438DFF", "#438DFF", "#438DFF", "#438DFF")
RANK_ORDER = ("이병", "일병", "상병", "병장")
PERSONNEL_COLUMNS = {
    "SOLDIER_ID",
    "SOLDIER_NAME",
    "REGION_NAME",
    "UNIT_NAME",
    "RANK_NAME",
}
FITNESS_COLUMNS = {
    "MESURE_ID",
    "SOLDIER_ID",
    "AGE",
    "HEIGHT",
    "WEIGHT",
    "BMI",
    "BODY_FAT_PERCENTAGE",
    "MESURE_DE",
    "STRENGTH",
    "ENDURANCE",
    "CARDIO",
    "FLEXIBILITY",
}
FITNESS_ITEM_LABELS = {
    "STRENGTH": "근력",
    "ENDURANCE": "근지구력",
    "CARDIO": "심폐지구력",
    "FLEXIBILITY": "유연성",
}
FITNESS_ITEM_COLORS = {
    "근력": "#438DFF",
    "근지구력": "#25C6D8",
    "심폐지구력": "#F2A93B",
    "유연성": "#F15B70",
}
NAVIGATION_ITEMS = (
    ("대시보드 홈", ":material/home:"),
    ("부대 현황", ":material/domain:"),
    ("체력 관리", ":material/fitness_center:"),
    ("개인 정보 조회", ":material/person_search:"),
    ("부상 현황", ":material/healing:"),
    ("통계/분석", ":material/analytics:"),
    ("리포트", ":material/description:"),
    ("설정", ":material/settings:"),
)


@st.cache_data(show_spinner=False)
def load_dashboard_data(
    personnel_path: str,
    fitness_path: str,
    personnel_file_version: tuple[int, int],
    fitness_file_version: tuple[int, int],
) -> pd.DataFrame:
    """명단과 측정 데이터를 검증하고 측정 이력 전체를 결합합니다."""
    personnel_file = Path(personnel_path)
    fitness_file = Path(fitness_path)
    if not personnel_file.is_file():
        raise FileNotFoundError(f"장병 명단 파일이 없습니다: {personnel_file}")
    if not fitness_file.is_file():
        raise FileNotFoundError(f"최종 측정 파일이 없습니다: {fitness_file}")

    personnel = pd.read_csv(
        personnel_file, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"}
    )
    fitness = pd.read_csv(
        fitness_file, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"}
    )
    missing_personnel = sorted(PERSONNEL_COLUMNS - set(personnel.columns))
    missing_fitness = sorted(FITNESS_COLUMNS - set(fitness.columns))
    if missing_personnel or missing_fitness:
        missing = []
        if missing_personnel:
            missing.append(f"장병 명단: {', '.join(missing_personnel)}")
        if missing_fitness:
            missing.append(f"측정 데이터: {', '.join(missing_fitness)}")
        raise ValueError(f"필수 컬럼이 없습니다 ({'; '.join(missing)}).")
    if personnel.empty or fitness.empty:
        raise ValueError("장병 명단 또는 측정 데이터가 비어 있습니다.")
    if personnel["SOLDIER_ID"].isna().any() or personnel["SOLDIER_ID"].duplicated().any():
        raise ValueError("장병 명단의 군번은 비어 있지 않고 고유해야 합니다.")
    if fitness["SOLDIER_ID"].isna().any():
        raise ValueError("측정 데이터에 군번이 비어 있는 행이 있습니다.")

    measure_ids = pd.to_numeric(fitness["MESURE_ID"], errors="coerce")
    if measure_ids.isna().any() or measure_ids.duplicated().any():
        raise ValueError("측정 데이터의 MESURE_ID는 유효하고 고유해야 합니다.")
    fitness["MESURE_ID"] = measure_ids.astype("int64")
    fitness["MESURE_DE"] = pd.to_datetime(
        fitness["MESURE_DE"].astype("string"), format="%Y%m%d", errors="coerce"
    )
    if fitness["MESURE_DE"].isna().any():
        raise ValueError("측정 데이터에 형식이 잘못된 측정일(MESURE_DE)이 있습니다.")

    numeric_columns = [
        "AGE",
        "HEIGHT",
        "WEIGHT",
        "BMI",
        "BODY_FAT_PERCENTAGE",
    ]
    for column in numeric_columns:
        fitness[column] = pd.to_numeric(fitness[column], errors="coerce")
    invalid_numeric = fitness[numeric_columns].isna().any(axis=1)
    if invalid_numeric.any():
        raise ValueError(
            f"측정 데이터 {int(invalid_numeric.sum()):,}행에 유효하지 않은 "
            "나이 또는 신체 측정값이 있습니다."
        )
    if (fitness["BMI"] <= 0).any():
        raise ValueError("BMI는 0보다 커야 합니다.")

    missing_personnel_ids = set(fitness["SOLDIER_ID"]) - set(personnel["SOLDIER_ID"])
    if missing_personnel_ids:
        raise ValueError(
            f"측정 데이터에 명단과 연결되지 않는 군번이 "
            f"{len(missing_personnel_ids):,}개 있습니다."
        )

    merged = fitness.merge(
        personnel,
        on="SOLDIER_ID",
        how="left",
        validate="many_to_one",
    )
    merged["BMI구간"] = classify_bmi(merged["BMI"])
    return merged.sort_values(
        ["MESURE_DE", "MESURE_ID"], kind="stable"
    ).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_injury_data(injury_path: str, file_version: tuple[int, int]) -> pd.DataFrame:
    """부상 기록을 검증하고 표시용 한글 컬럼을 추가합니다."""
    path = Path(injury_path)
    if not path.is_file():
        raise FileNotFoundError(f"부상 기록 파일이 없습니다: {path}")
    injury = pd.read_csv(path, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"})
    required = {"INJURY_ID", "SOLDIER_ID", "INJURY_CATEGORY", "INJURY_LOCATION", "PREVENTABILITY", "SEVERITY"}
    missing = sorted(required - set(injury.columns))
    if missing:
        raise ValueError(f"부상 기록에 필수 컬럼이 없습니다: {', '.join(missing)}")
    if injury["INJURY_ID"].duplicated().any() or injury["SOLDIER_ID"].isna().any():
        raise ValueError("부상 기록의 부상 ID는 고유하고 군번은 비어 있지 않아야 합니다.")
    return injury


def classify_bmi(values: pd.Series) -> pd.Series:
    """BMI를 저체중·정상·과체중·비만 구간으로 분류합니다."""
    return pd.Series(
        np.select(
            [values < 18.5, values < 25, values < 30],
            ["저체중", "정상", "과체중"],
            default="비만",
        ),
        index=values.index,
        dtype="string",
    )


def latest_measurements(
    measurements: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    """기간 안에서 장병별 가장 최근 측정 한 건을 반환합니다."""
    in_range = measurements.loc[
        measurements["MESURE_DE"].between(
            pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        )
    ]
    return (
        in_range.sort_values(["MESURE_DE", "MESURE_ID"], kind="stable")
        .drop_duplicates("SOLDIER_ID", keep="last")
        .reset_index(drop=True)
    )


def summarize_groups(data: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """지역 또는 부대별 인원 및 BMI 구간별 집계를 계산합니다."""
    if data.empty:
        return pd.DataFrame(
            columns=[
                group_column,
                "전체 장병 수",
                "정상 BMI 인원",
                "정상 BMI 비율(%)",
                "과체중·비만 인원",
                "저체중 인원",
            ]
        )

    summary = (
        data.assign(
            _normal=data["BMI구간"].eq("정상"),
            _overweight_obese=data["BMI구간"].isin(["과체중", "비만"]),
            _underweight=data["BMI구간"].eq("저체중"),
        )
        .groupby(group_column, dropna=False)
        .agg(
            **{
                "전체 장병 수": ("SOLDIER_ID", "nunique"),
                "정상 BMI 인원": ("_normal", "sum"),
                "과체중·비만 인원": ("_overweight_obese", "sum"),
                "저체중 인원": ("_underweight", "sum"),
            }
        )
        .reset_index()
    )
    summary["정상 BMI 인원"] = summary["정상 BMI 인원"].astype(int)
    summary["과체중·비만 인원"] = summary["과체중·비만 인원"].astype(int)
    summary["저체중 인원"] = summary["저체중 인원"].astype(int)
    summary["정상 BMI 비율(%)"] = (
        summary["정상 BMI 인원"] / summary["전체 장병 수"] * 100
    ).round(1)
    return summary.sort_values(
        ["전체 장병 수", group_column], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)


def summary_card_callback(categories: tuple[str, ...], card_name: str) -> None:
    """요약 카드를 누르면 장병 목록의 BMI 구간 필터를 설정합니다."""
    st.session_state[filter_state_key("bmi_filter")] = list(categories)
    st.session_state["active_summary_card"] = card_name
    st.session_state["personnel_page"] = 1


def filter_state_key(name: str) -> str:
    """현재 화면별로 분리된 필터 상태 키를 반환합니다."""
    view = st.session_state.get("active_view", "대시보드 홈")
    return f"{name}_{view}"


def reset_unit_selection() -> None:
    """지역이 바뀌면 새 지역 범위의 부대를 모두 선택합니다."""
    units_by_region = st.session_state.get(filter_state_key("units_by_region"), {})
    regions = st.session_state.get(filter_state_key("region_filter"), [])
    st.session_state[filter_state_key("unit_filter")] = sorted(
        {
            unit
            for region in regions
            for unit in units_by_region.get(region, [])
        }
    )


def filter_signature(*values: object) -> str:
    """현재 필터 조합을 표의 선택 상태 키에 사용할 짧은 값으로 변환합니다."""
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()[:12]


def reset_soldier_detail_dismissal() -> None:
    """새 장병 행 선택 시 상세정보 모달을 다시 열 수 있게 합니다."""
    st.session_state["soldier_detail_dismissed_id"] = None


def clear_bmi_chart_selection() -> None:
    """요약 기준이나 분석 단위가 바뀌면 이전 BMI 차트 선택을 지웁니다."""
    st.session_state["bmi_chart_selected_category"] = None
    st.session_state["bmi_chart_selection_key"] = None
    st.session_state["bmi_chart_dismissed_selection_key"] = None


def navigate_to_view(view_name: str) -> None:
    """사이드바 메뉴에서 선택한 화면으로 이동합니다."""
    st.session_state["active_view"] = view_name


def select_bmi_category(
    unit_name: str,
    category: str,
    chart_selection_context: str,
) -> None:
    """부대별 인원 항목을 누르면 해당 BMI 장병 표를 엽니다."""
    selection_key = (unit_name, category, chart_selection_context)
    st.session_state["bmi_chart_selection_key"] = selection_key
    st.session_state["bmi_chart_dismissed_selection_key"] = None
    st.session_state["bmi_chart_selected_category"] = category
    st.session_state["bmi_count_button_clicked"] = True


def dismiss_soldier_detail_dialog() -> None:
    """상세정보 모달을 닫을 때 현재 장병을 기록해 재실행 시 재개방을 막습니다."""
    st.session_state["soldier_detail_dismissed_id"] = st.session_state.get(
        "selected_soldier_id"
    )


def render_soldier_details(
    soldier: pd.Series, history: pd.DataFrame | None = None, injuries: pd.DataFrame | None = None
) -> None:
    """선택 장병의 기본 정보·회차별 변화·부상 이력을 표시합니다."""
    st.markdown(f"### {soldier['SOLDIER_NAME']} · {soldier['RANK_NAME']}")
    st.caption(
        f"{soldier['SOLDIER_ID']} · {soldier['REGION_NAME']} · {soldier['UNIT_NAME']}"
    )
    identity_columns = st.columns(3)
    identity_columns[0].metric("군번", str(soldier["SOLDIER_ID"]))
    identity_columns[1].metric("계급", str(soldier["RANK_NAME"]))
    identity_columns[2].metric("나이", f"{soldier['AGE']:.0f}세")

    measurement_columns = st.columns(3)
    measurement_columns[0].metric(
        "측정일", soldier["MESURE_DE"].strftime("%Y-%m-%d")
    )
    measurement_columns[1].metric("키", f"{soldier['HEIGHT']:.1f} cm")
    measurement_columns[2].metric("체중", f"{soldier['WEIGHT']:.1f} kg")

    fitness_columns = st.columns(3)
    fitness_columns[0].metric("BMI", f"{soldier['BMI']:.1f}")
    fitness_columns[1].metric(
        "체지방률", f"{soldier['BODY_FAT_PERCENTAGE']:.1f}%"
    )
    fitness_columns[2].metric("BMI 구간", str(soldier["BMI구간"]))

    if history is not None:
        soldier_history = add_deficiency_flags(
            history.loc[history["SOLDIER_ID"].eq(soldier["SOLDIER_ID"])].sort_values("MESURE_DE")
        )
        if not soldier_history.empty:
            st.markdown("#### 회차별 체력 측정 변화")
            history_table = soldier_history[[
                "MESURE_DE", "STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY",
                "등급_STRENGTH", "등급_ENDURANCE", "등급_CARDIO", "등급_FLEXIBILITY",
                "체력미달",
            ]].rename(columns={
                "MESURE_DE": "측정일", "STRENGTH": "근력", "ENDURANCE": "근지구력",
                "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성", "등급_STRENGTH": "근력 등급",
                "등급_ENDURANCE": "근지구력 등급", "등급_CARDIO": "심폐지구력 등급",
                "등급_FLEXIBILITY": "유연성 등급", "체력미달": "미달 여부",
            })
            st.dataframe(
                history_table,
                hide_index=True,
                width="stretch",
                column_config={
                    "측정일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    "근력": st.column_config.NumberColumn(format="%.1f"),
                    "근지구력": st.column_config.NumberColumn(format="%.1f"),
                    "심폐지구력": st.column_config.NumberColumn(format="%.1f"),
                    "유연성": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            deficiency_columns = [f"미달_{column}" for column in FITNESS_ITEM_LABELS]
            latest_flags = soldier_history.iloc[-1]
            deficient_items = [
                FITNESS_ITEM_LABELS[column]
                for column in FITNESS_ITEM_LABELS
                if bool(latest_flags[f"미달_{column}"])
            ]
            st.caption("현재 미달 종목: " + (", ".join(deficient_items) if deficient_items else "없음"))

    if injuries is not None:
        soldier_injuries = injuries.loc[injuries["SOLDIER_ID"].eq(soldier["SOLDIER_ID"])].copy()
        st.markdown(f"#### 개인 부상 이력 · {len(soldier_injuries):,}건")
        if soldier_injuries.empty:
            st.info("등록된 부상 이력이 없습니다.")
        else:
            st.dataframe(
                soldier_injuries[["INJURY_ID", "INJURY_CATEGORY", "INJURY_LOCATION", "SEVERITY", "PREVENTABILITY"]].rename(columns={
                    "INJURY_ID": "부상 ID", "INJURY_CATEGORY": "부상 분류", "INJURY_LOCATION": "부위",
                    "SEVERITY": "심각도", "PREVENTABILITY": "예방 가능",
                }),
                hide_index=True,
                width="stretch",
            )


@st.dialog(
    "장병 상세정보",
    width="large",
    on_dismiss=dismiss_soldier_detail_dialog,
)
def show_soldier_detail_dialog(
    soldier: pd.Series, history: pd.DataFrame, injuries: pd.DataFrame
) -> None:
    """장병 목록에서 선택한 장병의 상세정보를 모달로 표시합니다."""
    render_soldier_details(soldier, history, injuries)


def show_bmi_soldiers_panel(
    unit_name: str, category: str, soldiers: pd.DataFrame
) -> None:
    """선택한 부대와 BMI 구간의 장병 목록을 모달 패널로 표시합니다."""

    @st.dialog(f"{unit_name} · BMI 구간별 장병", width="large")
    def show_panel() -> None:
        st.markdown(
            f"**{category} · {len(soldiers):,}명** "
            "(현재 부대·계급·나이·측정 기간 필터 적용)"
        )
        if soldiers.empty:
            st.info("현재 필터 조건에 해당하는 장병이 없습니다.")
        else:
            panel_columns = soldiers[
                [
                    "SOLDIER_ID",
                    "SOLDIER_NAME",
                    "REGION_NAME",
                    "UNIT_NAME",
                    "RANK_NAME",
                    "AGE",
                    "MESURE_DE",
                    "BMI",
                    "BODY_FAT_PERCENTAGE",
                ]
            ].rename(
                columns={
                    "SOLDIER_ID": "군번",
                    "SOLDIER_NAME": "이름",
                    "REGION_NAME": "지역",
                    "UNIT_NAME": "부대",
                    "RANK_NAME": "계급",
                    "AGE": "나이",
                    "MESURE_DE": "측정일",
                    "BMI": "BMI",
                    "BODY_FAT_PERCENTAGE": "체지방률(%)",
                }
            )
            st.caption("목록 왼쪽 선택 칸을 누르면 상세 신체정보가 아래에 표시됩니다.")
            table_event = st.dataframe(
                panel_columns,
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
                key=(
                    "bmi_soldier_table_"
                    f"{filter_signature(category, tuple(soldiers['SOLDIER_ID']))}"
                ),
                column_config={
                    "나이": st.column_config.NumberColumn(format="%d세"),
                    "측정일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    "BMI": st.column_config.NumberColumn(format="%.1f"),
                    "체지방률(%)": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            selected_rows = table_event.selection.rows
            if selected_rows and 0 <= selected_rows[0] < len(soldiers):
                st.divider()
                render_soldier_details(soldiers.iloc[selected_rows[0]])
        if st.button("닫기", width="stretch", type="primary"):
            st.session_state["bmi_chart_selected_category"] = None
            st.session_state["bmi_chart_dismissed_selection_key"] = st.session_state.get(
                "bmi_chart_selection_key"
            )
            st.rerun()

    show_panel()


def add_deficiency_flags(data: pd.DataFrame) -> pd.DataFrame:
    """체력 4종목과 체격 기준을 적용해 미달 플래그를 추가합니다."""
    result = data.copy()
    for column in FITNESS_ITEM_LABELS:
        values = pd.to_numeric(result[column], errors="coerce")
        result[f"미달_{column}"] = values.lt(GRADE_CUTS[column][3])
        result[f"등급_{column}"] = np.select(
            [values.ge(GRADE_CUTS[column][1]), values.ge(GRADE_CUTS[column][2]), values.ge(GRADE_CUTS[column][3])],
            ["1등급", "2등급", "3등급"],
            default="미달",
        )
    for column, (lower, lower_inclusive, upper, upper_inclusive) in RANGE_STANDARDS.items():
        values = pd.to_numeric(result[column], errors="coerce")
        lower_failed = values.lt(lower) if lower_inclusive else values.le(lower)
        upper_failed = values.gt(upper) if upper_inclusive else values.ge(upper)
        result[f"미달_{column}"] = lower_failed | upper_failed
    fitness_flags = [f"미달_{column}" for column in FITNESS_ITEM_LABELS]
    management_flags = fitness_flags + ["미달_BMI", "미달_BODY_FAT_PERCENTAGE"]
    result["체력미달"] = result[fitness_flags].sum(axis=1).ge(2)
    result["관리대상"] = result[management_flags].any(axis=1)
    return result


def add_measurement_rounds(data: pd.DataFrame) -> pd.DataFrame:
    """장병별 측정일 순서로 개인 측정회차를 부여합니다."""
    result = data.sort_values(
        ["SOLDIER_ID", "MESURE_DE", "MESURE_ID"], kind="stable"
    ).copy()
    result["측정회차"] = result.groupby("SOLDIER_ID", sort=False).cumcount() + 1
    return result


def _overview_chart_layout(figure: object, height: int = 300) -> None:
    """홈 요약 차트에 공통 다크 테마를 적용합니다."""
    figure.update_layout(
        height=height,
        margin=dict(l=8, r=18, t=16, b=8),
        template="plotly_dark",
        paper_bgcolor=NAVY_BACKGROUND,
        plot_bgcolor=NAVY_BACKGROUND,
        font=dict(color=LIGHT_TEXT),
        legend=dict(font=dict(color=MUTED_TEXT)),
    )
    figure.update_xaxes(gridcolor=NAVY_BORDER, zerolinecolor=NAVY_BORDER)
    figure.update_yaxes(gridcolor=NAVY_BORDER, zerolinecolor=NAVY_BORDER)


def render_home_overview(
    scoped: pd.DataFrame,
    measurements: pd.DataFrame,
    date_start: date,
    date_end: date,
    selected_regions: list[str],
    selected_units: list[str],
    selected_ranks: list[str],
) -> None:
    """홈에서 전체 인원·회차·미달·관리 대상 현황을 시각화합니다."""
    latest = add_deficiency_flags(scoped)
    total_count = latest["SOLDIER_ID"].nunique()
    underperformers = latest.loc[latest["체력미달"], "SOLDIER_ID"].nunique()
    managed = latest.loc[latest["관리대상"], "SOLDIER_ID"].nunique()
    underperform_rate = underperformers / max(total_count, 1) * 100
    managed_rate = managed / max(total_count, 1) * 100

    st.subheader("전체 현황")
    st.caption("현재 필터의 장병별 최신 측정과 선택 기간의 전체 측정 회차를 함께 집계합니다.")
    cards = [
        ("전체 장병", f"{total_count:,}명", "기준 인원", "total"),
        ("측정 회차", f"{measurements['MESURE_DE'].nunique():,}회", "선택 기간 전체", "normal"),
        ("체력 미달", f"{underperformers:,}명", f"전체의 {underperform_rate:.1f}%", "risk"),
        ("관리 대상", f"{managed:,}명", f"전체의 {managed_rate:.1f}%", "underweight"),
    ]
    card_columns = st.columns(4)
    for column, (label, value, detail, style) in zip(card_columns, cards):
        with column:
            with st.container(border=True, key=f"overview-card-{style}"):
                st.metric(label, value)
                st.caption(detail)

    scoped_history = measurements.loc[
        measurements["MESURE_DE"].between(
            pd.Timestamp(date_start),
            pd.Timestamp(date_end) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1),
        )
        & measurements["REGION_NAME"].isin(selected_regions)
        & measurements["UNIT_NAME"].isin(selected_units)
        & measurements["RANK_NAME"].isin(selected_ranks)
    ].copy()
    scoped_history = add_measurement_rounds(scoped_history)
    round_summary = (
        scoped_history.groupby("측정회차", as_index=False)
        .agg(측정인원=("SOLDIER_ID", "nunique"), 측정건수=("MESURE_ID", "count"))
        .sort_values("측정회차")
    )
    history_with_flags = add_deficiency_flags(scoped_history)
    round_deficiency = (
        history_with_flags.groupby("측정회차", as_index=False)
        .agg(미달인원=("체력미달", "sum"), 관리대상=("관리대상", "sum"))
    )
    round_summary = round_summary.merge(round_deficiency, on="측정회차", how="left")
    recent_round_numbers = set(round_summary["측정회차"].sort_values().tail(3))
    round_summary = round_summary.loc[round_summary["측정회차"].isin(recent_round_numbers)].copy()
    round_summary["측정회차"] = round_summary["측정회차"].astype(int)
    round_summary["회차"] = round_summary["측정회차"].map(lambda value: f"{value}회차")
    round_summary["미달비율"] = round_summary["미달인원"] / round_summary["측정인원"].clip(lower=1) * 100

    chart_columns = st.columns([1.15, 0.85])
    with chart_columns[0]:
        st.markdown("**회차별 측정 인원 및 미달 인원**")
        if round_summary.empty:
            st.info("선택한 조건의 측정 회차가 없습니다.")
        else:
            figure = go.Figure()
            figure.add_trace(go.Bar(
                name="측정인원", x=round_summary["회차"], y=round_summary["측정인원"],
                marker_color=BLUE_ACCENT, hovertemplate="측정 인원: %{y:,}명<extra></extra>",
            ))
            figure.add_trace(go.Bar(
                name="미달인원", x=round_summary["회차"], y=round_summary["미달인원"],
                marker_color="#F15B70", hovertemplate="미달 인원: %{y:,}명<extra></extra>",
            ))
            figure.add_trace(go.Scatter(
                name="미달비율", x=round_summary["회차"], y=round_summary["미달비율"],
                yaxis="y2", mode="lines+markers", line=dict(color="#F2A93B", width=3),
                hovertemplate="미달 비율: %{y:.1f}%<extra></extra>",
            ))
            _overview_chart_layout(figure, 330)
            figure.update_layout(
                barmode="group", xaxis_title=None, yaxis_title="인원",
                yaxis2=dict(title="미달 비율(%)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.12, x=0),
            )
            st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    with chart_columns[1]:
        st.markdown("**현재 체력 판정**")
        status_data = pd.DataFrame({"판정": ["기준 충족", "체력 미달"], "인원": [total_count - underperformers, underperformers]})
        figure = px.pie(
            status_data, names="판정", values="인원", hole=0.62,
            color="판정", color_discrete_map={"기준 충족": "#16C79A", "체력 미달": "#F15B70"},
        )
        _overview_chart_layout(figure, 310)
        figure.update_traces(textinfo="label+percent", textfont_color=LIGHT_TEXT)
        figure.update_layout(showlegend=False)
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    st.markdown("**종목별 미달 현황**")
    item_rows = []
    for column, label in FITNESS_ITEM_LABELS.items():
        count = int(latest[f"미달_{column}"].sum())
        item_rows.append({"종목": label, "미달 인원": count, "미달 비율": count / max(total_count, 1) * 100})
    item_summary = pd.DataFrame(item_rows).sort_values("미달 인원", ascending=True)
    figure = px.bar(
        item_summary, x="미달 인원", y="종목", orientation="h", text="미달 인원",
        color="종목", color_discrete_map=FITNESS_ITEM_COLORS,
        hover_data={"미달 비율": ":.1f"},
    )
    _overview_chart_layout(figure, 270)
    figure.update_traces(texttemplate="%{x:,}명", textposition="outside")
    figure.update_layout(showlegend=False, xaxis_title="미달 인원", yaxis_title=None)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    stat_columns = st.columns(2)
    with stat_columns[0]:
        st.markdown("**종목별 평균 측정값**")
        average_rows = [
            {"종목": label, "평균값": float(pd.to_numeric(latest[column], errors="coerce").mean())}
            for column, label in FITNESS_ITEM_LABELS.items()
        ]
        average_summary = pd.DataFrame(average_rows).sort_values("평균값")
        figure = px.bar(average_summary, x="평균값", y="종목", orientation="h", text="평균값", color="종목", color_discrete_map=FITNESS_ITEM_COLORS)
        _overview_chart_layout(figure, 275)
        figure.update_traces(texttemplate="%{x:.1f}", textposition="outside")
        figure.update_layout(showlegend=False, xaxis_title="평균 측정값", yaxis_title=None)
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    with stat_columns[1]:
        st.markdown("**종목별 등급 분포**")
        grade_rows = []
        for column, label in FITNESS_ITEM_LABELS.items():
            counts = latest[f"등급_{column}"].value_counts()
            grade_rows.extend({"종목": label, "등급": grade, "인원": int(counts.get(grade, 0))} for grade in ["1등급", "2등급", "3등급", "미달"])
        grade_distribution = pd.DataFrame(grade_rows)
        figure = px.bar(grade_distribution, x="종목", y="인원", color="등급", barmode="stack", category_orders={"등급": ["1등급", "2등급", "3등급", "미달"]}, color_discrete_map={"1등급": "#16C79A", "2등급": "#25C6D8", "3등급": "#F2A93B", "미달": "#F15B70"})
        _overview_chart_layout(figure, 275)
        figure.update_layout(xaxis_title=None, yaxis_title="인원")
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    with st.expander("판정 기준 보기"):
        st.caption("체력 미달은 4개 체력 종목 중 2개 이상이 3등급 하한 미만인 경우이며, 관리 대상은 체력 종목 또는 BMI·체지방률 기준을 벗어난 인원입니다.")
        standards = pd.DataFrame([
            {"항목": FITNESS_ITEM_LABELS[column], "미달 기준": f"{GRADE_CUTS[column][3]:g} 미만"}
            for column in FITNESS_ITEM_LABELS
        ] + [
            {"항목": "BMI", "미달 기준": "18.5 미만 또는 25.0 이상"},
            {"항목": "체지방률", "미달 기준": "7.0 이하 또는 27.0 이상"},
        ])
        st.dataframe(standards, hide_index=True, width="stretch")


def render_injury_overview(
    scoped: pd.DataFrame, injuries: pd.DataFrame
) -> None:
    """부상 인원·건수·비율과 체력등급별·개인별 부상 현황을 표시합니다."""
    latest = add_deficiency_flags(scoped)
    total_count = latest["SOLDIER_ID"].nunique()
    scoped_injuries = injuries.loc[injuries["SOLDIER_ID"].isin(latest["SOLDIER_ID"])].copy()
    injured_count = scoped_injuries["SOLDIER_ID"].nunique()
    injury_count = len(scoped_injuries)
    injury_rate = injured_count / max(total_count, 1) * 100

    st.subheader("부상 현황")
    st.caption("현재 필터에 포함된 장병 기준으로 등록된 부상 기록을 집계합니다.")
    card_columns = st.columns(4)
    for column, label, value, detail, style in zip(
        card_columns,
        ["전체 장병", "부상 인원", "부상 건수", "부상 비율"],
        [f"{total_count:,}명", f"{injured_count:,}명", f"{injury_count:,}건", f"{injury_rate:.1f}%"],
        ["기준 인원", "1건 이상 등록", "중복 부상 포함", "부상 인원 / 전체 장병"],
        ["total", "risk", "normal", "underweight"],
    ):
        with column:
            with st.container(border=True, key=f"injury-card-{style}"):
                st.metric(label, value)
                st.caption(detail)

    chart_columns = st.columns(2)
    with chart_columns[0]:
        st.markdown("**부상 분류별 건수**")
        if scoped_injuries.empty:
            st.info("현재 필터에 해당하는 부상 기록이 없습니다.")
        else:
            category_counts = scoped_injuries["INJURY_CATEGORY"].value_counts().rename_axis("부상 분류").reset_index(name="건수")
            figure = px.bar(category_counts, x="건수", y="부상 분류", orientation="h", text="건수", color_discrete_sequence=["#F15B70"])
            _overview_chart_layout(figure, max(260, len(category_counts) * 42 + 90))
            figure.update_traces(texttemplate="%{x:,}건", textposition="outside")
            figure.update_layout(xaxis_title="부상 건수", yaxis_title=None)
            st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    with chart_columns[1]:
        st.markdown("**체력등급별 부상 비교**")
        grade_order = ["미달", "3등급", "2등급", "1등급"]
        latest["종합 체력등급"] = latest[[f"등급_{column}" for column in FITNESS_ITEM_LABELS]].apply(
            lambda row: min(row, key=lambda value: grade_order.index(value)), axis=1
        )
        grade_summary = latest.groupby("종합 체력등급").agg(전체인원=("SOLDIER_ID", "nunique")).reindex(grade_order, fill_value=0).reset_index()
        injured_by_grade = scoped_injuries.groupby("SOLDIER_ID").size().rename("부상건수").to_frame()
        grade_summary["부상인원"] = grade_summary["종합 체력등급"].map(
            latest.loc[latest["SOLDIER_ID"].isin(injured_by_grade.index)].groupby("종합 체력등급")["SOLDIER_ID"].nunique()
        ).fillna(0).astype(int)
        grade_long = grade_summary.melt(id_vars="종합 체력등급", value_vars=["전체인원", "부상인원"], var_name="구분", value_name="인원")
        figure = px.bar(grade_long, x="종합 체력등급", y="인원", color="구분", barmode="group", color_discrete_map={"전체인원": BLUE_ACCENT, "부상인원": "#F15B70"})
        _overview_chart_layout(figure, 310)
        figure.update_layout(xaxis_title=None, yaxis_title="인원")
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    st.markdown("**개인별 부상 내역**")
    if scoped_injuries.empty:
        st.info("현재 필터에 해당하는 개인 부상 내역이 없습니다.")
    else:
        detail = scoped_injuries.merge(
            latest[["SOLDIER_ID", "SOLDIER_NAME", "RANK_NAME", "UNIT_NAME", "종합 체력등급"]].drop_duplicates("SOLDIER_ID"),
            on="SOLDIER_ID", how="left",
        )
        detail = detail.rename(columns={
            "SOLDIER_NAME": "이름", "SOLDIER_ID": "군번", "RANK_NAME": "계급", "UNIT_NAME": "부대",
            "INJURY_ID": "부상 ID", "INJURY_CATEGORY": "부상 분류", "INJURY_LOCATION": "부위",
            "SEVERITY": "심각도", "PREVENTABILITY": "예방 가능",
        })
        st.dataframe(
            detail[["부상 ID", "군번", "이름", "계급", "부대", "종합 체력등급", "부상 분류", "부위", "심각도", "예방 가능"]],
            hide_index=True,
            width="stretch",
        )


def render_empty_menu_layout(view_name: str) -> None:
    """추후 기능을 채울 메뉴의 공통 레이아웃을 표시합니다."""
    st.subheader(view_name)
    st.caption("세부 기능을 준비 중입니다. 현재 메뉴 구조와 화면 틀을 먼저 제공합니다.")
    summary_columns = st.columns(3)
    for column, label in zip(summary_columns, ["요약 영역", "분석 영역", "상세 영역"]):
        with column:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption("추후 콘텐츠가 표시됩니다.")
    with st.container(border=True):
        st.markdown("**콘텐츠 영역**")
        st.info("이 화면은 추후 기능이 채워질 예정입니다.")


def render_fitness_management(scoped: pd.DataFrame, measurements: pd.DataFrame) -> None:
    """최근 3회차 체력 현황과 관리 대상 장병을 표시합니다."""
    scoped_ids = set(scoped["SOLDIER_ID"])
    history = add_measurement_rounds(
        measurements.loc[measurements["SOLDIER_ID"].isin(scoped_ids)].copy()
    )
    latest_round_by_soldier = history.groupby("SOLDIER_ID")["측정회차"].transform("max")
    history["최근회차"] = latest_round_by_soldier - history["측정회차"] + 1
    recent_history = add_deficiency_flags(history.loc[history["최근회차"].le(3)])
    latest = add_deficiency_flags(scoped)
    total_count = latest["SOLDIER_ID"].nunique()
    measured_count = recent_history["SOLDIER_ID"].nunique()
    underperformers = recent_history.loc[recent_history["체력미달"], "SOLDIER_ID"].nunique()
    managed = recent_history.loc[recent_history["관리대상"], "SOLDIER_ID"].nunique()

    st.subheader("체력 관리")
    st.caption("현재 필터 대상 중 최근 3회차 측정 기록을 기준으로 체력 취약 인원을 확인합니다.")
    cards = [
        ("최근 3회차 측정 인원", f"{measured_count:,}명", "중복 장병은 1명으로 집계", "total"),
        ("최근 3회차 미달 인원", f"{underperformers:,}명", f"측정 인원의 {underperformers / max(measured_count, 1) * 100:.1f}%", "risk"),
        ("최근 3회차 미달 건수", f"{int(recent_history['체력미달'].sum()):,}건", "회차별 미달 측정 포함", "normal"),
        ("관리 대상", f"{managed:,}명", f"전체 필터 대상 {total_count:,}명 중", "underweight"),
    ]
    card_columns = st.columns(4)
    for column, (label, value, detail, style) in zip(card_columns, cards):
        with column:
            with st.container(border=True, key=f"fitness-management-card-{style}"):
                st.metric(label, value)
                st.caption(detail)

    if recent_history.empty:
        st.info("최근 3회차 측정 기록이 없습니다.")
        return

    round_data = (
        recent_history.groupby("최근회차", as_index=False)
        .agg(측정인원=("SOLDIER_ID", "nunique"), 미달인원=("체력미달", "sum"))
        .sort_values("최근회차", ascending=False)
    )
    round_data["회차"] = round_data["최근회차"].map(lambda value: f"최근 {int(value)}회차")
    round_data["미달비율"] = round_data["미달인원"] / round_data["측정인원"].clip(lower=1) * 100

    chart_columns = st.columns([1.1, 0.9])
    with chart_columns[0]:
        st.markdown("**최근 3회차 측정·미달 인원**")
        round_long = round_data.melt(id_vars="회차", value_vars=["측정인원", "미달인원"], var_name="구분", value_name="인원")
        figure = px.bar(round_long, x="회차", y="인원", color="구분", barmode="group", color_discrete_map={"측정인원": BLUE_ACCENT, "미달인원": "#F15B70"})
        _overview_chart_layout(figure, 300)
        figure.update_layout(xaxis_title=None, yaxis_title="인원")
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    with chart_columns[1]:
        st.markdown("**최근 3회차 미달 비율 추이**")
        figure = px.line(round_data, x="회차", y="미달비율", markers=True, color_discrete_sequence=["#F2A93B"])
        _overview_chart_layout(figure, 300)
        figure.update_layout(xaxis_title=None, yaxis_title="미달 비율(%)")
        figure.update_traces(hovertemplate="미달 비율: %{y:.1f}%<extra></extra>")
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    st.markdown("**최근 3회차 종목별 평균·등급 분포**")
    stat_columns = st.columns(2)
    with stat_columns[0]:
        average_rows = [
            {"종목": label, "평균값": float(pd.to_numeric(recent_history[column], errors="coerce").mean())}
            for column, label in FITNESS_ITEM_LABELS.items()
        ]
        average_summary = pd.DataFrame(average_rows).sort_values("평균값")
        figure = px.bar(average_summary, x="평균값", y="종목", orientation="h", text="평균값", color="종목", color_discrete_map=FITNESS_ITEM_COLORS)
        _overview_chart_layout(figure, 280)
        figure.update_traces(texttemplate="%{x:.1f}", textposition="outside")
        figure.update_layout(showlegend=False, xaxis_title="최근 3회차 평균", yaxis_title=None)
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    with stat_columns[1]:
        grade_rows = []
        for column, label in FITNESS_ITEM_LABELS.items():
            counts = recent_history[f"등급_{column}"].value_counts()
            grade_rows.extend({"종목": label, "등급": grade, "인원": int(counts.get(grade, 0))} for grade in ["1등급", "2등급", "3등급", "미달"])
        grade_distribution = pd.DataFrame(grade_rows)
        figure = px.bar(grade_distribution, x="종목", y="인원", color="등급", barmode="stack", category_orders={"등급": ["1등급", "2등급", "3등급", "미달"]}, color_discrete_map={"1등급": "#16C79A", "2등급": "#25C6D8", "3등급": "#F2A93B", "미달": "#F15B70"})
        _overview_chart_layout(figure, 280)
        figure.update_layout(xaxis_title=None, yaxis_title="인원")
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    st.markdown("**종목별 미달 추이**")
    trend_rows = []
    for recent_round, date_group in recent_history.groupby("최근회차"):
        for column, label in FITNESS_ITEM_LABELS.items():
            count = int(date_group[f"미달_{column}"].sum())
            trend_rows.append({"최근회차": f"최근 {int(recent_round)}회차", "회차순서": int(recent_round), "종목": label, "미달 비율": count / max(len(date_group), 1) * 100})
    trend_data = pd.DataFrame(trend_rows)
    figure = px.line(trend_data.sort_values("회차순서", ascending=False), x="최근회차", y="미달 비율", color="종목", markers=True, color_discrete_map=FITNESS_ITEM_COLORS)
    _overview_chart_layout(figure, 300)
    figure.update_layout(xaxis_title=None, yaxis_title="미달 비율(%)")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    target_ids = set(recent_history.loc[recent_history["관리대상"], "SOLDIER_ID"])
    targets = latest.loc[latest["SOLDIER_ID"].isin(target_ids)].copy()
    targets["미달 종목"] = targets.apply(
        lambda row: ", ".join(FITNESS_ITEM_LABELS[column] for column in FITNESS_ITEM_LABELS if row[f"미달_{column}"]), axis=1
    )
    management_tab, personnel_tab = st.tabs([
        f"관리 대상 장병 · {len(targets):,}명",
        f"전체 장병 목록 · {len(latest):,}명",
    ])
    display_columns = ["SOLDIER_ID", "SOLDIER_NAME", "REGION_NAME", "UNIT_NAME", "RANK_NAME", "MESURE_DE", "미달 종목"]
    display_rename = {
        "SOLDIER_ID": "군번", "SOLDIER_NAME": "이름", "REGION_NAME": "지역", "UNIT_NAME": "부대",
        "RANK_NAME": "계급", "MESURE_DE": "최근 측정일",
    }
    with management_tab:
        st.dataframe(
            targets[display_columns].rename(columns=display_rename),
            hide_index=True,
            width="stretch",
            column_config={"최근 측정일": st.column_config.DateColumn(format="YYYY-MM-DD")},
        )
    with personnel_tab:
        st.dataframe(
            latest.assign(**{"미달 종목": latest.apply(
                lambda row: ", ".join(FITNESS_ITEM_LABELS[column] for column in FITNESS_ITEM_LABELS if row[f"미달_{column}"]), axis=1
            )})[display_columns].rename(columns=display_rename),
            hide_index=True,
            width="stretch",
            column_config={"최근 측정일": st.column_config.DateColumn(format="YYYY-MM-DD")},
        )


def show_dashboard() -> None:
    st.set_page_config(
        page_title="장병 체력·부상관리 대시보드",
        page_icon="🪖",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: dark;
            --navy-background: {NAVY_BACKGROUND};
            --navy-surface: {NAVY_SURFACE};
            --navy-border: {NAVY_BORDER};
            --light-text: {LIGHT_TEXT};
            --muted-text: {MUTED_TEXT};
            --cyan-accent: {CYAN_ACCENT};
            --blue-accent: {BLUE_ACCENT};
            --st-background-color: {NAVY_BACKGROUND};
            --st-secondary-background-color: {NAVY_SURFACE};
            --st-text-color: {LIGHT_TEXT};
            --st-primary-color: {BLUE_ACCENT};
            --st-border-color: {NAVY_BORDER};
            --st-dataframe-header-background-color: #142D49;
        }}
        .stApp,
        [data-testid="stAppViewContainer"] {{
            background:
                radial-gradient(ellipse at 76% -18%, rgba(24, 91, 154, 0.34), transparent 46%),
                linear-gradient(145deg, #09192B 0%, var(--navy-background) 58%, #050D18 100%);
            color: var(--light-text);
        }}
        [data-testid="stMain"] {{
            background: transparent;
        }}
        [data-testid="stMainBlockContainer"] {{
            padding-top: 2rem;
        }}
        [data-testid="stHeader"] {{
            background: rgba(7, 19, 33, 0.92);
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0A1D33 0%, #09192B 58%, #06101C 100%);
            border-right: 1px solid rgba(47, 91, 132, 0.48);
            box-shadow: 12px 0 36px rgba(0, 0, 0, 0.16);
        }}
        [data-testid="stSidebar"] [data-testid="stImage"] {{
            margin-bottom: -0.5rem;
        }}
        .st-key-sidebar-navigation button {{
            justify-content: flex-start;
            border-radius: 0.55rem;
            font-weight: 600;
        }}
        [data-testid="stSidebar"] [data-testid="stExpander"] {{
            background: rgba(16, 36, 58, 0.68);
            border: 1px solid rgba(47, 91, 132, 0.48);
            border-radius: 0.65rem;
        }}
        [data-testid="stMetric"] {{
            background: linear-gradient(145deg, #142F4B 0%, #0D2035 100%);
            border: 1px solid #285073;
            border-radius: 0.8rem;
            box-shadow: inset 0 1px 0 rgba(151, 203, 242, 0.045), 0 8px 22px rgba(0, 0, 0, 0.14);
            padding: 0.55rem 0.25rem;
        }}
        [data-testid="stLayoutWrapper"]:has(> .st-key-summary-card-total) {{
            background: linear-gradient(145deg, rgba(37, 137, 255, 0.25), rgba(13, 32, 53, 0.98));
            border-color: rgba(67, 141, 255, 0.78);
            box-shadow: inset 0 3px 0 #438DFF, 0 8px 24px rgba(27, 105, 207, 0.16);
        }}
        [data-testid="stLayoutWrapper"]:has(> .st-key-summary-card-normal) {{
            background: linear-gradient(145deg, rgba(22, 199, 154, 0.22), rgba(10, 38, 42, 0.98));
            border-color: rgba(22, 199, 154, 0.72);
            box-shadow: inset 0 3px 0 #16C79A, 0 8px 24px rgba(22, 199, 154, 0.12);
        }}
        [data-testid="stLayoutWrapper"]:has(> .st-key-summary-card-risk) {{
            background: linear-gradient(145deg, rgba(242, 169, 59, 0.22), rgba(43, 34, 28, 0.98));
            border-color: rgba(242, 169, 59, 0.76);
            box-shadow: inset 0 3px 0 #F2A93B, 0 8px 24px rgba(242, 169, 59, 0.12);
        }}
        [data-testid="stLayoutWrapper"]:has(> .st-key-summary-card-underweight) {{
            background: linear-gradient(145deg, rgba(241, 91, 112, 0.23), rgba(43, 27, 41, 0.98));
            border-color: rgba(241, 91, 112, 0.78);
            box-shadow: inset 0 3px 0 #F15B70, 0 8px 24px rgba(241, 91, 112, 0.12);
        }}
        .st-key-summary-card-total [data-testid="stMetricLabel"] p,
        .st-key-summary-card-total [data-testid="stMetricValue"] {{
            color: #A9CFFF;
        }}
        .st-key-summary-card-normal [data-testid="stMetricLabel"] p,
        .st-key-summary-card-normal [data-testid="stMetricValue"] {{
            color: #8FE5C9;
        }}
        .st-key-summary-card-risk [data-testid="stMetricLabel"] p,
        .st-key-summary-card-risk [data-testid="stMetricValue"] {{
            color: #FFD28B;
        }}
        .st-key-summary-card-underweight [data-testid="stMetricLabel"] p,
        .st-key-summary-card-underweight [data-testid="stMetricValue"] {{
            color: #FFADB7;
        }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background: linear-gradient(150deg, rgba(17, 39, 62, 0.94), rgba(10, 27, 46, 0.98));
            border-color: rgba(42, 78, 114, 0.92);
            border-radius: 0.8rem;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
        }}
        [data-testid="stMetricValue"] {{
            color: var(--light-text);
            font-size: clamp(0.95rem, 1.3vw, 1.35rem);
            overflow-wrap: anywhere;
        }}
        [data-testid="stMetricLabel"] p {{
            color: #E0E9F2;
            font-size: 0.68rem !important;
            white-space: nowrap;
        }}
        [data-testid="stCaptionContainer"] p {{
            color: var(--muted-text);
        }}
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        label,
        h1, h2, h3, h4 {{
            color: var(--light-text);
        }}
        h1 {{
            text-shadow: 0 0 26px rgba(33, 183, 213, 0.14);
        }}
        [data-testid="stDataFrame"] {{
            border: 1px solid #244666;
            border-radius: 0.65rem;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.14);
        }}
        [data-testid="stTextInputRootElement"] {{
            background: #0D2035 !important;
            border: 1px solid #2B5278 !important;
            border-radius: 0.55rem !important;
        }}
        [data-testid="stTextInputField"] {{
            background: transparent !important;
            color: var(--light-text) !important;
        }}
        [data-testid="stTextInputField"]::placeholder {{
            color: var(--muted-text) !important;
            opacity: 1;
        }}
        [data-testid="stSelectbox"] [role="group"],
        [data-testid="stMultiSelect"] [role="group"],
        [data-testid="stDateInput"] [role="group"] {{
            background: #0D2035 !important;
            border-color: #2B5278 !important;
            border-radius: 0.55rem !important;
            color: var(--light-text) !important;
        }}
        [data-testid="stSelectbox"] input,
        [data-testid="stMultiSelect"] input,
        [data-testid="stDateInput"] input {{
            color: var(--light-text) !important;
        }}
        [data-testid="stSelectbox"] input::placeholder,
        [data-testid="stMultiSelect"] input::placeholder,
        [data-testid="stDateInput"] input::placeholder {{
            color: var(--muted-text) !important;
            opacity: 1;
        }}
        [data-testid="stSlider"] input[type="range"] {{
            accent-color: var(--cyan-accent);
        }}
        button[kind="secondary"] {{
            background: linear-gradient(145deg, #17334F, #10243A);
            border: 1px solid #2B5278;
            color: var(--light-text);
            border-radius: 0.55rem;
            font-size: 0.8rem;
            padding-left: 0.35rem;
            padding-right: 0.35rem;
            white-space: nowrap;
            transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
        }}
        button[kind="secondary"]:hover {{
            background: #1B3D5D;
            border-color: var(--cyan-accent);
            color: #EFF5FB;
            transform: translateY(-1px);
        }}
        button[kind="primary"] {{
            background: linear-gradient(115deg, #2589FF, #176BD3);
            border-color: #4199FF;
            color: #EFF5FB;
            border-radius: 0.55rem;
            box-shadow: 0 5px 16px rgba(25, 118, 232, 0.22);
        }}
        button[kind="primary"]:hover {{
            background: linear-gradient(115deg, #4098FF, #2581E8);
            border-color: #70B0FF;
        }}
        [data-testid="stMultiSelectTagsContainer"] span[role="group"] > span:not([role]) {{
            background: #153956 !important;
            color: #DCEAF6 !important;
            border: 1px solid #32658D !important;
            border-radius: 999px;
        }}
        [data-testid="stMultiSelectTagsContainer"] span[role="group"] > span:not([role]) button svg {{
            fill: #A8C6D9 !important;
        }}
        [data-testid="stTab"][aria-selected="true"] {{
            color: var(--cyan-accent) !important;
            border-bottom-color: var(--cyan-accent) !important;
        }}
        [data-testid="stTab"][aria-selected="true"]::after {{
            background-color: var(--cyan-accent) !important;
        }}
        [data-testid="stTab"][role="tab"] {{
            color: #C2D2E2;
        }}
        [data-testid="stTab"][role="tab"]:hover {{
            color: #EFF5FB;
        }}
        [data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"] {{
            background: rgba(37, 137, 255, 0.16) !important;
            border-color: var(--cyan-accent) !important;
            color: #C2E8E2 !important;
        }}
        [data-testid="stSlider"] [role="slider"] {{
            background: var(--cyan-accent);
            border-color: var(--cyan-accent);
            box-shadow: 0 0 12px rgba(32, 200, 163, 0.34);
        }}
        [data-testid="stDialog"] {{
            background: #0A1929;
            border: 1px solid #2B5278;
            box-shadow: 0 18px 70px rgba(0, 0, 0, 0.52);
        }}
        [data-testid="stAlert"] {{
            background: linear-gradient(135deg, #142F4B, #0D2035);
            border-color: #2B5278;
        }}
        hr {{
            border-color: rgba(47, 86, 122, 0.5);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    active_view = st.session_state.setdefault("active_view", "대시보드 홈")
    st.title("🪖 장병 체력 현황")
    st.caption(
        f"{active_view} · 지역·부대별 신체 현황을 확인하고 장병의 최근 측정 정보를 살펴봅니다."
    )

    try:
        personnel_stat = PERSONNEL_PATH.stat()
        fitness_stat = FITNESS_PATH.stat()
        measurements = load_dashboard_data(
            str(PERSONNEL_PATH),
            str(FITNESS_PATH),
            (personnel_stat.st_mtime_ns, personnel_stat.st_size),
            (fitness_stat.st_mtime_ns, fitness_stat.st_size),
        )
        injury_stat = INJURY_PATH.stat()
        injuries = load_injury_data(
            str(INJURY_PATH), (injury_stat.st_mtime_ns, injury_stat.st_size)
        )
    except (FileNotFoundError, ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        st.error(f"대시보드 데이터를 불러오지 못했습니다: {error}")
        st.info(
            "먼저 프로젝트 루트에서 데이터 파이프라인의 합성 단계를 실행해 "
            "장병 명단과 최종 측정 데이터를 생성하세요."
        )
        st.stop()

    min_measure_date = measurements["MESURE_DE"].min().date()
    max_measure_date = measurements["MESURE_DE"].max().date()

    with st.sidebar:
        illustration_path = Path(__file__).resolve().parent / "img" / "personnel_health.svg"
        st.image(str(illustration_path), width="stretch")
        st.markdown("### 장병 체력·부상관리")
        st.caption("건강한 오늘, 더 강한 내일")
        with st.container(key="sidebar-navigation"):
            for view_name, view_icon in NAVIGATION_ITEMS:
                st.button(
                    view_name,
                    key=f"sidebar_nav_{view_name}",
                    icon=view_icon,
                    type="primary" if active_view == view_name else "secondary",
                    width="stretch",
                    on_click=navigate_to_view,
                    args=(view_name,),
                )



    if active_view in ("통계/분석", "리포트", "설정"):
        render_empty_menu_layout(active_view)
        return

    if active_view in ("개인 정보 조회", "부상 현황"):
        st.markdown("### 조회 조건")
        st.caption("지역·부대·계급·나이·측정 기간을 조절해 현재 화면의 대상을 좁힐 수 있습니다.")
        filter_container = st.container(border=True)
    else:
        filter_container = st.container()

    with filter_container:
        filter_columns = st.columns([1.2, 1.6, 1.6, 1.25, 1.25])
        with filter_columns[0]:
            selected_dates = st.date_input(
                "측정일 기간",
                value=(min_measure_date, max_measure_date),
                min_value=min_measure_date,
                max_value=max_measure_date,
                format="YYYY/MM/DD",
                key=filter_state_key("measurement_date_filter"),
            )
        if isinstance(selected_dates, tuple):
            date_start, date_end = selected_dates
        else:
            date_start = date_end = selected_dates
        if date_start > date_end:
            date_start, date_end = date_end, date_start

        population = latest_measurements(measurements, date_start, date_end)
        if population.empty:
            st.info("선택한 측정일 기간에 해당하는 측정 기록이 없습니다.")
            st.stop()

        all_regions = sorted(population["REGION_NAME"].dropna().unique().tolist())
        st.session_state[filter_state_key("units_by_region")] = (
            population.groupby("REGION_NAME")["UNIT_NAME"].unique().map(list).to_dict()
        )
        region_key = filter_state_key("region_filter")
        unit_key = filter_state_key("unit_filter")
        rank_key = filter_state_key("rank_filter")
        age_key = filter_state_key("age_filter")
        bmi_key = filter_state_key("bmi_filter")
        if region_key not in st.session_state or not set(st.session_state[region_key]).issubset(all_regions):
            st.session_state[region_key] = all_regions
        with filter_columns[1]:
            selected_regions = st.multiselect("지역", options=all_regions, key=region_key, on_change=reset_unit_selection)

        region_population = population.loc[population["REGION_NAME"].isin(selected_regions)]
        all_units = sorted(region_population["UNIT_NAME"].dropna().unique().tolist())
        if unit_key not in st.session_state or not set(st.session_state[unit_key]).issubset(all_units):
            st.session_state[unit_key] = all_units
        with filter_columns[2]:
            selected_units = st.multiselect("부대", options=all_units, key=unit_key)

        available_ranks = [rank for rank in RANK_ORDER if rank in population["RANK_NAME"].unique()]
        if rank_key not in st.session_state or not set(st.session_state[rank_key]).issubset(available_ranks):
            st.session_state[rank_key] = available_ranks
        with filter_columns[3]:
            selected_ranks = st.multiselect("계급", options=available_ranks, key=rank_key)

        age_min = int(population["AGE"].min())
        age_max = int(population["AGE"].max())
        if age_min < age_max:
            if age_key not in st.session_state:
                st.session_state[age_key] = (age_min, age_max)
            elif len(st.session_state[age_key]) != 2 or st.session_state[age_key][0] < age_min or st.session_state[age_key][1] > age_max:
                st.session_state[age_key] = (age_min, age_max)
            with filter_columns[4]:
                age_range = st.slider("나이 범위", min_value=age_min, max_value=age_max, key=age_key)
        else:
            age_range = (age_min, age_max)
            with filter_columns[4]:
                st.caption(f"나이 범위: {age_min}세")

        if bmi_key not in st.session_state:
            st.session_state[bmi_key] = list(BMI_CATEGORY_ORDER)
        if active_view in ("개인 정보 조회", "부상 현황"):
            with st.expander("추가 조건", expanded=False):
                st.multiselect("BMI 구간", options=list(BMI_CATEGORY_ORDER), key=bmi_key)

    scoped = population.loc[
        population["REGION_NAME"].isin(selected_regions)
        & population["UNIT_NAME"].isin(selected_units)
        & population["RANK_NAME"].isin(selected_ranks)
        & population["AGE"].between(age_range[0], age_range[1])
    ].copy()

    st.caption(
        f"측정 기간 {date_start:%Y-%m-%d} ~ {date_end:%Y-%m-%d} · "
        f"장병별 기간 내 최신 측정 기준 · 현재 지역·부대·계급·나이 조건 "
        f"{len(scoped):,}명"
    )

    if scoped.empty:
        st.info("현재 필터 조건에 해당하는 장병이 없습니다.")
        st.stop()

    if active_view == "리포트":
        st.subheader("리포트")
        st.info("리포트 화면은 준비 중입니다. 현재 필터 조건은 다른 화면에도 적용됩니다.")
    elif active_view == "설정":
        st.subheader("설정")
        st.info("설정 화면은 준비 중입니다.")
    elif active_view == "부상 현황":
        render_injury_overview(scoped, injuries)

    if active_view == "대시보드 홈":
        render_home_overview(
            scoped,
            measurements,
            date_start,
            date_end,
            selected_regions,
            selected_units,
            selected_ranks,
        )

    elif active_view == "체력 관리":
        render_fitness_management(scoped, measurements)

    elif active_view == "개인 정보 조회":
        st.subheader("개인 정보 조회")

    personnel_list_slot = (
        st.container()
        if active_view in ("대시보드 홈", "개인 정보 조회")
        else None
    )

    bmi_panel_open = False
    if active_view in ("부대 현황", "통계/분석"):
        summary_tab, analysis_tab = st.tabs(["지역·부대별 요약", "신체정보 분석"])
        with summary_tab:
            summary_level = st.segmented_control(
                "요약 기준",
                options=["지역별", "부대별"],
                default="지역별",
                key="summary_level",
                on_change=clear_bmi_chart_selection,
            )
            group_column = "REGION_NAME" if summary_level == "지역별" else "UNIT_NAME"
            summary = summarize_groups(scoped, group_column)
            display_summary = summary.rename(
                columns={group_column: "지역" if summary_level == "지역별" else "부대"}
            )
            st.dataframe(
                display_summary,
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

        with analysis_tab:
            analysis_level = st.segmented_control(
                "차트 분석 단위",
                options=["지역별", "부대별"],
                default="지역별",
                key="analysis_level",
                on_change=clear_bmi_chart_selection,
            )
            chart_group_column = "REGION_NAME" if analysis_level == "지역별" else "UNIT_NAME"
            chart_group_label = "지역" if analysis_level == "지역별" else "부대"
            chart_groups = sorted(scoped[chart_group_column].dropna().unique().tolist())
            selected_chart_group = st.selectbox(
                f"상세 분석 {chart_group_label}",
                options=chart_groups,
                key="selected_chart_group",
            )
            selected_group = scoped.loc[
                scoped[chart_group_column].eq(selected_chart_group)
            ]

            chart_columns = st.columns([1.35, 1])
            with chart_columns[0]:
                st.markdown(f"**{selected_chart_group} · BMI 구간별 인원**")
                bmi_distribution = (
                    selected_group["BMI구간"]
                    .value_counts()
                    .reindex(BMI_CATEGORY_ORDER, fill_value=0)
                    .rename_axis("BMI 구간")
                    .reset_index(name="인원")
                )
                bmi_distribution["비율(%)"] = (
                    bmi_distribution["인원"] / max(len(selected_group), 1) * 100
                )
                bmi_selection = alt.selection_point(
                    name="bmi_slice",
                    fields=["BMI 구간"],
                    on="click",
                    toggle=False,
                    clear="dblclick",
                )
                bmi_donut = (
                    alt.Chart(bmi_distribution)
                    .mark_arc(
                        innerRadius=78,
                        outerRadius=125,
                        stroke=NAVY_BACKGROUND,
                        strokeWidth=3,
                        cursor="pointer",
                    )
                    .encode(
                        theta=alt.Theta("인원:Q"),
                        color=alt.Color(
                            "BMI 구간:N",
                            scale=alt.Scale(
                                domain=list(BMI_CATEGORY_ORDER),
                                range=[BMI_COLORS[level] for level in BMI_CATEGORY_ORDER],
                            ),
                            legend=None,
                        ),
                        opacity=alt.condition(
                            bmi_selection,
                            alt.value(1),
                            alt.value(0.85),
                        ),
                        tooltip=[
                            alt.Tooltip("BMI 구간:N"),
                            alt.Tooltip("인원:Q", format=",d"),
                            alt.Tooltip("비율(%):Q", format=".1f"),
                        ],
                    )
                    .add_params(bmi_selection)
                )
                bmi_total = (
                    alt.Chart(pd.DataFrame({"label": [f"{len(selected_group):,}명"]}))
                    .mark_text(color=LIGHT_TEXT, fontSize=22, fontWeight="bold")
                    .encode(text="label:N")
                )
                bmi_figure = (
                    alt.layer(bmi_donut, bmi_total)
                    .properties(height=340)
                    .configure(background=NAVY_BACKGROUND)
                    .configure_view(stroke=None)
                    .configure_axis(labelColor=LIGHT_TEXT, titleColor=LIGHT_TEXT)
                )
                chart_selection_context = filter_signature(
                    summary_level,
                    analysis_level,
                    selected_chart_group,
                    tuple(selected_regions),
                    tuple(selected_units),
                    tuple(selected_ranks),
                    age_range,
                    date_start,
                    date_end,
                )
                bmi_chart_event = st.altair_chart(
                    bmi_figure,
                    width="stretch",
                    key=(
                        "bmi_distribution_chart_"
                        f"{filter_signature(analysis_level, selected_chart_group, chart_selection_context)}"
                    ),
                    on_select="rerun",
                    selection_mode="bmi_slice",
                )
                selected_points = bmi_chart_event.selection.get("bmi_slice", [])
                count_button_clicked = st.session_state.pop(
                    "bmi_count_button_clicked", False
                )
                if (
                    analysis_level == "부대별"
                    and selected_points
                    and not count_button_clicked
                ):
                    selected_category = selected_points[-1].get("BMI 구간")
                    if selected_category in BMI_CATEGORY_ORDER:
                        selection_key = (
                            selected_chart_group,
                            selected_category,
                            chart_selection_context,
                        )
                        st.session_state["bmi_chart_selection_key"] = selection_key
                        if st.session_state.get("bmi_chart_dismissed_selection_key") != selection_key:
                            st.session_state["bmi_chart_selected_category"] = selected_category

            with chart_columns[1]:
                st.markdown("**구간별 인원**")
                for _, category_row in bmi_distribution.iterrows():
                    category = str(category_row["BMI 구간"])
                    count = int(category_row["인원"])
                    percentage = float(category_row["비율(%)"])
                    st.markdown(
                        f"""
                        <div style="
                            display:flex;align-items:center;justify-content:space-between;
                            gap:0.75rem;padding:0.65rem 0.8rem;margin:0.35rem 0;
                            border:1px solid {NAVY_BORDER};border-radius:0.55rem;
                            background:{NAVY_SURFACE};">
                            <span style="display:flex;align-items:center;gap:0.55rem;color:{LIGHT_TEXT};">
                                <span style="width:0.7rem;height:0.7rem;border-radius:50%;
                                    background:{BMI_COLORS[category]};display:inline-block;"></span>
                                <strong>{category}</strong>
                            </span>
                            <span style="color:{LIGHT_TEXT};white-space:nowrap;">
                                {count:,}명 <span style="color:{MUTED_TEXT};">({percentage:.1f}%)</span>
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if analysis_level == "부대별":
                        st.button(
                            f"{count:,}명 보기",
                            key=(
                                f"bmi_count_{filter_signature(selected_chart_group, category, chart_selection_context)}"
                            ),
                            width="stretch",
                            on_click=select_bmi_category,
                            args=(selected_chart_group, category, chart_selection_context),
                        )
            with st.container():
                st.markdown(f"**{selected_chart_group} · 계급별 평균 BMI**")
                rank_average = (
                    selected_group.groupby("RANK_NAME", as_index=False)
                    .agg(평균_BMI=("BMI", "mean"), 인원=("SOLDIER_ID", "nunique"))
                )
                rank_average["RANK_NAME"] = pd.Categorical(
                    rank_average["RANK_NAME"],
                    categories=RANK_ORDER,
                    ordered=True,
                )
                rank_average = rank_average.sort_values("RANK_NAME")
                rank_figure = px.bar(
                    rank_average,
                    x="RANK_NAME",
                    y="평균_BMI",
                    text="평균_BMI",
                    color="RANK_NAME",
                    category_orders={"RANK_NAME": list(RANK_ORDER)},
                    color_discrete_map=dict(zip(RANK_ORDER, RANK_CHART_COLORS)),
                    hover_data={"인원": True, "평균_BMI": ":.2f"},
                    labels={
                        "RANK_NAME": "계급",
                        "평균_BMI": "평균 BMI",
                        "인원": "장병 수",
                    },
                    color_discrete_sequence=[BMI_COLORS["정상"]],
                )
                rank_figure.update_traces(texttemplate="%{y:.1f}", textposition="outside")
                rank_figure.update_layout(
                    height=360,
                    margin=dict(l=8, r=8, t=16, b=8),
                    showlegend=False,
                    xaxis_title=None,
                    yaxis_title="평균 BMI",
                    yaxis_rangemode="tozero",
                    template="plotly_dark",
                    paper_bgcolor=NAVY_BACKGROUND,
                    plot_bgcolor=NAVY_BACKGROUND,
                    font=dict(color=LIGHT_TEXT),
                    xaxis=dict(gridcolor=NAVY_BORDER),
                    yaxis=dict(gridcolor=NAVY_BORDER),
                )
                st.plotly_chart(
                    rank_figure,
                    width="stretch",
                    config={"displayModeBar": False},
                )

            st.markdown(f"**현재 필터 범위 · {chart_group_label}별 평균 체지방률**")
            body_fat_average = (
                scoped.groupby(chart_group_column, as_index=False)
                .agg(평균_체지방률=("BODY_FAT_PERCENTAGE", "mean"), 인원=("SOLDIER_ID", "nunique"))
                .sort_values("평균_체지방률", ascending=True)
            )
            body_fat_figure = px.bar(
                body_fat_average,
                x="평균_체지방률",
                y=chart_group_column,
                orientation="h",
                text="평균_체지방률",
                hover_data={"인원": True, "평균_체지방률": ":.1f"},
                labels={
                    chart_group_column: chart_group_label,
                    "평균_체지방률": "평균 체지방률(%)",
                    "인원": "장병 수",
                },
                color_discrete_sequence=[BMI_COLORS["과체중"]],
            )
            body_fat_figure.update_traces(texttemplate="%{x:.1f}%", textposition="outside")
            body_fat_figure.update_layout(
                height=max(300, min(620, 36 * len(body_fat_average) + 100)),
                margin=dict(l=8, r=40, t=8, b=8),
                xaxis_title="평균 체지방률(%)",
                yaxis_title=None,
                template="plotly_dark",
                paper_bgcolor=NAVY_BACKGROUND,
                plot_bgcolor=NAVY_BACKGROUND,
                font=dict(color=LIGHT_TEXT),
                xaxis=dict(gridcolor=NAVY_BORDER),
                yaxis=dict(gridcolor=NAVY_BORDER),
            )
            st.plotly_chart(
                body_fat_figure,
                width="stretch",
                config={"displayModeBar": False},
            )

            selected_bmi_category = st.session_state.get("bmi_chart_selected_category")
            selected_bmi_context = st.session_state.get("bmi_chart_selection_key")
            current_bmi_context = (
                selected_chart_group,
                selected_bmi_category,
                chart_selection_context,
            )
            bmi_panel_open = (
                analysis_level == "부대별"
                and selected_bmi_category in BMI_CATEGORY_ORDER
                and selected_bmi_context == current_bmi_context
            )
            if bmi_panel_open:
                category_soldiers = selected_group.loc[
                    selected_group["BMI구간"].eq(selected_bmi_category)
                ].sort_values(["UNIT_NAME", "RANK_NAME", "SOLDIER_NAME"])
                show_bmi_soldiers_panel(
                    selected_chart_group,
                    selected_bmi_category,
                    category_soldiers,
                )
    if active_view in ("대시보드 홈", "개인 정보 조회"):
        with personnel_list_slot:
            st.subheader("장병 목록")
            st.caption("장병 목록의 왼쪽 선택 칸을 누르면 상세 신체정보가 열립니다.")
            search_query = st.text_input(
                "군번·이름 검색",
                placeholder="군번 또는 이름을 입력하세요",
                key="personnel_search",
            ).strip()
            list_data = scoped.loc[
                scoped["BMI구간"].isin(st.session_state.get(filter_state_key("bmi_filter"), list(BMI_CATEGORY_ORDER)))
            ].copy()
            if search_query:
                matches = (
                    list_data["SOLDIER_ID"].str.contains(search_query, case=False, regex=False, na=False)
                    | list_data["SOLDIER_NAME"].str.contains(search_query, case=False, regex=False, na=False)
                )
                list_data = list_data.loc[matches]

            sort_options = {
                "측정일": "MESURE_DE",
                "군번": "SOLDIER_ID",
                "이름": "SOLDIER_NAME",
                "계급": "RANK_NAME",
                "지역": "REGION_NAME",
                "부대": "UNIT_NAME",
                "나이": "AGE",
                "BMI": "BMI",
                "체지방률": "BODY_FAT_PERCENTAGE",
            }
            list_controls = st.columns([1.2, 1, 1, 2])
            with list_controls[0]:
                sort_label = st.selectbox("정렬 기준", options=list(sort_options), key="sort_column")
            with list_controls[1]:
                sort_direction = st.selectbox(
                    "정렬 순서", options=["내림차순", "오름차순"], key="sort_direction"
                )
            with list_controls[2]:
                page_size = st.selectbox(
                    "페이지당 인원", options=[10, 20, 50, 100], index=1, key="page_size"
                )
            with list_controls[3]:
                st.caption("표의 열 제목을 클릭해도 정렬할 수 있습니다.")

            list_data = list_data.sort_values(
                sort_options[sort_label],
                ascending=sort_direction == "오름차순",
                kind="stable",
            ).reset_index(drop=True)
            total_rows = len(list_data)
            page_count = max(1, (total_rows + page_size - 1) // page_size)
            current_filter_signature = filter_signature(
                tuple(selected_regions),
                tuple(selected_units),
                tuple(selected_ranks),
                age_range,
                date_start,
                date_end,
                tuple(st.session_state.get(filter_state_key("bmi_filter"), [])),
                search_query,
                sort_label,
                sort_direction,
                page_size,
            )
            if st.session_state.get("table_filter_signature") != current_filter_signature:
                st.session_state["table_filter_signature"] = current_filter_signature
                st.session_state["personnel_page"] = 1
            current_page = min(max(st.session_state.get("personnel_page", 1), 1), page_count)
            st.session_state["personnel_page"] = current_page

            page_start = (current_page - 1) * page_size
            page_data = list_data.iloc[page_start : page_start + page_size].copy()
            page_controls = st.columns([1, 2, 1])
            with page_controls[0]:
                if st.button(
                    "← 이전",
                    disabled=current_page <= 1 or total_rows == 0,
                    width="stretch",
                ):
                    st.session_state["personnel_page"] = current_page - 1
                    st.rerun()
            with page_controls[1]:
                st.markdown(
                    f"<div style='text-align:center;padding-top:0.45rem'>"
                    f"{total_rows:,}명 · {current_page} / {page_count} 페이지</div>",
                    unsafe_allow_html=True,
                )
            with page_controls[2]:
                if st.button(
                    "다음 →",
                    disabled=current_page >= page_count or total_rows == 0,
                    width="stretch",
                ):
                    st.session_state["personnel_page"] = current_page + 1
                    st.rerun()

            if page_data.empty:
                st.info("검색어와 선택된 필터에 해당하는 장병이 없습니다.")
            else:
                table_columns = [
                    "SOLDIER_ID",
                    "SOLDIER_NAME",
                    "REGION_NAME",
                    "UNIT_NAME",
                    "RANK_NAME",
                    "AGE",
                    "MESURE_DE",
                    "BMI",
                    "BMI구간",
                    "BODY_FAT_PERCENTAGE",
                ]
                table = page_data[table_columns].rename(
                    columns={
                        "SOLDIER_ID": "군번",
                        "SOLDIER_NAME": "이름",
                        "REGION_NAME": "지역",
                        "UNIT_NAME": "부대",
                        "RANK_NAME": "계급",
                        "AGE": "나이",
                        "MESURE_DE": "측정일",
                        "BMI": "BMI",
                        "BMI구간": "BMI 구간",
                        "BODY_FAT_PERCENTAGE": "체지방률(%)",
                    }
                )
                table_key = (
                    f"personnel_table_{current_page}_"
                    f"{filter_signature(current_filter_signature, current_page)}"
                )
                table_event = st.dataframe(
                    table,
                    hide_index=True,
                    width="stretch",
                    on_select=reset_soldier_detail_dismissal,
                    selection_mode="single-row",
                    key=table_key,
                    column_config={
                        "나이": st.column_config.NumberColumn(format="%d세"),
                        "측정일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                        "BMI": st.column_config.NumberColumn(format="%.1f"),
                        "체지방률(%)": st.column_config.NumberColumn(format="%.1f"),
                    },
                )
                selected_rows = table_event.selection.rows
                if selected_rows:
                    selected_index = selected_rows[0]
                    if 0 <= selected_index < len(page_data):
                        st.session_state["selected_soldier_id"] = page_data.iloc[
                            selected_index
                        ]["SOLDIER_ID"]
                        selected_soldier = page_data.iloc[selected_index]
                        selected_soldier_id = selected_soldier["SOLDIER_ID"]
                        if (
                            not bmi_panel_open
                            and st.session_state.get("soldier_detail_dismissed_id")
                            != selected_soldier_id
                        ):
                            show_soldier_detail_dialog(selected_soldier, measurements, injuries)

    st.divider()
    st.caption(
        "BMI 구간은 일반적인 성인 기준(저체중 <18.5, 정상 18.5–25, "
        "과체중 25–30, 비만 ≥30)으로 표시합니다. 이 화면의 데이터는 "
        "개인 진단이나 의학적 판단을 대체하지 않습니다."
    )


show_dashboard()
