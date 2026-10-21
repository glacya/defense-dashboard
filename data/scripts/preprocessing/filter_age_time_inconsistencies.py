"""회원별 3행(첫·중간·마지막) 데이터에서 측정일과 나이의 흐름이 맞지 않는 회원을 분리합니다.

측정일이 지났는데 만나이가 줄었거나, 같은 날인데 나이가 다르거나, 흐른 연도에 비해
나이가 너무 많이 또는 너무 적게 늘어난 회원은 3행 모두 제거합니다.
입력은 select_three_measures.py의 결과입니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_AGE_TIME_FILTER, INTERMEDIATE_THREE_MEASURES, PASSED_FILENAME

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 제거 행 파일 이름
REMOVED_INCONSISTENT_FILENAME = "removed_inconsistent.csv"

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
AGE_COL = "AGE"
MEASURES_PER_MEMBER = 3
REASON_COL = "제거 사유"
_REQUIRED_COLUMNS = (ID_COL, DATE_COL, AGE_COL)


def read_input(path: Path) -> pd.DataFrame:
    """3회분 CSV를 모든 값을 문자열로 읽습니다."""
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def _validate_required_columns(df: pd.DataFrame) -> None:
    missing = [column for column in _REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")


def find_age_time_inconsistency(group_df: pd.DataFrame) -> str | None:
    """회원 1명의 측정 기록에서 측정일과 만나이의 흐름이 모순되면 그 사유를, 아니면 None을 반환합니다.

    앞의 검사에 걸리면 뒤의 검사는 하지 않으므로, 사유는 처음 걸린 하나만 반환합니다.
    """
    if len(group_df) != MEASURES_PER_MEMBER:
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
    for i in range(MEASURES_PER_MEMBER - 1):
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


def is_invalid_age_year_pattern(group_df: pd.DataFrame) -> bool:
    """회원 1명의 측정 기록에서 측정일과 만나이의 흐름이 모순되면 True를 반환합니다."""
    return find_age_time_inconsistency(group_df) is not None


def filter_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """회원 단위로 측정일·만나이 흐름을 검사해 (정상 행, 제거 행)을 반환합니다.

    제거 행에는 회원별 제거 사유를 REASON_COL 컬럼으로 붙입니다.
    """
    _validate_required_columns(df)
    if df.empty:
        return df.copy(), df.assign(**{REASON_COL: pd.Series(dtype=str)})

    reasons: dict[str, str] = {}
    for member_id, group in df.groupby(ID_COL, sort=False):
        reason = find_age_time_inconsistency(group)
        if reason is not None:
            reasons[member_id] = reason

    is_outlier = df[ID_COL].isin(reasons.keys())
    normal_df = df.loc[~is_outlier].copy()
    outlier_df = df.loc[is_outlier].copy()
    outlier_df[REASON_COL] = outlier_df[ID_COL].map(reasons)
    return normal_df, outlier_df


def run(input_path: Path, output_dir: Path) -> None:
    """input_path에서 측정일·만나이 흐름이 맞는 회원의 행만 골라 output_dir/passed.csv에 저장합니다.

    제거한 회원의 행은 사유를 붙여 removed_inconsistent.csv에 저장합니다.
    """
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / PASSED_FILENAME
    removed_path = output_dir / REMOVED_INCONSISTENT_FILENAME
    # 2. 입력 로드 및 필수 컬럼 검사
    data = read_input(input_path)
    _validate_required_columns(data)

    # 3. 회원 단위로 검사해 나눈다.
    passed, removed = filter_outliers(data)

    # 4. 저장 후, 통과 + 제거 행 수가 입력 행 수와 같은지 검증한다.
    passed.to_csv(output_path, index=False, encoding="utf-8-sig")
    removed.to_csv(removed_path, index=False, encoding="utf-8-sig")
    if len(passed) + len(removed) != len(data):
        raise RuntimeError("통과/제거 행 수가 입력 행 수와 일치하지 않습니다.")

    # 5. 요약 로그
    logger.info(
        "입력 %s: %s행, 회원 %s명",
        display_path(input_path), f"{len(data):,}", f"{data[ID_COL].nunique():,}",
    )
    logger.info(
        "측정일·나이 흐름 정상: %s행, 회원 %s명",
        f"{len(passed):,}", f"{passed[ID_COL].nunique():,}",
    )
    logger.info(
        "측정일·나이 흐름 모순 제거: %s행, 회원 %s명",
        f"{len(removed):,}", f"{removed[ID_COL].nunique():,}",
    )
    member_reasons = removed.drop_duplicates(ID_COL)[REASON_COL].value_counts()
    for reason, count in member_reasons.items():
        logger.info("  %s: 회원 %s명", reason, f"{count:,}")
    logger.info("저장(통과): %s", display_path(output_path))
    logger.info("저장(제거): %s", display_path(removed_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_THREE_MEASURES, INTERMEDIATE_AGE_TIME_FILTER)


if __name__ == "__main__":
    main()
