"""기존 미달 확률 파일을 읽어 네 등급을 계산합니다. 결과 CSV는 만들지 않습니다."""

import pandas as pd

from dashboard.data_source import CSV, resolve_source
from dashboard.db import run_query
from data.scripts.utils import require_columns

RISK_LEVELS = ['안전', '경계1등급', '경계2등급', '경계3등급']
RISK_RANGES = ['30% 미만', '30% 이상 · 50% 미만', '50% 이상 · 70% 미만', '70% 이상']
FOLLOWUP_THRESHOLD = .3  # 이 확률 이상(경계1~3등급)이 후속조치 대상
PROBABILITIES_SQL = """
SELECT soldier_id, failure_probability
FROM soldier_failure_probabilities
ORDER BY soldier_id
"""


def classify_probabilities(frame: pd.DataFrame) -> pd.DataFrame:
    """확률과 장병번호를 검증한 후 중복 없이 등급을 계산합니다."""
    require_columns(frame, ['SOLDIER_ID', 'FAILURE_PROBABILITY'])
    result = frame[['SOLDIER_ID', 'FAILURE_PROBABILITY']].copy()
    if result.SOLDIER_ID.isna().any() or result.SOLDIER_ID.astype(str).str.strip().eq('').any():
        raise ValueError('확률 자료에 장병번호가 없습니다.')
    if result.SOLDIER_ID.duplicated().any():
        raise ValueError('확률 자료의 장병번호가 중복됩니다.')
    values = pd.to_numeric(result.FAILURE_PROBABILITY, errors='coerce')
    if values.isna().any() or not values.between(0, 1).all():
        raise ValueError('미달 확률은 결측 없이 0~1 사이의 숫자여야 합니다.')
    result['FAILURE_PROBABILITY'] = values
    result['RISK_LEVEL'] = pd.cut(values, [-float('inf'), .3, .5, .7, float('inf')],
                                 labels=RISK_LEVELS, right=False).astype(str)
    result['FOLLOWUP_TARGET'] = values.ge(FOLLOWUP_THRESHOLD)
    return result


def load_probabilities(source: str | None = None) -> pd.DataFrame:
    """미달 확률을 읽기만 하며 등급은 메모리에서 계산합니다."""
    if resolve_source(source) != CSV:
        return classify_probabilities(run_query(PROBABILITIES_SQL))
    from data.scripts.paths import PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH
    from data.scripts.utils import read_text_csv
    return classify_probabilities(read_text_csv(PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH))


def type_key(grade, cluster) -> str:
    """체력유형 키(평균 백분위 등급-군집, 예: '1-0')."""
    return f'{int(grade)}-{int(cluster)}'


def load_followup_population() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """(확률이 있는 장병별 신상·위험 등급·최신 측정·체력유형, 유형 16개 표, 확률이 없는 장병 수)를 돌려줍니다."""
    from dashboard.py import queries

    rows = queries.load_followup_population()
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
    catalog = queries.load_fitness_types()
    catalog['FITNESS_TYPE_KEY'] = [type_key(g, c) for g, c in zip(catalog.AVERAGE_PERCENTILE_GRADE, catalog.CLUSTER)]
    return rows.reset_index(drop=True), catalog, missing
