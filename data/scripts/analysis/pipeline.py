"""분석 단계의 실행 목록을 정합니다.

분석은 전처리(와 합성) 결과를 읽기만 하고 서로의 결과에 기대지 않으므로, 순서는 실행 편의를 위한 것입니다.
프로파일링 보고서(view_fitness_statistics)는 실행이 오래 걸리고 반복할 필요가 없어 넣지 않습니다. 필요하면 단독 실행합니다.
"""

from data.scripts.analysis import (
    compare_cardio_groups,
    estimate_shuttle_run_latent_scores,
    standardize_cardio_scores,
    summarize_cut_anchored_scores,
)
from data.scripts.paths import (
    INTERMEDIATE_BASIC_REFINEMENT,
    INTERMEDIATE_CARDIO_GROUPS,
    INTERMEDIATE_CARDIO_ZSCORE,
    INTERMEDIATE_CUT_ANCHORED,
    INTERMEDIATE_ENLISTMENT_FILTER,
    INTERMEDIATE_SHUTTLE_RUN,
    INTERMEDIATE_THREE_MEASURES,
    PASSED_FILENAME,
)
from data.scripts.pipeline import Step

TITLE = "분석"


def build_steps() -> list[Step]:
    """분석 단계 목록을 만듭니다. 입출력은 각 모듈의 단독 실행 기본 경로와 같습니다."""
    return [
        Step(
            "셔틀런 잠재 점수 추정",
            estimate_shuttle_run_latent_scores.run,
            inputs={"input_path": INTERMEDIATE_BASIC_REFINEMENT / PASSED_FILENAME},
            outputs={"output_dir": INTERMEDIATE_SHUTTLE_RUN},
        ),
        Step(
            "심폐 종목별 Z점수",
            standardize_cardio_scores.run,
            inputs={"input_path": INTERMEDIATE_THREE_MEASURES},
            outputs={"output_dir": INTERMEDIATE_CARDIO_ZSCORE},
        ),
        Step(
            "등급 컷 기준 선형 변환 점수 통계",
            summarize_cut_anchored_scores.run,
            inputs={"input_path": INTERMEDIATE_THREE_MEASURES},
            outputs={"output_dir": INTERMEDIATE_CUT_ANCHORED},
        ),
        Step(
            "심폐 종목 집단 간 체력·신체조성 비교",
            compare_cardio_groups.run,
            inputs={"input_path": INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME},
            outputs={"output_dir": INTERMEDIATE_CARDIO_GROUPS},
        ),
    ]
