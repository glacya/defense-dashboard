"""전처리 단계의 실행 순서와 입출력 연결을 정합니다.

흐름: 원본 통합 -> 결측치·이상치 제거 -> 입대 후보 조건 필터 -> 3회 이상 측정 회원 추출 -> 최종 정의서 적용(측정·운동 처방 분리)
경로 상수는 data/scripts/paths.py에 있으며, 각 단계 모듈을 단독 실행할 때도 같은 경로를 씁니다.
"""

from data.scripts.paths import (
    DEFINITION_KS_NFA_MERGED,
    DEFINITION_KS_NFA_PRESCRIPTION,
    DEFINITION_KS_NFA_PROCESSED,
    DEFINITION_KS_NFA_RAW,
    INTERMEDIATE_BASIC_REFINEMENT,
    INTERMEDIATE_ENLISTMENT_FILTER,
    INTERMEDIATE_MERGED,
    INTERMEDIATE_THREE_MEASURES,
    PASSED_FILENAME,
    PROCESSED_FITNESS_PATH,
    PROCESSED_PRESCRIPTION_PATH,
    RAW_DIR,
)
from data.scripts.pipeline import Step
from data.scripts.preprocessing import (
    apply_processed_definition,
    filter_enlistment_candidates,
    merge_raw_measurements,
    remove_missings_and_outliers,
    select_three_measures,
)

TITLE = "전처리"


def build_steps() -> list[Step]:
    """실행 순서대로 전처리 단계 목록을 만듭니다. 앞 단계의 출력 경로를 다음 단계의 입력으로 연결합니다."""
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
            "결측치·이상치 제거",
            remove_missings_and_outliers.run,
            inputs={"input_path": INTERMEDIATE_MERGED},
            outputs={"output_dir": INTERMEDIATE_BASIC_REFINEMENT},
        ),
        Step(
            "입대 후보 조건 필터",
            filter_enlistment_candidates.run,
            inputs={"input_path": INTERMEDIATE_BASIC_REFINEMENT / PASSED_FILENAME},
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
