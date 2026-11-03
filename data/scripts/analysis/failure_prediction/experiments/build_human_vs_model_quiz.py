"""사람과 미달 예측 모델의 3차 미달 예측 실험용 문항 페이지를 만듭니다.

측정 10,746건에서 시드로 무작위로 뽑은 순서대로 그 측정의 장병을 골라(같은 장병은 한 번만) 100문항을 만들고,
장병의 1·2차 측정값, 3차 미달 정답, 모델 매개변수를 템플릿(human_vs_model_quiz_template.html)에 채워 저장합니다.
페이지는 브라우저에서 같은 1·2차 값으로 모델을 계산하므로 모델 시간도 같은 기기에서 잽니다.

- 정답: 3차 측정에서 3등급 하한 미만 종목이 2개 이상이면 미달(train_failure_probability_model과 같은 규칙).
- 모델 판정: 미달 확률이 THRESHOLD 이상이면 미달.
- 출력은 측정값이 들어 있으므로 Git에서 제외되는 data/intermediate/human_vs_model/에 저장합니다.
- 실험 계획은 같은 폴더의 human_vs_model_experiment.md.

실행: python data/scripts/analysis/failure_prediction/experiments/build_human_vs_model_quiz.py [--seed 20261103] [--count 100]
"""

import argparse
import base64
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from config import INTERMEDIATE_DIR
from data.scripts.analysis.failure_prediction.train_failure_probability_model import (
    MEMBER_ID_COLUMN,
    apply_interval_rule,
    build_dataset,
    load_measures,
)
from fitness_standards import FITNESS_EXERCISES, grade_cut
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import FAILURE_MODEL_PATH, PROCESSED_FITNESS_PATH

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).with_name("human_vs_model_quiz_template.html")
OUTPUT_PATH = INTERMEDIATE_DIR / "human_vs_model" / "human_vs_model_quiz.html"
PLACEHOLDER = "/*__QUIZ_DATA__*/"
DEFAULT_SEED = 20261103
DEFAULT_COUNT = 100
THRESHOLD = 0.5
EVENT_LABELS = {"STRENGTH": ("근력", "%"), "ENDURANCE": ("근지구력", "회"), "CARDIO": ("심폐", "VO₂max"), "FLEXIBILITY": ("유연성", "cm")}
COLUMNS = [*FITNESS_EXERCISES, "BMI"]


def sample_soldiers(measures: pd.DataFrame, eligible: pd.Index, count: int, seed: int) -> list[str]:
    """측정을 무작위 순서로 훑으며 그 측정의 장병을 모읍니다(같은 장병은 한 번, 모델 대상 장병만)."""
    order = np.random.default_rng(seed).permutation(len(measures))
    chosen: list[str] = []
    for soldier in measures[MEMBER_ID_COLUMN].to_numpy()[order]:
        if soldier in eligible and soldier not in chosen:
            chosen.append(soldier)
            if len(chosen) == count:
                return chosen
    raise ValueError(f"모델 대상 장병이 {count}명보다 적습니다.")


def round_values(measures: pd.DataFrame, soldiers: list[str]) -> dict[str, list[list[float]]]:
    """장병별 1·2차 측정값(종목 4개 + BMI)을 측정일 순서로 돌려줍니다."""
    ordered = measures.sort_values([MEMBER_ID_COLUMN, "MESURE_DE", "MESURE_ID"], kind="stable")
    by_soldier = {sid: group[COLUMNS].to_numpy(float).tolist() for sid, group in ordered.groupby(MEMBER_ID_COLUMN)}
    return {sid: by_soldier[sid][:2] for sid in soldiers}


