"""최종 측정 데이터에서 종목별 100분위를 계산하고, 평균 백분위로 1~4등급을 나눠 등급별 CSV로 저장합니다.

측정마다(장병마다가 아니라) 등급을 매깁니다. 백분위는 전체 측정 안에서 구합니다.
기준 종목 중 하나라도 결측인 측정은 등급을 매길 수 없어 제외합니다.

[입력] 최종 측정 데이터 (processed/KS_NFA_PROCESSED.csv)
[출력] intermediate/clustering/grade_1.csv ~ grade_4.csv (중간 데이터, Git 제외)
  - 원본 컬럼 + {종목}_PERCENTILE(4개), {신체}_PERCENTILE(2개), AVG_PERCENTILE, AVERAGE_PERCENTILE_GRADE
  - train_cluster_model.py와 assign_grade_and_cluster.py가 이 파일을 읽습니다.

실행: python -m data.scripts.analysis.clustering.classify_measurements_by_percentile
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.analysis.clustering.cluster_features import (
    GRADE_COLUMN,
    GRADES,
    ID_COLUMN,
    grade_file_path,
    percentile_column,
)
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_CLUSTERING, PROCESSED_FITNESS_PATH
from data.scripts.utils import require_columns, write_csv

logger = logging.getLogger(__name__)

# 체력 종목 -> 측정 컬럼 (클수록 양호)
MEASURE_COLUMNS = {
    "STRENGTH": "STRENGTH",
    "ENDURANCE": "ENDURANCE",
    "CARDIO": "CARDIO",
    "FLEXIBILITY": "FLEXIBILITY",
}

# 신체 항목 -> 측정 컬럼 (작을수록 양호하므로 백분위 방향을 뒤집는다)
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

AVERAGE_PERCENTILE_COLUMN = "AVG_PERCENTILE"


def load_measurements(path: Path) -> pd.DataFrame:
    """측정 데이터를 읽어 측정 컬럼을 숫자로 바꿉니다. 같은 MESURE_ID가 여러 번 있으면 첫 행만 남깁니다."""
    df = pd.read_csv(Path(path), encoding="utf-8-sig")  # utf-8-sig: 헤더 앞의 BOM 제거
    require_columns(df, [ID_COLUMN, *MEASURE_COLUMNS.values(), *BODY_COLUMNS.values()], Path(path).name)

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


def split_by_grade(df: pd.DataFrame, criterion_key: str = CRITERION_KEY) -> dict[int, pd.DataFrame]:
    """기준 종목의 평균 백분위로 등급을 매기고, 등급별 데이터프레임을 돌려줍니다.

    Raises:
        ValueError: 알 수 없는 기준 이름일 때
    """
    if criterion_key not in CRITERIA:
        raise ValueError(f"알 수 없는 기준: {criterion_key}")

    _, exercises = CRITERIA[criterion_key]
    graded = grade_by_criterion(df, exercises)
    return {
        grade: graded[graded[GRADE_COLUMN].eq(grade)].reset_index(drop=True)
        for grade in GRADES
    }


def run(input_path: Path, output_dir: Path) -> None:
    """측정 데이터를 평균 백분위 등급별로 나눠 output_dir/grade_{등급}.csv로 저장합니다."""
    df = add_percentiles(load_measurements(input_path))
    logger.info("입력 %s: 측정 %s건", display_path(input_path), f"{len(df):,}")

    for grade, part in split_by_grade(df).items():
        path = grade_file_path(output_dir, grade)
        write_csv(part, path)
        logger.info("%d등급: %s건 -> %s", grade, f"{len(part):,}", display_path(path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(PROCESSED_FITNESS_PATH, INTERMEDIATE_CLUSTERING)


if __name__ == "__main__":
    main()
