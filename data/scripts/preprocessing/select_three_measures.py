"""회원마다 측정 기록 3건을 고르고, 측정일과 나이의 흐름이 맞지 않는 회원을 제외해 저장합니다.

입력은 입대 후보 조건 필터의 결과(enlistment_filter/passed.csv)이며, 회원 식별자는 M_CODE,
측정일은 MESURE_DE(YYYYMMDD), 나이는 AGE(만나이) 컬럼을 사용합니다.
1. 측정 간격이 모두 MIN_INTERVAL_DAYS(30일) 이상인 3건 조합 중 전체 기간이 가장 길고, 두 간격이 가장 고른 조합을 고릅니다.
   고른 3건의 첫 측정과 마지막 측정이 3년 넘게 떨어진 회원은 제외합니다.
   같은 날 두 번 입력된 중복 기록은 간격이 0일이라 함께 뽑히지 않습니다.
2. 고른 3건에서 측정일이 지났는데 만나이가 줄었거나, 같은 날인데 나이가 다르거나, 흐른 연도에 비해
   나이가 너무 많이 또는 너무 적게 늘어난 회원은 3건 모두 제외하고, 사유를 붙여 따로 저장합니다.
"""

import itertools
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    INTERMEDIATE_ENLISTMENT_FILTER,
    INTERMEDIATE_THREE_MEASURES,
    INTERMEDIATE_THREE_MEASURES_REMOVED,
    PASSED_FILENAME,
)
from data.scripts.utils import read_text_csv, require_columns, write_csv

logger = logging.getLogger(__name__)

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
AGE_COL = "AGE"
MIN_MEASURES = 3
MIN_INTERVAL_DAYS = 30  # 최소 측정일 간격 설정 변수
MAX_SPAN_DAYS = 365 * 3  # 고른 3건의 첫 측정과 마지막 측정 사이 최대 기간
REASON_COL = "제거 사유"
_REQUIRED_COLUMNS = (ID_COL, DATE_COL)
_AGE_CHECK_COLUMNS = (ID_COL, DATE_COL, AGE_COL)


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


def find_age_time_inconsistency(group_df: pd.DataFrame) -> str | None:
    """회원 1명의 측정 기록 3건에서 측정일과 만나이의 흐름이 모순되면 그 사유를, 아니면 None을 반환합니다.

    앞의 검사에 걸리면 뒤의 검사는 하지 않으므로, 사유는 처음 걸린 하나만 반환합니다.
    """
    if len(group_df) != MIN_MEASURES:
        return f"측정 건수 {len(group_df)}건"

    # 같은 날 측정한 기록이 있어, 실행할 때마다 같은 순서가 되도록 안정 정렬로 입력 순서를 유지한다.
    sorted_df = group_df.sort_values(DATE_COL, kind="stable")
    dates = pd.to_datetime(sorted_df[DATE_COL].astype(str), format="%Y%m%d", errors="coerce")
    if dates.isna().any():
        return f"{DATE_COL} 형식 오류"

    years = dates.dt.year.values
    months = dates.dt.month.values
    days = dates.dt.day.values
    try:
        ages = sorted_df[AGE_COL].astype(int).values
    except ValueError:
        return f"{AGE_COL} 정수 아님"

    # 이웃한 두 측정끼리 차례로 비교한다.
    for i in range(MIN_MEASURES - 1):
        y1, m1, d1, a1 = years[i], months[i], days[i], ages[i]
        y2, m2, d2, a2 = years[i + 1], months[i + 1], days[i + 1], ages[i + 1]

        # 1. 시간이 흘렀는데 나이가 줄었거나, 같은 날인데 나이가 다르면 모순이다.
        time_passed = (y2 > y1) or (y2 == y1 and m2 > m1) or (y2 == y1 and m2 == m1 and d2 > d1)
        time_equal = y2 == y1 and m2 == m1 and d2 == d1
        if time_passed and a2 < a1:
            return "나이 감소"
        if time_equal and a2 != a1:
            return "같은 날 나이 다름"

        # 2. 만나이는 x년이 지나면 최대 x+1살까지만 늘어난다.
        year_diff = y2 - y1
        age_diff = a2 - a1
        if age_diff < 0:
            return "나이 감소"
        if age_diff > year_diff + 1:
            return "연도 차이보다 나이 증가가 큼"

        # 3. 연도가 2년 이상 차이 나면 생일이 적어도 (연도 차이 - 1)번은 지났어야 한다.
        #    상한(a1 + 연도 차이 + 1)은 2번에서 이미 검사했다.
        if a2 < a1 + max(0, year_diff - 1):
            return "연도 차이보다 나이 증가가 작음"

    return None


