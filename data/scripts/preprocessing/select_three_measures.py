"""회원별 측정 이력이 3건 이상인 경우 첫·중간·마지막 기록을 저장합니다.

입력 KS_NFA_TOTAL.csv는 data_merger.py가 생성하며, 회원 식별자는 M_CODE,
측정일은 MESURE_DE(YYYYMMDD) 컬럼을 사용합니다.
"""

import logging
from pathlib import Path
import itertools

import pandas as pd

from data.scripts.logging_setup import display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER, INTERMEDIATE_THREE_MEASURES, PASSED_FILENAME

logger = logging.getLogger(__name__)

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
MIN_MEASURES = 3
MIN_INTERVAL_DAYS = 30  # 최소 측정일 간격 설정 변수
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
    아니거나 조건에 맞는 3개의 측정 기록을 확보할 수 없는 회원은 제외합니다.
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
    work = work.sort_values(["_normalized_member_id", "_measure_date"], kind="stable")

    # 회원별로 3번 이상 측정 및 설정된 간격 이상을 만족하는 최적의 3행을 찾는 함수
    def select_valid_triplet(group_df: pd.DataFrame) -> pd.DataFrame:
        dates = group_df["_measure_date"].values
        n = len(dates)
        
        # 3번 미만 측정한 경우 모든 행 제거 (빈 DataFrame 반환)
        if n < 3:
            return pd.DataFrame(columns=group_df.columns)
        
        valid_triplets = []
        min_interval = pd.Timedelta(days=MIN_INTERVAL_DAYS)
        
        # 가능한 모든 3개의 조합(i, j, k) 탐색
        for i, j, k in itertools.combinations(range(n), 3):
            diff1 = dates[j] - dates[i]
            diff2 = dates[k] - dates[j]
            
            # 측정일 간격이 설정된 최소 일수 이상 벌어져 있는지 확인
            if diff1 >= min_interval and diff2 >= min_interval:
                total_span = diff1 + diff2      # 두 간격의 합 (전체 기간의 크기)
                abs_diff = abs(diff1 - diff2)   # 두 간격의 차이 (편차)
                
                # 정렬 기준: 
                # 1순위: total_span이 클수록 우선 (총 기간이 넓음)
                # 2순위: abs_diff가 작을수록 우선 (diff1과 diff2의 차이가 적음) -> -abs_diff 사용
                valid_triplets.append((total_span, -abs_diff, i, j, k))
                
        # 조건에 맞는 3행 조합이 없으면 모든 행 제거
        if not valid_triplets:
            return pd.DataFrame(columns=group_df.columns)
        
        # 총 간격이 가장 크고, 두 간격의 차이가 가장 적은 조합 채택
        valid_triplets.sort(reverse=True)
        _, _, best_i, best_j, best_k = valid_triplets[0]
        
        return group_df.iloc[[best_i, best_j, best_k]]

    # 그룹별 적용
    work = work.groupby("_normalized_member_id", sort=False).apply(select_valid_triplet)
    
    # apply로 인해 생긴 멀티 인덱스 정리
    if isinstance(work.index, pd.MultiIndex):
        work = work.reset_index(level=0, drop=True)
    work = work.reset_index(drop=True)

    if work.empty:
        return work

    # 최대/최소 측정일 차이가 3년 이내인 회원만 필터링
    groups = work.groupby("_normalized_member_id", sort=False)
    member_min_date = groups["_measure_date"].transform("min")
    member_max_date = groups["_measure_date"].transform("max")
    
    date_diff_3years = (member_max_date - member_min_date) <= pd.Timedelta(days=365 * 3)
    work = work[date_diff_3years]

    return work
def run(input_path: Path, output_path: Path) -> None:
    total = load_total(input_path)
    frequent = filter_frequent_members(total)
    result = pick_first_middle_last(frequent)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")

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
    setup_logging(Path(__file__).stem)
    run(INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME, INTERMEDIATE_THREE_MEASURES)


if __name__ == "__main__":
    main()