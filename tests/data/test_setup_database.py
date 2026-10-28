"""DB 테이블 세팅 스크립트(data/scripts/setup_database.py)를 테스트합니다. 실제 DB에는 접속하지 않습니다."""

import re
from pathlib import Path

import pytest

from data.scripts import setup_database
from data.scripts.paths import (
    DB_SOURCES,
    PROCESSED_FITNESS_PATH,
    PROCESSED_FITNESS_TYPE_PATH,
    PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
    PROCESSED_PRESCRIPTION_DETAIL_PATH,
    PROCESSED_PRESCRIPTION_PATH,
    PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH,
    SYNTHETIC_INJURY_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.setup_database import DB_TABLE_NAMES, build_schema, column_type, load_db_settings, run
from data.scripts.utils import read_text_csv

ENV_TEXT = """# 주석
DB_HOST=example.host
DB_PORT=5432

DB_NAME="dashboard"
DB_USER='tester'
DB_PASSWORD=pa=ss
DB_SSLMODE=require
"""

DEFINITION_HEADER = "순서,영문속성명,컬럼한글명,데이터타입,길이,PK여부,FK참조,NOT NULL여부,데이터 상품명\n"


class FakeCopy:
    """COPY로 보낸 글자를 모으는 가짜 객체."""

    def __init__(self, sink: list[str]):
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def write(self, data):
        self.sink.append(data)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def copy(self, sql):
        table = sql.split()[1]
        self.connection.executed.append(sql)
        return FakeCopy(self.connection.copied.setdefault(table, []))


class FakeResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return (self.value,)


class FakeConnection:
    """실행한 SQL과 COPY로 보낸 내용을 기록하는 가짜 연결. with 블록 종료 시 커밋 여부도 기록합니다.

    `SELECT count(*) FROM 테이블`에는 COPY로 받은 데이터 줄 수(헤더 제외)를 돌려줍니다.
    """

    def __init__(self):
        self.executed = []
        self.copied: dict[str, list[str]] = {}
        self.committed = False
        self.extra_rows = 0  # 행 수 불일치를 흉내 낼 때 쓴다

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.committed = exc_type is None

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if match := re.fullmatch(r"SELECT count\(\*\) FROM (\w+)", sql):
            lines = "".join(self.copied.get(match[1], [])).splitlines()
            return FakeResult(max(len(lines) - 1, 0) + self.extra_rows)
        return FakeResult(None)


@pytest.fixture
def env_path(tmp_path, monkeypatch):
    """접속 정보 파일을 만들고, 실행 환경의 DB_* 환경 변수가 테스트에 끼어들지 않게 지웁니다."""
    for key in (*setup_database.REQUIRED_SETTINGS, *setup_database.OPTIONAL_SETTINGS):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(ENV_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def fake_connection(monkeypatch):
    """connect()가 실제 DB 대신 가짜 연결을 돌려주게 합니다."""
    connection = FakeConnection()
    monkeypatch.setattr(setup_database, "connect", lambda settings: connection)
    return connection


def write_definition(path: Path, rows: list[str]) -> Path:
    """FK참조 열이 있는 정의서를 만듭니다. rows는 헤더 다음 줄들입니다."""
    path.write_text(DEFINITION_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


# CSV 파일 이름과 테이블 이름을 일부러 다르게 둔다.
SMALL_TABLE_NAMES = {"CHILD_DATA": "child_table", "PARENT_DATA": "parent_table"}


@pytest.fixture
def small_sources(tmp_path) -> tuple:
    """부모(PARENT_DATA)와 그것을 FK로 참조하는 자식(CHILD_DATA). 자식을 먼저 적어 순서 정렬을 확인합니다."""
    parent = write_definition(tmp_path / "PARENT_DEFINITION.csv", [
        "1,PARENT_ID,부모번호,VARCHAR,20,Y,,Y,",
        "2,SCORE,점수,DECIMAL,\"5,2\",N,,N,",
    ])
    child = write_definition(tmp_path / "CHILD_DEFINITION.csv", [
        "1,CHILD_ID,자식번호,INT,,Y,,Y,",
        "2,PARENT_ID,부모번호,VARCHAR,20,N,PARENT_DATA.PARENT_ID,Y,",
    ])
    # 실제 저장 파일처럼 BOM이 붙은 utf-8-sig로 쓴다.
    (tmp_path / "PARENT_DATA.csv").write_text("PARENT_ID,SCORE\np1,1.5\np2,\n", encoding="utf-8-sig")
    (tmp_path / "CHILD_DATA.csv").write_text("CHILD_ID,PARENT_ID\n1,p1\n2,p1\n3,p2\n", encoding="utf-8-sig")
    return (
        (tmp_path / "CHILD_DATA.csv", child),
        (tmp_path / "PARENT_DATA.csv", parent),
    )


# 접속 정보


def test_env_file_skips_comments_and_strips_quotes(env_path):
    """주석·빈 줄은 건너뛰고, 따옴표는 떼고, 값 안의 '='는 그대로 두는지 확인합니다."""
    settings = load_db_settings(env_path)

    assert settings["DB_NAME"] == "dashboard"
    assert settings["DB_USER"] == "tester"
    assert settings["DB_PASSWORD"] == "pa=ss"


def test_settings_come_from_environment_without_env_file(tmp_path, env_path, monkeypatch):
    """.env 파일이 없어도 환경 변수만으로 접속 정보를 읽는지 확인합니다(CI·배포)."""
    for key, value in load_db_settings(env_path).items():
        monkeypatch.setenv(key, value or "x")

    settings = load_db_settings(tmp_path / "missing.env")

    assert settings["DB_HOST"] == "example.host"


def test_environment_variable_overrides_env_file(env_path, monkeypatch):
    """같은 이름의 환경 변수가 있으면 .env 파일 값보다 우선하는지 확인합니다."""
    monkeypatch.setenv("DB_HOST", "from-environment")

    settings = load_db_settings(env_path)

    assert settings["DB_HOST"] == "from-environment"
    assert settings["DB_PORT"] == "5432"
    # 파일에 없는 선택 항목은 빈 값이다(접속 옵션으로 넘기지 않음).
    assert settings["DB_CHANNEL_BINDING"] == ""


def test_missing_settings_are_all_reported(tmp_path, monkeypatch):
    """필수 항목이 빠지면 빠진 이름을 모두 알려 주며 오류를 내는지 확인합니다."""
    for key in setup_database.REQUIRED_SETTINGS:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("DB_HOST=example.host\nDB_PORT=5432\n", encoding="utf-8")

    with pytest.raises(ValueError, match="DB_NAME, DB_USER, DB_PASSWORD"):
        load_db_settings(path)


# 정의서 -> SQL


@pytest.mark.parametrize(("data_type", "length", "expected"), [
    ("INT", "", "INTEGER"),
    ("VARCHAR", "20", "VARCHAR(20)"),
    ("DECIMAL", "7,6", "NUMERIC(7,6)"),
])
def test_column_type_maps_definition_types(data_type, length, expected):
    """정의서의 데이터타입·길이를 PostgreSQL 타입으로 바꾸는지 확인합니다."""
    assert column_type(data_type, length) == expected


@pytest.mark.parametrize(("data_type", "length"), [("VARCHAR", ""), ("DECIMAL", "7"), ("TEXT", "")])
def test_column_type_rejects_unknown_or_incomplete_types(data_type, length):
    """모르는 타입이나 길이가 맞지 않는 타입은 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="데이터타입"):
        column_type(data_type, length)


def test_schema_puts_referenced_table_first_with_keys(small_sources):
    """FK가 가리키는 테이블을 먼저 만들고, PK·NOT NULL·FK를 정의서대로 적는지 확인합니다."""
    schema = build_schema(small_sources, SMALL_TABLE_NAMES)

    assert [table for table, _ in schema] == ["parent_table", "child_table"]
    parent_sql, child_sql = (sql for _, sql in schema)
    assert "    parent_id VARCHAR(20) NOT NULL" in parent_sql
    # NOT NULL여부가 N이면 NOT NULL을 붙이지 않는다.
    assert "    score NUMERIC(5,2),\n" in parent_sql
    assert "PRIMARY KEY (parent_id)" in parent_sql
    # 테이블 이름과 FK참조의 대상 모두 CSV 이름(PARENT_DATA)이 아니라 딕셔너리의 테이블 이름(parent_table)을 쓴다.
    assert "FOREIGN KEY (parent_id) REFERENCES parent_table (parent_id)" in child_sql
    # 삭제 시 동작은 기본값을 쓰므로 ON DELETE를 적지 않는다.
    assert "ON DELETE" not in child_sql


def test_schema_rejects_reference_to_csv_not_uploaded(small_sources):
    """FK참조가 DB에 올리지 않는 CSV를 가리키면 오류를 내는지 확인합니다."""
    child_only = small_sources[:1]

    with pytest.raises(ValueError, match="DB_SOURCES"):
        build_schema(child_only, SMALL_TABLE_NAMES)


def test_schema_requires_table_name_for_each_csv(small_sources):
    """CSV 이름이 테이블 이름 딕셔너리에 없으면 추가할 곳을 알려 주며 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="DB_TABLE_NAMES"):
        build_schema(small_sources, {"CHILD_DATA": "child_table"})


def test_schema_rejects_duplicated_table_names(small_sources):
    """서로 다른 CSV가 같은 테이블 이름을 쓰면 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="같은 테이블 이름"):
        build_schema(small_sources, {"CHILD_DATA": "same", "PARENT_DATA": "same"})


def test_schema_rejects_cyclic_references(tmp_path):
    """테이블끼리 FK가 순환하면 오류를 내는지 확인합니다."""
    first = write_definition(tmp_path / "A_DEFINITION.csv", ["1,ID,번호,INT,,Y,B_DATA.ID,Y,"])
    second = write_definition(tmp_path / "B_DEFINITION.csv", ["1,ID,번호,INT,,Y,A_DATA.ID,Y,"])
    sources = ((tmp_path / "A_DATA.csv", first), (tmp_path / "B_DATA.csv", second))

    with pytest.raises(ValueError, match="순환"):
        build_schema(sources, {"A_DATA": "a", "B_DATA": "b"})


@pytest.fixture
def composite_sources(tmp_path) -> tuple:
    """두 컬럼 PK를 가진 유형 표(TYPE_DATA)와, 그것과 측정(MEASURE_DATA)을 함께 가리키는 분류 표(LABEL_DATA)."""
    measure = write_definition(tmp_path / "MEASURE_DEFINITION.csv", ["1,MEASURE_ID,측정번호,INT,,Y,,Y,"])
    types = write_definition(tmp_path / "TYPE_DEFINITION.csv", [
        "1,GRADE,등급,INT,,Y,,Y,",
        "2,CLUSTER,군집,INT,,Y,,Y,",
        "3,NAME,이름,VARCHAR,30,N,,Y,",
    ])
    # PK와 다른 순서(CLUSTER 먼저)로 적어도 대상 PK 순서로 묶여야 한다.
    labels = write_definition(tmp_path / "LABEL_DEFINITION.csv", [
        "1,MEASURE_ID,측정번호,INT,,Y,MEASURE_DATA.MEASURE_ID,Y,",
        "2,FIRST_MEASURE_ID,첫측정번호,INT,,N,MEASURE_DATA.MEASURE_ID,Y,",
        "3,CLUSTER,군집,INT,,N,TYPE_DATA.CLUSTER,Y,",
        "4,GRADE,등급,INT,,N,TYPE_DATA.GRADE,Y,",
    ])
    return (
        (tmp_path / "LABEL_DATA.csv", labels),
        (tmp_path / "MEASURE_DATA.csv", measure),
        (tmp_path / "TYPE_DATA.csv", types),
    )


COMPOSITE_TABLE_NAMES = {"LABEL_DATA": "labels", "MEASURE_DATA": "measures", "TYPE_DATA": "types"}


def test_composite_primary_key_reference_becomes_one_foreign_key(composite_sources):
    """여러 컬럼 PK를 가리키는 참조는 대상 PK 순서의 FK 하나로, 한 컬럼 PK 참조는 컬럼마다 FK 하나로 만드는지 확인합니다."""
    schema = dict(build_schema(composite_sources, COMPOSITE_TABLE_NAMES))

    assert "PRIMARY KEY (grade, cluster)" in schema["types"]
    label_sql = schema["labels"]
    assert "FOREIGN KEY (grade, cluster) REFERENCES types (grade, cluster)" in label_sql
    # 같은 한 컬럼 PK 테이블을 두 컬럼이 따로 가리키면 FK가 둘이다.
    assert "FOREIGN KEY (measure_id) REFERENCES measures (measure_id)" in label_sql
    assert "FOREIGN KEY (first_measure_id) REFERENCES measures (measure_id)" in label_sql
    assert label_sql.count("FOREIGN KEY") == 3
    assert list(schema).index("labels") == 2


def test_composite_reference_must_cover_whole_primary_key(composite_sources, tmp_path):
    """여러 컬럼 PK 중 일부만 가리키면 빠진 PK 컬럼을 알려 주며 오류를 내는지 확인합니다."""
    partial = write_definition(tmp_path / "PARTIAL_DEFINITION.csv", ["1,GRADE,등급,INT,,Y,TYPE_DATA.GRADE,Y,"])
    sources = (*composite_sources[1:], (tmp_path / "PARTIAL_DATA.csv", partial))

    with pytest.raises(ValueError, match="PK 컬럼을 모두"):
        build_schema(sources, {**COMPOSITE_TABLE_NAMES, "PARTIAL_DATA": "partial"})


def test_reference_must_point_to_primary_key_column(composite_sources, tmp_path):
    """FK참조가 대상 테이블의 PK가 아닌 컬럼을 가리키면 오류를 내는지 확인합니다."""
    wrong = write_definition(tmp_path / "WRONG_DEFINITION.csv", ["1,NAME,이름,VARCHAR,30,Y,TYPE_DATA.NAME,Y,"])
    sources = (*composite_sources[1:], (tmp_path / "WRONG_DATA.csv", wrong))

    with pytest.raises(ValueError, match="PK 컬럼을 가리켜야"):
        build_schema(sources, {**COMPOSITE_TABLE_NAMES, "WRONG_DATA": "wrong"})


def test_project_schema_creates_all_tables_with_expected_foreign_keys():
    """실제 정의서로 테이블을 모두 만들고, FK가 가리키는 테이블이 먼저 오며 FK 7개가 있는지 확인합니다."""
    schema = dict(build_schema())
    order = list(schema)
    # 테이블 이름은 바뀔 수 있으므로 CSV 경로로 찾는다.
    personnel, fitness, detail, prescription, injury, classification, fitness_type, failure = (
        DB_TABLE_NAMES[path.stem]
        for path in (
            SYNTHETIC_PERSONNEL_PATH,
            PROCESSED_FITNESS_PATH,
            PROCESSED_PRESCRIPTION_DETAIL_PATH,
            PROCESSED_PRESCRIPTION_PATH,
            SYNTHETIC_INJURY_PATH,
            PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
            PROCESSED_FITNESS_TYPE_PATH,
            PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH,
        )
    )

    assert set(order) == {DB_TABLE_NAMES[csv_path.stem] for csv_path, _ in DB_SOURCES}
    assert order.index(personnel) < order.index(fitness) < order.index(prescription)
    assert order.index(detail) < order.index(prescription)
    assert order.index(personnel) < order.index(injury)
    assert order.index(fitness) < order.index(classification)
    assert order.index(fitness_type) < order.index(classification)
    assert order.index(personnel) < order.index(failure)
    expected_foreign_keys = [
        (fitness, f"FOREIGN KEY (soldier_id) REFERENCES {personnel} (soldier_id)"),
        (prescription, f"FOREIGN KEY (mesure_id) REFERENCES {fitness} (mesure_id)"),
        (prescription, f"FOREIGN KEY (prescription_type_id) REFERENCES {detail} (prescription_type_id)"),
        (injury, f"FOREIGN KEY (soldier_id) REFERENCES {personnel} (soldier_id)"),
        (classification, f"FOREIGN KEY (mesure_id) REFERENCES {fitness} (mesure_id)"),
        (
            classification,
            f"FOREIGN KEY (average_percentile_grade, cluster) REFERENCES {fitness_type} (average_percentile_grade, cluster)",
        ),
        (failure, f"FOREIGN KEY (soldier_id) REFERENCES {personnel} (soldier_id)"),
    ]
    for table, foreign_key in expected_foreign_keys:
        assert foreign_key in schema[table]
    assert sum(sql.count("FOREIGN KEY") for sql in schema.values()) == 7


def test_db_sources_have_lowercase_table_names_and_fk_column():
    """올릴 CSV마다 테이블 이름이 있고(소문자), 정의서에 FK참조 열이 있는지 확인합니다."""
    # 저장 CSV는 Git에 없으므로(가공·가상 데이터) 정의서와 이름만 확인한다.
    for csv_path, definition_path in DB_SOURCES:
        table = DB_TABLE_NAMES[csv_path.stem]
        assert table == table.lower(), "PostgreSQL은 따옴표 없는 이름을 소문자로 바꾸므로 소문자로 적는다."
        assert "FK참조" in read_text_csv(definition_path).columns, definition_path


# 실행


def test_run_recreates_tables_and_loads_csv_in_one_transaction(small_sources, env_path, fake_connection):
    """기본 실행은 테이블을 역순으로 지우고 FK 순서로 만든 뒤, 같은 순서로 CSV를 COPY하고 커밋하는지 확인합니다."""
    run(env_path, sources=small_sources, table_names=SMALL_TABLE_NAMES)

    kinds = [sql.split("(")[0].strip() for sql in fake_connection.executed]
    assert kinds == [
        "DROP TABLE IF EXISTS child_table CASCADE;",
        "DROP TABLE IF EXISTS parent_table CASCADE;",
        "CREATE TABLE IF NOT EXISTS parent_table",
        "CREATE TABLE IF NOT EXISTS child_table",
        "COPY parent_table",
        "SELECT count",
        "COPY child_table",
        "SELECT count",
    ]
    assert "COPY child_table (child_id, parent_id) FROM STDIN WITH (FORMAT csv, HEADER true)" in fake_connection.executed
    # BOM을 떼고 보낸다. 빈 칸은 그대로 보내 COPY가 NULL로 넣는다.
    # 줄 끝은 저장한 OS를 따른다(Windows는 CRLF). PostgreSQL의 CSV COPY는 둘 다 읽는다.
    sent = "".join(fake_connection.copied["parent_table"]).replace("\r\n", "\n")
    assert sent == "PARENT_ID,SCORE\np1,1.5\np2,\n"
    assert fake_connection.committed


def test_schema_only_does_not_load_data(small_sources, env_path, fake_connection):
    """--schema-only면 테이블만 지우고 다시 만들고 COPY는 하지 않는지 확인합니다."""
    run(env_path, mode=setup_database.MODE_SCHEMA, sources=small_sources, table_names=SMALL_TABLE_NAMES)

    assert len(fake_connection.executed) == 4
    assert not fake_connection.copied


def test_load_only_truncates_existing_tables_before_copy(small_sources, env_path, fake_connection):
    """--load면 테이블을 다시 만들지 않고, 모두 비운 뒤 데이터만 넣는지 확인합니다."""
    run(env_path, mode=setup_database.MODE_LOAD, sources=small_sources, table_names=SMALL_TABLE_NAMES)

    assert fake_connection.executed[0] == "TRUNCATE parent_table, child_table;"
    assert not any(sql.startswith(("DROP", "CREATE")) for sql in fake_connection.executed)
    assert set(fake_connection.copied) == {"parent_table", "child_table"}


def test_header_mismatch_stops_before_touching_database(small_sources, env_path, fake_connection):
    """CSV 헤더가 정의서와 다르면 테이블을 지우기 전에 멈추는지 확인합니다."""
    small_sources[0][0].write_text("PARENT_ID,CHILD_ID\np1,1\n", encoding="utf-8-sig")

    with pytest.raises(ValueError, match="헤더가 정의서 컬럼과 다릅니다"):
        run(env_path, sources=small_sources, table_names=SMALL_TABLE_NAMES)

    assert fake_connection.executed == []


def test_row_count_mismatch_rolls_back(small_sources, env_path, fake_connection):
    """넣은 행 수가 CSV와 다르면 오류를 내고 커밋하지 않는지 확인합니다."""
    fake_connection.extra_rows = 1

    with pytest.raises(ValueError, match="행 수"):
        run(env_path, sources=small_sources, table_names=SMALL_TABLE_NAMES)

    assert not fake_connection.committed


def test_dry_run_does_not_connect(small_sources, tmp_path, monkeypatch):
    """--dry-run이면 접속 정보도 읽지 않고 DB에 접속하지 않는지 확인합니다."""
    def fail(settings):
        raise AssertionError("dry-run에서 접속하면 안 됩니다.")

    monkeypatch.setattr(setup_database, "connect", fail)

    run(tmp_path / "missing.env", dry_run=True, sources=small_sources, table_names=SMALL_TABLE_NAMES)
