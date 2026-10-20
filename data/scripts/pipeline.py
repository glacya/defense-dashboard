"""전처리·합성·분석 파이프라인이 함께 쓰는 단계 정의와 실행기입니다.

각 영역(preprocessing/, synthesis/, analysis/)의 pipeline.py가 build_steps()로 Step 목록을 만들고,
data/scripts/main.py가 run_steps()로 실행합니다.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from data.scripts.logging_setup import display_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Step:
    """파이프라인의 한 단계. inputs는 실행 전에 존재해야 하는 경로, outputs는 이 단계가 만드는 경로입니다."""

    name: str
    run: Callable[..., None]
    inputs: dict[str, Path]
    outputs: dict[str, Path]


def run_step(index: int, count: int, step: Step) -> None:
    """입력 경로를 확인한 뒤 단계를 실행하고, 시작·완료·실패와 걸린 시간을 로그로 남깁니다.

    Raises:
        FileNotFoundError: 입력 경로 중 하나라도 없을 때. 앞 영역(예: 전처리)을 먼저 실행하지 않은 경우다.
    """
    missing = [display_path(path) for path in step.inputs.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"[{step.name}] 입력이 없습니다: {', '.join(missing)}")

    logger.info("[%d/%d] %s 시작", index, count, step.name)
    start = time.perf_counter()
    try:
        step.run(**step.inputs, **step.outputs)
    except Exception:
        logger.exception("[%d/%d] %s 실패", index, count, step.name)
        raise
    logger.info("[%d/%d] %s 완료 (%.1f초)", index, count, step.name, time.perf_counter() - start)


def run_steps(title: str, steps: list[Step]) -> None:
    """단계 목록을 순서대로 실행합니다. 한 단계가 실패하면 예외를 그대로 올려 뒤 단계를 실행하지 않습니다."""
    if not steps:
        logger.info("%s: 실행할 단계가 없습니다.", title)
        return
    logger.info("%s 시작: %d단계", title, len(steps))
    start = time.perf_counter()
    for index, step in enumerate(steps, 1):
        run_step(index, len(steps), step)
    logger.info("%s 완료 (%.1f초)", title, time.perf_counter() - start)
