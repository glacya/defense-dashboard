"""가상 데이터 합성 단계의 실행 순서와 입출력 연결을 정합니다.

합성은 전처리가 끝난 데이터를 바탕으로 하므로 전처리 다음에 실행합니다.
"""

from data.scripts.paths import (
    LINKED_INJURY_RISK_PATH,
    PROCESSED_FITNESS_PATH,
    SYNTHETIC_INJURY_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.pipeline import Step
from data.scripts.synthesis.link_fitness_and_injury_risk import run as link_injury_risk
from data.scripts.synthesis.generate_synthetic_injuries import run as generate_injuries
from data.scripts.synthesis.generate_synthetic_personnel import run as generate_personnel

TITLE = "가상 데이터 합성"


def build_steps() -> list[Step]:
    """실행 순서대로 합성 단계 목록을 만듭니다."""
    return [
        Step(
            name="가상 장병 생성",
            run=generate_personnel,
            inputs={"fitness_path": PROCESSED_FITNESS_PATH},
            outputs={"output_path": SYNTHETIC_PERSONNEL_PATH},
        ),
        Step(
            name="체력 연계 및 부상 확률 계산",
            run=link_injury_risk,
            inputs={
                "personnel_path": SYNTHETIC_PERSONNEL_PATH,
                "fitness_path": PROCESSED_FITNESS_PATH,
            },
            outputs={"output_path": LINKED_INJURY_RISK_PATH},
        ),
        Step(
            name="개인별 부상 생성",
            run=generate_injuries,
            inputs={"personal_csv_path": LINKED_INJURY_RISK_PATH},
            outputs={"output_path": SYNTHETIC_INJURY_PATH},
        ),
    ]
