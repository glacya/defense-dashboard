"""회원별 측정 이력이 3건 이상인 경우 첫·중간·마지막 기록을 저장합니다.

입력 KS_NFA_TOTAL.csv는 data_merger.py가 생성하며, 회원 식별자는 M_CODE,
측정일은 MESURE_DE(YYYYMMDD) 컬럼을 사용합니다.
"""

import sys
from pathlib import Path

import pandas as pd

from config import CSV_DATA_DIR

INPUT_PATH = CSV_DATA_DIR / "KS_NFA_TOTAL.csv"
OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_THREE_MEASURES.csv"

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
MIN_MEASURES = 3
_REQUIRED_COLUMNS = (ID_COL, DATE_COL)


def load_total(path: Path) -> pd.DataFrame:
    """병합 데이터를 문자열 그대로 읽고 필수 컬럼을 검증합니다."""
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    _validate_required_columns(df)
    return df


def _validate_required_columns(df: pd.DataFrame) -> None:
    missing = [column for column in _REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")


def filter_frequent_members(
    df: pd.DataFrame, min_count: int = MIN_MEASURES
) -> pd.DataFrame:
    """유효한 회원 식별자가 있고 측정 건수가 min_count 이상인 행만 남깁니다."""
    _validate_required_columns(df)
    if min_count < 1:
        raise ValueError("min_count는 1 이상이어야 합니다.")

    member_ids = df[ID_COL].astype("string").str.strip()
    valid_ids = member_ids.notna() & member_ids.ne("")
    counts = member_ids.groupby(member_ids).transform("size")
    return df.loc[valid_ids & counts.ge(min_count)].copy()


def pick_first_middle_last(df: pd.DataFrame) -> pd.DataFrame:
    """회원마다 날짜순 첫·중간·마지막 기록을 선택합니다.

    같은 날짜의 기록은 입력된 순서를 유지합니다. 측정일이 YYYYMMDD 형식이
    아니거나 측정 건수가 3건 미만인 회원이 있으면 명시적으로 오류를 냅니다.
    """
    _validate_required_columns(df)
    if df.empty:
        return df.copy()

    member_ids = df[ID_COL].astype("string").str.strip()
    if member_ids.isna().any() or member_ids.eq("").any():
        raise ValueError(f"{ID_COL} 값이 비어 있는 행이 있습니다.")

    measure_dates = pd.to_datetime(
        df[DATE_COL].astype("string").str.strip(),
        format="%Y%m%d",
        errors="coerce",
    )
    invalid_dates = measure_dates.isna()
    if invalid_dates.any():
        raise ValueError(
            f"{DATE_COL} 값이 YYYYMMDD 형식이 아닌 행이 "
            f"{int(invalid_dates.sum()):,}개 있습니다."
        )

    work = df.copy()
    work["_normalized_member_id"] = member_ids
    work["_measure_date"] = measure_dates
    work = work.sort_values("_measure_date", kind="stable")

    groups = work.groupby("_normalized_member_id", sort=False)
    positions = groups.cumcount()
    counts = groups["_normalized_member_id"].transform("size")
    too_few = counts.lt(MIN_MEASURES)
    if too_few.any():
        raise ValueError(
            f"{MIN_MEASURES}건 미만인 회원이 있습니다. "
            "filter_frequent_members()를 먼저 적용하세요."
        )

    selected = work.loc[
        positions.eq(0) | positions.eq(counts // 2) | positions.eq(counts - 1)
    ]
    selected = selected.sort_values("_normalized_member_id", kind="stable")
    return selected.loc[:, df.columns].copy()


def main() -> None:
    if not INPUT_PATH.exists():
        sys.exit(f"{INPUT_PATH}이 없습니다. data_merger.py를 먼저 실행하세요.")

    total = load_total(INPUT_PATH)
    frequent = filter_frequent_members(total)
    result = pick_first_middle_last(frequent)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    total_member_ids = total[ID_COL].astype("string").str.strip().replace("", pd.NA)
    print(
        f"{INPUT_PATH.name}: {len(total):,}행, "
        f"회원 {total_member_ids.nunique():,}명"
    )
    print(
        f"{MIN_MEASURES}회 이상 측정: {len(frequent):,}행, "
        f"회원 {frequent[ID_COL].astype('string').str.strip().nunique():,}명"
    )
    print(f"{OUTPUT_PATH.name}: {len(result):,}행")


if __name__ == "__main__":
    main()
