"""data/scripts의 공통 파이프라인 실행기와 로그 이름 규칙을 확인합니다."""

from pathlib import Path

import pytest

from config import DATA_SCRIPTS_DIR
from data.scripts.logging_setup import caller_name
from data.scripts.main import ALL_COMMAND, PIPELINES, parse_command
from data.scripts.pipeline import Step, run_steps


def test_caller_name_includes_subfolder():
    """data/scripts 하위 폴더의 모듈은 "하위폴더.모듈" 이름이 되는지 확인합니다."""
    # 세 영역에 같은 이름의 모듈(pipeline.py 등)이 있어, 폴더가 빠지면 로그만으로 구분할 수 없다.
    path = DATA_SCRIPTS_DIR / "preprocessing" / "merge_raw_measurements.py"
    assert caller_name(path) == "preprocessing.merge_raw_measurements"


def test_caller_name_for_top_level_script():
    """data/scripts 바로 아래 파일은 모듈 이름만 쓰는지 확인합니다."""
    assert caller_name(DATA_SCRIPTS_DIR / "main.py") == "main"


def test_caller_name_outside_scripts_uses_stem(tmp_path):
    """data/scripts 밖의 파일은 오류 없이 파일 이름만 쓰는지 확인합니다."""
    assert caller_name(tmp_path / "other.py") == "other"


def test_run_steps_runs_in_order(tmp_path):
    """단계 목록을 적힌 순서대로 한 번씩 실행하는지 확인합니다."""
    calls = []
    input_path = tmp_path / "input.csv"
    input_path.write_text("x")
    steps = [
        Step("first", lambda input_path, output_path: calls.append("first"), {"input_path": input_path}, {"output_path": tmp_path / "a"}),
        Step("second", lambda input_path, output_path: calls.append("second"), {"input_path": input_path}, {"output_path": tmp_path / "b"}),
    ]
    run_steps("test", steps)
    assert calls == ["first", "second"]


def test_run_steps_stops_when_input_missing(tmp_path):
    """입력 경로가 없으면 단계를 실행하기 전에 FileNotFoundError를 내는지 확인합니다."""
    calls = []
    steps = [Step("missing", lambda input_path: calls.append("ran"), {"input_path": tmp_path / "none.csv"}, {})]
    with pytest.raises(FileNotFoundError):
        run_steps("test", steps)
    assert calls == []


def test_run_steps_stops_after_failure(tmp_path):
    """한 단계가 실패하면 뒤 단계를 실행하지 않고 예외를 올리는지 확인합니다."""
    calls = []

    def fail(input_path: Path) -> None:
        raise RuntimeError("fail")

    steps = [
        Step("fail", fail, {"input_path": tmp_path}, {}),
        Step("after", lambda input_path: calls.append("after"), {"input_path": tmp_path}, {}),
    ]
    with pytest.raises(RuntimeError):
        run_steps("test", steps)
    # 앞 단계가 실패했는데 뒤 단계가 돌면, 이전 실행에서 남은 파일을 입력으로 잘못된 결과를 만든다.
    assert calls == []


def test_parse_command_defaults_to_all():
    """명령을 생략하면 전체(all) 실행으로 해석하는지 확인합니다."""
    assert parse_command([]) == ALL_COMMAND


def test_pipelines_run_in_required_order():
    """영역 실행 순서가 전처리 -> 합성 -> 분석인지 확인합니다."""
    # 합성은 전처리가 끝난 데이터를 바탕으로 하므로 순서가 바뀌면 안 된다.
    assert list(PIPELINES) == ["preprocessing", "synthesis", "analysis"]
