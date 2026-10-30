"""메인·부대 현황 페이지가 쓰는 명단·측정·부상 로더입니다.

CSV 모드는 파일 수정 시각을 키로, DB 모드는 조회 결과를 ttl 동안 캐시합니다(dashboard.data_source).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.common.formatting import classify_bmi
from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL, run_query
from config import PROCESSED_DIR, SYNTHETIC_DIR

PERSONNEL_PATH = SYNTHETIC_DIR / "SOLDIER_PERSONNEL.csv"
FITNESS_PATH = PROCESSED_DIR / "KS_NFA_PROCESSED.csv"
INJURY_PATH = SYNTHETIC_DIR / "SOLDIER_INJURY.csv"

PERSONNEL_COLUMNS = {"SOLDIER_ID", "SOLDIER_NAME", "REGION_NAME", "UNIT_NAME", "RANK_NAME"}
FITNESS_COLUMNS = {
    "MESURE_ID", "SOLDIER_ID", "AGE", "HEIGHT", "WEIGHT", "BMI", "BODY_FAT_PERCENTAGE",
    "MESURE_DE", "STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY",
}
INJURY_COLUMNS = {"INJURY_ID", "SOLDIER_ID", "INJURY_CATEGORY", "INJURY_LOCATION", "PREVENTABILITY", "SEVERITY"}

# 측정 컬럼 전체 뒤에 명단 컬럼(군번 제외)을 붙인다. CSV 모드의 merge 결과와 컬럼 순서가 같다.
MEASUREMENTS_SQL = """
SELECT m.*, s.soldier_name, s.region_name, s.unit_name, s.rank_name, s.front_rear_classification
FROM fitness_measurements m
JOIN soldiers s USING (soldier_id)
ORDER BY m.mesure_id
"""
INJURIES_SQL = "SELECT * FROM injuries ORDER BY injury_id"


def _prepare_measurements(merged: pd.DataFrame) -> pd.DataFrame:
    """측정·명단을 이은 표의 값을 검사하고 화면에서 쓰는 형태로 바꿉니다(두 모드 공통)."""
    measure_ids = pd.to_numeric(merged["MESURE_ID"], errors="coerce")
    if measure_ids.isna().any() or measure_ids.duplicated().any():
        raise ValueError("측정 데이터의 MESURE_ID는 유효하고 고유해야 합니다.")
    merged["MESURE_ID"] = measure_ids.astype("int64")

    merged["MESURE_DE"] = pd.to_datetime(merged["MESURE_DE"].astype("string"), format="%Y%m%d", errors="coerce")
    if merged["MESURE_DE"].isna().any():
        raise ValueError("측정 데이터에 형식이 잘못된 측정일(MESURE_DE)이 있습니다.")

    numeric_columns = ["AGE", "HEIGHT", "WEIGHT", "BMI", "BODY_FAT_PERCENTAGE"]
    for column in numeric_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    invalid = merged[numeric_columns].isna().any(axis=1)
    if invalid.any():
        raise ValueError(f"측정 데이터 {int(invalid.sum()):,}행에 유효하지 않은 나이 또는 신체 측정값이 있습니다.")
    if (merged["BMI"] <= 0).any():
        raise ValueError("BMI는 0보다 커야 합니다.")

    merged["BMI구간"] = classify_bmi(merged["BMI"])
    return merged.sort_values(["MESURE_DE", "MESURE_ID"], kind="stable").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def _load_measurements(
    personnel_path: str,
    fitness_path: str,
    personnel_version: tuple[int, int],
    fitness_version: tuple[int, int],
) -> pd.DataFrame:
    personnel = pd.read_csv(personnel_path, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"})
    fitness = pd.read_csv(fitness_path, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"})

    missing_personnel = sorted(PERSONNEL_COLUMNS - set(personnel.columns))
    missing_fitness = sorted(FITNESS_COLUMNS - set(fitness.columns))
    if missing_personnel or missing_fitness:
        parts = []
        if missing_personnel:
            parts.append(f"장병 명단: {', '.join(missing_personnel)}")
        if missing_fitness:
            parts.append(f"측정 데이터: {', '.join(missing_fitness)}")
        raise ValueError(f"필수 컬럼이 없습니다 ({'; '.join(parts)}).")
    if personnel.empty or fitness.empty:
        raise ValueError("장병 명단 또는 측정 데이터가 비어 있습니다.")
    if personnel["SOLDIER_ID"].isna().any() or personnel["SOLDIER_ID"].duplicated().any():
        raise ValueError("장병 명단의 군번은 비어 있지 않고 고유해야 합니다.")
    if fitness["SOLDIER_ID"].isna().any():
        raise ValueError("측정 데이터에 군번이 비어 있는 행이 있습니다.")

    missing_ids = set(fitness["SOLDIER_ID"]) - set(personnel["SOLDIER_ID"])
    if missing_ids:
        raise ValueError(f"측정 데이터에 명단과 연결되지 않는 군번이 {len(missing_ids):,}개 있습니다.")

    merged = fitness.merge(personnel, on="SOLDIER_ID", how="left", validate="many_to_one")
    return _prepare_measurements(merged)


@st.cache_data(show_spinner=False)
def _load_injuries(injury_path: str, version: tuple[int, int]) -> pd.DataFrame:
    injury = pd.read_csv(injury_path, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"})
    missing = sorted(INJURY_COLUMNS - set(injury.columns))
    if missing:
        raise ValueError(f"부상 기록에 필수 컬럼이 없습니다: {', '.join(missing)}")
    if injury["INJURY_ID"].duplicated().any() or injury["SOLDIER_ID"].isna().any():
        raise ValueError("부상 기록의 부상 ID는 고유하고 군번은 비어 있지 않아야 합니다.")
    return injury


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_main_data_db() -> tuple[pd.DataFrame, pd.DataFrame]:
    # 군번 고유·연결, 필수 값은 DB의 PK·FK·NOT NULL이 보장한다.
    measurements = run_query(MEASUREMENTS_SQL)
    if measurements.empty:
        raise ValueError("장병 명단 또는 측정 데이터가 비어 있습니다.")
    injuries = run_query(INJURIES_SQL)
    injuries["INJURY_ID"] = injuries["INJURY_ID"].astype("int64")  # CSV 모드처럼 정수
    return _prepare_measurements(measurements), injuries


def load_main_data(source: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """측정 데이터와 부상 데이터를 반환합니다. CSV 모드에서 파일이 없으면 FileNotFoundError를 올립니다."""
    if resolve_source(source) != CSV:
        return _load_main_data_db()
    personnel_stat = PERSONNEL_PATH.stat()
    fitness_stat = FITNESS_PATH.stat()
    injury_stat = INJURY_PATH.stat()
    measurements = _load_measurements(
        str(PERSONNEL_PATH),
        str(FITNESS_PATH),
        (personnel_stat.st_mtime_ns, personnel_stat.st_size),
        (fitness_stat.st_mtime_ns, fitness_stat.st_size),
    )
    injuries = _load_injuries(str(INJURY_PATH), (injury_stat.st_mtime_ns, injury_stat.st_size))
    return measurements, injuries
