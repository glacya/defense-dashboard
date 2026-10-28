"""분석 단계의 실행 목록을 정합니다.

최종 측정으로 체력 유형(평균 백분위 등급·K-means 군집)과 장병별 다음 회차 미달 확률을 정해
별도 테이블로 저장합니다(Git에 있는 학습된 모델을 그대로 씀, 학습은 train_*.py를 직접 실행).
대시보드용 결과를 미리 만들던 analysis2 스크립트는 대시보드 쪽 SQL 조회로 옮길 예정이라 넣지 않습니다.
프로파일링 보고서(view_fitness_statistics)는 실행이 오래 걸리고 반복할 필요가 없어 넣지 않습니다. 필요하면 단독 실행합니다.
"""

from data.scripts.pipeline import Step
from data.scripts.analysis.clustering import assign_grade_and_cluster, classify_measurements_by_percentile
from data.scripts.analysis.failure_prediction import predict_failure_probability
from data.scripts.paths import (
    CLUSTER_MODEL_DIR,
    DEFINITION_FITNESS_TYPE,
    DEFINITION_MEASUREMENT_CLASSIFICATION,
    DEFINITION_SOLDIER_FAILURE_PROBABILITY,
    FAILURE_MODEL_PATH,
    INTERMEDIATE_CLUSTERING,
    PROCESSED_FITNESS_PATH,
    PROCESSED_FITNESS_TYPE_PATH,
    PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
    PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH,
)

TITLE = "분석"


def build_steps() -> list[Step]:
    """분석 단계 목록을 만듭니다. 입출력은 각 모듈의 단독 실행 기본 경로와 같습니다."""
    return [
        Step(
            "평균 백분위 등급별 측정 나누기",
            classify_measurements_by_percentile.run,
            inputs={"input_path": PROCESSED_FITNESS_PATH},
            outputs={"output_dir": INTERMEDIATE_CLUSTERING},
        ),
        Step(
            "측정별 등급·군집과 유형명 저장",
            assign_grade_and_cluster.run,
            inputs={
                "grade_dir": INTERMEDIATE_CLUSTERING,
                "model_dir": CLUSTER_MODEL_DIR,
                "classification_definition_path": DEFINITION_MEASUREMENT_CLASSIFICATION,
                "fitness_type_definition_path": DEFINITION_FITNESS_TYPE,
            },
            outputs={
                "classification_output_path": PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
                "fitness_type_output_path": PROCESSED_FITNESS_TYPE_PATH,
            },
        ),
        Step(
            "장병별 다음 회차 미달 확률 예측",
            predict_failure_probability.run,
            inputs={
                "input_path": PROCESSED_FITNESS_PATH,
                "model_path": FAILURE_MODEL_PATH,
                "definition_path": DEFINITION_SOLDIER_FAILURE_PROBABILITY,
            },
            outputs={"output_path": PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH},
        ),
    ]