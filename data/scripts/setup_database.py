"""컬럼 정의서로 PostgreSQL 테이블 생성 SQL을 만들고 DB에 실행합니다.

올릴 데이터(저장 CSV, 정의서)는 paths.DB_SOURCES, CSV 파일 이름과 SQL 테이블 이름의 짝은 이 모듈의 DB_TABLE_NAMES에 있습니다.
정의서의 데이터타입·길이·PK여부·NOT NULL여부·FK참조로 CREATE TABLE 문을 만들고,
FK가 가리키는 테이블을 먼저 만들도록 순서를 정합니다.
테이블 이름과 FK참조(`CSV이름.컬럼`)의 대상 테이블은 모두 DB_TABLE_NAMES에서 CSV 이름으로 찾습니다.
FK의 삭제 시 동작은 기본값(NO ACTION: 참조되는 행은 지울 수 없음)을 씁니다.

접속 정보는 data/.env(형식은 data/.env.example)에서 읽고, 같은 이름의 환경 변수가 있으면 그 값을 우선합니다.
CI·배포처럼 .env 파일 없이 환경 변수만 주는 경우에도 같은 코드로 접속할 수 있게 하기 위해서입니다.
모든 문을 트랜잭션 하나로 실행하므로, 중간에 실패하면 아무것도 바뀌지 않습니다.
파이프라인(main.py)에는 넣지 않고 직접 실행합니다. --dry-run이면 DB에 접속하지 않고 SQL만 출력합니다.
"""

import argparse
import logging
import os
import re
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import dotenv_values

