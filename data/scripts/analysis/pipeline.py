"""분석 단계의 실행 목록을 정합니다.

최종 측정과 장병 명단을 읽어 대시보드용 결과를 별도로 생성합니다.
프로파일링 보고서(view_fitness_statistics)는 실행이 오래 걸리고 반복할 필요가 없어 넣지 않습니다. 필요하면 단독 실행합니다.
"""

from data.scripts.pipeline import Step
from data.scripts.analysis.analysis2.fitness_overview import run
from data.scripts.analysis.analysis2.management_targets import run as run_targets
from data.scripts.analysis.analysis2.personal_detail import run as run_personal
from data.scripts.analysis.analysis2.injury_overview import run as run_injury
from data.scripts.paths import SYNTHETIC_INJURY_PATH, PROCESSED_INJURY_OVERVIEW_DIR
from data.scripts.paths import PROCESSED_PERSONAL_DETAIL_DIR
from data.scripts.paths import PROCESSED_MANAGEMENT_TARGETS_DIR
from data.scripts.paths import PROCESSED_FITNESS_PATH, SYNTHETIC_PERSONNEL_PATH, PROCESSED_FITNESS_OVERVIEW_DIR

TITLE = "분석"


def build_steps() -> list[Step]:
    """분석 단계 목록을 만듭니다. 입출력은 각 모듈의 단독 실행 기본 경로와 같습니다."""
    return [Step('전체 체력 현황 생성', run,
        inputs={'input_path': PROCESSED_FITNESS_PATH, 'personnel_path': SYNTHETIC_PERSONNEL_PATH},
        outputs={'output_dir': PROCESSED_FITNESS_OVERVIEW_DIR}),
        Step('체력 집중관리 대상자 생성', run_targets,
            inputs={'input_path':PROCESSED_FITNESS_PATH},
            outputs={'output_dir':PROCESSED_MANAGEMENT_TARGETS_DIR}),
        Step('개인 장병 상세 변화 생성',run_personal,
            inputs={'input_path':PROCESSED_FITNESS_PATH,
                    'targets_path':PROCESSED_MANAGEMENT_TARGETS_DIR/'management_targets.csv'},
            outputs={'output_dir':PROCESSED_PERSONAL_DETAIL_DIR}),
        Step('부상 현황 생성',run_injury,
            inputs={'input_path':PROCESSED_FITNESS_PATH,'personnel_path':SYNTHETIC_PERSONNEL_PATH,'injury_path':SYNTHETIC_INJURY_PATH},
            outputs={'output_dir':PROCESSED_INJURY_OVERVIEW_DIR})]
