"""3회 측정 장병의 회차별 체력 미달 비율 표를 만들어 저장합니다.

- 대상: 한 장병당 측정이 정확히 3회인 측정 데이터(KS_NFA_PROCESSED.csv). 측정일 오름차순으로 1·2·3차를 매깁니다.
  M_SEQ_NO는 원본 데이터셋 전체의 누적 측정 번호(최대 수백)라 회차로 쓰지 않습니다.
- 미달 판정: 체력 4종목(근력·근지구력·심폐지구력·유연성)이 각각 3등급 하한(fitness_standards.GRADE_CUTS)보다 낮으면 그 종목은 미달입니다.
- 출력 표 1(회차별 미달 비율): 행은 "N개 이상 종목 미달"(N=1~4), 열은 1·2·3차이고 값은 전체 장병 대비 미달 비율(%)입니다.
- 출력 표 2(3차 미달 인원·비율): 행은 표 1과 같고, 열은 3차 미달 인원과 미달 비율(%)입니다. 3차 통과 여부(타깃) 기준을 정할 때 씁니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.fitness_standards import FITNESS_EXERCISES, grade_cut
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.utils import read_text_csv, write_csv
from data.scripts.paths import PROCESSED_FITNESS_PATH


logger = logging.getLogger(__name__)

# 입력 컬럼
MEMBER_ID_COLUMN = "M_CODE"
MESURE_DE_COLUMN = "MESURE_DE"
MESURE_ID_COLUMN = "MESURE_ID"

# 이 단계에서 새로 만드는 컬럼
ROUND_COLUMN = "ROUND"
FAIL_COUNT_COLUMN = "FAIL_COUNT"

# 한 장병의 측정 횟수와 미달 기준 등급(3등급 하한 미만이면 미달)
MEASURE_COUNT = 3
CUT_GRADE = 3

# 출력 표의 컬럼 이름
CRITERIA_COLUMN = "미달 기준"
FINAL_COUNT_COLUMN = "3차 미달 인원"
FINAL_RATE_COLUMN = "미달 비율(%)"


def load_measures(path: Path) -> pd.DataFrame:
    """측정 데이터를 읽어 체력 4종목을 숫자로 바꿉니다.

    Raises:
        ValueError: 체력 값이 숫자가 아니거나 비어 있는 행이 있을 때
    """
    df = read_text_csv(path)
    for exercise in FITNESS_EXERCISES:
        values = pd.to_numeric(df[exercise].str.strip(), errors="coerce")
        if values.isna().any():
            raise ValueError(f"{exercise}가 숫자가 아니거나 비어 있는 행이 {int(values.isna().sum()):,}개 있습니다.")
        df[exercise] = values
    return df


def assign_rounds(df: pd.DataFrame) -> pd.DataFrame:
    """장병별로 측정일 오름차순 1·2·3차를 ROUND 컬럼에 붙입니다.

    측정일은 YYYYMMDD 문자열이라 문자열 순서가 날짜 순서와 같습니다.

    Raises:
        ValueError: 측정이 정확히 3회가 아닌 장병이 있을 때
    """
    counts = df.groupby(MEMBER_ID_COLUMN).size()
    invalid = counts[counts.ne(MEASURE_COUNT)]
    if len(invalid):
        raise ValueError(f"측정이 정확히 {MEASURE_COUNT}회가 아닌 장병이 {len(invalid):,}명 있습니다.")

    sorted_df = df.sort_values([MEMBER_ID_COLUMN, MESURE_DE_COLUMN, MESURE_ID_COLUMN]).reset_index(drop=True)
    sorted_df[ROUND_COLUMN] = sorted_df.groupby(MEMBER_ID_COLUMN).cumcount() + 1
    return sorted_df


def count_fails(df: pd.DataFrame) -> pd.DataFrame:
    """측정마다 3등급 하한 미만인 종목 수(0~4)를 FAIL_COUNT 컬럼에 붙입니다."""
    fails = pd.DataFrame({exercise: df[exercise].lt(grade_cut(exercise, CUT_GRADE)) for exercise in FITNESS_EXERCISES})
    return df.assign(**{FAIL_COUNT_COLUMN: fails.sum(axis=1)})


def build_fail_rate_table(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """회차별로 N개 이상 종목이 미달인 장병의 비율(%)과 인원을 구합니다.

    Returns:
        (비율 표, 인원 표). 두 표 모두 행은 "N개 이상 미달"(N=1~4), 열은 "1차"·"2차"·"3차"
    """
    max_count = len(FITNESS_EXERCISES)
    rates, members = {}, {}
    for round_no in range(1, MEASURE_COUNT + 1):
        fail_counts = df.loc[df[ROUND_COLUMN].eq(round_no), FAIL_COUNT_COLUMN]
        counts = [int(fail_counts.ge(n).sum()) for n in range(1, max_count + 1)]
        members[f"{round_no}차"] = counts
        rates[f"{round_no}차"] = [round(count / len(fail_counts) * 100, 2) for count in counts]

    index = pd.Index(
        [f"{n}개 이상 미달" if n < max_count else f"{n}개 모두 미달" for n in range(1, max_count + 1)],
        name=CRITERIA_COLUMN,
    )
    return pd.DataFrame(rates, index=index).reset_index(), pd.DataFrame(members, index=index).reset_index()


def build_final_round_table(rate_table: pd.DataFrame, member_table: pd.DataFrame) -> pd.DataFrame:
    """마지막 회차(3차)의 N개 이상 미달 인원과 비율(%)을 한 표로 합칩니다.

    Args:
        rate_table, member_table: build_fail_rate_table()의 결과

    Returns:
        컬럼이 "미달 기준", "3차 미달 인원", "미달 비율(%)"인 표
    """
    final_round = f"{MEASURE_COUNT}차"
    return pd.DataFrame({
        CRITERIA_COLUMN: member_table[CRITERIA_COLUMN],
        FINAL_COUNT_COLUMN: member_table[final_round],
        FINAL_RATE_COLUMN: rate_table[final_round],
    })


def run(input_path: Path, output_path: Path, final_round_output_path: Path) -> None:
    """input_path의 측정 데이터로 회차별 미달 비율 표를 만들어 output_path에 저장합니다.

    Args:
        input_path: 장병당 3회 측정이 들어 있는 측정 데이터 (KS_NFA_PROCESSED.csv)
        output_path: 회차별 미달 비율 표 저장 경로
        final_round_output_path: 3차 미달 인원·비율 표 저장 경로

    Raises:
        ValueError: 체력 값이 숫자가 아닐 때, 측정이 3회가 아닌 장병이 있을 때
    """
    # 1. 측정 데이터를 읽고 체력 4종목을 숫자로 바꾼다.
    df = load_measures(input_path)

    # 2. 장병별 측정일 순서로 1·2·3차를 매기고, 측정마다 3등급 하한 미만인 종목 수를 센다.
    df = count_fails(assign_rounds(df))

    # 3. 회차별로 N개 이상 미달 비율을 구해 저장하고, 3차 미달 인원·비율 표도 따로 저장한다.
    rate_table, member_table = build_fail_rate_table(df)
    write_csv(rate_table, output_path)
    write_csv(build_final_round_table(rate_table, member_table), final_round_output_path)

    # 4. 요약 로그
    member_count = df[MEMBER_ID_COLUMN].nunique()
    logger.info("입력 %s: %s행, 장병 %s명", display_path(input_path), f"{len(df):,}", f"{member_count:,}")
    logger.info(
        "미달 기준: %s 3등급 하한 미만",
        ", ".join(f"{exercise} {grade_cut(exercise, CUT_GRADE)}" for exercise in FITNESS_EXERCISES),
    )
    for _, row in member_table.iterrows():
        logger.info(
            "%s: %s",
            row[CRITERIA_COLUMN],
            ", ".join(f"{round_name} {int(row[round_name]):,}명" for round_name in member_table.columns[1:]),
        )
    logger.info("저장(회차별 미달 비율): %s", display_path(output_path))
    logger.info("저장(3차 미달 인원·비율): %s", display_path(final_round_output_path))


def main() -> None:
    """이 단계만 실행합니다. 출력 경로는 프로젝트에 맞게 고칩니다."""
    setup_logging(caller_name(__file__))
    run(
        PROCESSED_FITNESS_PATH,
        Path("data/scripts/analysis/data_model/pred_model/view/FAIL_RATE_BY_ROUND.csv"),  # TODO: 출력 경로(paths.py 상수로 교체)
        Path("data/scripts/analysis/data_model/pred_model/view/FAIL_RATE_FINAL_ROUND.csv"),  # TODO: 출력 경로(paths.py 상수로 교체)
    )


if __name__ == "__main__":
    main()