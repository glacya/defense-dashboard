"""체력 유형 군집 분석의 세 단계가 함께 쓰는 설정과 특성 계산입니다.

- classify_measurements_by_percentile.py: 측정을 평균 백분위 등급별 CSV로 나눕니다.
- train_cluster_model.py: 등급별 CSV로 K-means 모델을 학습합니다(필요할 때만 직접 실행).
- assign_grade_and_cluster.py: 학습된 모델로 측정마다 군집을 정합니다.
학습과 적용이 같은 특성을 같은 순서로 써야 하므로 여기 한곳에 둡니다.
"""

from itertools import combinations
from pathlib import Path

import pandas as pd

GRADES = (1, 2, 3, 4)
MEASURE_NAMES = ("STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY")

ID_COLUMN = "MESURE_ID"
GRADE_COLUMN = "AVERAGE_PERCENTILE_GRADE"
CLUSTER_COLUMN = "CLUSTER"

GRADE_FILE_TEMPLATE = "grade_{grade}.csv"
MODEL_NAME_TEMPLATE = "k_means_grade_{grade}.joblib"


def percentile_column(name: str) -> str:
    """종목 이름의 백분위 컬럼 이름입니다(예: STRENGTH_PERCENTILE)."""
    return f"{name}_PERCENTILE"


def gap_column(a: str, b: str) -> str:
    """두 종목 백분위의 차이(a - b) 컬럼 이름입니다."""
    return f"{a}_MINUS_{b}"


def gap_feature_columns() -> list[str]:
    """종목 4개의 쌍 편차 6개 컬럼 이름입니다. 모델 입력 순서이기도 합니다."""
    return [gap_column(a, b) for a, b in combinations(MEASURE_NAMES, 2)]


def build_gap_features(df: pd.DataFrame) -> pd.DataFrame:
    """백분위로 쌍 편차 6개를 만들고, 하나라도 결측인 행은 제외합니다."""
    gaps = pd.DataFrame(
        {gap_column(a, b): df[percentile_column(a)] - df[percentile_column(b)]
         for a, b in combinations(MEASURE_NAMES, 2)},
        index=df.index,
    )
    return gaps.dropna()


def grade_file_path(grade_dir: Path, grade: int) -> Path:
    """등급별 CSV 경로입니다(grade_dir/grade_{grade}.csv)."""
    return Path(grade_dir) / GRADE_FILE_TEMPLATE.format(grade=grade)


def model_path(model_dir: Path, grade: int) -> Path:
    """등급별 K-means 모델 경로입니다(model_dir/k_means_grade_{grade}.joblib)."""
    return Path(model_dir) / MODEL_NAME_TEMPLATE.format(grade=grade)


def load_graded_csv(path: Path) -> pd.DataFrame:
    """등급별 CSV를 읽고 MESURE_ID와 종목 백분위 컬럼이 있는지 확인합니다.

    Raises:
        FileNotFoundError: 파일이 없을 때(classify_measurements_by_percentile.py를 먼저 실행해야 함)
        ValueError: 필요한 컬럼이 없을 때
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"등급별 CSV가 없습니다. classify_measurements_by_percentile.py를 먼저 실행하세요: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={ID_COLUMN: str})
    required = [ID_COLUMN, *(percentile_column(name) for name in MEASURE_NAMES)]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{path.name}에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    df[ID_COLUMN] = df[ID_COLUMN].str.strip()
    return df
