"""회원마다 측정 기록 3건을 골라 저장합니다.

입력은 입대 후보 조건 필터의 결과(enlistment_filter/passed.csv)이며, 회원 식별자는 M_CODE,
측정일은 MESURE_DE(YYYYMMDD) 컬럼을 사용합니다.
측정 간격이 모두 MIN_INTERVAL_DAYS(30일) 이상인 3건 조합 중 전체 기간이 가장 길고, 두 간격이 가장 고른 조합을 고릅니다.
고른 3건의 첫 측정과 마지막 측정이 3년 넘게 떨어진 회원은 제외합니다.
같은 날 두 번 입력된 중복 기록은 간격이 0일이라 함께 뽑히지 않습니다.
"""

import itertools
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER, INTERMEDIATE_THREE_MEASURES, PASSED_FILENAME
from data.scripts.utils import read_text_csv, require_columns, write_csv

logger = logging.getLogger(__name__)

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
MIN_MEASURES = 3
MIN_INTERVAL_DAYS = 30  # 최소 측정일 간격 설정 변수
MAX_SPAN_DAYS = 365 * 3  # 고른 3건의 첫 측정과 마지막 측정 사이 최대 기간
_REQUIRED_COLUMNS = (ID_COL, DATE_COL)


def filter_frequent_members(
    df: pd.DataFrame, min_count: int = MIN_MEASURES
) -> pd.DataFrame:
    """유효한 회원 식별자가 있고 측정 건수가 min_count 이상인 행만 남깁니다."""
    require_columns(df, _REQUIRED_COLUMNS)
    if min_count < 1:
        raise ValueError("min_count는 1 이상이어야 합니다.")
    member_ids = df[ID_COL].astype("string").str.strip()
    valid_ids = member_ids.notna() & member_ids.ne("")
    counts = member_ids.groupby(member_ids).transform("size")
    return df.loc[valid_ids & counts.ge(min_count)].copy()


def select_valid_triplet(dates: np.ndarray) -> tuple[int, int, int] | None:
    """날짜순으로 정렬된 한 회원의 측정일 배열에서 고를 3건의 위치를 반환합니다. 조건에 맞는 조합이 없으면 None입니다.

    두 간격이 모두 MIN_INTERVAL_DAYS 이상인 조합 중, 전체 기간(두 간격의 합)이 가장 길고
    그다음으로 두 간격의 차이가 가장 작은 조합을 고릅니다.
    """
    if len(dates) < MIN_MEASURES:
        return None
    min_interval = np.timedelta64(MIN_INTERVAL_DAYS, "D")
    candidates = []
    for i, j, k in itertools.combinations(range(len(dates)), 3):
        first_gap = dates[j] - dates[i]
        second_gap = dates[k] - dates[j]
        if first_gap >= min_interval and second_gap >= min_interval:
            # 정렬 기준: 전체 기간이 길수록, 두 간격의 차이가 작을수록 앞(내림차순 정렬이라 차이는 음수로 둔다).
            candidates.append((first_gap + second_gap, -abs(first_gap - second_gap), i, j, k))
    if not candidates:
        return None
    _, _, best_i, best_j, best_k = max(candidates)
    return best_i, best_j, best_k


def pick_first_middle_last(df: pd.DataFrame) -> pd.DataFrame:
    """회원마다 측정 기록 3건을 고릅니다. 고르는 규칙은 select_valid_triplet()을 따릅니다.

    같은 날짜의 기록은 입력된 순서를 유지합니다. 조건에 맞는 3건을 고를 수 없는 회원과,
    고른 3건의 기간이 MAX_SPAN_DAYS를 넘는 회원은 제외합니다.
    결과에는 원래 컬럼 뒤에 정렬용 도우미 컬럼(_normalized_member_id, _measure_date)이 붙습니다.

    Raises:
        ValueError: 회원 식별자가 비어 있거나 측정일이 YYYYMMDD 형식이 아닌 행이 있을 때
    """
    require_columns(df, _REQUIRED_COLUMNS)
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
    work = work.sort_values(["_normalized_member_id", "_measure_date"], kind="stable")

    # 회원마다 고를 3건의 행 라벨을 모은다.
    # groupby().apply()로 행을 돌려받으면 pandas 2.2부터 그룹 컬럼 처리·빈 DataFrame 이어 붙이기에 대한
    # FutureWarning이 나고 이후 버전에서 동작이 바뀌므로, 라벨만 모아 한 번에 고른다.
    selected_labels = []
    for _, group in work.groupby("_normalized_member_id", sort=False):
        triplet = select_valid_triplet(group["_measure_date"].to_numpy())
        if triplet is not None:
            selected_labels.extend(group.index[list(triplet)])
    work = work.loc[selected_labels].reset_index(drop=True)

    if work.empty:
        return work

    # 고른 3건의 첫 측정과 마지막 측정이 MAX_SPAN_DAYS 이내인 회원만 남긴다.
    groups = work.groupby("_normalized_member_id", sort=False)["_measure_date"]
    span = groups.transform("max") - groups.transform("min")
    return work[span <= pd.Timedelta(days=MAX_SPAN_DAYS)]


def run(input_path: Path, output_path: Path) -> None:
    """input_path에서 3회 이상 측정한 회원마다 측정 기록 3건을 골라 output_path에 저장합니다."""
    total = read_text_csv(input_path)
    require_columns(total, _REQUIRED_COLUMNS)
    frequent = filter_frequent_members(total)
    result = pick_first_middle_last(frequent)
    write_csv(result, output_path)

    total_member_ids = total[ID_COL].astype("string").str.strip().replace("", pd.NA)
    logger.info(
        f"{input_path.name}: {len(total):,}행, "
        f"회원 {total_member_ids.nunique():,}명"
    )
    logger.info(
        f"{MIN_MEASURES}회 이상 측정: {len(result):,}행, "
        f"회원 {result[ID_COL].astype('string').str.strip().nunique():,}명"
    )
    logger.info(f"{output_path.name}: {len(result):,}행")
    logger.info("저장: %s (%s행)", display_path(output_path), f"{len(result):,}")
    
def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME, INTERMEDIATE_THREE_MEASURES)


if __name__ == "__main__":
    main()