"""회원별 3행(첫·중간·마지막) 데이터에서 각 행의 측정일과 나이를 기반으로
만나이 및 월(Month) 흐름에 따른 생물학적 모순(나이 역전, 비상식적 변화)을
검증하여 이상치 데이터를 분리하고 정상 데이터를 최종 저장합니다.
"""

import sys
from pathlib import Path
import pandas as pd

from config import CSV_DATA_DIR

# ==================== [설정 및 매개변수 영역] ====================
INPUT_PATH = CSV_DATA_DIR / "KS_NFA_THREE_MEASURES.csv"      # 입력 파일 경로
OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_FINAL_OUTPUT.csv"       # 정상 데이터 출력 파일 경로
OUTLIER_PATH = CSV_DATA_DIR / "KS_NFA_OUTLIERS.csv"          # 이상치 데이터 출력 파일 경로

ID_COL = "M_CODE"           # 회원 식별자 컬럼
DATE_COL = "MESURE_DE"      # 측정일 컬럼 (YYYYMMDD)
AGE_COL = "AGE"             # 나이 컬럼 (데이터셋의 실제 나이 컬럼명)
# ==============================================================

_REQUIRED_COLUMNS = (ID_COL, DATE_COL, AGE_COL)


def _validate_required_columns(df: pd.DataFrame) -> None:
    missing = [column for column in _REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")


def is_invalid_age_year_pattern(group_df: pd.DataFrame) -> bool:
    """회원별 3개 측정 기록의 (연도, 월, 일, 만나이)가 
    생일 경과 여부 및 시간 흐름상 논리적으로 모순이 없는지 엄밀히 검증합니다.
    """
    # 시간순 정렬 보장
    sorted_df = group_df.sort_values(DATE_COL)
    
    dates = pd.to_datetime(sorted_df[DATE_COL].astype(str), format="%Y%m%d", errors="coerce")
    if dates.isna().any():
        return True
        
    years = dates.dt.year.values
    months = dates.dt.month.values
    days = dates.dt.day.values
    
    try:
        ages = sorted_df[AGE_COL].astype(int).values
    except ValueError:
        return True

    if len(ages) != 3:
        return True

    # 3개 측정점 간의 연쇄적 나이 및 날짜 흐름 검증
    for i in range(2):
        y1, m1, d1, a1 = years[i], months[i], days[i], ages[i]
        y2, m2, d2, a2 = years[i+1], months[i+1], days[i+1], ages[i+1]
        
        # 1. 시간이 흘렀는데 나이가 줄어들거나, 동일한 시점인데 나이가 다르면 이상치
        time_passed = (y2 > y1) or (y2 == y1 and m2 > m1) or (y2 == y1 and m2 == m1 and d2 > d1)
        time_equal = (y2 == y1 and m2 == m1 and d2 == d1)
        
        if time_passed and (a2 < a1):
            return True
        if time_equal and (a2 != a1):
            return True
            
        # 2. 연도 차이 대비 나이 변화량의 물리적 한계 검증 (만나이는 x년 지나면 최대 x+1살까지만 증가 가능)
        year_diff = y2 - y1
        age_diff = a2 - a1
        
        if age_diff < 0:
            return True
        if age_diff > year_diff + 1:
            return True
            
        # 3. 월(Month) 단위를 고려한 정밀 경계 검증 (생일 경과에 따른 허용 범위 체크)
        # y1년 m1월에 a1살이었다면, y2년 m2월 시점에서 기대되는 만나이의 하한과 상한 계산
        expected_min_age = a1 + max(0, y2 - y1 - 1)
        expected_max_age = a1 + (y2 - y1) + 1
        
        if not (expected_min_age <= a2 <= expected_max_age):
            return True

    return False


def filter_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """회원별 데이터를 순회하며 만나이/연도 흐름 이상치가 있는 회원을 분리합니다."""
    _validate_required_columns(df)
    
    if df.empty:
        return df.copy(), df.copy()

    work = df.copy()
    outlier_member_ids = []
    
    grouped = work.groupby(ID_COL, sort=False)
    for member_id, group in grouped:
        # 정확히 3행이 아닐 경우 이상치로 처리
        if len(group) != 3:
            outlier_member_ids.append(member_id)
            continue
            
        if is_invalid_age_year_pattern(group):
            outlier_member_ids.append(member_id)

    # 이상치 회원과 정상 회원 분리
    is_outlier = work[ID_COL].isin(outlier_member_ids)
    
    outlier_df = work[is_outlier].copy()
    normal_df = work[~is_outlier].copy()
    
    return normal_df, outlier_df


def main() -> None:
    if not INPUT_PATH.exists():
        sys.exit(f"{INPUT_PATH}이 없습니다. 이전 단계를 먼저 실행하세요.")

    print(f"데이터 로드 중: {INPUT_PATH.name}")
    df = pd.read_csv(INPUT_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    
    _validate_required_columns(df)

    print("만나이 및 측정 연월 정합성 이상치 검사 및 분리 중...")
    normal_df, outlier_df = filter_outliers(df)

    # 파일 저장
    normal_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    outlier_df.to_csv(OUTLIER_PATH, index=False, encoding="utf-8-sig")

    total_members = df[ID_COL].nunique()
    normal_members = normal_df[ID_COL].nunique()
    outlier_members = outlier_df[ID_COL].nunique()

    print("-" * 40)
    print(f"총 입력 데이터: {len(df):,}행 (회원 {total_members:,}명)")
    print(f"정상 데이터 저장 ({OUTPUT_PATH.name}): {len(normal_df):,}행 (회원 {normal_members:,}명)")
    print(f"이상치 데이터 저장 ({OUTLIER_PATH.name}): {len(outlier_df):,}행 (회원 {outlier_members:,}명)")
    print("-" * 40)


if __name__ == "__main__":
    main()