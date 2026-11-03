"""체력 후속조치 기록 25건을 입력하는 데 걸리는 시간을 재는 실험 페이지를 만듭니다.

대시보드 7번 화면(체력 지도·후속조치 관리)의 후속조치 대상(다음 체력검정 미달 확률 30% 이상)에서
시드로 장병 25명을 무작위로 골라, 화면과 같은 장병 정보·최신 측정과 같은 입력 항목·검사 규칙을
템플릿(followup_entry_task_template.html)에 채워 저장합니다. 입력한 기록은 페이지 안에만 있고 어디에도 저장되지 않습니다.

- 입력 항목·검사 규칙은 `dashboard/py/management_store.py`의 `FIELDS['followup_records']`·`validate`와 같습니다.
- 출력은 장병 정보가 들어 있으므로 Git에서 제외되는 data/intermediate/human_experiments/에 저장합니다.
- 실험 계획은 같은 폴더의 README.md.

실행: python data/scripts/analysis/human_experiments/build_followup_entry_task.py [--seed 1103] [--count 25]
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config import INTERMEDIATE_DIR
from fitness_standards import FITNESS_EXERCISES, grade_cut
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    PROCESSED_FITNESS_PATH,
    PROCESSED_FITNESS_TYPE_PATH,
    PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
    PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).with_name("followup_entry_task_template.html")
OUTPUT_PATH = INTERMEDIATE_DIR / "human_experiments" / "followup_entry_task.html"
PLACEHOLDER = "/*__TASK_DATA__*/"
DEFAULT_SEED = 1103
DEFAULT_COUNT = 25
# 대시보드 followup_probability와 같은 경계(30% 이상이 후속조치 대상)
RISK_BINS = [-float("inf"), .3, .5, .7, float("inf")]
RISK_LEVELS = ["안전", "경계1등급", "경계2등급", "경계3등급"]
FOLLOWUP_THRESHOLD = .3
EVENT_LABELS = {"STRENGTH": ("근력", "%"), "ENDURANCE": ("근지구력", "회"), "CARDIO": ("심폐지구력", "VO₂max"), "FLEXIBILITY": ("유연성", "cm")}


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def latest_measurements(measures: pd.DataFrame) -> pd.DataFrame:
    """장병별 최신 측정(측정일 최대, 같은 날이면 MESURE_ID 최대) 1행씩."""
    ordered = measures.assign(_id=pd.to_numeric(measures.MESURE_ID)).sort_values(["SOLDIER_ID", "MESURE_DE", "_id"], kind="stable")
    return ordered.drop_duplicates("SOLDIER_ID", keep="last").drop(columns="_id")


def build_population() -> pd.DataFrame:
    """후속조치 대상 장병의 신상·확률·위험 등급·최신 측정·체력유형."""
    people = read(SYNTHETIC_PERSONNEL_PATH).merge(read(PROCESSED_SOLDIER_FAILURE_PROBABILITY_PATH), on="SOLDIER_ID")
    people["FAILURE_PROBABILITY"] = pd.to_numeric(people.FAILURE_PROBABILITY)
    people = people.loc[people.FAILURE_PROBABILITY.ge(FOLLOWUP_THRESHOLD)].copy()
    people["RISK_LEVEL"] = pd.cut(people.FAILURE_PROBABILITY, RISK_BINS, labels=RISK_LEVELS, right=False).astype(str)
    latest = latest_measurements(read(PROCESSED_FITNESS_PATH))
    classified = read(PROCESSED_MEASUREMENT_CLASSIFICATION_PATH)[["MESURE_ID", "AVERAGE_PERCENTILE_GRADE", "CLUSTER"]]
    types = read(PROCESSED_FITNESS_TYPE_PATH)[["AVERAGE_PERCENTILE_GRADE", "CLUSTER", "TYPE_NAME"]]
    latest = latest.merge(classified, on="MESURE_ID", how="left").merge(types, on=["AVERAGE_PERCENTILE_GRADE", "CLUSTER"], how="left")
    return people.merge(latest, on="SOLDIER_ID", how="left")


def run(output_path: Path, seed: int = DEFAULT_SEED, count: int = DEFAULT_COUNT) -> Path:
    """실험 페이지를 만들어 output_path에 저장하고 그 경로를 돌려줍니다."""
    population = build_population().sort_values("SOLDIER_ID", kind="stable").reset_index(drop=True)
    if len(population) < count:
        raise ValueError(f"후속조치 대상 장병이 {count}명보다 적습니다.")
    chosen = population.iloc[np.random.default_rng(seed).choice(len(population), size=count, replace=False)]
    # 대시보드 명단과 같이 미달 확률이 높은 순서
    chosen = chosen.sort_values("FAILURE_PROBABILITY", ascending=False, kind="stable")

    soldiers = [{
        "id": row.SOLDIER_ID, "name": row.SOLDIER_NAME, "rank": row.RANK_NAME, "unit": row.UNIT_NAME,
        "probability": float(row.FAILURE_PROBABILITY), "risk": row.RISK_LEVEL,
        "grade": row.AVERAGE_PERCENTILE_GRADE, "type": row.TYPE_NAME,
        "date": f"{row.MESURE_DE[:4]}-{row.MESURE_DE[4:6]}-{row.MESURE_DE[6:]}", "age": row.AGE, "bmi": row.BMI,
        "values": [getattr(row, e) for e in FITNESS_EXERCISES],
    } for row in chosen.itertuples()]
    data = {
        "seed": seed, "nPopulation": len(population), "soldiers": soldiers,
        "events": [{"label": EVENT_LABELS[e][0], "unit": EVENT_LABELS[e][1], "cut": grade_cut(e, 3)} for e in FITNESS_EXERCISES],
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"템플릿에 {PLACEHOLDER}가 정확히 한 번 있어야 합니다.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    output_path.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8")
    logger.info("후속조치 대상 %s명 중 %s명(시드 %s)", f"{len(population):,}", count, seed)
    logger.info("저장: %s", display_path(output_path))
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = parser.parse_args()
    setup_logging(caller_name(__file__))
    run(OUTPUT_PATH, args.seed, args.count)


if __name__ == "__main__":
    main()