from data.scripts.logging_setup import caller_name, setup_logging
from data.scripts.paths import (
    DB_ENV_PATH,
    DB_SOURCES,
    PROCESSED_FITNESS_PATH,
    PROCESSED_PRESCRIPTION_DETAIL_PATH,
    PROCESSED_PRESCRIPTION_PATH,
    SYNTHETIC_INJURY_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.utils import read_text_csv, require_columns

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
# 값이 있을 때만 접속 옵션으로 넘긴다(libpq의 sslmode, channel_binding).
OPTIONAL_SETTINGS = ("DB_SSLMODE", "DB_CHANNEL_BINDING")

# CSV 파일 이름(확장자 제외) -> SQL 테이블 이름. 둘이 달라질 수 있어 짝을 여기서 정하고, 테이블 이름을 바꿀 때는 여기만 고친다.
# 키는 paths의 CSV 경로에서 가져와, CSV 파일 이름이 바뀌어도 여기를 고칠 필요가 없다.
# 정의서의 FK참조(`CSV이름.컬럼`)도 이 표로 테이블 이름을 찾는다.
# PostgreSQL은 따옴표 없는 이름을 소문자로 바꾸므로 테이블 이름은 소문자로 적는다.
DB_TABLE_NAMES = {
    SYNTHETIC_PERSONNEL_PATH.stem: "soldiers",
    PROCESSED_FITNESS_PATH.stem: "fitness_measurements",
    PROCESSED_PRESCRIPTION_DETAIL_PATH.stem: "exercise_prescription_details",
    PROCESSED_PRESCRIPTION_PATH.stem: "exercise_prescriptions",
    SYNTHETIC_INJURY_PATH.stem: "injuries",
}

# 정의서에서 쓰는 열
NAME_COLUMN = "영문속성명"
TYPE_COLUMN = "데이터타입"
LENGTH_COLUMN = "길이"
PK_COLUMN = "PK여부"
FK_COLUMN = "FK참조"
NOT_NULL_COLUMN = "NOT NULL여부"
DEFINITION_COLUMNS = (NAME_COLUMN, TYPE_COLUMN, LENGTH_COLUMN, PK_COLUMN, FK_COLUMN, NOT_NULL_COLUMN)

# 정의서의 VARCHAR 길이는 글자 수이고, PostgreSQL의 VARCHAR(n)도 바이트가 아니라 글자 수라 그대로 쓴다.
_DECIMAL_LENGTH = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\s*$")

Source = tuple[Path, Path]


def column_type(data_type: str, length: str) -> str:
    """정의서의 데이터타입·길이를 PostgreSQL 타입으로 바꿉니다.

    Raises:
        ValueError: 모르는 타입이거나 VARCHAR·DECIMAL에 맞는 길이가 없을 때
    """
    data_type, length = data_type.strip().upper(), length.strip()
    if data_type == "INT":
        return "INTEGER"
    if data_type == "VARCHAR" and length.isdigit():
        return f"VARCHAR({length})"
    if data_type == "DECIMAL" and (match := _DECIMAL_LENGTH.match(length)):
        return f"NUMERIC({match[1]},{match[2]})"
    raise ValueError(f"정의서의 데이터타입을 SQL 타입으로 바꿀 수 없습니다: {data_type}, 길이 {length!r}")


def load_table_definition(definition_path: Path) -> pd.DataFrame:
    """정의서를 읽고 SQL 생성에 필요한 열이 있는지 확인합니다."""
    definition = read_text_csv(definition_path)
    require_columns(definition, DEFINITION_COLUMNS, definition_path.name)
    return definition


def table_name(csv_name: str, table_names: dict[str, str]) -> str:
    """CSV 파일 이름(확장자 제외)에 맞는 SQL 테이블 이름을 반환합니다.

    Raises:
        ValueError: table_names에 그 CSV 이름이 없을 때
    """
    if csv_name not in table_names:
        raise ValueError(f"CSV {csv_name}의 테이블 이름이 없습니다. setup_database.py의 DB_TABLE_NAMES에 추가하세요.")
    return table_names[csv_name]


def resolve_reference(reference: str, table_names: dict[str, str], tables: set[str]) -> tuple[str, str]:
    """FK참조 `CSV이름.컬럼`을 (테이블 이름, 컬럼 이름)으로 바꿉니다.

    Raises:
        ValueError: 형식이 틀렸거나, 테이블 이름이 없거나, 그 테이블을 만들지 않을 때(tables에 없음)
    """
    csv_name, separator, column = reference.strip().rpartition(".")
    if not separator or not csv_name or not column:
        raise ValueError(f"FK참조는 `CSV이름.컬럼` 형식이어야 합니다: {reference!r}")
    target = table_name(csv_name, table_names)
    if target not in tables:
        raise ValueError(f"FK참조의 CSV({csv_name})가 DB에 올릴 데이터(paths.DB_SOURCES)에 없습니다: {reference!r}")
    return target, column.lower()


def build_create_table(
    table: str,
    definition: pd.DataFrame,
    table_names: dict[str, str],
    tables: set[str],
) -> tuple[str, set[str]]:
    """CREATE TABLE 문과, 이 테이블이 FK로 참조하는 다른 테이블 이름들을 반환합니다.

    tables는 함께 만드는 테이블 이름들이고, FK는 그중 하나를 가리켜야 합니다.
    PostgreSQL은 따옴표 없는 이름을 소문자로 바꾸므로 컬럼 이름도 소문자로 적는다.
    """
    lines, primary_keys, dependencies = [], [], set()
    for row in definition.itertuples(index=False):
        values = dict(zip(definition.columns, row))
        column = values[NAME_COLUMN].strip().lower()
        not_null = " NOT NULL" if values[NOT_NULL_COLUMN].strip().upper() == "Y" else ""
        lines.append(f"    {column} {column_type(values[TYPE_COLUMN], values[LENGTH_COLUMN])}{not_null}")
        if values[PK_COLUMN].strip().upper() == "Y":
            primary_keys.append(column)
    if primary_keys:
        lines.append(f"    PRIMARY KEY ({', '.join(primary_keys)})")
    for row in definition.itertuples(index=False):
        values = dict(zip(definition.columns, row))
        if not values[FK_COLUMN].strip():
            continue
        target_table, target_column = resolve_reference(values[FK_COLUMN], table_names, tables)
        column = values[NAME_COLUMN].strip().lower()
        lines.append(f"    FOREIGN KEY ({column}) REFERENCES {target_table} ({target_column})")
        if target_table != table:
            dependencies.add(target_table)
    statement = f"CREATE TABLE IF NOT EXISTS {table} (\n" + ",\n".join(lines) + "\n);"
    return statement, dependencies


def build_schema(
    sources: tuple[Source, ...] = DB_SOURCES,
    table_names: dict[str, str] = DB_TABLE_NAMES,
) -> list[tuple[str, str]]:
    """(테이블 이름, CREATE TABLE 문)을 FK가 가리키는 테이블이 먼저 오는 순서로 반환합니다.

    테이블 이름은 각 저장 CSV의 파일 이름(확장자 제외)으로 table_names에서 찾습니다.

    Raises:
        ValueError: 테이블 이름이 없거나 겹칠 때, FK가 잘못되었거나 테이블끼리 순환할 때
    """
    tables = [(table_name(csv_path.stem, table_names), definition_path) for csv_path, definition_path in sources]
    names = [table for table, _ in tables]
    duplicated = sorted({table for table in names if names.count(table) > 1})
    if duplicated:
        raise ValueError(f"여러 CSV가 같은 테이블 이름을 씁니다: {', '.join(duplicated)}. setup_database.py의 DB_TABLE_NAMES를 확인하세요.")
    statements, graph = {}, {}
    for table, definition_path in tables:
        statements[table], graph[table] = build_create_table(
            table, load_table_definition(definition_path), table_names, set(names)
        )
    try:
        # FK가 가리키는 테이블이 먼저 만들어지도록 순서를 정한다.
        sorter = TopologicalSorter(graph)
        order = list(sorter.static_order())
    except CycleError as error:
        raise ValueError(f"테이블 FK가 순환합니다: {error.args[1]}") from error
    return [(table, statements[table]) for table in order]


def load_db_settings(env_path: Path = DB_ENV_PATH) -> dict[str, str]:
    """DB 접속 정보를 읽습니다. 환경 변수(os.environ)가 .env 파일 값보다 우선합니다.

    .env 파일이 없으면 환경 변수만 씁니다.

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
            "data/.env(형식은 data/.env.example)나 환경 변수에 적으세요."
        )
    return settings


def connect(settings: dict[str, str]) -> psycopg.Connection:
    """접속 정보로 PostgreSQL에 연결합니다."""
    options = {
        "sslmode": settings.get("DB_SSLMODE"),
        "channel_binding": settings.get("DB_CHANNEL_BINDING"),
    }
    return psycopg.connect(
        host=settings["DB_HOST"],
        port=settings["DB_PORT"],
        dbname=settings["DB_NAME"],
        user=settings["DB_USER"],
        password=settings["DB_PASSWORD"],
        **{name: value for name, value in options.items() if value},
    )


def drop_statements(table_names: list[str]) -> list[str]:
    """테이블을 만든 순서의 역순으로 지우는 문을 반환합니다(참조하는 테이블을 먼저 지움)."""
    return [f"DROP TABLE IF EXISTS {table} CASCADE;" for table in reversed(table_names)]


def run(
    env_path: Path,
    reset: bool = False,
    dry_run: bool = False,
    sources: tuple[Source, ...] = DB_SOURCES,
    table_names: dict[str, str] = DB_TABLE_NAMES,
) -> None:
    """정의서로 만든 테이블 생성 SQL을 DB에 실행합니다.

    Args:
        env_path: 접속 정보 파일 (data/.env)
        reset: True면 만들 테이블을 먼저 지우고 새로 만든다(데이터도 지워짐)
        dry_run: True면 DB에 접속하지 않고 실행할 SQL만 로그에 남긴다
        sources: DB에 올릴 (저장 CSV, 정의서) 목록
        table_names: CSV 파일 이름(확장자 제외) -> SQL 테이블 이름
    """
    schema = build_schema(sources, table_names)
    statements = (drop_statements([table for table, _ in schema]) if reset else []) + [sql for _, sql in schema]
    if dry_run:
        logger.info("실행하지 않음(--dry-run). 실행할 SQL:\n%s", "\n\n".join(statements))
        return

    settings = load_db_settings(env_path)
    # 비밀번호·사용자 이름은 로그에 남기지 않는다.
    logger.info("접속: %s:%s/%s", settings["DB_HOST"], settings["DB_PORT"], settings["DB_NAME"])
    # with 블록이 끝날 때 오류가 없으면 커밋, 있으면 롤백한다.
    with connect(settings) as conn:
        for statement in statements:
            conn.execute(statement)
    if reset:
        logger.info("삭제 후 다시 만듦: %s", ", ".join(table for table, _ in schema))
    logger.info("테이블 생성(이미 있으면 그대로 둠): %s", ", ".join(table for table, _ in schema))


def main() -> None:
    """data/.env의 접속 정보로 paths.DB_SOURCES의 테이블을 만듭니다."""
    parser = argparse.ArgumentParser(description="컬럼 정의서로 PostgreSQL 테이블을 만듭니다.")
    parser.add_argument("--reset", action="store_true", help="테이블을 먼저 지우고 새로 만듭니다(데이터 삭제).")
    parser.add_argument("--dry-run", action="store_true", help="DB에 접속하지 않고 실행할 SQL만 출력합니다.")
    args = parser.parse_args()

    setup_logging(caller_name(__file__))
    run(DB_ENV_PATH, args.reset, args.dry_run)


if __name__ == "__main__":
    main()
