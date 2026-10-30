"""분류에 사용한 전체 측정 백분위로 개인과 같은 유형의 평균을 비교합니다."""

import pandas as pd
import streamlit as st

from dashboard.py.followup_fitness_types import load_fitness_types
from data.scripts.paths import (PROCESSED_FITNESS_PATH,
                                PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
                                PROCESSED_FITNESS_TYPE_PATH)

EVENT_COLUMNS = ['STRENGTH', 'ENDURANCE', 'CARDIO', 'FLEXIBILITY']


@st.cache_data(show_spinner=False)
def _load_profiles(stamps: tuple[int, ...]) -> pd.DataFrame:
    measurements = pd.read_csv(PROCESSED_FITNESS_PATH,
                               usecols=['MESURE_ID', 'SOLDIER_ID', *EVENT_COLUMNS])
    if measurements.MESURE_ID.duplicated().any():
        raise ValueError('체력 측정 식별자가 중복되었습니다.')
    for event in EVENT_COLUMNS:
        values = pd.to_numeric(measurements[event], errors='coerce')
        measurements[event] = values.rank(pct=True) * 100
    profiles, _ = load_fitness_types(measurements)
    return profiles


def load_personal_profile(measurement_id) -> tuple[pd.Series, pd.Series, int]:
    """군집 번호가 같아도 평균 백분위 등급이 다르면 비교 집단에서 제외합니다."""
    paths = [PROCESSED_FITNESS_PATH, PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
             PROCESSED_FITNESS_TYPE_PATH]
    profiles = _load_profiles(tuple(path.stat().st_mtime_ns for path in paths))
    selected = profiles.loc[profiles.MESURE_ID.eq(int(measurement_id))]
    if selected.empty:
        raise ValueError('선택 측정의 백분위 자료가 없습니다.')
    personal = selected.iloc[0]
    if pd.isna(personal.FITNESS_TYPE_KEY):
        raise ValueError('선택 측정의 클러스터 분류가 없습니다.')
    members = profiles.loc[profiles.FITNESS_TYPE_KEY.eq(personal.FITNESS_TYPE_KEY)]
    return personal[EVENT_COLUMNS], members[EVENT_COLUMNS].mean(), len(members)
