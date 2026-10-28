"""1·2차 측정 결과로 3차 체력검정 미달 확률을 예측하는 모델을 학습해 파일로 저장합니다.

- 분석·검증(교차검증, 등급표, ROC, 보정 등)은 하지 않습니다. 모델만 학습해 OUTPUT_PATH에 저장합니다.
- 모델: 표준화 + L2 로지스틱 회귀(C=1), 2차 BMI 파생변수(정상범위 중앙 이탈 제곱) 사용.
- 학습 데이터: 전체 장병(층화 분할 없음).
- 저장한 모델은 predict_fail_probability.py에서 사용합니다(이 파일을 import하지 않습니다).

실행: python fail_probability_model.py
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from data.scripts.fitness_standards import FITNESS_EXERCISES, RANGE_STANDARDS, grade_cut
from data.scripts.paths import PROCESSED_FITNESS_PATH
from data.scripts.utils import read_text_csv

# ===========================================================================
# 설정 (입력·출력 경로, 입력 변수, 규칙)
# ===========================================================================

# --- 경로 ---
INPUT_PATH = Path(PROCESSED_FITNESS_PATH)  # 입력 CSV
OUTPUT_PATH = Path("data/scripts/analysis/data_model/final/models/fail_probability_model.joblib")  # TODO: paths.py 상수로 교체

# --- 입력 CSV 컬럼 ---
MEMBER_ID_COLUMN = "SOLDIER_ID"   # 장병 식별
MESURE_DE_COLUMN = "MESURE_DE"    # 측정일(YYYYMMDD)
MESURE_ID_COLUMN = "MESURE_ID"    # 측정 식별(같은 날짜 정렬용)
BMI_COLUMN = "BMI"

# --- 모형 입력 변수 (이 순서대로 모델에 들어갑니다) ---
# 종목별 2차 측정치(_R2)와 1·2차 변화량(_DELTA), 2차 BMI 파생변수
R2_SUFFIX = "R2"
DELTA_SUFFIX = "DELTA"
BMI_DEVIATION_SQ_COLUMN = "BMI_DEVIATION_SQ"  # (2차 BMI - 정상범위 중앙)^2
FEATURE_COLUMNS = [
    *[f"{exercise}_{R2_SUFFIX}" for exercise in FITNESS_EXERCISES],
    *[f"{exercise}_{DELTA_SUFFIX}" for exercise in FITNESS_EXERCISES],
    BMI_DEVIATION_SQ_COLUMN,
]

# --- 측정·라벨 규칙 ---
MEASURE_COUNT = 3          # 장병당 측정 횟수(정확히 3회)
MIN_INTERVAL_DAYS = 30     # 연속 측정 간격 하한(일). 미만이면 그 장병 제외
CUT_GRADE = 3              # 이 등급 하한 미만이면 종목 미달
TARGET_MIN_FAILS = 2       # 3차에서 미달 종목이 이 수 이상이면 미달(=1)
FAILED_COLUMN = "FAIL_3RD"

# --- 모델 설정 ---
LOGISTIC_C = 1.0
MAX_ITER = 1000

# 내부 컬럼명
ROUND_COLUMN = "ROUND"
FAIL_COUNT_COLUMN = "FAIL_COUNT"


# ===========================================================================
# 데이터 처리
# ===========================================================================

def load_measures(path: Path) -> pd.DataFrame:
    df = read_text_csv(path)
    for column in (*FITNESS_EXERCISES, BMI_COLUMN):
        values = pd.to_numeric(df[column].str.strip(), errors="coerce")
        if values.isna().any():
            raise ValueError(f"{column}이 숫자가 아니거나 비어 있는 행이 {int(values.isna().sum()):,}개 있습니다.")
        df[column] = values
    return df


def apply_interval_rule(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """같은 장병의 연속 측정 간격이 MIN_INTERVAL_DAYS 미만이면 그 장병 전체를 제외합니다."""
    dates = pd.to_datetime(df[MESURE_DE_COLUMN].astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    if dates.isna().any():
        raise ValueError(
            f"{MESURE_DE_COLUMN}을 YYYYMMDD 날짜로 읽을 수 없는 행이 {int(dates.isna().sum()):,}개 있습니다."
        )
    work = (
        df[[MEMBER_ID_COLUMN, MESURE_ID_COLUMN]]
        .assign(_date=dates)
        .sort_values([MEMBER_ID_COLUMN, "_date", MESURE_ID_COLUMN])
    )
    gap_days = work.groupby(MEMBER_ID_COLUMN)["_date"].diff().dt.days
    short_members = work.loc[gap_days < MIN_INTERVAL_DAYS, MEMBER_ID_COLUMN].unique()
    kept = df[~df[MEMBER_ID_COLUMN].isin(short_members)].copy()
    return kept, len(short_members)


def assign_rounds(df: pd.DataFrame) -> pd.DataFrame:
    counts = df.groupby(MEMBER_ID_COLUMN).size()
    invalid = counts[counts.ne(MEASURE_COUNT)]
    if len(invalid):
        raise ValueError(f"측정이 정확히 {MEASURE_COUNT}회가 아닌 장병이 {len(invalid):,}명 있습니다.")

    sorted_df = df.sort_values([MEMBER_ID_COLUMN, MESURE_DE_COLUMN, MESURE_ID_COLUMN]).reset_index(drop=True)
    sorted_df[ROUND_COLUMN] = sorted_df.groupby(MEMBER_ID_COLUMN).cumcount() + 1
    return sorted_df


def count_fails(df: pd.DataFrame) -> pd.DataFrame:
    fails = pd.DataFrame({exercise: df[exercise].lt(grade_cut(exercise, CUT_GRADE)) for exercise in FITNESS_EXERCISES})
    return df.assign(**{FAIL_COUNT_COLUMN: fails.sum(axis=1)})


def build_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """모형 입력(FEATURE_COLUMNS)과 3차 미달 라벨을 만듭니다."""
    wide = count_fails(assign_rounds(df)).pivot(
        index=MEMBER_ID_COLUMN,
        columns=ROUND_COLUMN,
        values=[*FITNESS_EXERCISES, BMI_COLUMN, FAIL_COUNT_COLUMN],
    )

    features = pd.DataFrame(index=wide.index)
    for exercise in FITNESS_EXERCISES:
        features[f"{exercise}_{R2_SUFFIX}"] = wide[(exercise, 2)]
        features[f"{exercise}_{DELTA_SUFFIX}"] = wide[(exercise, 2)] - wide[(exercise, 1)]
    bmi_low, _, bmi_high, _ = RANGE_STANDARDS[BMI_COLUMN]
    features[BMI_DEVIATION_SQ_COLUMN] = (wide[(BMI_COLUMN, 2)] - (bmi_low + bmi_high) / 2) ** 2

    failed = wide[(FAIL_COUNT_COLUMN, 3)].astype(int).ge(TARGET_MIN_FAILS).astype(int).rename(FAILED_COLUMN)
    return features[FEATURE_COLUMNS], failed


# ===========================================================================
# 모델 학습·저장
# ===========================================================================

def train_and_save(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> Path:
    df, excluded = apply_interval_rule(load_measures(input_path))
    x, y = build_dataset(df)
    if y.nunique() < 2:
        raise ValueError("3차 미달/통과 라벨이 한 종류뿐이라 모델을 학습할 수 없습니다.")

    model = make_pipeline(StandardScaler(), LogisticRegression(C=LOGISTIC_C, max_iter=MAX_ITER))
    model.fit(x, y)

    bmi_low, _, bmi_high, _ = RANGE_STANDARDS[BMI_COLUMN]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_columns": FEATURE_COLUMNS,
            # 사용 코드가 이 파일에 의존하지 않도록 입력 변수 생성에 필요한 값을 함께 저장
            "exercises": list(FITNESS_EXERCISES),
            "bmi_center": (bmi_low + bmi_high) / 2,
            "n_train": len(x),
            "fail_rate": float(y.mean()),
        },
        output_path,
    )
    print(f"입력: {input_path}")
    print(f"제외 장병(측정 간격 {MIN_INTERVAL_DAYS}일 미만): {excluded:,}명")
    print(f"학습 장병: {len(x):,}명 / 3차 미달률: {y.mean() * 100:.2f}%")
    print(f"모델 저장: {output_path}")
    return output_path


if __name__ == "__main__":
    train_and_save()