"""등급별 데이터로 종목 간 백분위 편차 K-means 군집 모델(k=4)을 등급마다 학습합니다.

실행: python -m data.scripts.analysis.data_model.cluster_model

[입력] DIR_PATH 폴더의 grade_1.csv ~ grade_4.csv (등급 기준 분류와 이상치 처리가 끝난 데이터)
       각 파일에는 {종목}_PERCENTILE 컬럼이 있어야 합니다.
[출력] OUTPUT_DIR_PATH 폴더의 k_means_grade_1.joblib ~ k_means_grade_4.joblib
       각 파일은 모델 번들 dict: kmeans, feature_columns, k, type_names,
       centroids, centroid_relative, cluster_sizes
"""

import logging
from itertools import combinations
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from data.scripts.logging_setup import caller_name, display_path, setup_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 입출력 설정
# ---------------------------------------------------------------------------

DIR_PATH = Path("data/scripts/analysis/data_model/graded")  # TODO: paths.py 상수로 교체
OUTPUT_DIR_PATH = Path("data/scripts/analysis/data_model/cluster_models")  # TODO: paths.py 상수로 교체

GRADE_FILE_PATTERN = "grade_*.csv"
GRADES = (1, 2, 3, 4)
MODEL_NAME_TEMPLATE = "k_means_grade_{grade}.joblib"

# ---------------------------------------------------------------------------
# 설정 (확정된 파라미터)
# ---------------------------------------------------------------------------

MEASURE_NAMES = ("STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY")
EXERCISE_LABELS = {"STRENGTH": "근력", "ENDURANCE": "근지구력", "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성"}

K = 4
KMEANS_N_INIT = 10
RANDOM_STATE = 42
BALANCE_SPREAD = 5.0  # 상대 프로필의 최대-최소 차이가 이보다 작으면 '균형형'


# ---------------------------------------------------------------------------
# 1. 데이터 로딩
# ---------------------------------------------------------------------------

def percentile_column(name: str) -> str:
    return f"{name}_PERCENTILE"


def load_graded_csv(path: Path) -> pd.DataFrame:
    """등급별 CSV를 읽고 백분위 컬럼이 있는지 확인합니다.

    Raises:
        ValueError: 백분위 컬럼이 없을 때
    """
    df = pd.read_csv(path, encoding="utf-8-sig")  # utf-8-sig: 헤더 앞의 BOM 제거
    missing = [percentile_column(n) for n in MEASURE_NAMES if percentile_column(n) not in df.columns]
    if missing:
        raise ValueError(f"{path.name}에 백분위 컬럼이 없습니다: {', '.join(missing)}")
    return df


def grade_file_paths(dir_path: Path) -> dict[int, Path]:
    """DIR_PATH에서 grade_1.csv ~ grade_4.csv를 찾아 등급 번호별로 돌려줍니다.

    Raises:
        FileNotFoundError: 등급 파일 중 하나라도 없을 때
    """
    found = {}
    for path in Path(dir_path).glob(GRADE_FILE_PATTERN):
        suffix = path.stem.rsplit("_", 1)[-1]
        if suffix.isdigit() and int(suffix) in GRADES:
            found[int(suffix)] = path

    missing = [g for g in GRADES if g not in found]
    if missing:
        raise FileNotFoundError(f"{dir_path}에 등급 파일이 없습니다: {', '.join(f'grade_{g}.csv' for g in missing)}")
    return {g: found[g] for g in GRADES}


# ---------------------------------------------------------------------------
# 2. 편차 특성
# ---------------------------------------------------------------------------

def gap_column(a: str, b: str) -> str:
    return f"{a}_MINUS_{b}"


def gap_feature_columns() -> list[str]:
    """종목 4개의 쌍 편차 6개 컬럼 이름입니다."""
    return [gap_column(a, b) for a, b in combinations(MEASURE_NAMES, 2)]


def build_gap_features(df: pd.DataFrame) -> pd.DataFrame:
    """백분위로 쌍 편차 6개를 만들고, 하나라도 결측인 행은 제외합니다."""
    gaps = pd.DataFrame(
        {gap_column(a, b): df[percentile_column(a)] - df[percentile_column(b)]
         for a, b in combinations(MEASURE_NAMES, 2)},
        index=df.index,
    )
    return gaps.dropna()


def gap_value(gaps: pd.DataFrame, a: str, b: str) -> pd.Series:
    """a - b 편차입니다. 저장된 방향이 반대면 부호를 뒤집어 씁니다."""
    key = gap_column(a, b)
    return gaps[key] if key in gaps.columns else -gaps[gap_column(b, a)]


def relative_profile(gaps: pd.DataFrame) -> pd.DataFrame:
    """종목별 상대 프로필 = 나머지 종목과의 편차 평균. 0보다 크면 상대적 강점, 작으면 상대적 약점입니다."""
    out = {}
    for e in MEASURE_NAMES:
        diffs = [gap_value(gaps, e, o) for o in MEASURE_NAMES if o != e]
        out[f"{e}_RELATIVE"] = sum(diffs) / len(diffs)
    return pd.DataFrame(out, index=gaps.index)


def type_name(relative: pd.Series) -> str:
    """상대 프로필로 유형의 설명 이름을 만듭니다."""
    values = {e: float(relative[f"{e}_RELATIVE"]) for e in MEASURE_NAMES}
    if max(values.values()) - min(values.values()) < BALANCE_SPREAD:
        return "균형형"
    strong = max(values, key=values.get)
    weak = min(values, key=values.get)
    return f"{EXERCISE_LABELS[strong]} 강점·{EXERCISE_LABELS[weak]} 약점형"


# ---------------------------------------------------------------------------
# 3. 학습
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. 저장과 불러오기
# ---------------------------------------------------------------------------

def save_model(bundle: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)




def model_path(grade: int, output_dir: Path = OUTPUT_DIR_PATH) -> Path:
    return Path(output_dir) / MODEL_NAME_TEMPLATE.format(grade=grade)


# ---------------------------------------------------------------------------
# 5. 실행: 등급별 파일마다 모델을 학습해 저장
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging(caller_name(__file__))
    paths = grade_file_paths(DIR_PATH)

    for grade, csv_path in paths.items():
        df = load_graded_csv(csv_path)
        bundle = train_cluster_model(df)
        saved = model_path(grade)
        save_model(bundle, saved)

        sizes = bundle["cluster_sizes"]
        logger.info("%d등급 (%s): 학습 인원 %s명, k=%d", grade, csv_path.name, f"{int(sizes.sum()):,}", bundle["k"])
        for cluster, name in bundle["type_names"].items():
            logger.info("  %s: %s명", name, f"{int(sizes[cluster]):,}")
        logger.info("  모델 저장: %s", display_path(saved))


if __name__ == "__main__":
    main()