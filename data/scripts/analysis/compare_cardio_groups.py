"""심폐 종목(트레드밀·스텝검사 대 20m 왕복 오래달리기)을 고른 집단끼리 다른 체력 항목과 신체조성 분포를 비교합니다. (탐색용 임시 스크립트)

종목별 Z점수나 등급 컷 보정은 "종목을 고른 집단의 체력이 비슷하다"는 가정에 기대므로,
심폐 외 항목에서 두 집단이 얼마나 다른지 확인합니다. 행(측정) 단위로 비교하며 첫 측정을 따로 구별하지 않습니다.
표본이 커서 p값은 거의 항상 작으므로 차이의 크기는 효과크기(Cohen's d, KS 통계량)로 판단합니다.
현재 파이프라인에서 쓰지 않습니다.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_CARDIO_GROUPS, INTERMEDIATE_ENLISTMENT_FILTER, PASSED_FILENAME
from data.scripts.analysis.standardize_cardio_scores import identify_cardio_event, read_input

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 파일 이름
SUMMARY_FILENAME = "group_summary.csv"
COMPARISON_FILENAME = "group_comparison.csv"

VO2_EVENTS = ("TRAD", "STEP")
SHUTTLE_EVENT = "20M_RUN"
GROUP_VO2 = "트레드밀·스텝검사"
GROUP_SHUTTLE = "오래달리기"
# 비교할 항목과 표시 이름
COMPARE_COLUMNS = {
    "REL_GRIP": "상대악력",
    "CROSS_UP": "교차윗몸일으키기",
    "SIT_REACH": "앉아윗몸앞으로굽히기",
    "BMI": "BMI",
    "BODY_FAT_PERCENTAGE": "체지방률",
    "HEIGHT": "신장",
    "WEIGHT": "체중",
    "AGE": "나이",
}
DECIMALS = 4


def assign_groups(df: pd.DataFrame) -> pd.Series:
    """행마다 심폐 종목 집단(트레드밀·스텝검사 또는 오래달리기)을 반환합니다."""
    events, _ = identify_cardio_event(df)
    return pd.Series(np.where(events.eq(SHUTTLE_EVENT), GROUP_SHUTTLE, GROUP_VO2), index=df.index)


def numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """비교 항목을 숫자로 바꿉니다. 빈칸이나 숫자가 아닌 값은 결측으로 둡니다."""
    return df[list(COMPARE_COLUMNS)].apply(lambda column: pd.to_numeric(column.str.strip(), errors="coerce"))


def summarize(values: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """집단·항목별 행 수, 평균, 표준편차, 사분위수를 표로 만듭니다."""
    rows = []
    for column, label in COMPARE_COLUMNS.items():
        for group in (GROUP_VO2, GROUP_SHUTTLE):
            x = values.loc[groups.eq(group), column].dropna()
            rows.append({
                "ITEM": label,
                "GROUP": group,
                "N": len(x),
                "MEAN": x.mean(),
                "STD": x.std(),
                "Q25": x.quantile(0.25),
                "MEDIAN": x.median(),
                "Q75": x.quantile(0.75),
            })
    return pd.DataFrame(rows)


def compare(values: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """항목별로 두 집단의 평균 차이, Cohen's d, KS 통계량, Mann-Whitney 검정 결과를 표로 만듭니다.

    차이와 d는 트레드밀·스텝검사 집단 − 오래달리기 집단 방향입니다.
    """
    rows = []
    for column, label in COMPARE_COLUMNS.items():
        a = values.loc[groups.eq(GROUP_VO2), column].dropna()
        b = values.loc[groups.eq(GROUP_SHUTTLE), column].dropna()
        pooled_std = np.sqrt(((len(a) - 1) * a.var() + (len(b) - 1) * b.var()) / (len(a) + len(b) - 2))
        ks = stats.ks_2samp(a, b)
        mann_whitney = stats.mannwhitneyu(a, b)
        rows.append({
            "ITEM": label,
            "MEAN_DIFF": a.mean() - b.mean(),
            "COHENS_D": (a.mean() - b.mean()) / pooled_std,
            "STD_RATIO": a.std() / b.std(),
            "KS_STAT": ks.statistic,
            "KS_P": ks.pvalue,
            "MANN_WHITNEY_P": mann_whitney.pvalue,
            # 무작위로 한 명씩 뽑았을 때 트레드밀·스텝검사 쪽 값이 더 클 확률. 0.5면 차이 없음.
            "PROB_VO2_GREATER": mann_whitney.statistic / (len(a) * len(b)),
        })
    return pd.DataFrame(rows)


def run(input_path: Path, output_dir: Path) -> None:
    """input_path의 측정 행을 심폐 종목 집단으로 나눠 다른 항목의 분포를 비교하고 output_dir에 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_FILENAME
    comparison_path = output_dir / COMPARISON_FILENAME
    # 2. 입력 로드 후 집단을 나누고 비교 항목을 숫자로 바꾼다.
    data = read_input(input_path).reset_index(drop=True)
    groups = assign_groups(data)
    values = numeric_columns(data)

    # 3. 집단별 요약과 집단 간 비교
    summary = summarize(values, groups)
    comparison = compare(values, groups)

    # 4. 저장
    summary.round(DECIMALS).to_csv(summary_path, index=False, encoding="utf-8-sig")
    comparison.to_csv(comparison_path, index=False, encoding="utf-8-sig", float_format="%.4g")

    # 5. 요약 로그
    logger.info(
        "입력 %s: %s행 (%s %s행, %s %s행)",
        display_path(input_path), f"{len(data):,}",
        GROUP_VO2, f"{int(groups.eq(GROUP_VO2).sum()):,}", GROUP_SHUTTLE, f"{int(groups.eq(GROUP_SHUTTLE).sum()):,}",
    )
    for _, row in comparison.iterrows():
        logger.info(
            "  %s: 평균 차이 %+.3f, Cohen's d %+.3f, 표준편차 비 %.3f, KS %.3f",
            row["ITEM"], row["MEAN_DIFF"], row["COHENS_D"], row["STD_RATIO"], row["KS_STAT"],
        )
    logger.info("저장(집단별 요약): %s", display_path(summary_path))
    logger.info("저장(집단 간 비교): %s", display_path(comparison_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME, INTERMEDIATE_CARDIO_GROUPS)


if __name__ == "__main__":
    main()
