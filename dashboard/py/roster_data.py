"""관리 화면(7·8번)이 쓰는 장병 명단·부상 기록·최신 측정을 읽습니다.

명단·부상은 관리 기록(management_store, 모두 문자열)과 이어 붙이므로 값을 모두 문자열로 돌려줍니다.
"""

import pandas as pd

from dashboard.common.formatting import FITNESS_ITEM_LABELS
from dashboard.data_source import CSV, resolve_source
from dashboard.db import run_query

PERSONNEL_SQL = "SELECT * FROM soldiers ORDER BY soldier_id"
INJURIES_SQL = "SELECT * FROM injuries ORDER BY injury_id"
MEASUREMENT_COLUMNS = ['SOLDIER_ID', 'MESURE_ID', 'MESURE_DE', 'AGE', 'BMI', *FITNESS_ITEM_LABELS]
MEASUREMENTS_SQL = f"""
SELECT {', '.join(MEASUREMENT_COLUMNS).lower()}
FROM fitness_measurements
ORDER BY mesure_id
"""


def _as_text(frame: pd.DataFrame) -> pd.DataFrame:
    """CSV 모드의 read_text_csv와 같게 모든 값을 문자열(object)로 바꿉니다."""
    return frame.astype(str).astype(object)


def load_personnel_text(source: str | None = None) -> pd.DataFrame:
    """장병 명단을 모두 문자열로 읽습니다."""
    if resolve_source(source) != CSV:
        return _as_text(run_query(PERSONNEL_SQL))
    from data.scripts.paths import SYNTHETIC_PERSONNEL_PATH
    from data.scripts.utils import read_text_csv
    return read_text_csv(SYNTHETIC_PERSONNEL_PATH)


def load_injuries_text(source: str | None = None) -> pd.DataFrame:
    """부상 기록을 모두 문자열로 읽습니다."""
    if resolve_source(source) != CSV:
        return _as_text(run_query(INJURIES_SQL))
    from data.scripts.paths import SYNTHETIC_INJURY_PATH
    from data.scripts.utils import read_text_csv
    return read_text_csv(SYNTHETIC_INJURY_PATH)


def load_latest_measurements(source: str | None = None) -> pd.DataFrame:
    """장병별 가장 최근 측정 한 건(측정일, 같으면 MESURE_ID가 큰 것)을 돌려줍니다."""
    if resolve_source(source) != CSV:
        measurements = run_query(MEASUREMENTS_SQL)
        measurements['SOLDIER_ID'] = measurements.SOLDIER_ID.astype(str)
        measurements['MESURE_ID'] = measurements.MESURE_ID.astype('int64')
    else:
        from data.scripts.paths import PROCESSED_FITNESS_PATH
        measurements = pd.read_csv(PROCESSED_FITNESS_PATH, dtype={'SOLDIER_ID': str}, usecols=MEASUREMENT_COLUMNS)
    measurements = measurements[MEASUREMENT_COLUMNS]  # usecols는 파일 순서를 따르므로 두 모드의 순서를 맞춘다.
    measurements['MESURE_DE'] = pd.to_datetime(measurements.MESURE_DE.astype(str).str.removesuffix('.0'),
                                               format='%Y%m%d', errors='coerce')
    return measurements.sort_values(['MESURE_DE', 'MESURE_ID'], kind='stable', na_position='first').drop_duplicates(
        'SOLDIER_ID', keep='last')
