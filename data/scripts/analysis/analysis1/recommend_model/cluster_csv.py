"""INPUT_PATH(passed.csv)에 등급·유형 속성을 붙여 CSV로 저장하고, 유형명 대응표는 JSON으로 저장합니다.

실행: python -m data.scripts.analysis.data_model.cluster_type_table

[흐름]
  1. DIR_PATH의 grade_1.csv ~ grade_4.csv 각각을 같은 번호의 K-means 모델에 넣어
     MESURE_ID별 등급·유형 조회표를 만듭니다. (편차는 모델 입력으로만 쓰고 출력에는 넣지 않습니다.)
  2. INPUT_PATH의 각 행을 MESURE_ID로 조회해 GRADE, CLUSTER, 유형명을 붙입니다.
  3. OUTPUT_DIR/SOLDIER_TYPE으로 저장합니다(STORAGE_BACKEND에 따라 CSV 또는 DB).
  4. 등급별 군집 번호와 유형명의 대응표를 OUTPUT_DIR/TYPE_NAME_TABLE.json으로 저장합니다.

[출력]
  SOLDIER_TYPE          : 원본 컬럼 + GRADE, CLUSTER, 유형명 (조회표에 없는 행은 비어 있음)
  TYPE_NAME_TABLE.json  : [{"GRADE": 1, "CLUSTER": 0, "유형명": "..."}, ...]
"""

import json
import logging
from itertools import combinations
from pathlib import Path

import joblib
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import PROCESSED_FITNESS_PATH
from data.scripts.storage import save_table

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 입출력 설정
# ---------------------------------------------------------------------------

INPUT_PATH = PROCESSED_FITNESS_PATH
DIR_PATH = Path("data/scripts/analysis/data_model/graded")  # grade_1.csv ~ grade_4.csv 폴더 (TODO: paths.py 상수로 교체)
MODEL_DIR = Path("data/scripts/analysis/data_model/cluster_models")  # k_means_grade_n.joblib 폴더 (TODO: paths.py 상수로 교체)
OUTPUT_DIR = Path("data/scripts/analysis/data_model/final")  # TODO: paths.py 상수로 교체
OUTPUT_NAME = "SOLDIER_TYPE"
TYPE_NAME_JSON_NAME = "TYPE_NAME_TABLE.json"

GRADE_FILE_PATTERN = "grade_*.csv"
MODEL_NAME_TEMPLATE = "k_means_grade_{grade}.joblib"
GRADES = (1, 2, 3, 4)

# ---------------------------------------------------------------------------
# 설정 (cluster_model.py와 같아야 합니다)
# ---------------------------------------------------------------------------

ID_COLUMN = "MESURE_ID"
GRADE_COLUMN = "GRADE"
CLUSTER_COLUMN = "CLUSTER"
TYPE_NAME_COLUMN = "유형명"
MEASURE_NAMES = ("STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY")
ATTRIBUTE_COLUMNS = [GRADE_COLUMN, CLUSTER_COLUMN, TYPE_NAME_COLUMN]


# ---------------------------------------------------------------------------
# 1. 편차 (모델 입력용, 출력에는 넣지 않음)
# ---------------------------------------------------------------------------

def percentile_column(name: str) -> str:
    return f"{name}_PERCENTILE"


def gap_column(a: str, b: str) -> str:
    return f"{a}_MINUS_{b}"


def build_gap_features(df: pd.DataFrame) -> pd.DataFrame:
    """백분위로 쌍 편차 6개를 만들고, 하나라도 결측인 행은 제외합니다."""
    gaps = pd.DataFrame(
        {gap_column(a, b): df[percentile_column(a)] - df[percentile_column(b)]
         for a, b in combinations(MEASURE_NAMES, 2)},
        index=df.index,
    )
    return gaps.dropna()


# ---------------------------------------------------------------------------
# 2. 등급별 CSV와 모델 불러오기
# ---------------------------------------------------------------------------

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


def load_graded_csv(path: Path) -> pd.DataFrame:
    """등급별 CSV를 읽고 ID와 백분위 컬럼이 있는지 확인합니다.

    Raises:
        ValueError: ID 또는 백분위 컬럼이 없을 때
    """
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={ID_COLUMN: str})
    required = [ID_COLUMN, *(percentile_column(n) for n in MEASURE_NAMES)]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    df[ID_COLUMN] = df[ID_COLUMN].str.strip()
    return df


def model_path(grade: int) -> Path:
    return MODEL_DIR / MODEL_NAME_TEMPLATE.format(grade=grade)


def load_bundles() -> dict[int, dict]:
    """등급별 모델 번들을 모두 불러옵니다.

    Raises:
        FileNotFoundError: 모델 파일이 하나라도 없을 때
    """
    bundles = {}
    for grade in GRADES:
        path = model_path(grade)
        if not path.exists():
            raise FileNotFoundError(f"모델 파일이 없습니다. cluster_model.py를 먼저 실행하세요: {path}")
        bundles[grade] = joblib.load(path)
    return bundles


