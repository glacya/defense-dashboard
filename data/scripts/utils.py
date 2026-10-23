"""data 스크립트 여러 곳에서 함께 쓰는 CSV 읽기·쓰기, 정의서, 명령줄 인자 도우미입니다.

같은 규칙(문자열로 읽기, utf-8-sig로 저장, 정의서 컬럼 순서 따르기)을 한곳에서 지키려고 모았습니다.
"""

import argparse
import math
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

CSV_ENCODING = "utf-8-sig"
# 우리가 만든 정의서에서 컬럼 이름이 들어 있는 열
DEFINITION_NAME_COLUMN = "영문속성명"


def read_text_csv(path: Path) -> pd.DataFrame:
    """CSV를 모든 값을 문자열로 읽습니다.

    빈 칸을 NaN이 아닌 빈 문자열로 유지해야 원본 값이 바뀌지 않으므로
    dtype=str, keep_default_na=False로 읽습니다.
    """
    return pd.read_csv(path, encoding=CSV_ENCODING, dtype=str, keep_default_na=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """부모 폴더를 만든 뒤 DataFrame을 인덱스 없이 utf-8-sig CSV로 저장합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding=CSV_ENCODING)


def require_columns(df: pd.DataFrame, columns: Iterable[str], source: str = "입력 데이터") -> None:
    """df에 columns가 모두 있는지 확인합니다.

    Raises:
        ValueError: 없는 컬럼이 있을 때. 메시지에 source와 없는 컬럼 이름을 적는다
    """
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{source}에 필수 컬럼이 없습니다: {', '.join(missing)}")


def load_definition_columns(path: Path, name_column: str = DEFINITION_NAME_COLUMN) -> list[str]:
    """정의서에서 컬럼명을 읽고 비어 있거나 중복된 이름을 거부합니다.

    Raises:
        ValueError: name_column 열이 없거나, 이름이 비어 있거나 중복되었을 때
    """
    definition = read_text_csv(path)
    if name_column not in definition.columns:
        raise ValueError(f"{path.name}에 '{name_column}' 컬럼이 없습니다.")

    names = definition[name_column].str.strip()
    if names.empty or names.eq("").any():
        raise ValueError(f"{path.name}의 '{name_column}' 값은 비워둘 수 없습니다.")
    duplicates = names[names.duplicated()].unique().tolist()
    if duplicates:
        raise ValueError(
            f"{path.name}의 '{name_column}' 값이 중복되었습니다: {', '.join(duplicates)}"
        )
    return names.tolist()


def select_definition_columns(df: pd.DataFrame, columns: list[str], definition_name: str) -> pd.DataFrame:
    """정의서의 컬럼만 정의서 순서대로 남깁니다.

    Raises:
        ValueError: 정의서에 있는 컬럼이 df에 없을 때
    """
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"{definition_name}의 컬럼이 데이터에 없습니다: {', '.join(missing_columns)}")
    return df[columns]


def write_by_definition(df: pd.DataFrame, definition_path: Path, output_path: Path) -> pd.DataFrame:
    """정의서 컬럼만 정의서 순서대로 골라 저장하고, 저장한 DataFrame을 반환합니다."""
    columns = load_definition_columns(definition_path)
    selected = select_definition_columns(df, columns, definition_path.name)
    write_csv(selected, output_path)
    return selected


def non_negative_float(value: str) -> float:
    """argparse 타입: 0 이상의 유한한 실수를 받습니다."""
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("숫자를 입력하세요.") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("0 이상의 숫자를 입력하세요.")
    return parsed


def positive_int(value: str) -> int:
    """argparse 타입: 1 이상의 정수를 받습니다."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("정수를 입력하세요.") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수를 입력하세요.")
    return parsed
