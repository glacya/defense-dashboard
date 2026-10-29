"""메인·부대 현황 페이지가 쓰는 명단·측정·부상 로더입니다. 파일 수정 시각을 키로 캐시합니다."""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.common.formatting import classify_bmi
from config import PROCESSED_DIR, SYNTHETIC_DIR
from data.scripts.fitness_standards import GRADE_CUTS

PERSONNEL_PATH = SYNTHETIC_DIR / "SOLDIER_PERSONNEL.csv"
FITNESS_PATH = PROCESSED_DIR / "KS_NFA_PROCESSED.csv"
INJURY_PATH = SYNTHETIC_DIR / "SOLDIER_INJURY.csv"

PERSONNEL_COLUMNS = {"SOLDIER_ID", "SOLDIER_NAME", "REGION_NAME", "UNIT_NAME", "RANK_NAME"}
FITNESS_COLUMNS = {
    "MESURE_ID", "SOLDIER_ID", "AGE", "HEIGHT", "WEIGHT", "BMI", "BODY_FAT_PERCENTAGE",
    "MESURE_DE", "STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY",
}
INJURY_COLUMNS = {"INJURY_ID", "SOLDIER_ID", "INJURY_CATEGORY", "INJURY_LOCATION", "PREVENTABILITY", "SEVERITY"}
FITNESS_ITEM_COLUMNS = ("STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY")


def add_fitness_deficiency_flags(data: pd.DataFrame) -> pd.DataFrame:
    """4개 체력 종목 중 2개 이상이 3등급 기준 미만인지 판정합니다."""
    result = data.copy()
    deficiency_columns = []
    for column in FITNESS_ITEM_COLUMNS:
        flag_column = f"미달_{column}"
        result[flag_column] = pd.to_numeric(result[column], errors="coerce").lt(
            GRADE_CUTS[column][3]
        )
        deficiency_columns.append(flag_column)
    result["체력미달"] = result[deficiency_columns].sum(axis=1).ge(2)
    return result


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

    measure_ids = pd.to_numeric(fitness["MESURE_ID"], errors="coerce")
    if measure_ids.isna().any() or measure_ids.duplicated().any():
        raise ValueError("측정 데이터의 MESURE_ID는 유효하고 고유해야 합니다.")
    fitness["MESURE_ID"] = measure_ids.astype("int64")

    fitness["MESURE_DE"] = pd.to_datetime(fitness["MESURE_DE"].astype("string"), format="%Y%m%d", errors="coerce")
    if fitness["MESURE_DE"].isna().any():
        raise ValueError("측정 데이터에 형식이 잘못된 측정일(MESURE_DE)이 있습니다.")

    numeric_columns = [
        "AGE", "HEIGHT", "WEIGHT", "BMI", "BODY_FAT_PERCENTAGE",
        *FITNESS_ITEM_COLUMNS,
    ]
    for column in numeric_columns:
        fitness[column] = pd.to_numeric(fitness[column], errors="coerce")
    invalid = fitness[numeric_columns].isna().any(axis=1)
    if invalid.any():
        raise ValueError(f"측정 데이터 {int(invalid.sum()):,}행에 유효하지 않은 나이 또는 신체 측정값이 있습니다.")
    if (fitness["BMI"] <= 0).any():
        raise ValueError("BMI는 0보다 커야 합니다.")

    missing_ids = set(fitness["SOLDIER_ID"]) - set(personnel["SOLDIER_ID"])
    if missing_ids:
        raise ValueError(f"측정 데이터에 명단과 연결되지 않는 군번이 {len(missing_ids):,}개 있습니다.")

    merged = fitness.merge(personnel, on="SOLDIER_ID", how="left", validate="many_to_one")
    merged["BMI구간"] = classify_bmi(merged["BMI"])
    merged = add_fitness_deficiency_flags(merged)
    return merged.sort_values(["MESURE_DE", "MESURE_ID"], kind="stable").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def _load_injuries(injury_path: str, version: tuple[int, int]) -> pd.DataFrame:
    injury = pd.read_csv(injury_path, encoding="utf-8-sig", dtype={"SOLDIER_ID": "string"})
    missing = sorted(INJURY_COLUMNS - set(injury.columns))
    if missing:
        raise ValueError(f"부상 기록에 필수 컬럼이 없습니다: {', '.join(missing)}")
    if injury["INJURY_ID"].duplicated().any() or injury["SOLDIER_ID"].isna().any():
        raise ValueError("부상 기록의 부상 ID는 고유하고 군번은 비어 있지 않아야 합니다.")
    return injury


def load_main_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """측정 데이터와 부상 데이터를 반환합니다. 파일이 없으면 FileNotFoundError를 올립니다."""
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
