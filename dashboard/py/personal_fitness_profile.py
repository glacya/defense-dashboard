"""분류에 사용한 전체 측정 백분위로 개인과 같은 유형의 평균을 비교합니다."""

import pandas as pd
import streamlit as st

from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL, run_query
from dashboard.py.followup_fitness_types import load_fitness_types

EVENT_COLUMNS = ['STRENGTH', 'ENDURANCE', 'CARDIO', 'FLEXIBILITY']
# 종목별 백분위(전체 측정 안, 소수 둘째 자리)는 분석 단계가 measurement_classifications에 저장해 둔다.
PERCENTILES_SQL = f"""
SELECT c.mesure_id, m.soldier_id,
    {', '.join(f'c.{event.lower()}_percentile AS {event.lower()}' for event in EVENT_COLUMNS)}
FROM measurement_classifications c
JOIN fitness_measurements m USING (mesure_id)
ORDER BY c.mesure_id
"""


@st.cache_data(show_spinner=False)
def _load_profiles(stamps: tuple[int, ...]) -> pd.DataFrame:
    from data.scripts.paths import PROCESSED_FITNESS_PATH
    measurements = pd.read_csv(PROCESSED_FITNESS_PATH,
                               usecols=['MESURE_ID', 'SOLDIER_ID', *EVENT_COLUMNS])
    if measurements.MESURE_ID.duplicated().any():
        raise ValueError('체력 측정 식별자가 중복되었습니다.')
    for event in EVENT_COLUMNS:
        measurements[event] = pd.to_numeric(measurements[event], errors='coerce').rank(pct=True) * 100
    profiles, _ = load_fitness_types(measurements, CSV)
    return profiles


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_profiles_db(source: str) -> pd.DataFrame:
    profiles, _ = load_fitness_types(run_query(PERCENTILES_SQL), source)
    return profiles


def load_profiles(source: str | None = None) -> pd.DataFrame:
    """전체 측정의 종목별 백분위와 체력유형을 돌려줍니다."""
    source = resolve_source(source)
    if source != CSV:
        return _load_profiles_db(source)
    from data.scripts.paths import (PROCESSED_FITNESS_PATH,
                                    PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
                                    PROCESSED_FITNESS_TYPE_PATH)
    paths = [PROCESSED_FITNESS_PATH, PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
             PROCESSED_FITNESS_TYPE_PATH]
    return _load_profiles(tuple(path.stat().st_mtime_ns for path in paths))


def load_personal_profile(measurement_id, source: str | None = None) -> tuple[pd.Series, pd.Series, int]:
    """군집 번호가 같아도 평균 백분위 등급이 다르면 비교 집단에서 제외합니다."""
    profiles = load_profiles(source)
    selected = profiles.loc[profiles.MESURE_ID.eq(int(measurement_id))]
    if selected.empty:
        raise ValueError('선택 측정의 백분위 자료가 없습니다.')
    personal = selected.iloc[0]
    if pd.isna(personal.FITNESS_TYPE_KEY):
        raise ValueError('선택 측정의 클러스터 분류가 없습니다.')
    members = profiles.loc[profiles.FITNESS_TYPE_KEY.eq(personal.FITNESS_TYPE_KEY)]
    return personal[EVENT_COLUMNS], members[EVENT_COLUMNS].mean(), len(members)
