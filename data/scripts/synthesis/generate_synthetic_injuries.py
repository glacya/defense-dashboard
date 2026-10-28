"""가상 장병마다 기대 부상 건수(Poisson λ)로 부상 건수를 뽑아 부상 기록을 만듭니다.

부상 부위와 부위별 예방 가능 비율은 선행 논문 표(Table 4)의 부위별 부상 빈도를 따르고,
결과는 SOLDIER_INJURY_DEFINITION.csv 구성으로 저장합니다. 장병별 총 부상 건수의 합은 Poisson(Σλ)를 따릅니다.
"""

import argparse
import logging
import random
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_SOLDIER_INJURY,
    LINKED_INJURY_RISK_PATH,
    SYNTHETIC_INJURY_PATH,
)
from data.scripts.synthesis.link_fitness_and_injury_risk import (
    EXPECTED_COUNT_COLUMN,
    INJURIES_PER_PERSON_YEAR,
    SOLDIER_ID_COLUMN,
)
from data.scripts.utils import non_negative_float, positive_int, read_text_csv, write_by_definition

logger = logging.getLogger(__name__)

DEFAULT_SEED = 42

# 선행 논문 Table 4의 부위별 부상 빈도: (상위 부위, 세부 부위, 전체 빈도, 예방 가능 빈도)
INJURY_LOCATION_DATA = [
    ("Upper", "Head", 1, 0),
    ("Upper", "Shoulder", 68, 25),
    ("Upper", "Arm", 11, 0),
    ("Upper", "Elbow", 6, 2),
    ("Upper", "Forearm", 3, 1),
    ("Upper", "Wrist", 24, 6),
    ("Upper", "Hand/finger", 73, 8),
    ("Upper", "Ribs", 1, 0),
    ("Upper", "Back lower", 19, 13),
    ("Lower", "Pelvic region", 9, 2),
    ("Lower", "Hip", 3, 2),
    ("Lower", "Leg upper", 12, 4),
    ("Lower", "Knee", 183, 121),
    ("Lower", "Leg lower", 22, 7),
    ("Lower", "Ankle", 157, 108),
    ("Lower", "Foot/toe", 23, 4),
    ("Lower", "Not specified", 1, 0),
]
# CSV 값은 한글로 저장한다(컬럼 이름만 영문).
CATEGORY_NAMES = {"Upper": "상지(상체)", "Lower": "하지(하체)"}
LOCATION_NAMES = {
    "Head": "머리",
    "Shoulder": "어깨",
    "Arm": "팔",
    "Elbow": "팔꿈치",
    "Forearm": "전완",
    "Wrist": "손목",
    "Hand/finger": "손/손가락",
    "Ribs": "갈비뼈",
    "Back lower": "요통/요추",
    "Pelvic region": "골반",
    "Hip": "고관절",
    "Leg upper": "허벅지",
    "Knee": "무릎",
    "Leg lower": "종아리",
    "Ankle": "발목",
    "Foot/toe": "발/발가락",
    "Not specified": "미지정",
}
LOCATION_COUNT = len(INJURY_LOCATION_DATA)
LOCATION_PROBABILITIES = np.array([row[2] for row in INJURY_LOCATION_DATA], dtype=float)
LOCATION_PROBABILITIES /= LOCATION_PROBABILITIES.sum()
PREVENTABLE_RATIOS = np.array([row[3] / row[2] for row in INJURY_LOCATION_DATA])

SEVERITY_LEVELS = ["경증", "중등증", "중증"]
SEVERITY_WEIGHTS = [0.55, 0.39, 0.06]
INJURY_ID_COLUMN = "INJURY_ID"


def _read_lambdas(df_soldiers: pd.DataFrame, injuries_per_person: float) -> tuple[np.ndarray, bool]:
    """장병별 λ와, λ가 장병 데이터에 있었는지를 반환합니다. 없으면 모두 injuries_per_person입니다."""
    if EXPECTED_COUNT_COLUMN not in df_soldiers.columns:
        return np.full(len(df_soldiers), injuries_per_person), False
    lambdas = pd.to_numeric(df_soldiers[EXPECTED_COUNT_COLUMN], errors="coerce").to_numpy(dtype=float)
    # Poisson 평균은 1을 넘어도 되므로 0 이상인지만 본다.
    if not np.isfinite(lambdas).all() or (lambdas < 0).any():
        raise ValueError(f"{EXPECTED_COUNT_COLUMN}(Poisson λ)는 0 이상의 유효한 숫자여야 합니다.")
    return lambdas, True