# ---------------------------------------------------------------------------
# 3. 등급별 데이터에 등급·유형 속성 붙이기
# ---------------------------------------------------------------------------

def build_attributes(df: pd.DataFrame, grade: int, bundle: dict) -> pd.DataFrame:
    """등급별 데이터의 MESURE_ID와 속성(GRADE, CLUSTER, 유형명)을 돌려줍니다."""
    attrs = pd.DataFrame({GRADE_COLUMN: grade}, index=df.index)

    features = build_gap_features(df)
    if not features.empty:
        labels = bundle["kmeans"].predict(features[bundle["feature_columns"]])
        names = bundle["type_names"]
        typed = pd.DataFrame(
            {
                CLUSTER_COLUMN: labels,
                TYPE_NAME_COLUMN: [names[int(label)] for label in labels],
            },
            index=features.index,
        )
        attrs = attrs.join(typed)

    return df[[ID_COLUMN]].join(attrs)


def build_lookup(bundles: dict[int, dict]) -> pd.DataFrame:
    """등급 CSV 4개를 각 모델로 처리해, MESURE_ID별 속성 조회표 하나로 합칩니다.

    Raises:
        ValueError: 같은 MESURE_ID가 여러 등급 데이터에 있을 때
    """
    csv_paths = grade_file_paths(DIR_PATH)
    pieces = []

    for grade in GRADES:
        df = load_graded_csv(csv_paths[grade])
        pieces.append(build_attributes(df, grade, bundles[grade]))
        logger.info("%d등급 (%s): %s명 처리", grade, csv_paths[grade].name, f"{len(df):,}")

    lookup = pd.concat(pieces, ignore_index=True)
    duplicated = lookup[ID_COLUMN].duplicated(keep=False)
    if duplicated.any():
        raise ValueError(f"{ID_COLUMN}이 여러 행에 중복된 데이터가 {int(duplicated.sum()):,}행 있습니다.")

    lookup[GRADE_COLUMN] = lookup[GRADE_COLUMN].astype(int)
    lookup[CLUSTER_COLUMN] = lookup[CLUSTER_COLUMN].astype("Int64")
    return lookup


# ---------------------------------------------------------------------------
# 4. 유형명 대응표 (JSON)
# ---------------------------------------------------------------------------

def build_type_name_records(bundles: dict[int, dict]) -> list[dict]:
    """등급별 군집 번호와 유형명의 대응표를 레코드 목록으로 만듭니다."""
    records = []
    for grade in GRADES:
        for cluster in sorted(bundles[grade]["type_names"]):
            records.append({
                GRADE_COLUMN: grade,
                CLUSTER_COLUMN: int(cluster),
                TYPE_NAME_COLUMN: bundles[grade]["type_names"][cluster],
            })
    return records


def save_json(records: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 5. INPUT_PATH에 속성 붙이기
# ---------------------------------------------------------------------------

def attach_to_input(raw: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    """INPUT_PATH의 각 행에 MESURE_ID가 같은 조회표 속성을 붙입니다. 원본 행 순서와 컬럼은 유지됩니다."""
    base = raw.drop(columns=[c for c in ATTRIBUTE_COLUMNS if c in raw.columns])
    return base.merge(lookup[[ID_COLUMN, *ATTRIBUTE_COLUMNS]], on=ID_COLUMN, how="left")


# ---------------------------------------------------------------------------
# 6. 실행
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging(caller_name(__file__))

    bundles = load_bundles()
    lookup = build_lookup(bundles)
    logger.info("등급·유형 조회표 %s행 생성", f"{len(lookup):,}")

    raw = pd.read_csv(INPUT_PATH, encoding="utf-8-sig", dtype={ID_COLUMN: str})
    raw[ID_COLUMN] = raw[ID_COLUMN].str.strip()

    table = attach_to_input(raw, lookup)
    table[GRADE_COLUMN] = table[GRADE_COLUMN].astype("Int64")
    table[CLUSTER_COLUMN] = table[CLUSTER_COLUMN].astype("Int64")
    save_table(table, OUTPUT_NAME, OUTPUT_DIR)

    type_name_path = OUTPUT_DIR / TYPE_NAME_JSON_NAME
    save_json(build_type_name_records(bundles), type_name_path)

    matched = int(table[GRADE_COLUMN].notna().sum())
    logger.info("입력 %s행 중 등급 매칭 %s행, 미매칭 %s행", f"{len(table):,}", f"{matched:,}", f"{len(table) - matched:,}")
    logger.info("유형명 JSON 저장: %s", display_path(type_name_path))
    logger.info("저장 위치: %s", display_path(OUTPUT_DIR))


if __name__ == "__main__":
    main()