def remove_age_time_inconsistencies(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """회원 단위로 측정일·만나이 흐름을 검사해 (통과 행, 제거 행)을 반환합니다.

    제거 행에는 회원별 제거 사유를 REASON_COL 컬럼으로 붙입니다. 행의 순서는 입력 순서를 유지합니다.
    """
    require_columns(df, _AGE_CHECK_COLUMNS)
    if df.empty:
        return df.copy(), df.assign(**{REASON_COL: pd.Series(dtype=str)})

    reasons: dict[str, str] = {}
    for member_id, group in df.groupby(ID_COL, sort=False):
        reason = find_age_time_inconsistency(group)
        if reason is not None:
            reasons[member_id] = reason

    is_inconsistent = df[ID_COL].isin(reasons.keys())
    removed = df.loc[is_inconsistent].copy()
    removed[REASON_COL] = removed[ID_COL].map(reasons)
    return df.loc[~is_inconsistent].copy(), removed


def run(input_path: Path, output_path: Path, removed_path: Path) -> None:
    """input_path에서 3회 이상 측정한 회원마다 측정 기록 3건을 고른 뒤, 측정일·나이 흐름이 맞는 회원만 output_path에 저장합니다.

    흐름이 맞지 않아 제외한 회원의 3건은 사유를 붙여 removed_path에 저장합니다.

    Raises:
        RuntimeError: 통과 + 제거 행 수가 3건 고르기 결과 행 수와 다를 때
    """
    total = read_text_csv(input_path)
    require_columns(total, _AGE_CHECK_COLUMNS)
    frequent = filter_frequent_members(total)
    selected = pick_first_middle_last(frequent)
    passed, removed = remove_age_time_inconsistencies(selected)
    if len(passed) + len(removed) != len(selected):
        raise RuntimeError("통과/제거 행 수가 3건 고르기 결과 행 수와 일치하지 않습니다.")
    write_csv(passed, output_path)
    write_csv(removed, removed_path)

    def count_members(df: pd.DataFrame) -> int:
        return df[ID_COL].astype("string").str.strip().replace("", pd.NA).nunique()

    logger.info("입력 %s: %s행, 회원 %s명", display_path(input_path), f"{len(total):,}", f"{count_members(total):,}")
    logger.info(
        "%d회 이상 측정 회원에서 3건 고르기: %s행, 회원 %s명",
        MIN_MEASURES, f"{len(selected):,}", f"{count_members(selected):,}",
    )
    logger.info(
        "측정일·나이 흐름 모순 제거: %s행, 회원 %s명",
        f"{len(removed):,}", f"{count_members(removed):,}",
    )
    for reason, count in removed.drop_duplicates(ID_COL)[REASON_COL].value_counts().items():
        logger.info("  %s: 회원 %s명", reason, f"{count:,}")
    logger.info("저장(통과): %s (%s행, 회원 %s명)", display_path(output_path), f"{len(passed):,}", f"{count_members(passed):,}")
    logger.info("저장(제거): %s", display_path(removed_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(
        INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME,
        INTERMEDIATE_THREE_MEASURES,
        INTERMEDIATE_THREE_MEASURES_REMOVED,
    )


if __name__ == "__main__":
    main()