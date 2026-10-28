"""1·2차 측정 결과로 3차 체력검정 미달 확률을 예측하고, 확률을 4개 등급(관리·위험·경계·안전)으로 나눠 검증합니다.

- 대상: 같은 장병의 연속 측정 간격이 30일 이상이고 측정이 정확히 3회인 데이터. 측정일 오름차순으로 1·2·3차를 매깁니다.
- 정답 라벨(미달=1, 통과=0): 3차 측정에서 3등급 하한 미만인 종목이 TARGET_MIN_FAILS개 이상이면 미달입니다.
- 입력: 2차 종목별 측정치 4개, 1·2차 종목별 변화량 4개, 2차 BMI 파생변수(채택 모형).
- 모형: 기준선 2개, 규칙 기준선(2차 미달 수 ≥ 2), L2 로지스틱 회귀(C=1) 2개(BMI 원본 / BMI 파생변수).

등급 기준 (슬라이드 확정안)
- 관리: 미달확률 ≥ 0.7 / 위험: 0.5 ≤ p < 0.7 / 경계: 0.3 ≤ p < 0.5 / 안전: p < 0.3
- 면담 대상은 위험 이상(p ≥ 0.5)으로 보고 재현율·정밀도를 산출합니다.

평가 순서 (테스트 누수 방지)
1) 학습/테스트 80/20 층화 분할. 테스트는 분리만 합니다.
2) 학습 데이터에서 교차검증 예측 확률을 모든 모형에 대해 만듭니다.
3) 교차검증 예측으로 등급의 단조성과 인접 등급 CI 겹침을 확인합니다. 기준은 바꾸지 않습니다.
4) 교차검증 성능을 계산합니다.
5) 확정된 모형과 등급 기준을 테스트에 1회만 적용합니다.

실행: python -m streamlit run fail_probability_app.py
"""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 화면 없이 그래프 객체만 만든다.
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from data.scripts.fitness_standards import FITNESS_EXERCISES, RANGE_STANDARDS, grade_cut
from data.scripts.logging_setup import display_path
from data.scripts.paths import PROCESSED_FITNESS_PATH
from data.scripts.utils import read_text_csv

st.set_page_config(page_title="3차 체력검정 미달 예측", layout="wide")

# 입력 컬럼 (샘플 CSV의 장병 식별 컬럼은 SOLDIER_ID)
MEMBER_ID_COLUMN = "SOLDIER_ID"
MESURE_DE_COLUMN = "MESURE_DE"
MESURE_ID_COLUMN = "MESURE_ID"
BMI_COLUMN = "BMI"

# 이 단계에서 새로 만드는 컬럼
ROUND_COLUMN = "ROUND"
FAIL_COUNT_COLUMN = "FAIL_COUNT"
BMI_DEVIATION_SQ_COLUMN = "BMI_DEVIATION_SQ"
FAILED_COLUMN = "FAIL_3RD"  # 3차 미달 여부 (미달=1, 통과=0)

# 측정·라벨 규칙
MEASURE_COUNT = 3
CUT_GRADE = 3
TARGET_MIN_FAILS = 2
MIN_INTERVAL_DAYS = 30  # 연속 측정 간격 하한(일)

# 검증 설정
TEST_SIZE = 0.2
MAX_CV_SPLITS = 5
RANDOM_STATE = 42
LOGISTIC_C = 1.0

# 모형 이름
ADOPTED_MODEL_NAME = "로지스틱 회귀(BMI파생변수)"
RULE_BASELINE_NAME = "규칙 기준선(2차 미달 수 ≥ 2)"
PRIOR_BASELINE_NAME = "기준선(항상 다수 클래스)"
RANDOM_BASELINE_NAME = "기준선(비율대로 무작위)"
BASELINE = "baseline"
RANDOM_BASELINE = "random_baseline"
LOGISTIC = "logistic"

# 등급 기준 (슬라이드 확정안). 교차검증에서 확인만 하고, 테스트 결과로 바꾸지 않습니다.
GRADE_CUTS = (0.3, 0.5, 0.7)  # (경계 하한, 위험 하한, 관리 하한)
GRADE_ORDER = ("관리", "위험", "경계", "안전")
GRADE_COLORS = ("#C44E52", "#DD8452", "#E9C46A", "#55A868")
PRIMARY_THRESHOLD = 0.5  # 면담 대상(위험 이상) 판정 기준. 재현율·정밀도 산출에 사용
CI_Z = 1.96
CALIBRATION_BINS = 5

