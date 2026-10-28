"""전처리 단계의 실행 순서와 입출력 연결을 정합니다.

흐름: 원본 통합 -> 운동 처방 상세 테이블 생성 -> 결측치·이상치 제거 -> 입대 후보 조건 필터 -> 3회 이상 측정 회원 추출(측정일·나이 흐름 모순 회원 제외) -> 최종 정의서 적용(측정·운동 처방 분리)
경로 상수는 data/scripts/paths.py에 있으며, 각 단계 모듈을 단독 실행할 때도 같은 경로를 씁니다.
"""

from data.scripts.paths import (
    DEFINITION_KS_NFA_MERGED,
    DEFINITION_KS_NFA_PRESCRIPTION,
    DEFINITION_KS_NFA_PRESCRIPTION_DETAIL,
    DEFINITION_KS_NFA_RAW,
    DEFINITION_KS_NFA_REFINED,
    INTERMEDIATE_BASIC_REFINEMENT,
    INTERMEDIATE_ENLISTMENT_FILTER,
    INTERMEDIATE_MERGED,
    INTERMEDIATE_MULTI_CARDIO,
    INTERMEDIATE_REFINED,
    INTERMEDIATE_THREE_MEASURES,
    INTERMEDIATE_THREE_MEASURES_REMOVED,
    PASSED_FILENAME,
    PROCESSED_PRESCRIPTION_DETAIL_PATH,
    PROCESSED_PRESCRIPTION_PATH,
    RAW_DIR,
)
from data.scripts.pipeline import Step
from data.scripts.preprocessing import (
    apply_refined_definition,
    build_prescription_details,
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
            outputs={"output_path": INTERMEDIATE_MERGED, "multi_cardio_path": INTERMEDIATE_MULTI_CARDIO},
        ),
        Step(
            "운동 처방 상세 테이블 생성",
            build_prescription_details.run,
            inputs={
                "input_path": INTERMEDIATE_MERGED,
                "definition_path": DEFINITION_KS_NFA_PRESCRIPTION_DETAIL,
            },
            outputs={"output_path": PROCESSED_PRESCRIPTION_DETAIL_PATH},
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
            "3회 이상 측정한 회원의 측정 데이터 추출 (측정일·나이 흐름 검사)",
            select_three_measures.run,
            inputs={"input_path": INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME},
            outputs={
                "output_path": INTERMEDIATE_THREE_MEASURES,
                "removed_path": INTERMEDIATE_THREE_MEASURES_REMOVED,
            },
        ),
        Step(
            "최종 정의서 적용 (MESURE_ID 부여, 측정·운동 처방 분리)",
            apply_refined_definition.run,
            inputs={
                "input_path": INTERMEDIATE_THREE_MEASURES,
                "fitness_definition_path": DEFINITION_KS_NFA_REFINED,
                "prescription_definition_path": DEFINITION_KS_NFA_PRESCRIPTION,
                # 2단계에서 만든 상세 테이블. 입력으로 두어 없으면 실행 전에 멈추게 한다.
                "prescription_detail_path": PROCESSED_PRESCRIPTION_DETAIL_PATH,
            },
            outputs={
                "fitness_output_path": INTERMEDIATE_REFINED,
                "prescription_output_path": PROCESSED_PRESCRIPTION_PATH,
            },
        ),
    ]
