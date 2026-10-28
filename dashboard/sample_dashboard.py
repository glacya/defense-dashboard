"""장병의 최근 체력 측정과 인적 정보를 살펴보는 Streamlit 대시보드."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from config import PROCESSED_DIR, SYNTHETIC_DIR

PERSONNEL_PATH = SYNTHETIC_DIR / "SOLDIER_PERSONNEL.csv"
FITNESS_PATH = PROCESSED_DIR / "KS_NFA_PROCESSED.csv"

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
}
NAVIGATION_ITEMS = (
    ("대시보드 홈", ":material/home:"),
    ("개인 정보 조회", ":material/person_search:"),
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
    st.session_state["bmi_filter"] = list(categories)
    st.session_state["active_summary_card"] = card_name
    st.session_state["personnel_page"] = 1


def reset_unit_selection() -> None:
    """지역이 바뀌면 새 지역 범위의 부대를 모두 선택합니다."""
    units_by_region = st.session_state.get("units_by_region", {})
    regions = st.session_state.get("region_filter", [])
    st.session_state["unit_filter"] = sorted(
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


def render_soldier_details(soldier: pd.Series) -> None:
    """선택 장병의 인적 정보와 최신 신체 측정값을 표시합니다."""
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


@st.dialog(
    "장병 상세정보",
    width="medium",
    on_dismiss=dismiss_soldier_detail_dialog,
)
def show_soldier_detail_dialog(soldier: pd.Series) -> None:
    """장병 목록에서 선택한 장병의 상세정보를 모달로 표시합니다."""
    render_soldier_details(soldier)


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

        with st.expander("필터", icon=":material/filter_list:", expanded=False):
            selected_dates = st.date_input(
                "측정일 기간",
                value=(min_measure_date, max_measure_date),
                min_value=min_measure_date,
                max_value=max_measure_date,
                format="YYYY/MM/DD",
                key="measurement_date_filter",
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
            st.session_state["units_by_region"] = (
                population.groupby("REGION_NAME")["UNIT_NAME"]
                .unique()
                .map(list)
                .to_dict()
            )
            if "region_filter" not in st.session_state or not set(
                st.session_state["region_filter"]
            ).issubset(all_regions):
                st.session_state["region_filter"] = all_regions
            selected_regions = st.multiselect(
                "지역",
                options=all_regions,
                key="region_filter",
                on_change=reset_unit_selection,
            )
            region_population = population.loc[
                population["REGION_NAME"].isin(selected_regions)
            ]
            all_units = sorted(region_population["UNIT_NAME"].dropna().unique().tolist())
            if "unit_filter" not in st.session_state:
                st.session_state["unit_filter"] = all_units
            elif not set(st.session_state["unit_filter"]).issubset(all_units):
                st.session_state["unit_filter"] = all_units
            selected_units = st.multiselect(
                "부대",
                options=all_units,
                key="unit_filter",
            )
            available_ranks = [
                rank for rank in RANK_ORDER if rank in population["RANK_NAME"].unique()
            ]
            if "rank_filter" not in st.session_state or not set(
                st.session_state["rank_filter"]
            ).issubset(available_ranks):
                st.session_state["rank_filter"] = available_ranks
            selected_ranks = st.multiselect(
                "계급",
                options=available_ranks,
                key="rank_filter",
            )

            age_min = int(population["AGE"].min())
            age_max = int(population["AGE"].max())
            if age_min < age_max:
                if "age_filter" not in st.session_state:
                    st.session_state["age_filter"] = (age_min, age_max)
                elif (
                    len(st.session_state["age_filter"]) != 2
                    or st.session_state["age_filter"][0] < age_min
                    or st.session_state["age_filter"][1] > age_max
                ):
                    st.session_state["age_filter"] = (age_min, age_max)
                age_range = st.slider(
                    "나이 범위",
                    min_value=age_min,
                    max_value=age_max,
                    key="age_filter",
                )
            else:
                age_range = (age_min, age_max)
                st.caption(f"나이 범위: {age_min}세")

            if "bmi_filter" not in st.session_state:
                st.session_state["bmi_filter"] = list(BMI_CATEGORY_ORDER)
            st.multiselect(
                "BMI 구간 (목록)",
                options=list(BMI_CATEGORY_ORDER),
                key="bmi_filter",
            )

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

    if active_view == "대시보드 홈":
        st.subheader("전체 현황 요약")
        category_counts = scoped["BMI구간"].value_counts()
        total_count = scoped["SOLDIER_ID"].nunique()
        normal_count = int(category_counts.get("정상", 0))
        overweight_obese_count = int(
            category_counts.get("과체중", 0) + category_counts.get("비만", 0)
        )
        underweight_count = int(category_counts.get("저체중", 0))
        cards = [
            ("전체 장병", total_count, tuple(BMI_CATEGORY_ORDER), "total"),
            ("정상 BMI", normal_count, ("정상",), "normal"),
            ("과체중·비만", overweight_obese_count, ("과체중", "비만"), "risk"),
            ("저체중", underweight_count, ("저체중",), "underweight"),
        ]
        card_columns = st.columns(4)
        for column, (label, count, categories, card_style) in zip(card_columns, cards):
            card_active = st.session_state.get("active_summary_card") == label
            with column:
                with st.container(border=True, key=f"summary-card-{card_style}"):
                    st.metric(label, f"{count:,}명")
                    st.button(
                        "선택됨" if card_active else "장병 조회",
                        key=f"summary_card_{label}",
                        type="primary" if card_active else "secondary",
                        width="stretch",
                        on_click=summary_card_callback,
                        args=(categories, label),
                    )

    elif active_view == "개인 정보 조회":
        st.subheader("개인 정보 조회")

    personnel_list_slot = (
        st.container()
        if active_view in ("대시보드 홈", "개인 정보 조회")
        else None
    )

    bmi_panel_open = False
    if active_view in ("대시보드 홈", "통계/분석"):
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
                scoped["BMI구간"].isin(st.session_state.get("bmi_filter", list(BMI_CATEGORY_ORDER)))
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
                tuple(st.session_state.get("bmi_filter", [])),
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
                            show_soldier_detail_dialog(selected_soldier)

    st.divider()
    st.caption(
        "BMI 구간은 일반적인 성인 기준(저체중 <18.5, 정상 18.5–25, "
        "과체중 25–30, 비만 ≥30)으로 표시합니다. 이 화면의 데이터는 "
        "개인 진단이나 의학적 판단을 대체하지 않습니다."
    )


show_dashboard()
