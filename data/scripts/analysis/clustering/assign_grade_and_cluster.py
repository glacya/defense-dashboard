"""학습된 K-means 모델로 측정마다 평균 백분위 등급과 군집을 정하고, 등급·군집별 유형명 표를 저장합니다.

모델은 Git에 넣어 둔 것을 그대로 씁니다(학습은 train_cluster_model.py).
측정 데이터(KS_NFA_PROCESSED)에는 컬럼을 붙이지 않고, MESURE_ID로 연결되는 별도 테이블을 만듭니다.

[입력] intermediate/clustering/grade_1.csv ~ grade_4.csv, CLUSTER_MODEL_DIR/k_means_grade_{등급}.joblib
[출력]
  processed/MEASUREMENT_CLASSIFICATION.csv : MESURE_ID, AVERAGE_PERCENTILE_GRADE, CLUSTER (측정마다 한 행)
  processed/FITNESS_TYPE.csv               : AVERAGE_PERCENTILE_GRADE, CLUSTER, TYPE_NAME (등급·군집마다 한 행)

실행: python -m data.scripts.analysis.clustering.assign_grade_and_cluster
"""

import logging
from pathlib import Path

import joblib
import pandas as pd

from data.scripts.analysis.clustering.cluster_features import (
    CLUSTER_COLUMN,
    GRADE_COLUMN,
    GRADES,
    ID_COLUMN,
    build_gap_features,
    grade_file_path,
    load_graded_csv,
    model_path,
)
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    CLUSTER_MODEL_DIR,
    DEFINITION_FITNESS_TYPE,
    DEFINITION_MEASUREMENT_CLASSIFICATION,
    INTERMEDIATE_CLUSTERING,
    PROCESSED_FITNESS_TYPE_PATH,
    PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
)
from data.scripts.utils import write_by_definition

logger = logging.getLogger(__name__)

TYPE_NAME_COLUMN = "TYPE_NAME"


def load_bundles(model_dir: Path) -> dict[int, dict]:
    """등급별 모델 번들을 모두 불러옵니다.

    Raises:
        FileNotFoundError: 모델 파일이 하나라도 없을 때
    """
    bundles = {}
    for grade in GRADES:
        path = model_path(model_dir, grade)
        if not path.exists():
            raise FileNotFoundError(f"모델 파일이 없습니다. train_cluster_model.py를 먼저 실행하세요: {path}")
        bundles[grade] = joblib.load(path)
    return bundles


def classify_grade(df: pd.DataFrame, grade: int, bundle: dict) -> pd.DataFrame:
    """한 등급의 측정에 군집 번호를 붙여 MESURE_ID, 등급, 군집을 돌려줍니다.

    종목 백분위가 하나라도 없어 편차를 만들 수 없는 측정은 군집이 비어 있습니다.
    """
    classified = pd.DataFrame({ID_COLUMN: df[ID_COLUMN], GRADE_COLUMN: grade}, index=df.index)
    features = build_gap_features(df)
    if not features.empty:
        labels = bundle["kmeans"].predict(features[bundle["feature_columns"]])
        classified = classified.join(pd.DataFrame({CLUSTER_COLUMN: labels}, index=features.index))
    else:
        classified[CLUSTER_COLUMN] = pd.NA
    return classified


def build_classifications(grade_dir: Path, bundles: dict[int, dict]) -> pd.DataFrame:
    """등급별 CSV 4개를 각 모델로 처리해 측정별 등급·군집 표 하나로 합칩니다(MESURE_ID 순).

    Raises:
        ValueError: 같은 MESURE_ID가 여러 등급 데이터에 있을 때
    """
    pieces = []
    for grade in GRADES:
        csv_path = grade_file_path(grade_dir, grade)
        df = load_graded_csv(csv_path)
        pieces.append(classify_grade(df, grade, bundles[grade]))
        logger.info("%d등급 (%s): 측정 %s건", grade, csv_path.name, f"{len(df):,}")

    classifications = pd.concat(pieces, ignore_index=True)
    duplicated = classifications[ID_COLUMN].duplicated(keep=False)
    if duplicated.any():
        raise ValueError(f"{ID_COLUMN}이 여러 등급에 중복된 측정이 {int(duplicated.sum()):,}행 있습니다.")

    classifications[ID_COLUMN] = classifications[ID_COLUMN].astype(int)
    classifications[GRADE_COLUMN] = classifications[GRADE_COLUMN].astype(int)
    classifications[CLUSTER_COLUMN] = classifications[CLUSTER_COLUMN].astype("Int64")
    return classifications.sort_values(ID_COLUMN, kind="stable").reset_index(drop=True)


def build_fitness_types(bundles: dict[int, dict]) -> pd.DataFrame:
    """등급별 군집 번호와 유형명의 대응표를 만듭니다. 등급·군집마다 한 행입니다."""
    return pd.DataFrame([
        {
            GRADE_COLUMN: grade,
            CLUSTER_COLUMN: int(cluster),
            TYPE_NAME_COLUMN: bundles[grade]["type_names"][cluster],
        }
        for grade in GRADES
        for cluster in sorted(bundles[grade]["type_names"])
    ])


def run(
    grade_dir: Path,
    model_dir: Path,
    classification_definition_path: Path,
    fitness_type_definition_path: Path,
    classification_output_path: Path,
    fitness_type_output_path: Path,
) -> None:
    """측정별 등급·군집 표와 유형명 표를 정의서대로 저장합니다.

    군집을 정할 수 없는 측정(종목 백분위 결측)은 정의서상 비울 수 없으므로 빼고 경고로 남깁니다.
    """
    bundles = load_bundles(model_dir)
    classifications = build_classifications(grade_dir, bundles)
    unclustered = classifications[CLUSTER_COLUMN].isna()
    if unclustered.any():
        logger.warning("군집을 정할 수 없어 뺀 측정: %s건(종목 백분위 결측)", f"{int(unclustered.sum()):,}")
        classifications = classifications[~unclustered]

    write_by_definition(classifications, classification_definition_path, classification_output_path)
    fitness_types = write_by_definition(build_fitness_types(bundles), fitness_type_definition_path, fitness_type_output_path)

    logger.info("측정별 등급·군집 %s건 저장: %s", f"{len(classifications):,}", display_path(classification_output_path))
    logger.info("유형명 %s개 저장: %s", f"{len(fitness_types):,}", display_path(fitness_type_output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(
        INTERMEDIATE_CLUSTERING,
        CLUSTER_MODEL_DIR,
        DEFINITION_MEASUREMENT_CLASSIFICATION,
        DEFINITION_FITNESS_TYPE,
        PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
        PROCESSED_FITNESS_TYPE_PATH,
    )


if __name__ == "__main__":
    main()
