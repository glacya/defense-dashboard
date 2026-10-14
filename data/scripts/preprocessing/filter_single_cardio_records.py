"""심폐지구력 종목(트레드밀·스텝검사·20m 왕복 오래달리기) 중 정확히 하나만 기록된 행만 남깁니다.

제거한 행은 사유를 붙여 결측·정수형 소수 이상치·기타 조건의 세 파일로 나눠 저장합니다.
"""

import logging
from pathlib import Path

import pandas as pd

from dashboard.py.loader import load_csv_data
from data.scripts.logging_setup import display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_CARDIO_FILTER, INTERMEDIATE_MERGED, PASSED_FILENAME

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 제거 행 파일 이름
REMOVED_MISSING_FILENAME = "removed_missing.csv"
REMOVED_OUTLIER_FILENAME = "removed_outlier.csv"
REMOVED_OTHER_FILENAME = "removed_other.csv"

CARDIO_COLUMNS = [
    "TRAD",
    "STEP",
    "20M_RUN",
]
NUMERIC_ATTRIBUTE_COLUMNS = [
    "AGE",
    "REL_GRIP",
    "CROSS_UP",
    "TRAD",
    "STEP",
    "20M_RUN",
    "SIT_REACH",
    "HEIGHT",
    "KG",
    "BMI",
    "BODY_FAT",
]
INTEGER_SCORE_COLUMNS = [
    "CROSS_UP",
    "20M_RUN",
]


