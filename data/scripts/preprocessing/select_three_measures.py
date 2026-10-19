"""회원별 측정 이력이 3건 이상인 경우 첫·중간·마지막 기록을 저장합니다.

입력은 merge_raw_measurements.py의 결과이며, 회원 식별자는 M_CODE,
측정일은 MESURE_DE(YYYYMMDD) 컬럼을 사용합니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER, INTERMEDIATE_THREE_MEASURES, PASSED_FILENAME

logger = logging.getLogger(__name__)

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

    # 1. 회원 ID와 측정일 형식을 검사한다. 측정일은 날짜로 바꿔 정렬에 쓴다.
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

    # 2. 측정일 오름차순으로 정렬한다.
    #    같은 날 측정한 기록이 있어, 실행할 때마다 같은 행이 뽑히도록 안정 정렬로 입력 순서를 유지한다.
    work = df.copy()
    work["_normalized_member_id"] = member_ids
    work["_measure_date"] = measure_dates
    work = work.sort_values("_measure_date", kind="stable")

    # 3. 회원별로 날짜순 위치(0, 1, 2, ...)와 측정 건수 N을 구한다.
    groups = work.groupby("_normalized_member_id", sort=False)
    positions = groups.cumcount()
    counts = groups["_normalized_member_id"].transform("size")
    too_few = counts.lt(MIN_MEASURES)
    if too_few.any():
        raise ValueError(
            f"{MIN_MEASURES}건 미만인 회원이 있습니다. "
            "filter_frequent_members()를 먼저 적용하세요."
        )

    # 4. rows[0], rows[N // 2], rows[N - 1]만 남기고, 회원 ID 순으로 정렬해 원래 컬럼만 반환한다.
    selected = work.loc[
        positions.eq(0) | positions.eq(counts // 2) | positions.eq(counts - 1)
    ]
    selected = selected.sort_values("_normalized_member_id", kind="stable")
    return selected.loc[:, df.columns].copy()


def run(input_path: Path, output_path: Path) -> None:
    """input_path에서 3회 이상 측정한 회원의 첫·중간·마지막 기록을 골라 output_path에 저장합니다."""
    # 1. 입력 로드
    total = load_total(input_path)
    # 2. 3회 이상 측정한 회원의 행만 남긴다.
    frequent = filter_frequent_members(total)
    # 3. 회원마다 첫·중간·마지막 기록 3건을 고른다.
    result = pick_first_middle_last(frequent)
    # 4. 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")

    # 5. 요약 로그
    total_member_ids = total[ID_COL].astype("string").str.strip().replace("", pd.NA)
    logger.info(
        "입력 %s: %s행, 회원 %s명",
        display_path(input_path), f"{len(total):,}", f"{total_member_ids.nunique():,}",
    )
    logger.info(
        "%d회 이상 측정: %s행, 회원 %s명",
        MIN_MEASURES, f"{len(frequent):,}",
        f"{frequent[ID_COL].astype('string').str.strip().nunique():,}",
    )
    logger.info("저장: %s (%s행)", display_path(output_path), f"{len(result):,}")


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(Path(__file__).stem)
    run(INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME, INTERMEDIATE_THREE_MEASURES)


if __name__ == "__main__":
    main()
