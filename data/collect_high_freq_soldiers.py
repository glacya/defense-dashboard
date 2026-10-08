"""KS_NFA_TOTAL.csv에서 3번 이상 측정한 회원만 골라, 회원마다 첫·중간·마지막 측정 3건을 KS_NFA_THREE_MEASURES.csv로 저장합니다.

같은 사람의 체력 변화를 시간 순서로 비교하기 위한 데이터를 만드는 전처리 스크립트입니다.
입력 파일은 data_merger.py가 만듭니다. 먼저 data_merger.py를 실행하세요.

결측치와 이상치를 제거하지 않은 데이터를 이용해 3개를 고르는 것입니다.
만약 결측치, 이상치를 제거한 데이터를 사용해야 한다면 대상 파일 경로와 파이프라인 스크립트를 바꾸기 바랍니다.
"""

import sys
from pathlib import Path

import pandas as pd

# (경로 상수와 sys.path 설정은 원본 그대로 유지)

INPUT_PATH = CSV_DATA_DIR / "KS_NFA_TOTAL.csv"
OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_THREE_MEASURES.csv"

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
MIN_MEASURES = 3


def load_total(path: Path) -> pd.DataFrame:
    """data_merger.py의 결과 파일을 모든 값을 문자열로 읽어 반환합니다.

    숫자로 바꾸지 않고 읽어야 저장할 때 원본 값(소수점 자릿수, 빈 칸 등)이 그대로 유지됩니다.
    """
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def filter_frequent_members(df: pd.DataFrame, min_count: int = MIN_MEASURES) -> pd.DataFrame:
    """회원식별번호가 min_count번 이상 등장하는 회원의 행만 남깁니다.

    같은 날 여러 번 측정한 기록도 각각 한 번으로 셉니다.
    """
    counts = df.groupby(ID_COL)[ID_COL].transform("size")
    return df[counts >= min_count]


def pick_first_middle_last(df: pd.DataFrame) -> pd.DataFrame:
    """회원마다 측정일 오름차순으로 정렬한 rows에서 rows[0], rows[N // 2], rows[N - 1]만 남깁니다.

    N >= 3이어야 세 위치가 서로 겹치지 않으므로, filter_frequent_members를 거친 데이터를 넣어야 합니다.
    """
    # 같은 회원이 같은 날 여러 번 측정한 행이 있어, 실행할 때마다 같은 행이 뽑히도록 안정 정렬로 원본 순서를 유지한다.
    rows = df.sort_values(DATE_COL, kind="stable")
    groups = rows.groupby(ID_COL, sort=False)
    pos = groups.cumcount()
    n = groups[ID_COL].transform("size")
    picked = rows[(pos == 0) | (pos == n // 2) | (pos == n - 1)]
    return picked.sort_values(ID_COL, kind="stable")


def main() -> None:
    # (main 앞부분 원본 유지)
    total = load_total(INPUT_PATH)
    frequent = filter_frequent_members(total)
    result = pick_first_middle_last(frequent)
    # Excel에서 한글이 깨지지 않도록 BOM을 붙여 저장
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"{INPUT_PATH.name}: {len(total):,}행, 회원 {total[ID_COL].nunique():,}명")
    print(f"{MIN_MEASURES}회 이상 측정: {len(frequent):,}행, 회원 {frequent[ID_COL].nunique():,}명")
    print(f"{OUTPUT_PATH.name}: {len(result):,}행")
