"""대시보드 로더가 CSV와 DB 중 어디서 읽을지 정합니다(전환 기간용).

로더는 모두 `source` 인자를 받고, 비워 두면 설정값을 따릅니다.
- 우선순위: 함수 인자 > 환경 변수 DASHBOARD_DATA_SOURCE > dashboard/.env > 기본값(db)
- DB 모드는 dashboard.db.run_query(SQL)만 쓰고, CSV 모드는 전환 전 코드를 그대로 씁니다.
두 모드의 결과가 같은지는 dashboard/compare_data_sources.py로 확인합니다.
검증이 끝나면 CSV 모드와 이 모듈을 지우고 SQL만 남깁니다.
"""

import os

from dotenv import dotenv_values

from dashboard.db import ENV_PATH

CSV = "csv"
DB = "db"
SOURCES = (CSV, DB)
SETTING_NAME = "DASHBOARD_DATA_SOURCE"
# 2026-10-30 두 모드 결과가 같음을 확인해 DB로 바꿈. CSV 모드는 배포 환경에서 DB 모드를 확인한 뒤 지운다.
DEFAULT_SOURCE = DB


def resolve_source(source: str | None = None) -> str:
    """읽을 곳(csv 또는 db)을 정합니다.

    Raises:
        ValueError: csv·db가 아닌 값일 때
    """
    if source is None:
        source = os.environ.get(SETTING_NAME) or dotenv_values(ENV_PATH).get(SETTING_NAME) or DEFAULT_SOURCE
    source = source.strip().lower()
    if source not in SOURCES:
        raise ValueError(f"{SETTING_NAME}은(는) {' 또는 '.join(SOURCES)}이어야 합니다: {source!r}")
    return source
