"""가상 데이터 합성 단계의 실행 순서와 입출력 연결을 정합니다.

합성은 전처리가 끝난 데이터를 바탕으로 하므로 전처리 다음에 실행합니다.
흐름: 가상 장병 명단 생성 -> 회원별 최근 측정 연계·부상 위험 그룹 계산(최종 측정 데이터 생성) -> 부상 기록 생성
"""

from data.scripts.paths import (
    DEFINITION_INJURY_RISK_GROUP,
    DEFINITION_KS_NFA_FINAL,
    DEFINITION_SOLDIER_INJURY,
    DEFINITION_SOLDIER_PERSONNEL,
    INTERMEDIATE_REFINED,
    LINKED_INJURY_RISK_PATH,
    PROCESSED_FITNESS_PATH,
    PROCESSED_INJURY_RISK_GROUP_PATH,
    SYNTHETIC_INJURY_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.pipeline import Step
from data.scripts.synthesis import (
    generate_synthetic_injuries,
    generate_synthetic_personnel,
    link_fitness_and_injury_risk,
)

TITLE = "가상 데이터 합성"


def build_steps() -> list[Step]:
    """실행 순서대로 합성 단계 목록을 만듭니다."""
    return [
        Step(
            "가상 장병 명단 생성",
            generate_synthetic_personnel.run,
            inputs={
                "fitness_path": INTERMEDIATE_REFINED,
                "definition_path": DEFINITION_SOLDIER_PERSONNEL,
            },
            outputs={"output_path": SYNTHETIC_PERSONNEL_PATH},
        ),
        Step(
            "최근 측정 연계 및 부상 위험 그룹 계산",
            link_fitness_and_injury_risk.run,
            inputs={
                "personnel_path": SYNTHETIC_PERSONNEL_PATH,
                "fitness_path": INTERMEDIATE_REFINED,
                "fitness_definition_path": DEFINITION_KS_NFA_FINAL,
                "risk_group_definition_path": DEFINITION_INJURY_RISK_GROUP,
            },
            outputs={
                "output_path": LINKED_INJURY_RISK_PATH,
                "risk_group_output_path": PROCESSED_INJURY_RISK_GROUP_PATH,
                "fitness_output_path": PROCESSED_FITNESS_PATH,
            },
        ),
        Step(
            "부상 기록 생성",
            generate_synthetic_injuries.run,
            inputs={
                "soldiers_path": LINKED_INJURY_RISK_PATH,
                "definition_path": DEFINITION_SOLDIER_INJURY,
            },
            outputs={"output_path": SYNTHETIC_INJURY_PATH},
        ),
    ]
