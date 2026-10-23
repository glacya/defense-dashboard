
"""실행: python -m streamlit run data/experiments/장병체력미달현황_회차별변화.py"""
from pathlib import Path

import pandas as pd
import numpy as np
import streamlit as st

# ============================================
# 1. 화면 설정
# ============================================

st.set_page_config(
    page_title="장병 체력 미달 현황",
    layout="wide"
)

st.title("장병 체력 미달 현황")
st.caption("1차 · 2차 · 3차 체력측정 비교 대시보드")

BASE_DIR = Path(__file__).resolve().parents[2]
RESULT_DIR = BASE_DIR / "data" / "experiments" / "results"

SUMMARY_PATH = RESULT_DIR / "fitness_risk_summary.csv"
DETAIL_PATH = RESULT_DIR / "fitness_risk_by_round.csv"

# ============================================
# 2. 데이터 로딩
# ============================================

@st.cache_data
def load_csv(path):
    return pd.read_csv(path, low_memory=False)


if not SUMMARY_PATH.exists():
    st.error(f"파일이 없습니다: {SUMMARY_PATH}")
    st.stop()

try:
    df = load_csv(str(SUMMARY_PATH))
except Exception as e:
    st.error(f"CSV 읽기 오류: {e}")
    st.stop()

required = ["SOLDIER_ID", "weak_1", "weak_2", "weak_3"]

missing = [c for c in required if c not in df.columns]

if missing:
    st.error(f"필수 컬럼이 없습니다: {missing}")
    st.stop()

if df["SOLDIER_ID"].duplicated().any():
    st.error("SOLDIER_ID가 중복되어 있습니다. 장병별 1행이어야 합니다.")
    st.stop()

for i in [1, 2, 3]:
    df[f"weak_{i}"] = pd.to_numeric(
        df[f"weak_{i}"], errors="coerce"
    )

    if (
        df[f"weak_{i}"].isna().any()
        or not df[f"weak_{i}"].between(0, 4).all()
        or not (df[f"weak_{i}"] % 1 == 0).all()
    ):
        st.error(f"weak_{i}에 유효하지 않은 값이 있습니다.")
        st.stop()

    df[f"weak_{i}"] = df[f"weak_{i}"].astype(int)

# ============================================
# 3. 회차별 미달 장병 수
# ============================================

round_counts = {}

for i in [1, 2, 3]:
    round_counts[i] = int(
        (df[f"weak_{i}"] >= 1).sum()
    )


def change_rate(before, after):
    if before == 0:
        return np.nan
    return (after - before) / before * 100


rate_12 = change_rate(round_counts[1], round_counts[2])
rate_23 = change_rate(round_counts[2], round_counts[3])
rate_13 = change_rate(round_counts[1], round_counts[3])

def format_rate(value):
    return "-" if pd.isna(value) else f"{value:+.1f}%"


# ============================================
# 4. KPI
# ============================================

st.subheader("주요 KPI")

c1, c2, c3, c4 = st.columns(4)

c1.metric("전체 장병", f"{len(df):,}명")

c2.metric(
    "1차 미달 장병",
    f"{round_counts[1]:,}명"
)

c3.metric(
    "2차 미달 장병",
    f"{round_counts[2]:,}명",
    delta=format_rate(rate_12),
    delta_color="inverse"
)

c4.metric(
    "3차 미달 장병",
    f"{round_counts[3]:,}명",
    delta=format_rate(rate_23),
    delta_color="inverse"
)

st.caption(
    f"1차 대비 3차 미달자 수 변화율: "
    f"{format_rate(rate_13)}"
)

# ============================================
# 5. 회차별 미달자 수 및 변화율
# ============================================

st.divider()
st.subheader("회차별 미달 장병 수 및 변화율")

round_summary = pd.DataFrame({
    "회차": ["1차", "2차", "3차"],
    "미달자 수": [
        round_counts[1],
        round_counts[2],
        round_counts[3]
    ],
    "전 회차 대비 변화율(%)": [
        np.nan,
        rate_12,
        rate_23
    ]
})

st.dataframe(
    round_summary,
    hide_index=True,
    width="stretch"
)

