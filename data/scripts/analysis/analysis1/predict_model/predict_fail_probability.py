"""저장된 모델로 장병별 4회차 체력검정 미달확률을 계산해 CSV에 컬럼으로 추가합니다.

- fail_probability_model.py를 import하지 않습니다. 모델 파일(joblib)만 있으면 됩니다.
- 모델 입력: 2·3차 측정(3차 측정치, 2→3차 변화량, 3차 BMI 파생변수)을 모델의 "현재·직전" 자리에 넣습니다.
- 출력: 입력 CSV의 모든 컬럼을 그대로 두고 PREDICTION_COLUMN을 추가해 OUTPUT_DIR/OUTPUT_NAME으로 저장합니다
       (save_table 사용: STORAGE_BACKEND에 따라 CSV 또는 DB).
       한 장병의 모든 측정 행에 같은 확률이 들어가며, 대상이 아닌 장병은 빈 값입니다.
- 대상: 측정이 정확히 3회이고 연속 측정 간격이 MIN_INTERVAL_DAYS 이상인 장병.

실행: python predict_fail_probability.py
"""

from pathlib import Path

import joblib
import pandas as pd

from data.scripts.paths import PROCESSED_FITNESS_PATH
from data.scripts.storage import save_table
from data.scripts.utils import read_text_csv

# ===========================================================================
# 설정 (입력·출력 경로, 컬럼, 규칙)
# ===========================================================================

# --- 경로 ---
INPUT_PATH = Path(PROCESSED_FITNESS_PATH)  # 입력 CSV
MODEL_PATH = Path("data/scripts/analysis/data_model/final/models/fail_probability_model.joblib")  # TODO: paths.py 상수로 교체
OUTPUT_DIR = Path("data/scripts/analysis/data_model/final")  # TODO: paths.py 상수로 교체
OUTPUT_NAME = "FAIL_PROBABILITY_4TH"  # save_table에 넘기는 테이블 이름

# --- 입력 CSV 컬럼 ---
MEMBER_ID_COLUMN = "SOLDIER_ID"
MESURE_DE_COLUMN = "MESURE_DE"
MESURE_ID_COLUMN = "MESURE_ID"
BMI_COLUMN = "BMI"

# --- 출력 CSV에 추가되는 컬럼 ---
PREDICTION_COLUMN = "FAIL_PROB_4TH"  # 4회차 미달확률(0~1)
PREDICTION_DECIMALS = 4

# --- 모델 입력 변수 이름 규칙 (학습 때와 같아야 합니다. 모델 파일의 feature_columns와 대조해 확인) ---
R2_SUFFIX = "R2"
DELTA_SUFFIX = "DELTA"
BMI_DEVIATION_SQ_COLUMN = "BMI_DEVIATION_SQ"

# --- 대상 규칙 ---
MEASURE_COUNT = 3
MIN_INTERVAL_DAYS = 30
CURRENT_ROUND = 3   # 모델의 "2차" 자리에 들어가는 회차
PREVIOUS_ROUND = 2  # 모델의 "1차" 자리에 들어가는 회차

ROUND_COLUMN = "ROUND"


# ===========================================================================
# 데이터 처리
# ===========================================================================

def load_measures(path: Path, numeric_columns: list[str]) -> pd.DataFrame:
    df = read_text_csv(path)
    for column in numeric_columns:
        values = pd.to_numeric(df[column].str.strip(), errors="coerce")
        if values.isna().any():
            raise ValueError(f"{column}이 숫자가 아니거나 비어 있는 행이 {int(values.isna().sum()):,}개 있습니다.")
        df[column] = values
    return df


def select_eligible(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """측정 3회 + 간격 규칙을 만족하는 장병만 남기고 회차를 매깁니다."""
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


# ===========================================================================
# 예측·저장
# ===========================================================================

def predict_and_save(
    input_path: Path = INPUT_PATH, model_path: Path = MODEL_PATH, output_dir: Path = OUTPUT_DIR
) -> None:
    bundle = joblib.load(model_path)
    df = load_measures(input_path, [*bundle["exercises"], BMI_COLUMN])
    kept, wrong_count, short_gap = select_eligible(df)
    if kept.empty:
        raise ValueError("예측 대상 장병이 없습니다.")

    features = build_features(kept, bundle)
    probability = pd.Series(
        bundle["model"].predict_proba(features)[:, 1], index=features.index
    ).round(PREDICTION_DECIMALS)

    # 원본 CSV(문자열 그대로)에 컬럼만 추가
    original = read_text_csv(input_path)
    original[PREDICTION_COLUMN] = original[MEMBER_ID_COLUMN].map(probability)

    save_table(original, OUTPUT_NAME, output_dir)

    print(f"입력: {input_path}")
    print(f"모델: {model_path}")
    print(f"예측 장병: {len(probability):,}명 (평균 4회차 미달확률 {probability.mean() * 100:.2f}%)")
    print(f"제외: 측정 {MEASURE_COUNT}회 아님 {wrong_count:,}명, 간격 {MIN_INTERVAL_DAYS}일 미만 {short_gap:,}명")
    print(f"저장: {output_dir} / {OUTPUT_NAME} ({PREDICTION_COLUMN} 컬럼 추가)")


if __name__ == "__main__":
    predict_and_save()