"""저장된 모델로 장병별 다음(4회차) 체력검정 미달 확률을 계산해 장병당 한 행으로 저장합니다.

- 모델 학습은 train_failure_probability_model.py가 하고, 이 파일은 저장된 모델(joblib)만 씁니다(Git 추적, 사용자 결정).
- 모델 입력: 2·3차 측정(3차 측정치, 2→3차 변화량, 3차 BMI 파생변수)을 모델의 "현재·직전" 자리에 넣습니다.
- 대상: 측정이 정확히 3회이고 연속 측정 간격이 MIN_INTERVAL_DAYS 이상인 장병. 대상이 아닌 장병은 행을 만들지 않습니다.
- 측정 데이터(KS_NFA_PROCESSED)에는 컬럼을 붙이지 않고, SOLDIER_ID로 연결되는 별도 테이블을 만듭니다.

[입력] processed/KS_NFA_PROCESSED.csv, FAILURE_MODEL_PATH
[출력] processed/SOLDIER_FAILURE_PROBABILITY.csv : SOLDIER_ID, FAILURE_PROBABILITY(0~1, 소수 4자리)

실행: python -m data.scripts.analysis.failure_prediction.predict_failure_probability
"""

import logging
from pathlib import Path

import joblib
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_SOLDIER_FAILURE_PROBABILITY,
    FAILURE_MODEL_PATH,
    PROCESSED_FITNESS_PATH,
    PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH,
)
from data.scripts.utils import read_text_csv, write_by_definition

logger = logging.getLogger(__name__)

MEMBER_ID_COLUMN = "SOLDIER_ID"
MESURE_DE_COLUMN = "MESURE_DE"
MESURE_ID_COLUMN = "MESURE_ID"
BMI_COLUMN = "BMI"

PREDICTION_COLUMN = "FAILURE_PROBABILITY"
PREDICTION_DECIMALS = 4  # 정의서의 DECIMAL(5,4)

# 모델 입력 변수 이름 규칙(학습 때와 같아야 하며, 모델 파일의 feature_columns와 대조해 확인한다)
R2_SUFFIX = "R2"
DELTA_SUFFIX = "DELTA"
BMI_DEVIATION_SQ_COLUMN = "BMI_DEVIATION_SQ"

MEASURE_COUNT = 3
MIN_INTERVAL_DAYS = 30
CURRENT_ROUND = 3   # 모델의 "2차" 자리에 들어가는 회차
PREVIOUS_ROUND = 2  # 모델의 "1차" 자리에 들어가는 회차

ROUND_COLUMN = "ROUND"


def load_measures(path: Path, numeric_columns: list[str]) -> pd.DataFrame:
    """측정 데이터를 읽고 모델에 쓰는 컬럼을 숫자로 바꿉니다.

    Raises:
        ValueError: 숫자로 읽을 수 없거나 비어 있는 값이 있을 때
    """
    df = read_text_csv(path)
    for column in numeric_columns:
        values = pd.to_numeric(df[column].str.strip(), errors="coerce")
        if values.isna().any():
            raise ValueError(f"{column}이 숫자가 아니거나 비어 있는 행이 {int(values.isna().sum()):,}개 있습니다.")
        df[column] = values
    return df