def run(input_path: Path, output_dir: Path) -> None:
    """input_path에서 심폐 종목이 하나만 기록된 행을 output_dir/passed.csv에, 제거한 행을 사유별 파일에 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / PASSED_FILENAME
    missing_removed_path = output_dir / REMOVED_MISSING_FILENAME
    outlier_removed_path = output_dir / REMOVED_OUTLIER_FILENAME
    other_removed_path = output_dir / REMOVED_OTHER_FILENAME
    # 2. 입력 로드 및 필수 컬럼 검사
    #    값을 문자열 그대로 읽어 빈 칸을 빈 문자열로 유지하고, 숫자 변환은 필요한 곳에서만 한다.
    df = load_csv_data(
        input_path,
        encoding="utf-8-sig",
        keep_default_na=False,
        dtype=str,
    )
    missing_columns = [column for column in CARDIO_COLUMNS if column not in df.columns]
    missing_columns.extend(
        column for column in INTEGER_SCORE_COLUMNS if column not in df.columns
    )
    missing_columns.extend(
        column for column in NUMERIC_ATTRIBUTE_COLUMNS if column not in df.columns
    )
    if missing_columns:
        raise ValueError(f"필수 측정 컬럼이 없습니다: {', '.join(missing_columns)}")

    # 3. 행마다 심폐 종목(TRAD·STEP·20M_RUN)이 몇 개 기록됐는지 센다.
    #    국민체력100은 심폐 종목 중 하나를 골라 측정하므로 정확히 1개인 행이 정상이다.
    cardio_presence = df[CARDIO_COLUMNS].astype("string").apply(
        lambda column: column.str.strip().ne("")
    ).fillna(False)
    cardio_count = cardio_presence.sum(axis=1)
    exactly_one_cardio = cardio_count.eq(1)
    missing_cardio = cardio_count.eq(0)
    multiple_cardio = cardio_count.gt(1)
    # 4. 심폐 3종목을 뺀 나머지 컬럼이 모두 채워졌는지 확인한다.
    #    MVM_PRSCRPTN_CN(운동 처방)도 포함되므로, 운동 처방만 빈 행도 결측으로 제거된다.
    other_columns = [column for column in df.columns if column not in CARDIO_COLUMNS]
    complete_other_attributes = df[other_columns].astype("string").apply(
        lambda column: column.str.strip().ne("")
    ).all(axis=1)

    # 5. 횟수 종목(CROSS_UP·20M_RUN)에 소수 값이 있는지 확인한다.
    #    횟수는 정수여야 하므로 소수는 입력 오류로 보고 제거한다.
    integer_scores = df[INTEGER_SCORE_COLUMNS].apply(
        lambda column: pd.to_numeric(column.str.strip(), errors="coerce")
    )
    integer_score_present = df[INTEGER_SCORE_COLUMNS].apply(
        lambda column: column.astype("string").str.strip().ne("")
    )
    decimal_score_masks = {
        column: integer_score_present[column]
        & integer_scores[column].notna()
        & integer_scores[column].mod(1).ne(0)
        for column in INTEGER_SCORE_COLUMNS
    }
    # 6. [진단용] 숫자 속성끼리 값이 같은 행을 표시한다.
    #    마지막 로그의 '이상치 의심 건수'에만 쓰이고 행을 제거하지는 않는다.
    #    AGE=BMI처럼 우연히 같은 경우도 포함되므로 실제 이상치 수가 아니다.
    numeric_attributes = df[NUMERIC_ATTRIBUTE_COLUMNS].apply(
        lambda column: pd.to_numeric(column.astype("string").str.strip(), errors="coerce")
    )
    same_value_by_attribute = {
        column: pd.Series(False, index=df.index)
        for column in NUMERIC_ATTRIBUTE_COLUMNS
    }
    for index, left_column in enumerate(NUMERIC_ATTRIBUTE_COLUMNS):
        for right_column in NUMERIC_ATTRIBUTE_COLUMNS[index + 1 :]:
            left_values = numeric_attributes[left_column]
            right_values = numeric_attributes[right_column]
            same_value = (
                left_values.notna()
                & right_values.notna()
                & left_values.eq(right_values)
            )
            same_value_by_attribute[left_column] |= same_value
            same_value_by_attribute[right_column] |= same_value
    outlier_masks_by_attribute = {
        column: mask.copy()
        for column, mask in same_value_by_attribute.items()
    }
    for column, mask in decimal_score_masks.items():
        outlier_masks_by_attribute[column] |= mask

    # [진단용] 컬럼별 결측 수 (로그 출력용)
    missing_by_attribute = df.astype("string").apply(
        lambda column: column.isna() | column.str.strip().eq("")
    ).sum()

    # 7. CROSS_UP과 20M_RUN 값이 같은 행을 찾는다.
    #    컬럼이 밀려 값이 복사된 오류로 보고 제거하지만, 두 값이 우연히 같은 정상 기록도 함께 제거될 수 있다.
    same_integer_score = (
        integer_score_present.all(axis=1)
        & integer_scores.notna().all(axis=1)
        & integer_scores[INTEGER_SCORE_COLUMNS[0]].eq(
            integer_scores[INTEGER_SCORE_COLUMNS[1]]
        )
    )

    # 8. 행마다 걸린 조건을 모두 '사유1; 사유2' 형태의 제거 사유로 기록한다.
    removal_reasons = pd.Series("", index=df.index, dtype="string")

    def add_reason(mask: pd.Series, reason: str) -> None:
        existing = removal_reasons.loc[mask]
        removal_reasons.loc[mask] = existing.where(
            existing.eq(""), existing + "; "
        ) + reason

    add_reason(missing_cardio, "심폐 측정값 결측")
    add_reason(multiple_cardio, "심폐 측정값이 2개 이상")
    add_reason(~complete_other_attributes, "나머지 속성 결측")
    for column, mask in decimal_score_masks.items():
        add_reason(mask, f"{column}에 소수 기록")
    add_reason(
        same_integer_score,
        f"{INTEGER_SCORE_COLUMNS[0]}와 {INTEGER_SCORE_COLUMNS[1]} 점수가 동일",
    )

    # 9. 남길 행과 제거할 행을 나눈다.
    #    제거 행은 한 파일에만 들어가며, 우선순위는 소수 이상치 > 결측 > 기타(심폐 2개 이상, CROSS_UP=20M_RUN)다.
    #    제거 사유 컬럼에는 우선순위와 관계없이 걸린 조건이 모두 적힌다.
    integer_outlier_rows = pd.concat(decimal_score_masks, axis=1).any(axis=1)
    keep_rows = (
        exactly_one_cardio
        & complete_other_attributes
        & ~integer_outlier_rows
        & ~same_integer_score
    )
    retained = df.loc[keep_rows].copy()
    missing_rows = (missing_cardio | ~complete_other_attributes) & ~integer_outlier_rows
    other_removed_rows = ~keep_rows & ~missing_rows & ~integer_outlier_rows
    missing_removed = df.loc[missing_rows].copy()
    missing_removed["제거 사유"] = removal_reasons.loc[missing_rows]
    outlier_removed = df.loc[integer_outlier_rows].copy()
    outlier_removed["제거 사유"] = removal_reasons.loc[integer_outlier_rows]
    other_removed = df.loc[other_removed_rows].copy()
    other_removed["제거 사유"] = removal_reasons.loc[other_removed_rows]

    # [진단용] 기타 조건으로 제거된 행이 어느 컬럼 때문인지 표시한다 (로그 출력용).
    other_attribute_masks = {
        column: multiple_cardio & cardio_presence[column]
        for column in CARDIO_COLUMNS
    }
    for column in INTEGER_SCORE_COLUMNS:
        other_attribute_masks[column] = (
            other_attribute_masks.get(column, pd.Series(False, index=df.index))
            | same_integer_score
        )

    # 10. 저장 후, 통과 + 제거 행 수가 입력 행 수와 같은지 검증한다.
    retained.to_csv(output_path, index=False, encoding="utf-8-sig")
    missing_removed.to_csv(missing_removed_path, index=False, encoding="utf-8-sig")
    outlier_removed.to_csv(outlier_removed_path, index=False, encoding="utf-8-sig")
    other_removed.to_csv(other_removed_path, index=False, encoding="utf-8-sig")
    if (
        len(retained)
        + len(missing_removed)
        + len(outlier_removed)
        + len(other_removed)
        != len(df)
    ):
        raise RuntimeError(
            "통과/결측 제거/이상치 제거/기타 제거 행 수가 원본 행 수와 일치하지 않습니다."
        )

    # 11. 요약 로그
    logger.info(
        "입력 %s: %s행 -> %s행 (결측 %s행, 정수형 소수 이상치 %s행, 기타 조건 %s행 제거)",
        display_path(input_path), f"{len(df):,}", f"{len(retained):,}",
        f"{len(missing_removed):,}", f"{len(outlier_removed):,}", f"{len(other_removed):,}",
    )
    logger.info("기타 조건 제거 속성별 관련 행 수(속성 간 중복 집계):")
    for column in [*CARDIO_COLUMNS, "CROSS_UP"]:
        count = int((other_removed_rows & other_attribute_masks[column]).sum())
        logger.info("  %s: %s행", column, f"{count:,}")
    logger.info("속성별 결측/이상치 수 (동일값은 의심 건수, 속성 간 중복 가능):")
    for column in df.columns:
        missing_count = int(missing_by_attribute[column])
        outlier_mask = outlier_masks_by_attribute.get(column)
        if outlier_mask is None:
            logger.info("  %s: 결측 %s행, 이상치 진단 대상 아님", column, f"{missing_count:,}")
        else:
            logger.info(
                "  %s: 결측 %s행, 이상치 %s행",
                column, f"{missing_count:,}", f"{int(outlier_mask.sum()):,}",
            )
    logger.info("정수형 속성 소수값 이상치 제거 수:")
    for column in INTEGER_SCORE_COLUMNS:
        logger.info("  %s: %s행", column, f"{int(decimal_score_masks[column].sum()):,}")
    logger.info("저장(통과): %s", display_path(output_path))
    logger.info("저장(결측 제거): %s", display_path(missing_removed_path))
    logger.info("저장(정수형 소수 이상치 제거): %s", display_path(outlier_removed_path))
    logger.info("저장(기타 조건 제거): %s", display_path(other_removed_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(Path(__file__).stem)
    run(INTERMEDIATE_MERGED, INTERMEDIATE_CARDIO_FILTER)


if __name__ == "__main__":
    main()