st.line_chart(
    round_summary.set_index("회차")[["미달자 수"]]
)

# ============================================
# 6. 취약 체력종목 수별 장병 분포
# ============================================

st.divider()
st.subheader("취약 체력종목 수별 장병 분포")

distribution = pd.DataFrame(
    index=["0개", "1개", "2개", "3개", "4개"]
)

for i in [1, 2, 3]:
    counts = (
        df[f"weak_{i}"]
        .value_counts()
        .reindex(range(5), fill_value=0)
    )

    distribution[f"{i}차"] = counts.to_numpy()

st.caption(
    "숫자 셀을 클릭하면 해당 회차에서 "
    "해당 개수만큼 미달한 장병을 조회합니다."
)

event = st.dataframe(
    distribution,
    width="stretch",
    on_select="rerun",
    selection_mode="single-cell",
    key="weak_distribution"
)

cells = event.selection.cells

if cells:
    row_idx, col_idx = cells[0]

    weak_count = int(
        distribution.index[row_idx].replace("개", "")
    )

    round_no = int(
        distribution.columns[col_idx][0]
    )

    soldiers = df[
        df[f"weak_{round_no}"] == weak_count
    ].copy()

    st.subheader(
        f"{round_no}차 · 취약 종목 {weak_count}개 장병"
    )

    st.metric("해당 장병 수", f"{len(soldiers):,}명")

    st.dataframe(
        soldiers,
        width="stretch",
        hide_index=True
    )

# ============================================
# 7. 장병별 개선 · 악화 분석
# ============================================

st.divider()
st.subheader("장병별 체력 변화 분석")

before_round = st.selectbox(
    "기준 회차",
    [1, 2],
    index=0
)

after_round = st.selectbox(
    "비교 회차",
    [2, 3],
    index=1
)

if before_round >= after_round:
    st.warning("비교 회차는 기준 회차보다 커야 합니다.")
else:
    before = df[f"weak_{before_round}"]
    after = df[f"weak_{after_round}"]

    # 취약 종목 개수 변화 기준
    df_compare = df.copy()

    df_compare["변화"] = np.select(
        [
            after < before,
            after > before
        ],
        [
            "개선",
            "악화"
        ],
        default="유지"
    )

    change_counts = (
        df_compare["변화"]
        .value_counts()
        .reindex(["개선", "유지", "악화"], fill_value=0)
    )

    c1, c2, c3 = st.columns(3)

    c1.metric("개선 장병", f"{change_counts['개선']:,}명")
    c2.metric("유지 장병", f"{change_counts['유지']:,}명")
    c3.metric("악화 장병", f"{change_counts['악화']:,}명")

    selected_status = st.radio(
        "장병 목록 조회",
        ["개선", "유지", "악화"],
        horizontal=True
    )

    target = df_compare[
        df_compare["변화"] == selected_status
    ]

    st.dataframe(
        target[
            ["SOLDIER_ID",
             f"weak_{before_round}",
             f"weak_{after_round}",
             "변화"]
        ],
        hide_index=True,
        width="stretch"
    )

# ============================================
# 8. 종목별 상세 미달 현황
# ============================================

st.divider()
st.subheader("체력종목별 미달 현황")

if DETAIL_PATH.exists():

    detail = load_csv(str(DETAIL_PATH))

    st.caption(
        "상세 데이터에 종목별 0/1 미달 컬럼이 있으면 "
        "해당 컬럼을 지정해 조회할 수 있습니다."
    )

    st.write("상세 데이터 컬럼:")
    st.code(", ".join(detail.columns))

    with st.expander("종목별 컬럼 설정"):
        st.info(
            "상세 데이터의 종목별 미달 여부 컬럼이 "
            "확인되면 이 영역에 연결합니다."
        )

else:
    st.info(
        "fitness_risk_by_round.csv 파일이 없어 "
        "종목별 상세 조회는 표시하지 않습니다."
    )

# ============================================
# 9. CSV 다운로드
# ============================================

st.divider()

st.download_button(
    "장병별 체력 위험 요약 다운로드",
    data=df.to_csv(index=False).encode("utf-8-sig"),
    file_name="fitness_risk_summary_export.csv",
    mime="text/csv"
)
