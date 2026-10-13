from config import (
    CSV_DATA_DIR,
)
from dashboard.py.error_handlers import safe_execution
from dashboard.py.loader import (
    load_csv_data,
)

import pandas as pd

DATA_DIR = CSV_DATA_DIR
FIT_PATH = DATA_DIR / "KS_NFA_TOTAL.csv"
OUTPUT_PATH = DATA_DIR / "KS_NFA_TOTAL_CARDIO_DEDUPED.csv"
MISSING_REMOVED_PATH = DATA_DIR / "KS_NFA_TOTAL_CARDIO_REMOVED_MISSING.csv"
OUTLIER_REMOVED_PATH = DATA_DIR / "KS_NFA_TOTAL_CARDIO_REMOVED_OUTLIER.csv"
OTHER_REMOVED_PATH = DATA_DIR / "KS_NFA_TOTAL_CARDIO_REMOVED_OTHER.csv"
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


@safe_execution(error_message="심폐지구력 중복 제거 실패", error_type="error", reraise=True)
def main():
    if not FIT_PATH.exists():
        raise FileNotFoundError(f"csv 파일을 찾을 수 없습니다: {FIT_PATH}")

    df = load_csv_data(
        FIT_PATH,
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

    cardio_presence = df[CARDIO_COLUMNS].astype("string").apply(
        lambda column: column.str.strip().ne("")
    ).fillna(False)
    cardio_count = cardio_presence.sum(axis=1)
    exactly_one_cardio = cardio_count.eq(1)
    missing_cardio = cardio_count.eq(0)
    multiple_cardio = cardio_count.gt(1)
    other_columns = [column for column in df.columns if column not in CARDIO_COLUMNS]
    complete_other_attributes = df[other_columns].astype("string").apply(
        lambda column: column.str.strip().ne("")
    ).all(axis=1)

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

    missing_by_attribute = df.astype("string").apply(
        lambda column: column.isna() | column.str.strip().eq("")
    ).sum()

    same_integer_score = (
        integer_score_present.all(axis=1)
        & integer_scores.notna().all(axis=1)
        & integer_scores[INTEGER_SCORE_COLUMNS[0]].eq(
            integer_scores[INTEGER_SCORE_COLUMNS[1]]
        )
    )

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

    other_attribute_masks = {
        column: multiple_cardio & cardio_presence[column]
        for column in CARDIO_COLUMNS
    }
    for column in INTEGER_SCORE_COLUMNS:
        other_attribute_masks[column] = (
            other_attribute_masks.get(column, pd.Series(False, index=df.index))
            | same_integer_score
        )

    retained.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    missing_removed.to_csv(MISSING_REMOVED_PATH, index=False, encoding="utf-8-sig")
    outlier_removed.to_csv(OUTLIER_REMOVED_PATH, index=False, encoding="utf-8-sig")
    other_removed.to_csv(OTHER_REMOVED_PATH, index=False, encoding="utf-8-sig")
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

    print(
        f"{FIT_PATH.name}: {len(df):,}행 -> {len(retained):,}행 "
        f"(결측 {len(missing_removed):,}행, 정수형 소수 이상치 "
        f"{len(outlier_removed):,}행, 기타 조건 {len(other_removed):,}행 제거)"
    )
    print("기타 조건 제거 속성별 관련 행 수(속성 간 중복 집계):")
    for column in [*CARDIO_COLUMNS, "CROSS_UP"]:
        count = int((other_removed_rows & other_attribute_masks[column]).sum())
        print(f"  {column}: {count:,}행")
    print("속성별 결측/이상치 수 (동일값은 의심 건수, 속성 간 중복 가능):")
    for column in df.columns:
        missing_count = int(missing_by_attribute[column])
        outlier_mask = outlier_masks_by_attribute.get(column)
        if outlier_mask is None:
            print(f"  {column}: 결측 {missing_count:,}행, 이상치 진단 대상 아님")
        else:
            print(
                f"  {column}: 결측 {missing_count:,}행, "
                f"이상치 {int(outlier_mask.sum()):,}행"
            )
    print("정수형 속성 소수값 이상치 제거 수:")
    for column in INTEGER_SCORE_COLUMNS:
        print(f"  {column}: {int(decimal_score_masks[column].sum()):,}행")
    print(f"통과 데이터 저장 완료: {OUTPUT_PATH}")
    print(f"결측 제거 데이터 저장 완료: {MISSING_REMOVED_PATH}")
    print(f"정수형 소수 이상치 제거 데이터 저장 완료: {OUTLIER_REMOVED_PATH}")
    print(f"기타 조건 제거 데이터 저장 완료: {OTHER_REMOVED_PATH}")

if __name__ == "__main__":
    main()
