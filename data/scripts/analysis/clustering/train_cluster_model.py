"""등급별 측정 데이터로 종목 간 백분위 편차 K-means 군집 모델(k=4)을 등급마다 학습해 저장합니다.

모델은 Git에 넣어 두고 파이프라인은 그 모델을 그대로 씁니다(매번 학습하지 않음, 사용자 결정).
그래서 이 스크립트는 파이프라인에 넣지 않고, 모델을 다시 학습할 때만 직접 실행합니다.
다시 학습하면 군집 번호와 유형명이 바뀔 수 있으므로 assign_grade_and_cluster.py도 다시 실행해야 합니다.

[입력] intermediate/clustering/grade_1.csv ~ grade_4.csv (classify_measurements_by_percentile.py의 출력)
[출력] CLUSTER_MODEL_DIR/k_means_grade_1.joblib ~ k_means_grade_4.joblib
       각 파일은 모델 번들 dict: kmeans, feature_columns, k, type_names,
       centroids, centroid_relative, cluster_sizes

실행: python -m data.scripts.analysis.clustering.train_cluster_model
"""

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from data.scripts.analysis.clustering.cluster_features import (
    GRADES,
    MEASURE_NAMES,
    build_gap_features,
    gap_column,
    gap_feature_columns,
    grade_file_path,
    load_graded_csv,
    model_path,
)
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import CLUSTER_MODEL_DIR, INTERMEDIATE_CLUSTERING

logger = logging.getLogger(__name__)

EXERCISE_LABELS = {"STRENGTH": "근력", "ENDURANCE": "근지구력", "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성"}

K = 4
KMEANS_N_INIT = 10
RANDOM_STATE = 42
BALANCE_SPREAD = 5.0  # 상대 프로필의 최대-최소 차이가 이보다 작으면 '균형형'


def gap_value(gaps: pd.DataFrame, a: str, b: str) -> pd.Series:
    """a - b 편차입니다. 저장된 방향이 반대면 부호를 뒤집어 씁니다."""
    key = gap_column(a, b)
    return gaps[key] if key in gaps.columns else -gaps[gap_column(b, a)]


def relative_profile(gaps: pd.DataFrame) -> pd.DataFrame:
    """종목별 상대 프로필 = 나머지 종목과의 편차 평균. 0보다 크면 상대적 강점, 작으면 상대적 약점입니다."""
    out = {}
    for exercise in MEASURE_NAMES:
        diffs = [gap_value(gaps, exercise, other) for other in MEASURE_NAMES if other != exercise]
        out[f"{exercise}_RELATIVE"] = sum(diffs) / len(diffs)
    return pd.DataFrame(out, index=gaps.index)


def type_name(relative: pd.Series) -> str:
    """상대 프로필로 유형의 설명 이름을 만듭니다."""
    values = {exercise: float(relative[f"{exercise}_RELATIVE"]) for exercise in MEASURE_NAMES}
    if max(values.values()) - min(values.values()) < BALANCE_SPREAD:
        return "균형형"
    strong = max(values, key=values.get)
    weak = min(values, key=values.get)
    return f"{EXERCISE_LABELS[strong]} 강점·{EXERCISE_LABELS[weak]} 약점형"


def train_cluster_model(df: pd.DataFrame) -> dict:
    """편차 6개로 K-means(k=4)를 학습하고 모델 번들을 반환합니다.

    Raises:
        ValueError: 학습에 쓸 인원이 k보다 적을 때
    """
    features = build_gap_features(df)
    if len(features) < K:
        raise ValueError(f"학습 인원({len(features)}명)이 군집 수 k={K}보다 적습니다.")

    feature_columns = gap_feature_columns()
    kmeans = KMeans(n_clusters=K, n_init=KMEANS_N_INIT, random_state=RANDOM_STATE).fit(features[feature_columns])

    centroids = pd.DataFrame(kmeans.cluster_centers_, columns=feature_columns)
    centroid_relative = relative_profile(centroids)
    type_names = {
        int(cluster): f"유형{cluster}: {type_name(row)}"
        for cluster, row in centroid_relative.iterrows()
    }
    return {
        "kmeans": kmeans,
        "feature_columns": feature_columns,
        "k": K,
        "type_names": type_names,
        "centroids": centroids.round(2),
        "centroid_relative": centroid_relative.round(2),
        "cluster_sizes": np.bincount(kmeans.labels_, minlength=K),
    }


def run(grade_dir: Path, model_dir: Path) -> None:
    """등급별 CSV마다 모델을 학습해 model_dir에 저장합니다."""
    for grade in GRADES:
        csv_path = grade_file_path(grade_dir, grade)
        bundle = train_cluster_model(load_graded_csv(csv_path))
        saved = model_path(model_dir, grade)
        saved.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, saved)

        sizes = bundle["cluster_sizes"]
        logger.info("%d등급 (%s): 학습 인원 %s명, k=%d", grade, csv_path.name, f"{int(sizes.sum()):,}", bundle["k"])
        for cluster, name in bundle["type_names"].items():
            logger.info("  %s: %s명", name, f"{int(sizes[cluster]):,}")
        logger.info("  모델 저장: %s", display_path(saved))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 모델을 다시 학습합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_CLUSTERING, CLUSTER_MODEL_DIR)


if __name__ == "__main__":
    main()
