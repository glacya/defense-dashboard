"""통합 측정 데이터에서 결측치와 이상치가 있는 행을 제거합니다.

결측치를 먼저 제거하고, 남은 행에서 이상치를 제거합니다.
이상치는 정수여야 하는 횟수 종목의 소수 기록과, 사람이 낼 수 없는 수준의 심폐지구력(VO₂max) 값입니다.
심폐지구력(CARDIO)은 원본 통합 단계에서 세 종목 중 하나로 정해 두었으므로, 여기서는 다른 측정값과 똑같이 결측만 검사합니다.
제거한 행은 사유를 붙여 결측·이상치 두 파일로 나눠 저장합니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_BASIC_REFINEMENT, INTERMEDIATE_MERGED, PASSED_FILENAME

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 제거 행 파일 이름
REMOVED_MISSING_FILENAME = "removed_missing.csv"
REMOVED_OUTLIER_FILENAME = "removed_outlier.csv"
REASON_COLUMN = "제거 사유"

# 횟수로 기록하는 종목. 소수 값은 입력 오류로 본다.
# 오래달리기는 이제 횟수가 아니라 VO₂max(소수)로 들어오므로 여기서 빠졌다.
INTEGER_SCORE_COLUMNS = [
    "CROSS_UP",
]
# 심폐지구력 VO₂max(mL/kg/min) 상한. 이보다 큰 값은 이상치로 제거한다.
# 엘리트 지구력 선수도 80 안팎이고, 19~24세 남성 데이터의 99.99% 분위는 64.7이다(2026-10-20 기준).
# 이 기준으로 걸리는 값은 96.5 하나뿐인데(다음으로 큰 값 70.4), 스텝검사 회복기 심박수로 계산하면 약 50이 나오는 입력 오류였다.
CARDIO_COLUMN = "CARDIO"
CARDIO_MAX = 80.0
# 비어 있어도 결측으로 제거하지 않는 컬럼.
# 운동 처방은 측정값이 아니고, 본운동 단계가 없는 처방은 원본 통합 단계에서 빈칸이 되므로 결측 검사에서 뺀다.
NULLABLE_COLUMNS = [
    "MVM_PRSCRPTN_CN",
]


def read_input(path: Path) -> pd.DataFrame:
    """통합 CSV를 모든 값을 문자열로 읽습니다. 빈 칸은 빈 문자열로 유지합니다."""
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def find_missing(df: pd.DataFrame) -> pd.DataFrame:
    """NULLABLE_COLUMNS를 뺀 컬럼마다 값이 비어 있는지를 표시한 True/False 표를 반환합니다."""
    required_columns = [column for column in df.columns if column not in NULLABLE_COLUMNS]
    return df[required_columns].apply(lambda column: column.str.strip().eq(""))


def find_decimal_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """INTEGER_SCORE_COLUMNS마다 값이 정수가 아닌(소수) 행을 표시한 True/False 표를 반환합니다.

    빈 값과 숫자가 아닌 값은 이상치로 보지 않습니다. 빈 값은 결측 단계에서 걸러집니다.
    """
    numbers = df[INTEGER_SCORE_COLUMNS].apply(lambda column: pd.to_numeric(column.str.strip(), errors="coerce"))
    return numbers.notna() & numbers.mod(1).ne(0)


def find_cardio_over_limit(df: pd.DataFrame) -> pd.DataFrame:
    """심폐지구력(VO₂max)이 CARDIO_MAX보다 큰 행을 표시한 True/False 표(CARDIO 한 컬럼)를 반환합니다.

    빈 값과 숫자가 아닌 값은 이상치로 보지 않습니다. 빈 값은 결측 단계에서 걸러집니다.
    """
    cardio = pd.to_numeric(df[CARDIO_COLUMN].str.strip(), errors="coerce")
    return cardio.gt(CARDIO_MAX).to_frame(CARDIO_COLUMN)


def describe_reasons(masks: pd.DataFrame, suffix: str = "") -> pd.Series:
    """행마다 True인 컬럼 이름에 suffix를 붙여 '컬럼1 결측; 컬럼2 결측'처럼 이어 붙인 사유를 만듭니다.

    suffix가 비어 있으면 컬럼 이름만 씁니다(컬럼 이름에 사유가 이미 들어 있을 때).
    """
    # 행이 없으면 apply가 Series 대신 빈 DataFrame을 돌려주므로 따로 처리한다.
    if masks.empty:
        return pd.Series(dtype="string", index=masks.index)
    labels = masks.columns if not suffix else masks.columns + f" {suffix}"
    reasons = masks.apply(lambda row: "; ".join(labels[row.to_numpy()]), axis=1)
    return reasons.astype("string")


def remove_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """결측값이 있는 행을 제거합니다.

    Returns:
        (남은 행, 제거 사유를 붙인 제거 행, 컬럼별 결측 행 수)
    """
    missing = find_missing(df)
    removed_rows = missing.any(axis=1)
    removed = df.loc[removed_rows].copy()
    removed[REASON_COLUMN] = describe_reasons(missing.loc[removed_rows], "결측")
    return df.loc[~removed_rows].copy(), removed, missing.sum()


def remove_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """이상치가 있는 행을 제거합니다. 횟수 종목의 소수 기록과 CARDIO_MAX를 넘는 심폐지구력이 대상입니다.

    Returns:
        (남은 행, 제거 사유를 붙인 제거 행, 이상치 종류별 행 수. 키는 '컬럼 사유' 형식)
    """
    rules = {
        "소수 기록": find_decimal_outliers(df),
        f"{CARDIO_MAX:g} 초과": find_cardio_over_limit(df),
    }
    # 규칙별 표를 한 표로 합쳐 사유 문구를 만든다. 컬럼 이름에 사유를 붙여 두면 describe_reasons를 그대로 쓸 수 있다.
    masks = pd.concat(
        [rule_masks.add_suffix(f" {suffix}") for suffix, rule_masks in rules.items()], axis=1
    )
    removed_rows = masks.any(axis=1)
    removed = df.loc[removed_rows].copy()
    removed[REASON_COLUMN] = describe_reasons(masks.loc[removed_rows])
    return df.loc[~removed_rows].copy(), removed, masks.sum()


def run(input_path: Path, output_dir: Path) -> None:
    """input_path에서 결측치·이상치가 없는 행을 output_dir/passed.csv에, 제거한 행을 사유별 파일에 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / PASSED_FILENAME
    missing_removed_path = output_dir / REMOVED_MISSING_FILENAME
    outlier_removed_path = output_dir / REMOVED_OUTLIER_FILENAME
    # 2. 입력 로드 및 필수 컬럼 검사
    df = read_input(input_path)
    missing_columns = [column for column in [*INTEGER_SCORE_COLUMNS, CARDIO_COLUMN] if column not in df.columns]
    if missing_columns:
        raise ValueError(f"필수 측정 컬럼이 없습니다: {', '.join(missing_columns)}")

    # 3. 결측치를 먼저 제거하고, 남은 행에서 이상치를 제거한다.
    #    두 조건에 모두 걸린 행은 결측 파일에만 들어간다.
    without_missing, missing_removed, missing_counts = remove_missing(df)
    passed, outlier_removed, outlier_counts = remove_outliers(without_missing)

    # 4. 저장 후, 통과 + 제거 행 수가 입력 행 수와 같은지 검증한다.
    passed.to_csv(output_path, index=False, encoding="utf-8-sig")
    missing_removed.to_csv(missing_removed_path, index=False, encoding="utf-8-sig")
    outlier_removed.to_csv(outlier_removed_path, index=False, encoding="utf-8-sig")
    if len(passed) + len(missing_removed) + len(outlier_removed) != len(df):
        raise RuntimeError("통과/결측 제거/이상치 제거 행 수가 입력 행 수와 일치하지 않습니다.")

    # 5. 요약 로그
    logger.info(
        "입력 %s: %s행 -> %s행 (결측 %s행, 이상치 %s행 제거)",
        display_path(input_path), f"{len(df):,}", f"{len(passed):,}",
        f"{len(missing_removed):,}", f"{len(outlier_removed):,}",
    )
    logger.info("속성별 결측 수 (한 행이 여러 속성에서 결측일 수 있음):")
    for column in df.columns:
        if column in NULLABLE_COLUMNS:
            logger.info("  %s: 결측이어도 제거하지 않음", column)
        else:
            logger.info("  %s: 결측 %s행", column, f"{int(missing_counts[column]):,}")
    logger.info("이상치 종류별 행 수 (결측 제거 후, 한 행이 여러 종류에 걸릴 수 있음):")
    for label, count in outlier_counts.items():
        logger.info("  %s: %s행", label, f"{count:,}")
    logger.info("저장(통과): %s", display_path(output_path))
    logger.info("저장(결측 제거): %s", display_path(missing_removed_path))
    logger.info("저장(이상치 제거): %s", display_path(outlier_removed_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_MERGED, INTERMEDIATE_BASIC_REFINEMENT)


if __name__ == "__main__":
    main()
