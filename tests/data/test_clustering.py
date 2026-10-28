"""체력 유형 군집 분석(data/scripts/analysis/clustering)을 테스트합니다.

실제 모델 파일 대신 작은 가상 측정으로 모델을 학습해 등급 나누기 -> 학습 -> 적용 흐름을 확인합니다.
"""

import numpy as np
import pandas as pd
import pytest

from data.scripts.analysis.clustering.assign_grade_and_cluster import run as assign_run
from data.scripts.analysis.clustering.classify_measurements_by_percentile import assign_grades, split_by_grade
from data.scripts.analysis.clustering.classify_measurements_by_percentile import add_percentiles
from data.scripts.analysis.clustering.classify_measurements_by_percentile import run as classify_run
from data.scripts.analysis.clustering.train_cluster_model import run as train_run
from data.scripts.paths import DEFINITION_FITNESS_TYPE, DEFINITION_MEASUREMENT_CLASSIFICATION
from data.scripts.utils import load_definition_columns, read_text_csv


def make_measurements(count: int = 400, seed: int = 0) -> pd.DataFrame:
    """종목 값이 고르게 퍼진 가상 측정 데이터를 만듭니다."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "MESURE_ID": np.arange(1, count + 1),
        "STRENGTH": rng.normal(55, 8, count).round(1),
        "ENDURANCE": rng.integers(20, 70, count),
        "CARDIO": rng.normal(45, 5, count).round(1),
        "FLEXIBILITY": rng.normal(10, 6, count).round(1),
        "BMI": rng.normal(23, 3, count).round(2),
        "BODY_FAT_PERCENTAGE": rng.normal(18, 5, count).round(1),
    })


def test_grade_cuts_follow_average_percentile_lower_bounds():
    """평균 백분위 70·50·30 이상이 각각 1·2·3등급, 그 미만은 4등급이고 결측은 비어 있는지 확인합니다."""
    grades = assign_grades(pd.Series([70.0, 69.99, 50.0, 30.0, 29.99, np.nan]))

    assert grades.tolist()[:5] == [1, 2, 2, 3, 4]
    assert pd.isna(grades.iloc[5])


def test_body_percentile_is_reversed_and_missing_measurements_are_excluded():
    """신체 항목은 작을수록 높은 백분위를 받고, 종목이 비어 있는 측정은 등급에서 빠지는지 확인합니다."""
    df = make_measurements(10)
    df.loc[0, "CARDIO"] = np.nan

    percentiles = add_percentiles(df)
    parts = split_by_grade(percentiles)

    lowest_bmi = percentiles["BMI"].idxmin()
    assert percentiles.loc[lowest_bmi, "BMI_PERCENTILE"] == 100
    assert sum(len(part) for part in parts.values()) == 9
    assert all(part["AVERAGE_PERCENTILE_GRADE"].eq(grade).all() for grade, part in parts.items())


def test_classify_train_and_assign_write_tables_by_definition(tmp_path):
    """등급별 CSV -> 모델 학습 -> 측정별 등급·군집 표와 유형명 표 저장이 정의서대로 이어지는지 확인합니다."""
    input_path = tmp_path / "measurements.csv"
    make_measurements().to_csv(input_path, index=False, encoding="utf-8-sig")
    grade_dir, model_dir = tmp_path / "grades", tmp_path / "models"
    classification_path, fitness_type_path = tmp_path / "classification.csv", tmp_path / "fitness_type.csv"

    classify_run(input_path, grade_dir)
    train_run(grade_dir, model_dir)
    assign_run(
        grade_dir, model_dir,
        DEFINITION_MEASUREMENT_CLASSIFICATION, DEFINITION_FITNESS_TYPE,
        classification_path, fitness_type_path,
    )

    classifications = read_text_csv(classification_path)
    fitness_types = read_text_csv(fitness_type_path)
    assert classifications.columns.tolist() == load_definition_columns(DEFINITION_MEASUREMENT_CLASSIFICATION)
    assert fitness_types.columns.tolist() == load_definition_columns(DEFINITION_FITNESS_TYPE)
    # 측정마다 한 행, MESURE_ID 순
    assert classifications["MESURE_ID"].astype(int).tolist() == list(range(1, 401))
    # 등급 4개 × 군집 4개, 모든 분류가 유형명 표에 있다(복합 FK).
    assert len(fitness_types) == 16
    keys = ["AVERAGE_PERCENTILE_GRADE", "CLUSTER"]
    assert classifications[keys].merge(fitness_types[keys], how="left", indicator=True)["_merge"].eq("both").all()


def test_assign_requires_trained_models(tmp_path):
    """모델 파일이 없으면 학습 스크립트를 먼저 실행하라고 알려 주는지 확인합니다."""
    input_path = tmp_path / "measurements.csv"
    make_measurements(40).to_csv(input_path, index=False, encoding="utf-8-sig")
    classify_run(input_path, tmp_path / "grades")

    with pytest.raises(FileNotFoundError, match="train_cluster_model.py"):
        assign_run(
            tmp_path / "grades", tmp_path / "no_models",
            DEFINITION_MEASUREMENT_CLASSIFICATION, DEFINITION_FITNESS_TYPE,
            tmp_path / "classification.csv", tmp_path / "fitness_type.csv",
        )
