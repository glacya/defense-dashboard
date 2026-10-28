"""passed.csv에서 100분위를 계산하고 등급을 나눠 grade_1.csv ~ grade_4.csv로 저장합니다.

실행: python -m data.scripts.analysis.data_model.grade_split

[입력] INPUT_PATH (passed.csv): 개인별 측정치와 BMI·체지방률
[출력] OUTPUT_PATH_DIR/grade_1.csv ~ grade_4.csv
  - 원본 컬럼 + {종목}_PERCENTILE(4개), {신체}_PERCENTILE(2개), AVG_PERCENTILE, GRADE
  - cluster_model.py의 DIR_PATH를 OUTPUT_PATH_DIR과 같은 폴더로 맞춰 주세요.
  - 기준 종목 중 하나라도 결측인 장병은 등급을 매길 수 없어 제외합니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import PROCESSED_FITNESS_PATH
from data.scripts.utils import write_csv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 입출력 설정
# ---------------------------------------------------------------------------

INPUT_PATH = PROCESSED_FITNESS_PATH
OUTPUT_PATH_DIR = Path("data/scripts/analysis/data_model/graded")  # cluster_model.py의 DIR_PATH와 같아야 합니다.
GRADE_FILE_TEMPLATE = "grade_{grade}.csv"

# ---------------------------------------------------------------------------
# 설정 (percentile_grade와 동일하게 유지)
# ---------------------------------------------------------------------------

ID_COLUMN = "MESURE_ID"

# 체력 종목 -> 실제 측정 컬럼 (TODO: passed.csv의 컬럼 이름에 맞게 확인)
MEASURE_COLUMNS = {
    "STRENGTH": "STRENGTH",
    "ENDURANCE": "ENDURANCE",
    "CARDIO": "CARDIO",
    "FLEXIBILITY": "FLEXIBILITY",
}

# 낮을수록 양호한 신체 항목 -> 실제 측정 컬럼 (TODO: passed.csv의 컬럼 이름에 맞게 확인)
BODY_COLUMNS = {
    "BMI": "BMI",
    "BODY_FAT": "BODY_FAT_PERCENTAGE",
}

# 등급 기준: 키는 이름, 값은 (표시 이름, 평균을 낼 종목)
CRITERIA = {
    "2items": ("2종목(근력·심폐지구력)", ("STRENGTH", "CARDIO")),
    "3items": ("3종목(근력·근지구력·심폐지구력)", ("STRENGTH", "ENDURANCE", "CARDIO")),
    "4items": ("4종목(근력·근지구력·심폐지구력·유연성)", ("STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY")),
}
CRITERION_KEY = "4items"

# 평균 백분위 하한: 1등급 70 이상, 2등급 50 이상, 3등급 30 이상, 나머지 4등급
GRADE_SCORE_CUTS = (70.0, 50.0, 30.0)
GRADES = (1, 2, 3, 4)

AVERAGE_PERCENTILE_COLUMN = "AVG_PERCENTILE"
GRADE_COLUMN = "GRADE"


# ---------------------------------------------------------------------------
# 1. 데이터 로딩과 백분위
# ---------------------------------------------------------------------------

def percentile_column(name: str) -> str:
    return f"{name}_PERCENTILE"


def load_individuals(path: Path) -> pd.DataFrame:
    """passed.csv를 읽어 같은 M_CODE의 첫 행만 남기고 측정 컬럼을 숫자로 바꿉니다.

    Raises:
        ValueError: 필요한 컬럼이 없을 때
    """
    df = pd.read_csv(Path(path), encoding="utf-8-sig")  # utf-8-sig: 헤더 앞의 BOM 제거
    required = [ID_COLUMN, *MEASURE_COLUMNS.values(), *BODY_COLUMNS.values()]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{Path(path).name}에 필요한 컬럼이 없습니다: {', '.join(missing)}")

    df = df.drop_duplicates(subset=ID_COLUMN, keep="first").reset_index(drop=True)
    for column in (*MEASURE_COLUMNS.values(), *BODY_COLUMNS.values()):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """종목마다 100분위(클수록 양호)를, 신체 항목마다 100분위(작을수록 양호하므로 방향을 뒤집어)를 붙입니다."""
    percentiles = {
        percentile_column(name): df[column].rank(pct=True) * 100
        for name, column in MEASURE_COLUMNS.items()
    }
    percentiles.update({
        percentile_column(name): df[column].rank(ascending=False, pct=True) * 100
        for name, column in BODY_COLUMNS.items()
    })
    return df.assign(**percentiles)


# ---------------------------------------------------------------------------
# 2. 등급 나누기
# ---------------------------------------------------------------------------

def assign_grades(average: pd.Series) -> pd.Series:
    """평균 백분위로 1~4등급을 나눕니다. 평균이 없는 행은 비워 둡니다."""
    high, middle, low = GRADE_SCORE_CUTS
    return pd.cut(
        average,
        bins=[-float("inf"), low, middle, high, float("inf")],
        labels=[4, 3, 2, 1],
        right=False,
    ).astype("Int64")


def grade_by_criterion(df: pd.DataFrame, exercises: tuple[str, ...]) -> pd.DataFrame:
    """기준 종목들의 평균 백분위와 등급을 붙입니다. 기준 종목 중 하나라도 결측이면 제외합니다."""
    columns = [percentile_column(exercise) for exercise in exercises]
    average = df[columns].mean(axis=1, skipna=False)
    graded = df.assign(**{AVERAGE_PERCENTILE_COLUMN: average.round(2)})
    graded = graded[average.notna()].copy()
    graded[GRADE_COLUMN] = assign_grades(average[average.notna()])
    return graded.reset_index(drop=True)


def split_by_grade(df: pd.DataFrame, criterion_key: str) -> dict[int, pd.DataFrame]:
    """기준 종목의 평균 백분위로 등급을 매기고, 등급별 데이터프레임을 돌려줍니다."""
    if criterion_key not in CRITERIA:
        raise ValueError(f"알 수 없는 기준: {criterion_key}")

    _, exercises = CRITERIA[criterion_key]
    graded = grade_by_criterion(df, exercises)
    return {
        grade: graded[graded[GRADE_COLUMN].eq(grade)].reset_index(drop=True)
        for grade in GRADES
    }


# ---------------------------------------------------------------------------
# 3. 실행
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging(caller_name(__file__))

    df = add_percentiles(load_individuals(INPUT_PATH))
    logger.info("입력 %s명 로드", f"{len(df):,}")

    parts = split_by_grade(df, CRITERION_KEY)
    OUTPUT_PATH_DIR.mkdir(parents=True, exist_ok=True)

    for grade, part in parts.items():
        path = OUTPUT_PATH_DIR / GRADE_FILE_TEMPLATE.format(grade=grade)
        write_csv(part, path)  # cluster_model.py가 CSV를 읽으므로 write_csv를 씁니다.
        logger.info("%d등급: %s명 -> %s", grade, f"{len(part):,}", display_path(path))


if __name__ == "__main__":
    main()