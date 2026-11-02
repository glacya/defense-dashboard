"""대시보드 DB 공용 모듈(dashboard/db.py)을 테스트합니다. 실제 DB에는 접속하지 않습니다."""

from decimal import Decimal

import pandas as pd
import pytest

from dashboard import db

ENV_TEXT = """DB_HOST=example.host
DB_PORT=5432
DB_NAME=dashboard
DB_USER=reader
DB_PASSWORD=secret
DB_SSLMODE=require
"""


class FakeDBAPIConnection:
    """with 블록으로 열리고 닫혔는지 기록하는 가짜 연결."""

    def __init__(self):
        self.open = False

    def __enter__(self):
        self.open = True
        return self

    def __exit__(self, *exc_info):
        self.open = False
        return False


class FakeConnection:
    """connect()로 가짜 연결을 내주고, 열린 횟수와 열린 채 남은 연결을 기록하는 가짜 st.connection."""

    def __init__(self):
        self.opened = []

    def connect(self):
        connection = FakeDBAPIConnection()
        self.opened.append(connection)
        return connection


@pytest.fixture
def env_path(tmp_path, monkeypatch):
    """접속 정보 파일을 만들고, 실행 환경의 DB_* 환경 변수가 끼어들지 않게 지웁니다."""
    for key in (*db.REQUIRED_SETTINGS, *db.OPTIONAL_SETTINGS):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(ENV_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def fake_connection(monkeypatch):
    """get_connection()이 가짜 연결을, pandas.read_sql이 정해 둔 결과를 돌려주게 하고 읽은 SQL·params를 기록합니다."""
    connection = FakeConnection()
    connection.reads = []

    def fake_read_sql(sql, con, params=None):
        assert con.open, "연결이 with 블록 안에서 쓰여야 합니다."
        connection.reads.append((str(sql), params))
        return pd.DataFrame({"soldier_id": ["22-1"], "bmi": [Decimal("21.50")]})

    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db.pd, "read_sql", fake_read_sql)
    return connection


def test_environment_variable_overrides_env_file(env_path, monkeypatch):
    """환경 변수(배포의 Streamlit Secrets)가 .env 파일 값보다 우선하는지 확인합니다."""
    monkeypatch.setenv("DB_HOST", "from-secrets")

    settings = db.load_db_settings(env_path)

    assert settings["DB_HOST"] == "from-secrets"
    assert settings["DB_USER"] == "reader"


def test_missing_settings_are_all_reported(tmp_path, monkeypatch):
    """필수 항목이 빠지면 빠진 이름을 모두 알려 주는지 확인합니다."""
    for key in db.REQUIRED_SETTINGS:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"):
        db.load_db_settings(tmp_path / "missing.env")


def test_connection_uses_ssl_options_and_disables_prepared_statements(env_path, monkeypatch):
    """SSL 옵션은 값이 있는 것만 넘기고, 풀러 대비로 자동 prepared statement를 끄는지 확인합니다."""
    captured = {}
    monkeypatch.setattr(db, "ENV_PATH", env_path)
    monkeypatch.setattr(db.st, "connection", lambda name, **kwargs: captured.update(kwargs, name=name))

    db.get_connection()

    assert captured["name"] == db.CONNECTION_NAME
    assert (captured["dialect"], captured["driver"]) == ("postgresql", "psycopg")
    assert captured["query"] == {"sslmode": "require"}  # channel_binding은 .env에 없어서 넘기지 않음
    assert captured["connect_args"] == {"prepare_threshold": None}
    assert captured["pool_pre_ping"] is True  # Neon이 끊은 연결을 빌려주기 전에 걸러 낸다


def test_tidy_matches_previous_csv_shape():
    """컬럼은 대문자, NUMERIC(Decimal)은 float, *_ID는 문자열로 바꾸고 나머지는 그대로 두는지 확인합니다."""
    raw = pd.DataFrame({
        "mesure_id": [1, 2],
        "soldier_id": ["22-1", "22-2"],
        "bmi": [Decimal("21.50"), None],
        "unit_name": ["A", "B"],
        "age": [20, 21],
    })

    tidy = db.tidy(raw)

    assert tidy.columns.tolist() == ["MESURE_ID", "SOLDIER_ID", "BMI", "UNIT_NAME", "AGE"]
    assert tidy["MESURE_ID"].dtype == "string" and tidy["MESURE_ID"].tolist() == ["1", "2"]
    assert tidy["BMI"].dtype == float and pd.isna(tidy["BMI"].iloc[1])
    assert tidy["UNIT_NAME"].dtype == object
    assert pd.api.types.is_integer_dtype(tidy["AGE"])


def test_run_query_closes_connection_and_caches(fake_connection):
    """값은 params로 넘기고, 연결은 with로 열고 닫으며(열린 트랜잭션을 남기지 않음), 같은 조회는 캐시를 쓰는지 확인합니다."""
    sql = "SELECT * FROM soldiers WHERE soldier_id = :soldier_id -- test_run_query_closes_connection_and_caches"

    result = db.run_query(sql, {"soldier_id": "22-1"}, ttl=30)
    db.run_query(sql, {"soldier_id": "22-1"}, ttl=30)

    assert fake_connection.reads == [(sql, {"soldier_id": "22-1"})]  # 두 번째는 캐시
    assert len(fake_connection.opened) == 1 and not fake_connection.opened[0].open
    assert result.columns.tolist() == ["SOLDIER_ID", "BMI"] and result.BMI.dtype == float


def test_each_ttl_has_its_own_cache(fake_connection):
    """ttl이 다르면 캐시 함수가 따로 있어, 서로의 캐시를 지우지 않는지 확인합니다."""
    sql = "SELECT 1 -- test_each_ttl_has_its_own_cache"

    db.run_query(sql, ttl=11)
    db.run_query(sql, ttl=12)
    db.run_query(sql, ttl=11)

    assert db._cached_reader(11) is not db._cached_reader(12)
    assert len(fake_connection.reads) == 2
