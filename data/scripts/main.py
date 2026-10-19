"""전처리 파이프라인 진입점입니다. 단계의 실행 순서와 입출력 연결은 이 파일에서만 정합니다.

흐름: 원본 통합 -> 심폐 단일 종목 필터 -> 입대 후보 조건 필터 -> 3회 이상 측정 회원 추출 -> 최종 정의서 적용(측정·운동 처방 분리)
경로 상수는 data/scripts/paths.py에 있으며, 각 단계 모듈을 단독 실행할 때도 같은 경로를 씁니다.
실행: python data/scripts/main.py
로그는 data/scripts/logs/{yyyymmdd}_{hhmmss}_main.log에 남습니다.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from data.scripts.logging_setup import display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_KS_NFA_MERGED,
    DEFINITION_KS_NFA_PRESCRIPTION,
    DEFINITION_KS_NFA_PROCESSED,
    DEFINITION_KS_NFA_RAW,
    INTERMEDIATE_CARDIO_FILTER,
    INTERMEDIATE_ENLISTMENT_FILTER,
    INTERMEDIATE_MERGED,
    INTERMEDIATE_THREE_MEASURES,
    PASSED_FILENAME,
    PROCESSED_FITNESS_PATH,
    PROCESSED_PRESCRIPTION_PATH,
    RAW_DIR,
)
from data.scripts.preprocessing import (
    apply_processed_definition,
    filter_enlistment_candidates,
    filter_single_cardio_records,
    merge_raw_measurements,
    select_three_measures,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Step:
    """파이프라인의 한 단계. inputs는 실행 전에 존재해야 하는 경로, outputs는 이 단계가 만드는 경로입니다."""

    name: str
    run: Callable[..., None]
    inputs: dict[str, Path]
    outputs: dict[str, Path]


def build_pipeline() -> list[Step]:
    """실행 순서대로 단계 목록을 만듭니다. 앞 단계의 출력 경로를 다음 단계의 입력으로 연결합니다."""
    return [
        Step(
            "원본 측정 데이터 통합",
            merge_raw_measurements.run,
            inputs={
                "raw_dir": RAW_DIR,
                "source_definition_path": DEFINITION_KS_NFA_RAW,
                "output_definition_path": DEFINITION_KS_NFA_MERGED,
            },
            outputs={"output_path": INTERMEDIATE_MERGED},
        ),
        Step(
            "심폐 단일 종목 필터",
            filter_single_cardio_records.run,
            inputs={"input_path": INTERMEDIATE_MERGED},
            outputs={"output_dir": INTERMEDIATE_CARDIO_FILTER},
        ),
        Step(
            "입대 후보 조건 필터",
            filter_enlistment_candidates.run,
            inputs={"input_path": INTERMEDIATE_CARDIO_FILTER / PASSED_FILENAME},
            outputs={"output_dir": INTERMEDIATE_ENLISTMENT_FILTER},
        ),
        Step(
            "3회 이상 측정한 회원의 측정 데이터 추출",
            select_three_measures.run,
            inputs={"input_path": INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME},
            outputs={"output_path": INTERMEDIATE_THREE_MEASURES},
        ),
        Step(
            "최종 정의서 적용 (MESURE_ID 부여, 측정·운동 처방 분리)",
            apply_processed_definition.run,
            inputs={
                "input_path": INTERMEDIATE_THREE_MEASURES,
                "fitness_definition_path": DEFINITION_KS_NFA_PROCESSED,
                "prescription_definition_path": DEFINITION_KS_NFA_PRESCRIPTION,
            },
            outputs={
                "fitness_output_path": PROCESSED_FITNESS_PATH,
                "prescription_output_path": PROCESSED_PRESCRIPTION_PATH,
            },
        ),
    ]


def run_step(index: int, count: int, step: Step) -> None:
    """입력 경로를 확인한 뒤 단계를 실행하고, 시작·완료·실패와 걸린 시간을 로그로 남깁니다."""
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


def main() -> None:
    log_path = setup_logging("main")
    pipeline = build_pipeline()
    logger.info("전처리 시작: %d단계, 로그 %s", len(pipeline), display_path(log_path))
    for index, step in enumerate(pipeline, 1):
        run_step(index, len(pipeline), step)
    logger.info(
        "전처리 완료: 최종 결과 %s, %s",
        display_path(PROCESSED_FITNESS_PATH), display_path(PROCESSED_PRESCRIPTION_PATH),
    )


if __name__ == "__main__":
    main()
