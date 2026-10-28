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


class FakeConnection:
    """query()에 넘긴 인자를 기록하고 정해 둔 결과를 돌려주는 가짜 연결."""

    def __init__(self, result: pd.DataFrame):
        self.result = result
        self.calls = []

    def query(self, sql, **kwargs):
        self.calls.append((sql, kwargs))
        return self.result


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
    connection = FakeConnection(pd.DataFrame({"soldier_id": ["22-1"], "bmi": [Decimal("21.50")]}))
    monkeypatch.setattr(db, "get_connection", lambda: connection)
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


def test_run_query_passes_params_and_ttl(fake_connection):
    """값은 SQL에 넣지 않고 params로, 캐시 시간은 ttl로 넘기는지 확인합니다."""
    result = db.run_query("SELECT * FROM soldiers WHERE soldier_id = :soldier_id", {"soldier_id": "22-1"}, ttl=30)

    sql, kwargs = fake_connection.calls[0]
    assert sql == "SELECT * FROM soldiers WHERE soldier_id = :soldier_id"
    assert kwargs["params"] == {"soldier_id": "22-1"} and kwargs["ttl"] == 30
    assert result.columns.tolist() == ["SOLDIER_ID", "BMI"]
