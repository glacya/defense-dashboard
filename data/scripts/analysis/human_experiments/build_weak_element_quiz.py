"""사람과 판정 알고리즘의 취약 체력 요소 식별 실험용 문항 페이지를 만듭니다.

측정 10,746건에서 시드로 측정 100건을 무작위로 뽑아(같은 장병의 측정이 여러 번 나와도 됨) 문항을 만들고,
측정값 6개(근력·근지구력·심폐지구력·유연성·BMI·체지방률)와 취약 여부 정답을 템플릿(weak_element_quiz_template.html)에 채워 저장합니다.
페이지는 브라우저에서 같은 값으로 알고리즘을 실행하므로 알고리즘 시간도 같은 기기에서 잽니다.

- 취약 기준(대시보드 `add_deficiency_flags`와 같음): 체력 4종목은 3등급 하한 미만,
  BMI·체지방률은 `fitness_standards.RANGE_STANDARDS`의 정상 범위 밖.
- 출력은 측정값이 들어 있으므로 Git에서 제외되는 data/intermediate/human_experiments/에 저장합니다.
- 실험 계획은 같은 폴더의 README.md.

실행: python data/scripts/analysis/human_experiments/build_weak_element_quiz.py [--seed 1103] [--count 100]
"""

import argparse
import base64
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config import INTERMEDIATE_DIR
from fitness_standards import FITNESS_EXERCISES, RANGE_STANDARDS, grade_cut
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import PROCESSED_FITNESS_PATH

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).with_name("weak_element_quiz_template.html")
OUTPUT_PATH = INTERMEDIATE_DIR / "human_experiments" / "weak_element_quiz.html"
PLACEHOLDER = "/*__QUIZ_DATA__*/"
DEFAULT_SEED = 1103
DEFAULT_COUNT = 100
ELEMENTS = [*FITNESS_EXERCISES, *RANGE_STANDARDS]
LABELS = {
    "STRENGTH": ("근력", "%"), "ENDURANCE": ("근지구력", "회"), "CARDIO": ("심폐지구력", "VO₂max"),
    "FLEXIBILITY": ("유연성", "cm"), "BMI": ("BMI", "kg/m²"), "BODY_FAT_PERCENTAGE": ("체지방률", "%"),
}


def criterion(element: str) -> dict:
    """요소의 취약 기준을 템플릿이 쓰는 모양으로 돌려줍니다."""
    if element in FITNESS_EXERCISES:
        return {"kind": "cut", "cut": grade_cut(element, 3)}
    low, low_inclusive, high, high_inclusive = RANGE_STANDARDS[element]
    return {"kind": "range", "low": low, "lowInclusive": low_inclusive, "high": high, "highInclusive": high_inclusive}


def is_weak(value: float, rule: dict) -> bool:
    """템플릿의 JavaScript와 같은 식으로 취약 여부를 판정합니다."""
    if rule["kind"] == "cut":
        return value < rule["cut"]
    below = value < rule["low"] if rule["lowInclusive"] else value <= rule["low"]
    above = value > rule["high"] if rule["highInclusive"] else value >= rule["high"]
    return below or above


def weak_flags(measures: pd.DataFrame) -> pd.DataFrame:
    """대시보드와 같은 방식(pandas 비교)으로 요소별 취약 여부를 계산합니다."""
    flags = pd.DataFrame(index=measures.index)
    for element in ELEMENTS:
        values = pd.to_numeric(measures[element])
        if element in FITNESS_EXERCISES:
            flags[element] = values.lt(grade_cut(element, 3))
        else:
            low, low_inclusive, high, high_inclusive = RANGE_STANDARDS[element]
            below = values.lt(low) if low_inclusive else values.le(low)
            above = values.gt(high) if high_inclusive else values.ge(high)
            flags[element] = below | above
    return flags


def encode_answers(flags: pd.DataFrame) -> str:
    """문항마다 요소 6개의 취약 여부를 한 바이트(비트)로 묶고 문항 번호로 섞어 base64로 싣습니다."""
    packed = [sum(int(flag) << bit for bit, flag in enumerate(row)) for row in flags.to_numpy()]
    return base64.b64encode(bytes((p ^ ((i * 53 + 29) & 255)) & 255 for i, p in enumerate(packed))).decode("ascii")


def run(input_path: Path, output_path: Path, seed: int = DEFAULT_SEED, count: int = DEFAULT_COUNT) -> Path:
    """문항 페이지를 만들어 output_path에 저장하고 그 경로를 돌려줍니다."""
    measures = pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    measures = measures.sort_values("MESURE_ID", key=pd.to_numeric, kind="stable").reset_index(drop=True)
    chosen = measures.iloc[np.random.default_rng(seed).choice(len(measures), size=count, replace=False)]

    rules = {element: criterion(element) for element in ELEMENTS}
    flags = weak_flags(chosen)
    # 화면에 보이는 문자열을 그대로 숫자로 바꿔 판정해도 pandas 결과와 같은지 확인
    browser = [[is_weak(float(chosen.at[i, e]), rules[e]) for e in ELEMENTS] for i in chosen.index]
    if not np.array_equal(np.array(browser), flags.to_numpy()):
        raise ValueError("브라우저 식과 대시보드 기준의 판정이 다릅니다.")

    data = {
        "seed": seed, "nMeasures": len(measures),
        "elements": [{"key": e, "label": LABELS[e][0], "unit": LABELS[e][1], "rule": rules[e]} for e in ELEMENTS],
        "items": [[chosen.at[i, e] for e in ELEMENTS] for i in chosen.index],
        "key": encode_answers(flags),
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"템플릿에 {PLACEHOLDER}가 정확히 한 번 있어야 합니다.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # </script>가 데이터 안에 들어가지 않도록 '<'를 이스케이프
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    output_path.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8")

    # 실험 참가자가 볼 수 있으므로 문항의 정답 분포는 남기지 않는다.
    logger.info("측정 %s건 중 %s건(시드 %s)으로 문항을 만들었습니다.", f"{len(measures):,}", count, seed)
    logger.info("저장: %s", display_path(output_path))
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = parser.parse_args()
    setup_logging(caller_name(__file__))
    run(PROCESSED_FITNESS_PATH, OUTPUT_PATH, args.seed, args.count)


if __name__ == "__main__":
    main()
