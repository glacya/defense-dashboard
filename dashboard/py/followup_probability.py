"""장병별 다음 회차 미달 확률을 읽어 네 위험 등급을 계산합니다."""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

from dashboard.db import DEFAULT_TTL
from dashboard.py import queries

RISK_LEVELS = ['안전', '경계1등급', '경계2등급', '경계3등급']
RISK_RANGES = ['30% 미만', '30% 이상 · 50% 미만', '50% 이상 · 70% 미만', '70% 이상']
FOLLOWUP_THRESHOLD = .3  # 이 확률 이상(경계1~3등급)이 후속조치 대상


def classify_probabilities(frame: pd.DataFrame) -> pd.DataFrame:
    """장병별 미달 확률에 위험 등급과 후속조치 대상 여부를 붙입니다.

    장병번호(PK)·확률(NOT NULL)은 DB가 보장하므로 다시 검사하지 않습니다.
    """
    result = frame[['SOLDIER_ID', 'FAILURE_PROBABILITY']].copy()
    values = result.FAILURE_PROBABILITY
    result['RISK_LEVEL'] = pd.cut(values, [-float('inf'), .3, .5, .7, float('inf')],
                                 labels=RISK_LEVELS, right=False).astype(str)
    result['FOLLOWUP_TARGET'] = values.ge(FOLLOWUP_THRESHOLD)
    return result


def type_key(grade, cluster) -> str:
    """체력유형 키(평균 백분위 등급-군집, 예: '1-0')."""
    return f'{int(grade)}-{int(cluster)}'


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def load_followup_population() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """(확률이 있는 장병별 신상·위험 등급·최신 측정·체력유형, 유형 16개 표, 확률이 없는 장병 수)를 돌려줍니다."""
    rows, catalog = _load_followup_sources()
    missing = int(rows.FAILURE_PROBABILITY.isna().sum())
    rows = rows.loc[rows.FAILURE_PROBABILITY.notna()].copy()
    levels = classify_probabilities(rows[['SOLDIER_ID', 'FAILURE_PROBABILITY']])
    rows['RISK_LEVEL'] = levels.RISK_LEVEL.to_numpy()
    rows['FOLLOWUP_TARGET'] = levels.FOLLOWUP_TARGET.to_numpy()
    rows['SOLDIER_ID'] = rows.SOLDIER_ID.astype(str)
    rows['MESURE_ID'] = pd.to_numeric(rows.MESURE_ID).astype('Int64')
    rows['MESURE_DE'] = pd.to_datetime(rows.MESURE_DE, format='%Y%m%d', errors='coerce')
    typed = rows.AVERAGE_PERCENTILE_GRADE.notna()
    rows['FITNESS_TYPE_KEY'] = None
    rows.loc[typed, 'FITNESS_TYPE_KEY'] = [type_key(g, c) for g, c in zip(rows.AVERAGE_PERCENTILE_GRADE[typed], rows.CLUSTER[typed])]
    catalog['FITNESS_TYPE_KEY'] = [type_key(g, c) for g, c in zip(catalog.AVERAGE_PERCENTILE_GRADE, catalog.CLUSTER)]
    return rows.reset_index(drop=True), catalog, missing


def _load_followup_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="followup-population") as executor:
        rows_future = executor.submit(queries.load_followup_population)
        catalog_future = executor.submit(queries.load_fitness_types)
        rows = rows_future.result()
        catalog = catalog_future.result()
    return rows, catalog
