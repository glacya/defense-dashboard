"""passed.csv에서 (1,2등급 제외 / 개인별 첫 행 / 처방 있는 데이터)를 선별한다."""
import sys
import pandas as pd
import logging
from pathlib import Path

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    INTERMEDIATE_ENLISTMENT_FILTER,
    PASSED_FILENAME,
)
from data.scripts.preprocessing.merge_raw_measurements import load_definition_columns
from data.scripts.fitness_standards import grade_cut_table

logger = logging.getLogger(__name__)
DATA_DIR = INTERMEDIATE_ENLISTMENT_FILTER
DATA_NAME = PASSED_FILENAME
DATA_PATH = DATA_DIR / DATA_NAME
OUT_PATH = "selected.csv"

ID_COL = "M_CODE"  # 개인 식별번호
PRESCRIPTION_COL = "MVM_PRSCRPTN_CN"  # 운동처방 내용

# 등급 정의의 영문속성명 -> 실제 측정 컬럼
MEASURE_COL = {
    "STRENGTH": "REL_GRIP",     # 근력 (상대악력, %)
    "ENDURANCE": "CROSS_UP",    # 근지구력 (회)
    "CARDIO": "CARDIO",         # 심폐지구력
    "FLEXIBILITY": "SIT_REACH", # 유연성
}

# "any": 4개 항목 중 하나라도 1,2등급이면 제외
# "all": 4개 항목 모두 1,2등급일 때만 제외
EXCLUDE_MODE = "any"


def load_data(data_path=DATA_PATH):
    # utf-8-sig: 헤더 앞의 BOM(﻿M_CODE) 제거
    df = pd.read_csv(data_path, encoding="utf-8-sig")
    # 등급 하한은 data/scripts/fitness_standards.py에서 가져온다(1·2등급 제외에 2등급 하한이 필요).
    grade = grade_cut_table(grades=(3, 2))
    return df, grade


def top2_mask(df, grade, mode=EXCLUDE_MODE):
    """1,2등급(값 >= 2등급컷)인 행의 boolean mask."""
    flags = []
    for _, row in grade.iterrows():
        col = MEASURE_COL[row["영문속성명"]]
        flags.append(df[col] >= row["2등급컷"])  # NaN은 False
    flags = pd.concat(flags, axis=1)
    return flags.any(axis=1) if mode == "any" else flags.all(axis=1)


def select(df, grade, mode=EXCLUDE_MODE):
    # 1) 개인별 데이터: 같은 M_CODE는 파일상 가장 첫 행만 사용
    df = df.drop_duplicates(subset=ID_COL, keep="first")

    # 2) 1,2등급 인원 제외
    df = df[~top2_mask(df, grade, mode)]

    # 3) 처방이 있는 데이터 (NaN / 빈 문자열 / 공백 제외)
    has_rx = df[PRESCRIPTION_COL].fillna("").astype(str).str.strip() != ""
    return df[has_rx].reset_index(drop=True)


if __name__ == "__main__":
    data_path = sys.argv[1] if len(sys.argv) > 1 else DATA_PATH
    out_path = sys.argv[2] if len(sys.argv) > 2 else OUT_PATH

    raw, grade = load_data(data_path)
    result = select(raw, grade)

    print(f"원본 행 수          : {len(raw):,}")
    print(f"개인별(중복 제거) 후: {raw[ID_COL].nunique():,}")
    print(f"최종 선별 행 수     : {len(result):,}")
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장: {DATA_PATH,out_path}")