# 지표 이름
AUC_METRIC = "ROC_AUC"
BRIER_METRIC = "브라이언 점수"
LOGLOSS_METRIC = "로그 손실"
RECALL_METRIC = f"재현율(미달확률 {PRIMARY_THRESHOLD} 이상)"
PRECISION_METRIC = f"정밀도(미달확률 {PRIMARY_THRESHOLD} 이상)"
METRICS = (AUC_METRIC, BRIER_METRIC, LOGLOSS_METRIC, RECALL_METRIC, PRECISION_METRIC)

CV_SPLIT = "교차검증(학습 데이터)"
TEST_SPLIT = "Hold-out 테스트"

EXERCISE_LABELS = {"STRENGTH": "근력", "ENDURANCE": "근지구력", "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성"}


# ---------------------------------------------------------------------------
# 1. 데이터 처리
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    input_label: str
    excluded_members: int
    n_members: int
    fail_count: int
    fail_rate: float
    n_train: int
    n_test: int
    base_rate: float
    cv_grade_ok: bool
    performance: pd.DataFrame
    coefficients: pd.DataFrame
    vif: pd.DataFrame
    bmi_band_cv: pd.DataFrame
    cv_grade: pd.DataFrame
    cv_threshold: pd.DataFrame
    test_grade: pd.DataFrame
    test_threshold: pd.DataFrame
    predictions: pd.DataFrame
    y_train: pd.Series
    oof_probability: np.ndarray
    y_test: pd.Series
    test_probability: dict[str, np.ndarray]


def set_korean_font() -> None:
    """matplotlib에서 한글이 깨지지 않도록 폰트를 설정합니다."""
    plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


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


def build_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """모형 입력(features), 3차 미달 라벨, 3차 미달 수, 2차 미달 수(규칙 기준선용)를 만듭니다."""
    wide = count_fails(assign_rounds(df)).pivot(
        index=MEMBER_ID_COLUMN,
        columns=ROUND_COLUMN,
        values=[*FITNESS_EXERCISES, BMI_COLUMN, FAIL_COUNT_COLUMN],
    )

    features = pd.DataFrame(index=wide.index)
    for exercise in FITNESS_EXERCISES:
        features[f"{exercise}_R2"] = wide[(exercise, 2)]
        features[f"{exercise}_DELTA"] = wide[(exercise, 2)] - wide[(exercise, 1)]
    features[BMI_COLUMN] = wide[(BMI_COLUMN, 2)]
    bmi_low, _, bmi_high, _ = RANGE_STANDARDS[BMI_COLUMN]
    features[BMI_DEVIATION_SQ_COLUMN] = (features[BMI_COLUMN] - (bmi_low + bmi_high) / 2) ** 2

    fail_count_3rd = wide[(FAIL_COUNT_COLUMN, 3)].astype(int)
    fail_count_2nd = wide[(FAIL_COUNT_COLUMN, 2)].astype(int)
    failed = fail_count_3rd.ge(TARGET_MIN_FAILS).astype(int).rename(FAILED_COLUMN)
    return features, failed, fail_count_3rd, fail_count_2nd


def feature_labels(columns: list[str]) -> dict[str, str]:
    labels = {}
    for column in columns:
        exercise, _, kind = column.rpartition("_")
        if exercise in EXERCISE_LABELS:
            labels[column] = f"{EXERCISE_LABELS[exercise]} {'2차 측정치' if kind == 'R2' else '1·2차 변화량'}"
    labels[BMI_COLUMN] = "2차 BMI"
    labels[BMI_DEVIATION_SQ_COLUMN] = "2차 BMI의 정상범위 중앙 이탈 제곱"
    return {column: labels.get(column, column) for column in columns}


def model_specs(features: pd.DataFrame) -> dict[str, tuple[str, list[str]]]:
    """확률 모형 목록입니다. 규칙 기준선은 확률이 아니라 별도로 평가합니다."""
    base_columns = [column for column in features.columns if column != BMI_DEVIATION_SQ_COLUMN]
    columns_without_bmi = [column for column in base_columns if column != BMI_COLUMN]
    return {
        PRIOR_BASELINE_NAME: (BASELINE, base_columns),
        RANDOM_BASELINE_NAME: (RANDOM_BASELINE, base_columns),
        "로지스틱 회귀(BMI)": (LOGISTIC, base_columns),
        ADOPTED_MODEL_NAME: (LOGISTIC, [*columns_without_bmi, BMI_DEVIATION_SQ_COLUMN]),
    }


def make_model(kind: str):
    if kind in (BASELINE, RANDOM_BASELINE):
        return DummyClassifier(strategy="prior")
    return make_pipeline(StandardScaler(), LogisticRegression(C=LOGISTIC_C, max_iter=1000))


