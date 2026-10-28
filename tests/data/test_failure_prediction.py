"""장병별 다음 회차 미달 확률 예측(data/scripts/analysis/failure_prediction)을 테스트합니다.

실제 모델 파일 대신 가상 측정으로 모델을 학습해 예측까지 이어 봅니다.
"""

import numpy as np
import pandas as pd

from data.scripts.analysis.failure_prediction.predict_failure_probability import run as predict_run
from data.scripts.analysis.failure_prediction.train_failure_probability_model import run as train_run
from data.scripts.paths import DEFINITION_SOLDIER_FAILURE_PROBABILITY
from data.scripts.utils import load_definition_columns, read_text_csv

ROUND_DATES = ("20240101", "20240301", "20240601")


def make_measurements(soldier_count: int = 120, seed: int = 0) -> pd.DataFrame:
    """장병마다 3회 측정한 가상 데이터를 만듭니다. 값이 등급 하한 근처에 퍼져 미달·통과가 섞입니다."""
    rng = np.random.default_rng(seed)
    rows = []
    measure_id = 1
    for soldier in range(soldier_count):
        for date in ROUND_DATES:
            rows.append({
                "MESURE_ID": measure_id,
                "SOLDIER_ID": f"S{soldier:04d}",
                "MESURE_DE": date,
                "STRENGTH": round(rng.normal(52, 6), 1),
                "ENDURANCE": int(rng.integers(30, 60)),
                "CARDIO": round(rng.normal(42, 4), 1),
                "FLEXIBILITY": round(rng.normal(6, 5), 1),
                "BMI": round(rng.normal(23, 3), 2),
            })
            measure_id += 1
    return pd.DataFrame(rows)


def test_prediction_writes_one_probability_per_eligible_soldier(tmp_path):
    """측정 3회·간격 규칙을 만족하는 장병마다 확률 한 행을 정의서대로 저장하고, 대상이 아닌 장병은 빼는지 확인합니다."""
    training = make_measurements()
    training_path, model_path = tmp_path / "training.csv", tmp_path / "model.joblib"
    training.to_csv(training_path, index=False, encoding="utf-8-sig")
    train_run(training_path, model_path)

    # 예측 입력에는 측정이 2회뿐인 장병과 측정 간격이 30일 미만인 장병을 더한다.
    extra = make_measurements(2, seed=1).assign(SOLDIER_ID=lambda df: df["SOLDIER_ID"].map({"S0000": "SHORT", "S0001": "GAP"}))
    extra = extra[~((extra["SOLDIER_ID"] == "SHORT") & (extra["MESURE_DE"] == ROUND_DATES[2]))]
    extra.loc[(extra["SOLDIER_ID"] == "GAP") & (extra["MESURE_DE"] == ROUND_DATES[1]), "MESURE_DE"] = "20240110"
    extra["MESURE_ID"] = range(100_000, 100_000 + len(extra))
    input_path, output_path = tmp_path / "input.csv", tmp_path / "failure.csv"
    pd.concat([training, extra]).to_csv(input_path, index=False, encoding="utf-8-sig")

    predict_run(input_path, model_path, DEFINITION_SOLDIER_FAILURE_PROBABILITY, output_path)

    result = read_text_csv(output_path)
    assert result.columns.tolist() == load_definition_columns(DEFINITION_SOLDIER_FAILURE_PROBABILITY)
    assert result["SOLDIER_ID"].tolist() == sorted(training["SOLDIER_ID"].unique())
    probability = result["FAILURE_PROBABILITY"].astype(float)
    assert probability.between(0, 1).all()
    # 정의서의 DECIMAL(5,4)에 맞춰 소수 4자리 이내
    assert (result["FAILURE_PROBABILITY"].str.split(".").str[1].str.len().fillna(0) <= 4).all()
