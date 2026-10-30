"""측정별 분류와 16개 유형명을 연결합니다. 결과 파일을 생성하지 않습니다."""

import pandas as pd

from dashboard.data_source import CSV, resolve_source
from dashboard.db import run_query
from data.scripts.utils import require_columns

TYPE_COLUMNS = ['AVERAGE_PERCENTILE_GRADE', 'CLUSTER']
CLASSIFICATIONS_SQL = """
SELECT mesure_id, average_percentile_grade, cluster
FROM measurement_classifications
ORDER BY mesure_id
"""
TYPES_SQL = """
SELECT average_percentile_grade, cluster, type_name
FROM fitness_types
ORDER BY average_percentile_grade, cluster
"""


def attach_fitness_types(people: pd.DataFrame, classifications: pd.DataFrame,
                         types: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """장병별 최신 MESURE_ID에만 분류를 연결하고 4등급×4군집을 구별합니다."""
    require_columns(people, ['SOLDIER_ID', 'MESURE_ID'])
    require_columns(classifications, ['MESURE_ID', *TYPE_COLUMNS])
    require_columns(types, [*TYPE_COLUMNS, 'TYPE_NAME'])
    classifications = classifications[['MESURE_ID', *TYPE_COLUMNS]].copy()
    types = types[[*TYPE_COLUMNS, 'TYPE_NAME']].copy()
    for frame in [classifications, types]:
        for field in TYPE_COLUMNS:
            frame[field] = pd.to_numeric(frame[field], errors='raise')
    expected = {(grade, cluster) for grade in range(1, 5) for cluster in range(4)}
    if types.duplicated(TYPE_COLUMNS).any() or set(map(tuple, types[TYPE_COLUMNS].to_numpy())) != expected:
        raise ValueError('운동유형은 백분위 1~4등급 × 군집 0~3의 16개 조합이어야 합니다.')
    types['FITNESS_TYPE_KEY'] = types.apply(lambda row: f'{int(row.AVERAGE_PERCENTILE_GRADE)}-{int(row.CLUSTER)}', axis=1)
    if types.TYPE_NAME.isna().any() or types.TYPE_NAME.astype(str).str.strip().eq('').any():
        raise ValueError('운동유형명이 누락되었습니다.')
    result = people.copy()
    for frame in [classifications, result]:
        frame['MESURE_ID'] = pd.to_numeric(frame.MESURE_ID, errors='raise').astype('Int64')
    if classifications.MESURE_ID.isna().any() or classifications.MESURE_ID.duplicated().any():
        raise ValueError('측정 분류 식별자가 누락되었거나 중복되었습니다.')
    linked = classifications.merge(types, on=TYPE_COLUMNS, how='left', validate='many_to_one')
    if linked.FITNESS_TYPE_KEY.isna().any():
        raise ValueError('16개 조합에 포함되지 않는 측정 분류가 있습니다.')
    result = result.merge(linked, on='MESURE_ID', how='left', validate='many_to_one')
    return result, types.sort_values(TYPE_COLUMNS)


def read_fitness_type_tables(source: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """측정별 분류와 16개 유형명 표를 읽습니다."""
    if resolve_source(source) != CSV:
        return run_query(CLASSIFICATIONS_SQL), run_query(TYPES_SQL)
    from data.scripts.paths import PROCESSED_MEASUREMENT_CLASSIFICATION_PATH, PROCESSED_FITNESS_TYPE_PATH
    return pd.read_csv(PROCESSED_MEASUREMENT_CLASSIFICATION_PATH), pd.read_csv(PROCESSED_FITNESS_TYPE_PATH)


def load_fitness_types(people: pd.DataFrame, source: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """두 표를 읽어 메모리에서 연결합니다."""
    return attach_fitness_types(people, *read_fitness_type_tables(source))