def browser_probability(model_params: dict, r1: list[float], r2: list[float]) -> float:
    """템플릿의 JavaScript와 같은 식(확인용)."""
    x = [*r2[:4], *(np.array(r2[:4]) - np.array(r1[:4])), (r2[4] - model_params["bmiCenter"]) ** 2]
    z = model_params["intercept"] + sum(c * (v - m) / s for c, v, m, s in zip(model_params["coef"], x, model_params["mean"], model_params["scale"]))
    return 1 / (1 + np.exp(-z))


def encode_answers(answers: list[int]) -> str:
    """정답을 문항 번호로 섞어 base64로 싣습니다(템플릿이 같은 식으로 풉니다)."""
    return base64.b64encode(bytes((a ^ ((i * 37 + 11) & 255)) & 255 for i, a in enumerate(answers))).decode("ascii")


def run(input_path: Path, model_path: Path, output_path: Path, seed: int = DEFAULT_SEED, count: int = DEFAULT_COUNT) -> Path:
    """문항 페이지를 만들어 output_path에 저장하고 그 경로를 돌려줍니다."""
    measures = load_measures(input_path)
    kept, excluded = apply_interval_rule(measures)
    features, failed = build_dataset(kept)
    bundle = joblib.load(model_path)
    scaler, logistic = bundle["model"][0], bundle["model"][-1]
    if list(features.columns) != bundle["feature_columns"]:
        raise ValueError("모델의 입력 변수와 지금 만든 입력 변수가 다릅니다.")
    model_params = {
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "coef": logistic.coef_[0].tolist(), "intercept": float(logistic.intercept_[0]),
        "bmiCenter": bundle["bmi_center"], "threshold": THRESHOLD,
    }

    soldiers = sample_soldiers(measures, features.index, count, seed)
    values = round_values(kept, soldiers)
    answers = failed.loc[soldiers].astype(int).tolist()

    # 브라우저 식과 sklearn이 같은 확률을 내는지 확인
    sklearn_p = bundle["model"].predict_proba(features.loc[soldiers])[:, 1]
    browser_p = np.array([browser_probability(model_params, *values[s]) for s in soldiers])
    if not np.allclose(sklearn_p, browser_p, rtol=0, atol=1e-9):
        raise ValueError(f"브라우저 식과 모델 확률이 다릅니다(최대 차이 {np.abs(sklearn_p - browser_p).max():.3g}).")
    all_p = bundle["model"].predict_proba(features)[:, 1]

    data = {
        "seed": seed, "nTrain": int(bundle["n_train"]),
        "events": [{"key": e, "label": EVENT_LABELS[e][0], "unit": EVENT_LABELS[e][1], "cuts": [grade_cut(e, g) for g in (1, 2, 3)]}
                   for e in FITNESS_EXERCISES],
        "items": [{"r1": values[s][0], "r2": values[s][1]} for s in soldiers],
        "key": encode_answers(answers),
        "model": model_params,
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"템플릿에 {PLACEHOLDER}가 정확히 한 번 있어야 합니다.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # </script>가 데이터 안에 들어가지 않도록 '<'를 이스케이프
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    output_path.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8")

    # 실험 참가자가 볼 수 있으므로 문항의 정답 분포나 문항에서의 모델 성적은 남기지 않는다(전체 장병 기준만).
    all_fail, all_pred = failed.to_numpy() == 1, all_p >= THRESHOLD
    logger.info("모델 대상 장병 %s명(측정 간격 규칙으로 제외 %s명), 문항 %s개(시드 %s)", f"{len(features):,}", excluded, count, seed)
    logger.info("전체 장병 기준 모델 Precision %.1f%%, 재현율 %.1f%%",
                (all_pred & all_fail).sum() / all_pred.sum() * 100, (all_pred & all_fail).sum() / all_fail.sum() * 100)
    logger.info("저장: %s", display_path(output_path))
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = parser.parse_args()
    setup_logging(caller_name(__file__))
    run(PROCESSED_FITNESS_PATH, FAILURE_MODEL_PATH, OUTPUT_PATH, args.seed, args.count)


if __name__ == "__main__":
    main()
