"""대시보드가 DB(PostgreSQL, Neon)를 읽는 공용 모듈입니다.

화면 코드는 이 모듈의 run_query()만 씁니다. 접속 방식이 바뀌어도 이 파일만 고치면 됩니다.
- 접속 정보: 환경 변수가 dashboard/.env(Git 제외)보다 우선합니다. Streamlit Community Cloud에서는 앱 설정의
  Secrets에 같은 이름(DB_HOST 등)으로 적으면 환경 변수로 들어오므로 .env 없이 같은 코드로 접속합니다.
- 연결: st.connection(type="sql")을 씁니다(SQLAlchemy + psycopg 3). 연결은 Streamlit이 캐시하고,
  조회 결과는 ttl 동안 캐시됩니다(st.cache_data와 같은 방식).
- 결과 모양: DB 컬럼 이름은 소문자이지만 기존 화면 코드가 대문자(MESURE_ID 등)를 쓰므로 대문자로 바꾸고,
  NUMERIC 값(Decimal)은 float로, *_ID 컬럼은 문자열로 바꿔 CSV를 읽던 때와 같게 돌려줍니다.

사용 예:
    from dashboard.db import run_query

    soldiers = run_query("SELECT * FROM soldiers")
    measures = run_query(
        "SELECT * FROM fitness_measurements WHERE soldier_id = :soldier_id",
        {"soldier_id": soldier_id},
    )

화면 입력값은 반드시 params로 넘깁니다. SQL 문자열에 f-string으로 넣으면 SQL 인젝션이 생길 수 있습니다.
params로 넘긴 값은 psycopg가 SQL 문장과 따로(서버 쪽 파라미터 바인딩) 보내므로 SQL로 해석되지 않습니다.
"""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import dotenv_values
from streamlit.connections import SQLConnection

# 배포 환경에서는 저장소 루트의 config.py를 import하지 않게 할 예정이라(CLAUDE.md 배포 계획) 이 파일 기준으로 찾는다.
ENV_PATH = Path(__file__).resolve().parent / ".env"

CONNECTION_NAME = "defense_db"
DEFAULT_TTL = 600  # 초. 데이터는 파이프라인을 다시 돌릴 때만 바뀌므로 10분 캐시로 충분하다.

REQUIRED_SETTINGS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
# 값이 있을 때만 접속 옵션으로 넘긴다(libpq의 sslmode, channel_binding).
OPTIONAL_SETTINGS = ("DB_SSLMODE", "DB_CHANNEL_BINDING")

ID_SUFFIX = "_ID"


def load_db_settings(env_path: Path = ENV_PATH) -> dict[str, str]:
    """DB 접속 정보를 읽습니다. 환경 변수(os.environ)가 .env 파일 값보다 우선합니다.

    Raises:
        ValueError: 필수 항목이 없거나 비어 있을 때(빠진 이름을 모두 알려 줌)
    """
    # load_dotenv()는 os.environ을 바꾸므로, 파일 값만 딕셔너리로 읽는 dotenv_values()를 쓴다.
    file_values = dotenv_values(env_path)
    settings = {
        key: os.environ.get(key) or file_values.get(key) or ""
        for key in (*REQUIRED_SETTINGS, *OPTIONAL_SETTINGS)
    }
    missing = [key for key in REQUIRED_SETTINGS if not settings[key]]
    if missing:
        raise ValueError(
            f"DB 접속 정보가 없습니다: {', '.join(missing)}. "
            "dashboard/.env(배포에서는 Streamlit Secrets)에 적으세요."
        )
    return settings


def get_connection() -> SQLConnection:
    """DB 연결을 돌려줍니다. 같은 이름·설정이면 Streamlit이 만든 연결을 다시 씁니다."""
    settings = load_db_settings(ENV_PATH)
    ssl_options = {
        "sslmode": settings["DB_SSLMODE"],
        "channel_binding": settings["DB_CHANNEL_BINDING"],
    }
    return st.connection(
        CONNECTION_NAME,
        type="sql",
        dialect="postgresql",
        driver="psycopg",
        host=settings["DB_HOST"],
        port=settings["DB_PORT"],
        database=settings["DB_NAME"],
        username=settings["DB_USER"],
        password=settings["DB_PASSWORD"],
        query={name: value for name, value in ssl_options.items() if value},
        # Neon 풀러 주소(-pooler)는 PgBouncer를 거친다. psycopg 3는 같은 쿼리를 여러 번 실행하면
        # 서버 쪽 prepared statement를 자동으로 쓰는데, PgBouncer 설정에 따라 "prepared statement does not exist"
        # 오류가 날 수 있어 자동 준비를 끈다. 대시보드 조회 규모에서는 속도 차이가 거의 없다.
        # 끄는 것은 "같은 문장을 서버에 저장해 재사용"하는 성능 최적화뿐이고, params 값을 SQL과 따로 보내는
        # 파라미터 바인딩(SQL 인젝션 방어)은 그대로 쓴다.
        connect_args={"prepare_threshold": None},
    )


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    """DB 조회 결과를 CSV로 읽던 때와 같은 모양으로 바꿉니다.

    - 컬럼 이름을 대문자로(PostgreSQL은 따옴표 없는 이름을 소문자로 저장한다)
    - NUMERIC 컬럼(psycopg가 Decimal로 돌려줌, pandas에서는 object)을 float로
    - *_ID 컬럼을 pandas 문자열(string)로(기존 화면 코드가 ID를 문자열로 다룬다)
    """
    df = df.rename(columns=str.upper)
    for column in df.columns:
        values = df[column].dropna()
        if df[column].dtype == object and not values.empty and values.map(lambda v: isinstance(v, Decimal)).all():
            df[column] = df[column].astype(float)
        if column.endswith(ID_SUFFIX):
            df[column] = df[column].astype("string")
    return df


def run_query(sql: str, params: dict[str, Any] | None = None, ttl: int | None = DEFAULT_TTL) -> pd.DataFrame:
    """읽기 전용 SQL을 실행해 DataFrame으로 돌려줍니다. 값은 SQL에 `:이름`으로 적고 params로 넘깁니다.

    같은 SQL·params면 ttl초 동안 캐시된 결과를 씁니다(None이면 계속 캐시).
    """
    result = get_connection().query(sql, params=params, ttl=ttl, show_spinner=False)
    return tidy(result)

