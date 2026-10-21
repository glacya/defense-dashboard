"""data 파이프라인 진입점입니다. 전처리·합성·분석 중 하나 또는 전체를 실행합니다.

전체 순서는 전처리 -> 합성 -> 분석입니다. 합성은 전처리가 끝난 데이터를 바탕으로 하므로 둘을 동시에 실행하지 않습니다.
각 영역의 단계 목록은 preprocessing/, synthesis/, analysis/의 pipeline.py에서 정합니다.
실행: python data/scripts/main.py [preprocessing | synthesis | analysis | all]  (생략하면 all)
로그는 data/scripts/logs/{yyyymmdd}_{hhmmss}_main.{명령}.log에 남습니다.
"""

import argparse
import logging
from types import ModuleType

from data.scripts.analysis import pipeline as analysis_pipeline
from data.scripts.logging_setup import display_path, setup_logging
from data.scripts.pipeline import run_steps
from data.scripts.preprocessing import pipeline as preprocessing_pipeline
from data.scripts.synthesis import pipeline as synthesis_pipeline

logger = logging.getLogger(__name__)

# 실행 순서대로 둔다. all은 이 순서로 하나씩 실행하고, 앞 영역이 실패하면 멈춘다.
PIPELINES: dict[str, ModuleType] = {
    "preprocessing": preprocessing_pipeline,
    "synthesis": synthesis_pipeline,
    "analysis": analysis_pipeline,
}
ALL_COMMAND = "all"


def parse_command(argv: list[str] | None = None) -> str:
    """명령줄에서 실행할 영역 이름을 읽습니다. 생략하면 all입니다."""
    parser = argparse.ArgumentParser(description="data 파이프라인(전처리 -> 합성 -> 분석)을 실행합니다.")
    parser.add_argument(
        "command",
        nargs="?",
        default=ALL_COMMAND,
        choices=[*PIPELINES, ALL_COMMAND],
        help="실행할 영역. all은 전처리 -> 합성 -> 분석 순서로 모두 실행합니다.",
    )
    return parser.parse_args(argv).command


def run_command(command: str) -> None:
    """명령에 해당하는 영역의 단계를 실행합니다. all이면 모든 영역을 순서대로 실행합니다."""
    names = list(PIPELINES) if command == ALL_COMMAND else [command]
    for name in names:
        module = PIPELINES[name]
        run_steps(module.TITLE, module.build_steps())


def main(argv: list[str] | None = None) -> None:
    """명령줄 인자를 읽어 로그를 설정하고 해당 영역을 실행합니다."""
    command = parse_command(argv)
    log_path = setup_logging(f"main.{command}")
    logger.info("실행: %s, 로그 %s", command, display_path(log_path))
    run_command(command)


if __name__ == "__main__":
    main()
