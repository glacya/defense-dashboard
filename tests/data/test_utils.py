"""data/scripts/utils.py의 CSV·정의서·명령줄 도우미를 테스트합니다."""

import argparse

import pandas as pd
import pytest

from data.scripts.utils import (
    load_definition_columns,
    non_negative_float,
    positive_int,
    read_text_csv,
    require_columns,
    select_definition_columns,
    write_by_definition,
    write_csv,
)


def write_definition(path, names: list[str]) -> None:
    """영문속성명 열만 있는 정의서를 만듭니다."""
    pd.DataFrame({"순서": range(1, len(names) + 1), "영문속성명": names}).to_csv(
        path, index=False, encoding="utf-8-sig"
    )


def test_write_and_read_text_csv_keep_values_as_strings(tmp_path):
    """저장 시 폴더를 만들고, 읽을 때 앞자리 0과 빈 칸을 문자열 그대로 유지하는지 확인합니다."""
    path = tmp_path / "nested" / "data.csv"

    write_csv(pd.DataFrame({"code": ["007"], "memo": [""]}), path)

    assert read_text_csv(path).to_dict("records") == [{"code": "007", "memo": ""}]


def test_require_columns_names_source_and_missing_columns():
    """필수 컬럼이 빠지면 데이터 이름과 빠진 컬럼을 메시지에 담아 오류를 내는지 확인합니다."""
    df = pd.DataFrame({"A": [1]})

    require_columns(df, ["A"])
    with pytest.raises(ValueError, match="입력 CSV에 필수 컬럼이 없습니다: B, C"):
        require_columns(df, ["A", "B", "C"], "입력 CSV")


def test_load_definition_columns_rejects_duplicates(tmp_path):
    """정의서의 컬럼 이름이 중복되면 오류를 내는지 확인합니다."""
    path = tmp_path / "definition.csv"
    write_definition(path, ["A", "B", "A"])

    with pytest.raises(ValueError, match="중복"):
        load_definition_columns(path)


def test_select_definition_columns_orders_and_rejects_missing():
    """정의서 순서대로 컬럼을 고르고, 없는 컬럼이 있으면 오류를 내는지 확인합니다."""
    df = pd.DataFrame({"B": [1], "A": [2], "C": [3]})

    assert select_definition_columns(df, ["A", "B"], "정의서").columns.tolist() == ["A", "B"]
    with pytest.raises(ValueError, match="D"):
        select_definition_columns(df, ["A", "D"], "정의서")


def test_write_by_definition_saves_only_definition_columns(tmp_path):
    """정의서에 있는 컬럼만 정의서 순서대로 저장하는지 확인합니다."""
    definition_path = tmp_path / "definition.csv"
    output_path = tmp_path / "out.csv"
    write_definition(definition_path, ["B", "A"])

    write_by_definition(pd.DataFrame({"A": [1], "B": [2], "extra": [3]}), definition_path, output_path)

    assert read_text_csv(output_path).columns.tolist() == ["B", "A"]


def test_argument_types_reject_out_of_range_values():
    """명령줄 인자 타입이 음수·0·숫자가 아닌 값을 거부하는지 확인합니다."""
    assert non_negative_float("0.3") == 0.3
    assert positive_int("5") == 5
    for parse, value in ((non_negative_float, "-1"), (non_negative_float, "abc"), (positive_int, "0")):
        with pytest.raises(argparse.ArgumentTypeError):
            parse(value)
