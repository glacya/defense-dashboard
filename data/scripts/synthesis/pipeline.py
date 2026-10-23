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
from data.scripts.synthesis.generate_linkage_injury import run as link_injury_risk
from data.scripts.synthesis.generate_synthetic_injuries import run as generate_injuries
from data.scripts.synthesis.generate_synthetic_personnels import run as generate_personnels

TITLE = "가상 데이터 합성"


def build_steps() -> list[Step]:
    """실행 순서대로 합성 단계 목록을 만듭니다."""
    # TODO: generate_synthetic_personnels·generate_synthetic_injuries는 아직 이전 구조(경로 직접 지정, run(입력, 출력) 없음)라
    # 단계 형식으로 정비한 뒤 여기에 추가한다.
    return [
        Step(
            name="가상 장병 생성",
            run=generate_personnels,
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