def predict_fail_probability(model, x: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(x)[:, 1]


# ---------------------------------------------------------------------------
# 2. 지표 계산
# ---------------------------------------------------------------------------

def precision(predicted_fail: np.ndarray, actual_fail: np.ndarray) -> float:
    return (predicted_fail & actual_fail).sum() / predicted_fail.sum() if predicted_fail.any() else np.nan


def evaluate_probability(kind: str, y_true: pd.Series, probability: np.ndarray, base_rate: float) -> dict[str, float]:
    """확률 모형의 지표입니다. 재현율·정밀도는 PRIMARY_THRESHOLD 기준입니다."""
    actual = y_true.to_numpy() == 1
    metrics = {
        AUC_METRIC: roc_auc_score(y_true, probability),
        BRIER_METRIC: brier_score_loss(y_true, probability),
        LOGLOSS_METRIC: log_loss(y_true, probability, labels=[0, 1]),
    }
    if kind == RANDOM_BASELINE:
        # 미달률(base_rate) 비율로 무작위 미달 판정을 했을 때의 기대값
        metrics[RECALL_METRIC] = base_rate
        metrics[PRECISION_METRIC] = actual.mean()
        return metrics

    predicted = probability >= PRIMARY_THRESHOLD
    metrics[RECALL_METRIC] = (predicted & actual).sum() / actual.sum()
    metrics[PRECISION_METRIC] = precision(predicted, actual)
    return metrics


def evaluate_rule(y_true: pd.Series, fail_count_2nd: pd.Series) -> dict[str, float]:
    """규칙 기준선(2차 미달 수 ≥ TARGET_MIN_FAILS)입니다. 확률이 없으므로 Brier·LogLoss는 비워 둡니다."""
    actual = y_true.to_numpy() == 1
    predicted = fail_count_2nd.to_numpy() >= TARGET_MIN_FAILS
    return {
        AUC_METRIC: roc_auc_score(y_true, fail_count_2nd),  # 2차 미달 수를 점수로 본 AUC
        BRIER_METRIC: np.nan,
        LOGLOSS_METRIC: np.nan,
        RECALL_METRIC: (predicted & actual).sum() / actual.sum(),
        PRECISION_METRIC: precision(predicted, actual),
    }


def summarize(split: str, model_name: str, frame: pd.DataFrame) -> dict:
    row = {"모형": model_name, "평가 구간": split}
    for metric in METRICS:
        values = frame[metric]
        row[metric] = round(float(values.mean()), 4)
        row[f"{metric}_표준편차"] = round(float(values.std()), 4) if values.notna().sum() > 1 else np.nan
    return row


def cv_splits(y: pd.Series) -> list[tuple[np.ndarray, np.ndarray]]:
    """모든 모형이 같은 폴드를 쓰도록 분할을 한 번만 만듭니다."""
    n_splits = min(MAX_CV_SPLITS, int(y.value_counts().min()))
    if n_splits < 2:
        raise ValueError("소수 클래스 인원이 2명 미만이라 교차검증을 할 수 없습니다.")
    return list(StratifiedKFold(n_splits, shuffle=True, random_state=RANDOM_STATE).split(np.zeros(len(y)), y))


def cv_model(kind: str, columns: list[str], x: pd.DataFrame, y: pd.Series, splits) -> tuple[pd.DataFrame, pd.Series]:
    oof = pd.Series(np.nan, index=y.index)
    rows = []
    for train_pos, valid_pos in splits:
        model = make_model(kind).fit(x.iloc[train_pos][columns], y.iloc[train_pos])
        probability = predict_fail_probability(model, x.iloc[valid_pos][columns])
        oof.iloc[valid_pos] = probability
        rows.append(evaluate_probability(kind, y.iloc[valid_pos], probability, y.iloc[train_pos].mean()))
    return pd.DataFrame(rows), oof


# ---------------------------------------------------------------------------
# 3. 등급과 구간별 검증
# ---------------------------------------------------------------------------

def assign_grade(probability) -> np.ndarray:
    low, mid, high = GRADE_CUTS
    p = np.asarray(probability)
    return np.select(
        [p >= high, p >= mid, p >= low],
        [GRADE_ORDER[0], GRADE_ORDER[1], GRADE_ORDER[2]],
        default=GRADE_ORDER[3],
    )


def wilson_interval(successes: int, n: int, z: float = CI_Z) -> tuple[float, float]:
    if n == 0:
        return np.nan, np.nan
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return center - half, center + half


def grade_table(y_true: pd.Series, probability: np.ndarray) -> pd.DataFrame:
    """등급별 인원, 실제 미달율과 Wilson CI, 리프트, 누적 포착률, 인접 등급 CI 겹침을 계산합니다."""
    actual = y_true.to_numpy() == 1
    p = np.asarray(probability)
    grades = assign_grade(p)
    total = len(actual)
    total_fail = int(actual.sum())
    overall_rate = actual.mean()

    rows, cumulative = [], 0
    for grade in GRADE_ORDER:
        mask = grades == grade
        n = int(mask.sum())
        fails = int((mask & actual).sum())
        cumulative += fails
        rate = fails / n if n else np.nan
        ci_low, ci_high = wilson_interval(fails, n)
        rows.append({
            "등급": grade,
            "인원(명)": n,
            "비율(%)": round(n / total * 100, 2),
            "평균 예측 미달확률(%)": round(p[mask].mean() * 100, 2) if n else np.nan,
            "실제 미달(명)": fails,
            "실제 미달율(%)": round(rate * 100, 2) if n else np.nan,
            "미달율 CI 하한(%)": round(ci_low * 100, 2) if n else np.nan,
            "미달율 CI 상한(%)": round(ci_high * 100, 2) if n else np.nan,
            "리프트(전체 미달률 대비)": round(rate / overall_rate, 2) if n else np.nan,
            "누적 포착률(%)": round(cumulative / total_fail * 100, 2),
        })

    table = pd.DataFrame(rows)
    overlap = ["-"]
    for i in range(1, len(table)):
        upper, lower = table.iloc[i - 1], table.iloc[i]
        if pd.isna(upper["실제 미달율(%)"]) or pd.isna(lower["실제 미달율(%)"]):
            overlap.append("-")
        elif lower["미달율 CI 상한(%)"] >= upper["미달율 CI 하한(%)"]:
            overlap.append("겹침(구분 불확실)")
        else:
            overlap.append("구분됨")
    table["위 등급과 CI"] = overlap
    return table


def is_monotonic(grade_df: pd.DataFrame) -> bool:
    """관리 > 위험 > 경계 > 안전 순으로 실제 미달율이 낮아지는지 확인합니다."""
    rates = grade_df["실제 미달율(%)"].to_numpy(dtype=float)
    if np.isnan(rates).any():
        return False
    return bool(np.all(rates[:-1] > rates[1:]))


def threshold_table(y_true: pd.Series, probability: np.ndarray, cuts: tuple[float, ...]) -> pd.DataFrame:
    """등급 기준값별로 '이상' 판정 인원과 포착률을 보여 줍니다. 값을 고르는 데 쓰지 않습니다."""
    actual = y_true.to_numpy() == 1
    total_fail = int(actual.sum())
    p = np.asarray(probability)
    rows = []
    for cut in cuts:
        predicted = p >= cut
        n = int(predicted.sum())
        caught = int((predicted & actual).sum())
        rows.append({
            "임계값(이상)": cut,
            "판정 인원(명)": n,
            "실제 미달 포착(명)": caught,
            "재현율(%)": round(caught / total_fail * 100, 2),
            "정밀도(%)": round(caught / n * 100, 2) if n else np.nan,
        })
    return pd.DataFrame(rows)


def bmi_band_table(bmi: pd.Series, y_true: pd.Series, probability: np.ndarray) -> pd.DataFrame:
    """BMI 구간별 실제 미달율을 보여 줍니다. 파생변수의 대칭 가정(정상 중앙 기준 양쪽 동일 위험)을 확인합니다."""
    bmi_low = RANGE_STANDARDS[BMI_COLUMN][0]
    bmi_high = RANGE_STANDARDS[BMI_COLUMN][2]
    labels = ("저체중(하한 미만)", "정상 범위", "과체중 이상(상한 이상)")
    b = bmi.to_numpy(dtype=float)
    bands = np.select([b < bmi_low, b < bmi_high], [labels[0], labels[1]], default=labels[2])
    actual = y_true.to_numpy() == 1
    p = np.asarray(probability)

    rows = []
    for label in labels:
        mask = bands == label
        n = int(mask.sum())
        rows.append({
            "BMI 구간": label,
            "인원(명)": n,
            "평균 예측 미달확률(%)": round(p[mask].mean() * 100, 2) if n else np.nan,
            "실제 미달율(%)": round(actual[mask].mean() * 100, 2) if n else np.nan,
        })
    return pd.DataFrame(rows)


def vif_table(x: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """각 변수를 나머지 변수로 회귀해 VIF를 계산합니다. 학습 데이터로만 계산합니다."""
    matrix = x[columns].to_numpy(dtype=float)
    labels = feature_labels(columns)
    rows = []
    for i, column in enumerate(columns):
        target = matrix[:, i]
        others = np.delete(matrix, i, axis=1)
        design = np.column_stack([np.ones(len(others)), others])
        coef, *_ = np.linalg.lstsq(design, target, rcond=None)
        residual = target - design @ coef
        ss_total = ((target - target.mean()) ** 2).sum()
        r2 = 1 - (residual ** 2).sum() / ss_total if ss_total > 0 else 0.0
        vif = np.inf if r2 >= 1 else 1 / (1 - r2)
        rows.append({
            "변수": labels[column],
            "컬럼": column,
            "VIF": round(float(vif), 2),
            "판정": "충족(<5)" if vif < 5 else "주의(≥5)",
        })
    return pd.DataFrame(rows)


def build_coefficient_table(model, columns: list[str]) -> pd.DataFrame:
    coefficients = model[-1].coef_[0]
    labels = feature_labels(columns)
    table = pd.DataFrame({
        "변수": [labels[column] for column in columns],
        "컬럼": columns,
        "회귀계수(1표준편차당)": np.round(coefficients, 4),
        "오즈비(1표준편차당)": np.round(np.exp(coefficients), 4),
        "방향": np.where(coefficients >= 0, "미달 확률 증가", "미달 확률 감소"),
    })
    return table.reindex(table["회귀계수(1표준편차당)"].abs().sort_values(ascending=False).index).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. 전체 분석 (교차검증 → 확정 → 테스트 1회)
# ---------------------------------------------------------------------------

def run_analysis(input_path: Path) -> AnalysisResult:
    raw = load_measures(input_path)
    df, excluded = apply_interval_rule(raw)
    features, failed, fail_count_3rd, fail_count_2nd = build_dataset(df)
    specs = model_specs(features)
    if ADOPTED_MODEL_NAME not in specs:
        raise ValueError(f"채택 모형 '{ADOPTED_MODEL_NAME}'이 모형 목록에 없습니다.")

    # 0) 분할: 테스트는 여기서 분리만 한다
    x_train, x_test, y_train, y_test = train_test_split(
        features, failed, test_size=TEST_SIZE, stratify=failed, random_state=RANDOM_STATE
    )
    base_rate = float(y_train.mean())  # 학습 데이터에서만 계산
    if GRADE_CUTS[0] <= base_rate:
        raise ValueError(
            f"경계 하한({GRADE_CUTS[0]})이 기저율({base_rate:.3f}) 이하라 등급 구분이 성립하지 않습니다."
        )
    fail2_train = fail_count_2nd.loc[x_train.index]
    fail2_test = fail_count_2nd.loc[x_test.index]

    # 1) 교차검증 (테스트 미사용)
    splits = cv_splits(y_train)
    performance_rows, oof_by_model = [], {}
    for name, (kind, columns) in specs.items():
        fold_df, oof_by_model[name] = cv_model(kind, columns, x_train, y_train, splits)
        performance_rows.append(summarize(CV_SPLIT, name, fold_df))
    rule_fold = pd.DataFrame([evaluate_rule(y_train.iloc[v], fail2_train.iloc[v]) for _, v in splits])
    performance_rows.append(summarize(CV_SPLIT, RULE_BASELINE_NAME, rule_fold))

    # 2) 등급 구조 확인 (교차검증 예측만 사용)
    cv_oof = oof_by_model[ADOPTED_MODEL_NAME].to_numpy()
    cv_grade = grade_table(y_train, cv_oof)
    cv_grade_ok = is_monotonic(cv_grade)
    cv_threshold = threshold_table(y_train, cv_oof, GRADE_CUTS)

    # 3) 테스트: 확정된 모형과 등급 기준을 1회만 적용
    adopted_kind, adopted_columns = specs[ADOPTED_MODEL_NAME]
    adopted_model = make_model(adopted_kind).fit(x_train[adopted_columns], y_train)

    test_probability = {}
    for name, (kind, columns) in specs.items():
        model = adopted_model if name == ADOPTED_MODEL_NAME else make_model(kind).fit(x_train[columns], y_train)
        test_probability[name] = predict_fail_probability(model, x_test[columns])
        performance_rows.append(summarize(
            TEST_SPLIT, name,
            pd.DataFrame([evaluate_probability(kind, y_test, test_probability[name], base_rate)]),
        ))
    performance_rows.append(summarize(
        TEST_SPLIT, RULE_BASELINE_NAME, pd.DataFrame([evaluate_rule(y_test, fail2_test)]),
    ))

    test_prob_adopted = test_probability[ADOPTED_MODEL_NAME]
    test_grade = grade_table(y_test, test_prob_adopted)
    test_threshold = threshold_table(y_test, test_prob_adopted, GRADE_CUTS)

    # 4) 개인별 예측 (학습은 교차검증 확률, 테스트는 테스트 확률)
    full_probability = pd.concat([
        pd.Series(cv_oof, index=y_train.index),
        pd.Series(test_prob_adopted, index=y_test.index),
    ]).reindex(features.index)
    predictions = pd.DataFrame({
        MEMBER_ID_COLUMN: features.index,
        "구분": np.where(features.index.isin(x_test.index), "테스트", "학습(교차검증)"),
        "3차 미달확률": full_probability.round(4).to_numpy(),
        "등급": assign_grade(full_probability.to_numpy()),
        "실제 3차 미달 종목 수": fail_count_3rd.to_numpy(),
        "실제 3차 결과": np.where(failed.eq(1), "미달", "통과"),
    })

    return AnalysisResult(
        input_label=display_path(input_path),
        excluded_members=excluded,
        n_members=len(features),
        fail_count=int(failed.sum()),
        fail_rate=float(failed.mean()),
        n_train=len(x_train),
        n_test=len(x_test),
        base_rate=base_rate,
        cv_grade_ok=cv_grade_ok,
        performance=pd.DataFrame(performance_rows),
        coefficients=build_coefficient_table(adopted_model, adopted_columns),
        vif=vif_table(x_train, adopted_columns),
        bmi_band_cv=bmi_band_table(x_train[BMI_COLUMN], y_train, cv_oof),
        cv_grade=cv_grade,
        cv_threshold=cv_threshold,
        test_grade=test_grade,
        test_threshold=test_threshold,
        predictions=predictions,
        y_train=y_train,
        oof_probability=cv_oof,
        y_test=y_test,
        test_probability=test_probability,
    )


# ---------------------------------------------------------------------------
# 5. 그래프
# ---------------------------------------------------------------------------

def make_grade_figure(table: pd.DataFrame, title: str):
    set_korean_font()
    x = np.arange(len(table))
    rates = table["실제 미달율(%)"].to_numpy(dtype=float)
    low = table["미달율 CI 하한(%)"].to_numpy(dtype=float)
    high = table["미달율 CI 상한(%)"].to_numpy(dtype=float)
    yerr = np.vstack([np.nan_to_num(rates - low), np.nan_to_num(high - rates)])

    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.bar(x, np.nan_to_num(rates), color=GRADE_COLORS[: len(table)], width=0.6, yerr=yerr, capsize=6)
    for xi, value, n in zip(x, rates, table["인원(명)"]):
        if not np.isnan(value):
            ax.text(xi, value + 2, f"{value:.1f}%\n(n={n:,})", ha="center", va="bottom", fontsize=10)
    ax.set_xticks(x, table["등급"].tolist())
    ax.set_ylim(0, 115)
    ax.set_ylabel("실제 미달율(%)")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


def make_roc_figure(y_test: pd.Series, probabilities: dict[str, np.ndarray]):
    set_korean_font()
    fig, ax = plt.subplots(figsize=(6, 5.5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="무작위(AUC 0.500)")
    for name, probability in probabilities.items():
        fpr, tpr, _ = roc_curve(y_test, probability)
        ax.plot(fpr, tpr, label=f"{name}(AUC {roc_auc_score(y_test, probability):.3f})")
    ax.set_xlabel("1 - 특이도")
    ax.set_ylabel("민감도(재현율)")
    ax.set_title("ROC 곡선 (Hold-out 테스트, 1회 평가)")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def make_calibration_figure(y_train: pd.Series, p_train, y_test: pd.Series, p_test):
    set_korean_font()
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharex=True, sharey=True)
    panels = [
        ("학습 데이터(교차검증)", y_train.to_numpy(), np.asarray(p_train)),
        ("Hold-out 테스트", y_test.to_numpy(), np.asarray(p_test)),
    ]
    for ax, (title, y, p) in zip(axes, panels):
        observed, predicted = calibration_curve(y, p, n_bins=CALIBRATION_BINS, strategy="uniform")
        ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="완벽한 보정")
        ax.plot(predicted, observed, marker="o", color="#4C72B0", label="모형")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("평균 예측 미달확률")
        ax.set_ylabel("실제 미달율")
        ax.set_title(f"{title} (n={len(y):,}명)")
        ax.legend(loc="upper left")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 6. Streamlit 화면
# ---------------------------------------------------------------------------

def format_metric(mean: float, sd: float | None) -> str:
    if pd.isna(mean):
        return "-"
    if sd is None or pd.isna(sd):
        return f"{mean:.4f}"
    return f"{mean:.4f} ± {sd:.4f}"


def performance_display(performance: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in performance.iterrows():
        display_row = {"모형": row["모형"], "평가 구간": row["평가 구간"]}
        for metric in METRICS:
            display_row[metric] = format_metric(row[metric], row[f"{metric}_표준편차"])
        rows.append(display_row)
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="모형을 학습하고 평가하는 중입니다...")
def load_result(input_path: str) -> AnalysisResult:
    return run_analysis(Path(input_path))


def main() -> None:
    st.title("3차 체력검정 미달 예측 모형 결과")
    st.caption("미달확률을 관리·위험·경계·안전 4개 등급으로 나누고, 등급별 실제 미달율을 검증합니다.")

    with st.sidebar:
        st.header("설정")
        input_path = st.text_input("입력 데이터 경로", value=str(PROCESSED_FITNESS_PATH))
        if st.button("다시 계산"):
            st.cache_data.clear()

    try:
        result = load_result(input_path)
    except (FileNotFoundError, ValueError) as error:
        st.error(f"분석을 실행하지 못했습니다: {error}")
        st.stop()

    st.sidebar.success(f"입력: {result.input_label}")
    if result.excluded_members:
        st.sidebar.info(f"측정 간격 {MIN_INTERVAL_DAYS}일 미만으로 제외된 장병: {result.excluded_members:,}명")

    test_auc = result.performance.loc[
        result.performance["모형"].eq(ADOPTED_MODEL_NAME) & result.performance["평가 구간"].eq(TEST_SPLIT),
        AUC_METRIC,
    ].iloc[0]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("분석 장병 수", f"{result.n_members:,}명")
    col2.metric("3차 미달 인원", f"{result.fail_count:,}명", f"{result.fail_rate * 100:.2f}%", delta_color="off")
    col3.metric("기저율(학습 미달률)", f"{result.base_rate * 100:.1f}%")
    col4.metric("등급 기준(경계/위험/관리)", "0.3 / 0.5 / 0.7")
    col5.metric("테스트 ROC-AUC", f"{test_auc:.4f}")

    st.info(
        f"채택 모형: **{ADOPTED_MODEL_NAME}** · 학습 {result.n_train:,}명 / 테스트 {result.n_test:,}명 (80/20 층화)\n\n"
        "등급: 관리 ≥ 0.7 · 위험 0.5~0.7 · 경계 0.3~0.5 · 안전 < 0.3 (면담 대상은 위험 이상)"
    )
    if not result.cv_grade_ok:
        st.warning(
            "교차검증에서 등급별 실제 미달율이 관리 > 위험 > 경계 > 안전 순으로 나오지 않습니다. "
            "테스트 결과를 보고 등급 기준을 바꾸지 말고, 교차검증 결과만으로 재검토하세요."
        )

    tabs = st.tabs([
        "검증 절차", "모형 성능", "등급 확인(교차검증)", "최종 테스트(1회)",
        "회귀계수·VIF·BMI", "ROC·보정", "개인별 예측",
    ])
    tab_steps, tab_perf, tab_cv, tab_test, tab_coef, tab_roc, tab_pred = tabs

    with tab_steps:
        st.subheader("검증 절차")
        st.markdown(
            "1. 같은 장병의 연속 측정 간격이 30일 미만이면 그 장병을 제외합니다.\n"
            "2. 학습/테스트를 80/20 층화로 분할합니다. 테스트는 분리만 합니다.\n"
            "3. 학습 데이터의 교차검증 예측 확률을 모든 모형에 대해 만듭니다.\n"
            "4. 교차검증 예측으로 등급의 단조성과 인접 등급 CI 겹침을 확인합니다.\n"
            "5. 교차검증 성능을 계산합니다.\n"
            "6. 확정된 모형과 등급 기준을 테스트에 1회만 적용합니다.\n"
            "7. 테스트 결과를 보고 등급 기준이나 모형을 바꾸지 않습니다."
        )
        st.caption(
            "등급 기준 0.3/0.5/0.7은 슬라이드 확정안입니다. 이 값이 테스트 결과를 보고 얻은 것이었다면, "
            "보고서에서는 교차검증 확인 결과를 근거로 제시하고 테스트 표는 확인용으로만 표기해야 합니다."
        )
        st.caption(
            f"기저율은 학습 데이터 미달률({result.base_rate:.4f})이며, 테스트 데이터는 계산에 쓰지 않습니다."
        )

    with tab_perf:
        st.subheader("모형 성능평가")
        st.caption(
            f"{CV_SPLIT}은 평균 ± 표준편차, {TEST_SPLIT}은 단일 값입니다. "
            f"재현율·정밀도는 미달확률 {PRIMARY_THRESHOLD} 이상 판정 기준입니다."
        )
        st.caption(
            "'-'는 정의되지 않는 값입니다. 항상 다수 클래스 기준선은 미달로 판정하는 사람이 없어 정밀도가 정의되지 않습니다. "
            "규칙 기준선은 확률이 없으므로 Brier·LogLoss가 비어 있습니다. "
            "정확도는 불균형 데이터에서 과대평가되므로 평가 척도에서 뺐습니다."
        )
        st.dataframe(performance_display(result.performance), width="stretch", hide_index=True)

    with tab_cv:
        st.subheader("등급 확인 (교차검증 예측만 사용)")
        st.caption(
            "이 표로 등급 구조가 단조로운지, 인접 등급의 CI가 구분되는지 확인합니다. "
            "기준을 바꾸는 근거로는 이 표만 사용합니다."
        )
        st.dataframe(result.cv_grade, width="stretch", hide_index=True)
        st.markdown("**임계값별 참고(교차검증)**")
        st.dataframe(result.cv_threshold, width="stretch", hide_index=True)
        st.pyplot(make_grade_figure(result.cv_grade, "등급별 실제 미달율 (교차검증)"), width="stretch")
        plt.close("all")

    with tab_test:
        st.subheader("최종 테스트 (확정 등급 기준 1회 적용)")
        st.caption(
            "교차검증에서 확인한 등급 기준을 테스트에 한 번만 적용한 결과입니다. "
            "인원이 적은 등급은 CI가 넓으니 함께 보세요."
        )
        st.dataframe(result.test_grade, width="stretch", hide_index=True)
        st.markdown("**임계값별 참고(테스트)**")
        st.dataframe(result.test_threshold, width="stretch", hide_index=True)
        st.pyplot(make_grade_figure(result.test_grade, "등급별 실제 미달율 (Hold-out 테스트)"), width="stretch")
        plt.close("all")

    with tab_coef:
        st.subheader("회귀계수·오즈비 (채택 모형)")
        st.caption("회귀계수와 오즈비는 변수를 1표준편차 올렸을 때의 값입니다.")
        st.dataframe(result.coefficients, width="stretch", hide_index=True)
        st.bar_chart(result.coefficients.set_index("변수")["회귀계수(1표준편차당)"])

        st.subheader("다중공선성 (VIF, 학습 데이터)")
        st.caption("VIF 5 미만이면 회귀계수 해석의 안정성에 큰 문제가 없다고 봅니다.")
        st.dataframe(result.vif, width="stretch", hide_index=True)

        st.subheader("BMI 구간별 실제 미달율 (교차검증 예측)")
        st.caption(
            "BMI 파생변수는 정상 범위 중앙에서 양쪽이 같은 위험이라고 가정합니다. "
            "저체중과 과체중 이상의 미달율이 대칭적이지 않다면 이 가정을 다시 검토해야 합니다."
        )
        st.dataframe(result.bmi_band_cv, width="stretch", hide_index=True)

    with tab_roc:
        st.subheader("ROC 곡선 (Hold-out 테스트, 1회 평가)")
        st.caption("ROC 곡선은 임계값과 무관합니다. 규칙 기준선은 확률이 없어 여기에 넣지 않았습니다.")
        logistic_probabilities = {
            name: probability
            for name, probability in result.test_probability.items()
            if "로지스틱" in name
        }
        st.pyplot(make_roc_figure(result.y_test, logistic_probabilities), width="stretch")
        plt.close("all")

        st.subheader("보정 곡선 (예측 확률과 실제 미달율의 일치)")
        st.caption(
            "점이 대각선 위에 있으면 실제 미달이 예측보다 많고(과소예측), 아래에 있으면 예측이 실제보다 높습니다(과대예측). "
            "등급 기준은 확률 값에 의존하므로 특히 0.5 이상 구간의 일치를 확인하세요."
        )
        st.pyplot(
            make_calibration_figure(
                result.y_train, result.oof_probability,
                result.y_test, result.test_probability[ADOPTED_MODEL_NAME],
            ),
            width="stretch",
        )
        plt.close("all")

    with tab_pred:
        st.subheader("개인별 예측 확률과 등급")
        predictions = result.predictions
        split_options = sorted(predictions["구분"].unique())
        grade_options = list(GRADE_ORDER)

        selected_split = st.multiselect("구분", options=split_options, default=split_options)
        selected_grade = st.multiselect("등급", options=grade_options, default=grade_options)
        filtered = predictions[predictions["구분"].isin(selected_split) & predictions["등급"].isin(selected_grade)]

        st.write(f"조회 결과: {len(filtered):,}명")
        st.dataframe(filtered, width="stretch", hide_index=True)
        st.download_button(
            "개인별 예측 CSV 다운로드",
            data=predictions.to_csv(index=False).encode("utf-8-sig"),
            file_name="FAIL_PROBABILITY_PREDICTION.csv",
            mime="text/csv",
        )


main()