def _choose_injured_soldiers(
    lambdas: np.ndarray,
    weighted: bool,
    injury_count: int | None,
) -> np.ndarray:
    """부상 한 건마다 다친 장병의 위치(행 번호)를 반환합니다."""
    n_total = len(lambdas)
    if injury_count is None:
        # 장병마다 Poisson(λ)로 건수를 뽑아 반복 부상도 허용한다. 같은 부위를 두 번 고르지
        # 않으므로 부위 수로 자르지만, λ가 작아 실제로 잘리는 일은 사실상 없다.
        counts = np.minimum(np.random.poisson(lambdas), LOCATION_COUNT)
        selected = np.repeat(np.arange(n_total), counts)
        np.random.shuffle(selected)
        return selected

    if injury_count < 0:
        raise ValueError("부상 건수는 0 이상이어야 합니다.")
    if injury_count and n_total == 0:
        raise ValueError("장병 데이터가 비어 있으면 부상 기록을 생성할 수 없습니다.")
    if injury_count > n_total * LOCATION_COUNT:
        raise ValueError(
            f"부상 건수는 장병 수와 부상 위치 수의 곱({n_total * LOCATION_COUNT})을 초과할 수 없습니다."
        )
    # 정확히 injury_count건을 λ에 비례해(λ가 없으면 균등하게) 한 건씩 나눈다.
    assigned = np.zeros(n_total, dtype=int)
    selected = []
    for _ in range(injury_count):
        eligible = np.flatnonzero(assigned < LOCATION_COUNT)
        if weighted:
            weights = lambdas[eligible]
            if weights.sum() == 0:
                raise ValueError("기대 부상 건수가 0인 장병만 남아 지정한 부상 건수를 채울 수 없습니다.")
            soldier = int(np.random.choice(eligible, p=weights / weights.sum()))
        else:
            soldier = int(np.random.choice(eligible))
        assigned[soldier] += 1
        selected.append(soldier)
    return np.array(selected, dtype=int)


def generate_injury_data(
    df_soldiers: pd.DataFrame,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
    seed: int = DEFAULT_SEED,
    injury_count: int | None = None,
) -> pd.DataFrame:
    """장병 데이터로 부상 기록(SOLDIER_ID, INJURY_CATEGORY, INJURY_LOCATION, PREVENTABILITY, SEVERITY)을 만듭니다.

    - 장병마다 부상 건수를 Poisson(λ)에서 따로 뽑으므로 총 건수는 Poisson(Σλ)를 따릅니다.
    - λ는 EXPECTED_INJURY_COUNT_PER_YEAR 컬럼(개인별 연간 기대 부상 건수)이고, 컬럼이 없으면 모든 장병에게
      injuries_per_person(기본 1인당 연간 0.3건)을 씁니다.
    - injury_count를 주면 Poisson 대신 정확히 그 건수를 λ에 비례해 장병에게 나눕니다.
    - 한 장병이 같은 부위를 두 번 다치지 않도록 부위는 장병마다 겹치지 않게 고릅니다.

    Raises:
        ValueError: SOLDIER_ID가 없거나, λ나 injuries_per_person이 음수이거나, injury_count를 채울 수 없을 때
    """
    if SOLDIER_ID_COLUMN not in df_soldiers.columns:
        raise ValueError(f"장병 데이터에 필수 컬럼이 없습니다: {SOLDIER_ID_COLUMN}")
    if not np.isfinite(injuries_per_person) or injuries_per_person < 0:
        raise ValueError("injuries_per_person은 0 이상의 숫자여야 합니다.")
    np.random.seed(seed)
    python_rng = random.Random(seed)

    lambdas, weighted = _read_lambdas(df_soldiers, injuries_per_person)
    injured = _choose_injured_soldiers(lambdas, weighted, injury_count)

    location_indices = []
    used_locations: dict[int, set[int]] = {}
    for soldier in injured:
        used = used_locations.setdefault(int(soldier), set())
        available = np.array([index for index in range(LOCATION_COUNT) if index not in used])
        probabilities = LOCATION_PROBABILITIES[available] / LOCATION_PROBABILITIES[available].sum()
        location = int(np.random.choice(available, p=probabilities))
        used.add(location)
        location_indices.append(location)

    categories = [INJURY_LOCATION_DATA[index][0] for index in location_indices]
    locations = [INJURY_LOCATION_DATA[index][1] for index in location_indices]
    preventable = [python_rng.random() < PREVENTABLE_RATIOS[index] for index in location_indices]
    severities = np.random.choice(SEVERITY_LEVELS, size=len(injured), p=SEVERITY_WEIGHTS)

    return pd.DataFrame({
        SOLDIER_ID_COLUMN: df_soldiers[SOLDIER_ID_COLUMN].to_numpy()[injured],
        "INJURY_CATEGORY": [CATEGORY_NAMES[category] for category in categories],
        "INJURY_LOCATION": [LOCATION_NAMES[location] for location in locations],
        "PREVENTABILITY": ["Y" if flag else "N" for flag in preventable],
        "SEVERITY": severities,
    })