def select_eligible(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """측정 3회 + 간격 규칙을 만족하는 장병만 남기고 회차를 매깁니다.

    Returns:
        (대상 측정, 측정 횟수가 맞지 않아 뺀 장병 수, 간격이 짧아 뺀 장병 수)

    Raises:
        ValueError: 측정일을 YYYYMMDD로 읽을 수 없을 때
    """
    dates = pd.to_datetime(df[MESURE_DE_COLUMN].astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    if dates.isna().any():
        raise ValueError(
            f"{MESURE_DE_COLUMN}을 YYYYMMDD 날짜로 읽을 수 없는 행이 {int(dates.isna().sum()):,}개 있습니다."
        )
    work = df.assign(_date=dates).sort_values([MEMBER_ID_COLUMN, "_date", MESURE_ID_COLUMN]).reset_index(drop=True)
    work[ROUND_COLUMN] = work.groupby(MEMBER_ID_COLUMN).cumcount() + 1

    counts = work.groupby(MEMBER_ID_COLUMN).size()
    wrong_count = counts.index[counts.ne(MEASURE_COUNT)]
    gap_days = work.groupby(MEMBER_ID_COLUMN)["_date"].diff().dt.days
    short_gap = work.loc[gap_days < MIN_INTERVAL_DAYS, MEMBER_ID_COLUMN].unique()

    excluded = set(wrong_count) | set(short_gap)
    kept = work[~work[MEMBER_ID_COLUMN].isin(excluded)]
    return kept, len(wrong_count), len(set(short_gap) - set(wrong_count))


def build_features(kept: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """장병마다 모델 입력 변수를 만듭니다(행 = 장병).

    Raises:
        ValueError: 모델이 요구하는 입력 변수를 만들 수 없을 때
    """
    exercises = bundle["exercises"]
    wide = kept.pivot(index=MEMBER_ID_COLUMN, columns=ROUND_COLUMN, values=[*exercises, BMI_COLUMN])

    features = pd.DataFrame(index=wide.index)
    for exercise in exercises:
        features[f"{exercise}_{R2_SUFFIX}"] = wide[(exercise, CURRENT_ROUND)]
        features[f"{exercise}_{DELTA_SUFFIX}"] = wide[(exercise, CURRENT_ROUND)] - wide[(exercise, PREVIOUS_ROUND)]
    features[BMI_DEVIATION_SQ_COLUMN] = (wide[(BMI_COLUMN, CURRENT_ROUND)] - bundle["bmi_center"]) ** 2

    expected = bundle["feature_columns"]
    missing = [column for column in expected if column not in features.columns]
    if missing:
        raise ValueError(f"모델이 요구하는 입력 변수를 만들 수 없습니다: {missing}")
    return features[expected]


def predict_failure_probability(df: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """대상 장병마다 다음 회차 미달 확률을 계산해 (SOLDIER_ID, FAILURE_PROBABILITY)로 돌려줍니다(군번 순).

    Raises:
        ValueError: 예측 대상 장병이 없을 때
    """
    kept, wrong_count, short_gap = select_eligible(df)
    if kept.empty:
        raise ValueError("예측 대상 장병이 없습니다.")
    if wrong_count or short_gap:
        logger.info("제외: 측정 %d회 아님 %s명, 간격 %d일 미만 %s명",
                    MEASURE_COUNT, f"{wrong_count:,}", MIN_INTERVAL_DAYS, f"{short_gap:,}")

    features = build_features(kept, bundle)
    probability = bundle["model"].predict_proba(features)[:, 1]
    return pd.DataFrame({
        MEMBER_ID_COLUMN: features.index,
        PREDICTION_COLUMN: pd.Series(probability).round(PREDICTION_DECIMALS),
    })


def run(input_path: Path, model_path: Path, definition_path: Path, output_path: Path) -> None:
    """장병별 다음 회차 미달 확률을 정의서대로 저장합니다."""
    bundle = joblib.load(model_path)
    df = load_measures(input_path, [*bundle["exercises"], BMI_COLUMN])
    predictions = write_by_definition(predict_failure_probability(df, bundle), definition_path, output_path)

    logger.info("입력 %s, 모델 %s", display_path(input_path), display_path(model_path))
    logger.info(
        "예측 장병 %s명 (평균 다음 회차 미달 확률 %.2f%%), 저장: %s",
        f"{len(predictions):,}", predictions[PREDICTION_COLUMN].mean() * 100, display_path(output_path),
    )


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(
        PROCESSED_FITNESS_PATH,
        FAILURE_MODEL_PATH,
        DEFINITION_SOLDIER_FAILURE_PROBABILITY,
        PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH,
    )


if __name__ == "__main__":
    main()
