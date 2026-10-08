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
OTHER_REMOVED_PATH = DATA_DIR / "KS_NFA_TOTAL_CARDIO_REMOVED_OTHER.csv"
CARDIO_COLUMNS = [
    "TRAD",
    "STEP",
    "20M_RUN",
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

    keep_rows = (
        exactly_one_cardio
        & complete_other_attributes
        & ~pd.concat(decimal_score_masks, axis=1).any(axis=1)
        & ~same_integer_score
    )
    retained = df.loc[keep_rows].copy()
    missing_rows = missing_cardio | ~complete_other_attributes
    other_removed_rows = ~keep_rows & ~missing_rows
    missing_removed = df.loc[missing_rows].copy()
    missing_removed["제거 사유"] = removal_reasons.loc[missing_rows]
    other_removed = df.loc[other_removed_rows].copy()
    other_removed["제거 사유"] = removal_reasons.loc[other_removed_rows]

    retained.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    missing_removed.to_csv(MISSING_REMOVED_PATH, index=False, encoding="utf-8-sig")
    other_removed.to_csv(OTHER_REMOVED_PATH, index=False, encoding="utf-8-sig")
    if len(retained) + len(missing_removed) + len(other_removed) != len(df):
        raise RuntimeError("통과/결측 제거/기타 제거 행 수가 원본 행 수와 일치하지 않습니다.")

    print(
        f"{FIT_PATH.name}: {len(df):,}행 -> {len(retained):,}행 "
        f"(결측 {len(missing_removed):,}행, 기타 조건 {len(other_removed):,}행 제거)"
    )
    print(f"통과 데이터 저장 완료: {OUTPUT_PATH}")
    print(f"결측 제거 데이터 저장 완료: {MISSING_REMOVED_PATH}")
    print(f"기타 조건 제거 데이터 저장 완료: {OTHER_REMOVED_PATH}")

if __name__ == "__main__":
    main()