def build_injury_records(injuries: pd.DataFrame) -> pd.DataFrame:
    """부상 기록 맨 앞에 부상식별번호(INJURY_ID, 1부터)를 붙입니다."""
    records = injuries.reset_index(drop=True)
    records.insert(0, INJURY_ID_COLUMN, np.arange(1, len(records) + 1))
    return records


def _attach_soldiers(df_soldiers: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """부상 기록에 장병의 지역·부대·계급·전후방 구분을 붙입니다."""
    return injuries.merge(df_soldiers, on=SOLDIER_ID_COLUMN, how="left", suffixes=("", "_SOLDIER"))


def get_injury_location_summary(injuries: pd.DataFrame) -> pd.DataFrame:
    """부위별 부상 건수와 비율을 많은 순으로 반환합니다."""
    summary = injuries.groupby(["INJURY_CATEGORY", "INJURY_LOCATION"]).size().reset_index(name="부상건수")
    summary["비율(%)"] = (summary["부상건수"] / len(injuries) * 100).round(1)
    return summary.sort_values(by="부상건수", ascending=False)


def get_unit_injury_summary(df_soldiers: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """부대별 전체 인원, 부상 건수, 예방 가능·중증 부상 건수와 비율을 반환합니다."""
    injured = _attach_soldiers(df_soldiers, injuries)
    summary = df_soldiers.groupby("UNIT_NAME").size().to_frame(name="전체인원")
    injury_summary = injured.groupby("UNIT_NAME").agg(
        총_부상건수=(SOLDIER_ID_COLUMN, "count"),
        예방가능_건수=("PREVENTABILITY", lambda values: (values == "Y").sum()),
        중증_부상건수=("SEVERITY", lambda values: (values == "중증").sum()),
    ).reindex(summary.index, fill_value=0)
    summary = summary.join(injury_summary)
    summary["예방가능_비율(%)"] = (
        summary["예방가능_건수"] / summary["총_부상건수"].replace(0, 1) * 100
    ).round(1)
    summary["부상률(%)"] = (summary["총_부상건수"] / summary["전체인원"] * 100).round(1)
    return summary.reset_index().sort_values(by="총_부상건수", ascending=False)


def get_region_injury_summary(df_soldiers: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """지역별 전체 인원, 부상 건수·인원, 지역 안 부상률, 전체 부상자 중 비율을 반환합니다."""
    injured = _attach_soldiers(df_soldiers, injuries)
    summary = df_soldiers.groupby("REGION_NAME").size().to_frame(name="전체인원")
    summary["부상건수"] = injured.groupby("REGION_NAME").size().reindex(summary.index, fill_value=0)
    summary["부상인원"] = (
        injured.groupby("REGION_NAME")[SOLDIER_ID_COLUMN].nunique().reindex(summary.index, fill_value=0)
    )
    summary["지역내_부상률(%)"] = (summary["부상인원"] / summary["전체인원"] * 100).round(1)
    total_injured = injuries[SOLDIER_ID_COLUMN].nunique()
    summary["전체부상중_비율(%)"] = (
        (summary["부상인원"] / total_injured * 100).round(1) if total_injured else 0.0
    )
    return summary.sort_values(by="부상인원", ascending=False).reset_index()


def get_front_rear_summary(df_soldiers: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """전방·후방별 부상 건수와 전체 부상 중 비율을 반환합니다."""
    injured = _attach_soldiers(df_soldiers, injuries)
    counts = injured["FRONT_REAR_CLASSIFICATION"].value_counts().reindex(["전방", "후방"], fill_value=0)
    summary = counts.rename_axis("구분").reset_index(name="부상건수")
    summary["비율(%)"] = (summary["부상건수"] / len(injuries) * 100).round(1) if len(injuries) else 0.0
    return summary


def get_repeat_injury_soldiers(injuries: pd.DataFrame) -> pd.DataFrame:
    """부상 기록이 두 건 이상인 장병과 건수를 반환합니다."""
    counts = injuries.groupby(SOLDIER_ID_COLUMN).size().reset_index(name="부상건수")
    return counts[counts["부상건수"] > 1].sort_values(by="부상건수", ascending=False)


def get_unit_location_crosstab(df_soldiers: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """부대 × 세부 부상 부위 교차표를 합계와 함께 반환합니다."""
    injured = _attach_soldiers(df_soldiers, injuries)
    return pd.crosstab(injured["UNIT_NAME"], injured["INJURY_LOCATION"], margins=True, margins_name="합계")


def get_specific_unit_report(df_soldiers: pd.DataFrame, injuries: pd.DataFrame, unit_name: str) -> pd.DataFrame:
    """한 부대의 부위·심각도·예방 가능 여부별 부상 건수를 반환합니다. 부상이 없으면 빈 표입니다."""
    injured = _attach_soldiers(df_soldiers, injuries)
    unit = injured[injured["UNIT_NAME"] == unit_name]
    report = unit.groupby(
        ["INJURY_CATEGORY", "INJURY_LOCATION", "SEVERITY", "PREVENTABILITY"]
    ).size().reset_index(name="건수")
    return report.sort_values(by="건수", ascending=False)


def format_table(data: pd.DataFrame) -> str:
    """DataFrame을 로그에 남기기 좋은 격자 표 문자열로 바꿉니다."""
    return tabulate(data, headers="keys", tablefmt="grid", showindex=False, stralign="center", numalign="right")


def run(
    soldiers_path: Path,
    definition_path: Path,
    output_path: Path,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
    seed: int = DEFAULT_SEED,
    injury_count: int | None = None,
) -> None:
    """장병별 기대 부상 건수로 부상 기록을 만들어 정의서 컬럼 순서대로 저장하고 요약을 로그에 남깁니다.

    Args:
        soldiers_path: 장병 연계 결과 (SOLDIER_ID, 장병 속성, EXPECTED_INJURY_COUNT_PER_YEAR)
        definition_path: 부상 기록 정의서 (SOLDIER_INJURY_DEFINITION.csv)
        output_path: 부상 기록 저장 경로
        injuries_per_person: EXPECTED_INJURY_COUNT_PER_YEAR가 없을 때 쓸 1인당 연간 평균 부상 건수
        seed: 난수 시드
        injury_count: 지정하면 Poisson 대신 정확히 이 건수를 만든다
    """
    df_soldiers = read_text_csv(soldiers_path)
    injuries = generate_injury_data(df_soldiers, injuries_per_person, seed, injury_count)
    write_by_definition(build_injury_records(injuries), definition_path, output_path)

    expected = (
        pd.to_numeric(df_soldiers[EXPECTED_COUNT_COLUMN]).sum()
        if EXPECTED_COUNT_COLUMN in df_soldiers.columns
        else injuries_per_person * len(df_soldiers)
    )
    logger.info("입력 %s: 장병 %s명", display_path(soldiers_path), f"{len(df_soldiers):,}")
    logger.info(
        "부상 기록 %s건 (부상 장병 %s명, 기대 건수 %s, 시드 %s)",
        f"{len(injuries):,}", f"{injuries[SOLDIER_ID_COLUMN].nunique():,}", f"{expected:,.1f}", seed,
    )
    logger.info("두 건 이상 다친 장병: %s명", f"{len(get_repeat_injury_soldiers(injuries)):,}")
    logger.info("전방·후방 부상 건수\n%s", format_table(get_front_rear_summary(df_soldiers, injuries)))
    logger.info("지역별 부상 현황\n%s", format_table(get_region_injury_summary(df_soldiers, injuries)))
    logger.info("부대별 부상 현황\n%s", format_table(get_unit_injury_summary(df_soldiers, injuries)))
    logger.info("저장: %s", display_path(output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    parser = argparse.ArgumentParser(description="장병별 기대 부상 건수로 가상 부상 기록을 만듭니다.")
    parser.add_argument(
        "-n", "--count", type=positive_int, default=None,
        help="만들 부상 기록 건수 (기본: 장병별 Poisson 추출로 정해짐)",
    )
    parser.add_argument(
        "--injuries-per-person", type=non_negative_float, default=INJURIES_PER_PERSON_YEAR,
        help=(
            f"{EXPECTED_COUNT_COLUMN} 컬럼이 없을 때 쓸 1인당 연간 평균 부상 건수 "
            f"(기본값: {INJURIES_PER_PERSON_YEAR}, --count 지정 시 무시)"
        ),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"난수 시드 (기본값: {DEFAULT_SEED})")
    args = parser.parse_args()

    setup_logging(caller_name(__file__))
    run(
        LINKED_INJURY_RISK_PATH,
        DEFINITION_SOLDIER_INJURY,
        SYNTHETIC_INJURY_PATH,
        args.injuries_per_person,
        args.seed,
        args.count,
    )


if __name__ == "__main__":
    main()
