"""가상 장병을 회원별 가장 최근 체력 측정과 연결하고 기대 부상 건수(Poisson λ)를 계산합니다.

BMI와 심폐지구력을 각각 백분위 3구간으로 나눈 부상 위험 그룹(3 × 3 = 9개)마다 기대 부상 건수를 정해
그룹 표(INJURY_RISK_GROUP)로 저장하고, 최종 측정 데이터(FINAL)에는 측정마다 군번과 그룹 번호를 붙입니다.
"""

import argparse
import logging
import math
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_INJURY_RISK_GROUP,
    DEFINITION_KS_NFA_FINAL,
    INTERMEDIATE_REFINED,
    LINKED_INJURY_RISK_PATH,
    PROCESSED_FITNESS_PATH,
    PROCESSED_INJURY_RISK_GROUP_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.utils import non_negative_float, read_text_csv, write_by_definition, write_csv

logger = logging.getLogger(__name__)

# 원본 연구처럼 BMI와 심폐지구력을 모두 백분위로 나눈다: 하위 25%(LOW)·중간 50%(MODERATE)·상위 25%(HIGH).
LEVELS = ("LOW", "MODERATE", "HIGH")
LOWER_PERCENTILE, UPPER_PERCENTILE = 0.25, 0.75

# BMI 구간 × 심폐지구력 구간별 상대 위험도 (원본 연구의 값). INJURY_RISK[BMI 구간][심폐 구간]
# 값의 절대 크기는 상관없다. 장병 평균이 1이 되도록 나눈 뒤 1인당 부상 건수(0.3)를 곱하므로 비율만 쓰인다.
# 가중치는 아래 논문의 표 4-6에서 발췌하였다.
# National Research Council. (2006). Assessing fitness for military enlistment: Physical, medical, and mental health standards. The National Academies Press. https://doi.org/10.17226/11511 
INJURY_RISK: dict[str, dict[str, float | None]] = {
    "LOW": {"HIGH": 16.5, "MODERATE": 21.4, "LOW": 28.7},
    "MODERATE": {"HIGH": 19.6, "MODERATE": 19.3, "LOW": 25.1},
    "HIGH": {"HIGH": 20.5, "MODERATE": 19.8, "LOW": 26.5},
}

# 그룹 번호는 BMI 구간 순서 × 심폐 구간 순서로 고정한다.
# 1: BMI 하위·심폐 하위, 2: BMI 하위·심폐 중간, ..., 9: BMI 상위·심폐 상위
RISK_GROUP_IDS = {
    group: group_id
    for group_id, group in enumerate(product(LEVELS, LEVELS), start=1)
}

# 선행 연구의 장병 1명당 연간 부상 건수. 모든 측정이 같은 해에 이루어졌다고 가정하므로
# 장병 N명의 기대 부상 건수 합은 0.3N이고, 실제 생성 건수는 Poisson(0.3N)을 따른다.
INJURIES_PER_PERSON_YEAR = 0.3
# 정의서의 DECIMAL(7,6)에 맞춘 자릿수
EXPECTED_COUNT_DECIMALS = 6

SOLDIER_ID_COLUMN = "SOLDIER_ID"
FITNESS_ID_COLUMN = "MESURE_ID"
MEMBER_ID_COLUMN = "M_CODE"
MEASURE_DATE_COLUMN = "MESURE_DE"
RISK_GROUP_ID_COLUMN = "INJURY_RISK_GROUP_ID"
EXPECTED_COUNT_COLUMN = "EXPECTED_INJURY_COUNT"
IDENTITY_COLUMNS = (FITNESS_ID_COLUMN, MEMBER_ID_COLUMN, MEASURE_DATE_COLUMN)
FITNESS_COLUMNS = (
    "STRENGTH",
    "ENDURANCE",
    "CARDIO",
    "FLEXIBILITY",
    "HEIGHT",
    "WEIGHT",
    "BMI",
    "BODY_FAT_PERCENTAGE",
)

_LEVEL_LABELS = {"LOW": "하위 25%", "MODERATE": "중간 50%", "HIGH": "상위 25%"}

Cuts = tuple[float, float]


def percentile_cuts(values: pd.Series) -> Cuts:
    """하위 25%·상위 25% 경계(25·75 백분위수)를 반환합니다. 전체 측정을 넘겨 경계를 정합니다."""
    lower, upper = values.quantile([LOWER_PERCENTILE, UPPER_PERCENTILE])
    return float(lower), float(upper)


def classify_level(values: pd.Series, cuts: Cuts) -> pd.Series:
    """값을 하위 25%(LOW, 하위 경계 이하)·중간 50%(MODERATE)·상위 25%(HIGH, 상위 경계 이상)로 나눕니다."""
    lower, upper = cuts
    return pd.Series(
        np.select([values <= lower, values < upper], ["LOW", "MODERATE"], default="HIGH"),
        index=values.index,
        dtype="object",
    )


def assign_risk_group_ids(bmi: pd.Series, cardio: pd.Series, bmi_cuts: Cuts, cardio_cuts: Cuts) -> pd.Series:
    """BMI 구간과 심폐 구간으로 부상 위험 그룹 번호(1~9)를 반환합니다."""
    groups = zip(classify_level(bmi, bmi_cuts), classify_level(cardio, cardio_cuts))
    return pd.Series([RISK_GROUP_IDS[group] for group in groups], index=bmi.index, dtype="int64")


def measurement_cuts(df_fitness: pd.DataFrame) -> tuple[Cuts, Cuts]:
    """전체 측정으로 BMI와 심폐지구력의 백분위 경계를 정합니다."""
    return (
        percentile_cuts(pd.to_numeric(df_fitness["BMI"])),
        percentile_cuts(pd.to_numeric(df_fitness["CARDIO"])),
    )


def assign_measurement_risk_groups(df_fitness: pd.DataFrame) -> pd.Series:
    """모든 측정에 부상 위험 그룹 번호를 붙입니다. 백분위 경계는 전체 측정으로 정합니다."""
    bmi_cuts, cardio_cuts = measurement_cuts(df_fitness)
    return assign_risk_group_ids(
        pd.to_numeric(df_fitness["BMI"]), pd.to_numeric(df_fitness["CARDIO"]), bmi_cuts, cardio_cuts
    )


def group_risks() -> dict[int, float]:
    """그룹 번호별 상대 위험도를 INJURY_RISK에서 읽습니다.

    Raises:
        ValueError: 비어 있거나(None) 0 이하인 가중치가 있을 때
    """
    risks = {
        group_id: INJURY_RISK[bmi_level][cardio_level]
        for (bmi_level, cardio_level), group_id in RISK_GROUP_IDS.items()
    }
    invalid = [group_id for group_id, risk in risks.items() if risk is None or not risk > 0]
    if invalid:
        raise ValueError(
            "INJURY_RISK의 가중치가 비어 있거나 0 이하입니다 "
            f"(그룹 {', '.join(map(str, invalid))}). link_fitness_and_injury_risk.py의 INJURY_RISK를 채우세요."
        )
    return risks


def build_risk_group_table(
    soldier_group_ids: pd.Series,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
) -> pd.DataFrame:
    """9개 부상 위험 그룹의 기대 부상 건수 표를 만듭니다.

    상대 위험도를 장병 평균 위험도로 나눠, 장병 전체의 기대 부상 건수 평균이
    `injuries_per_person`이 되게 합니다. 장병이 없는 그룹도 표에는 넣습니다.

    Raises:
        ValueError: 장병이 없거나 INJURY_RISK 가중치가 비어 있을 때
    """
    if soldier_group_ids.empty:
        raise ValueError("부상 위험 그룹을 정할 장병이 없습니다.")
    risks = group_risks()
    mean_risk = soldier_group_ids.map(risks).mean()
    return pd.DataFrame([
        {
            RISK_GROUP_ID_COLUMN: group_id,
            "BMI_LEVEL": bmi_level,
            "CARDIO_LEVEL": cardio_level,
            EXPECTED_COUNT_COLUMN: round(injuries_per_person * risks[group_id] / mean_risk, EXPECTED_COUNT_DECIMALS),
        }
        for (bmi_level, cardio_level), group_id in RISK_GROUP_IDS.items()
    ])


def select_latest_measurements(df_fitness: pd.DataFrame) -> pd.DataFrame:
    """회원(M_CODE)마다 가장 최근 측정 한 건을 MESURE_ID 순서로 반환합니다.

    같은 날 측정이 여러 건이면 MESURE_ID가 큰 쪽을 최근으로 봅니다.
    """
    order = (
        df_fitness.assign(_measure_id=pd.to_numeric(df_fitness[FITNESS_ID_COLUMN]))
        .sort_values([MEASURE_DATE_COLUMN, "_measure_id"], kind="stable")
    )
    latest = order.groupby(MEMBER_ID_COLUMN, sort=False).tail(1)
    return latest.sort_values("_measure_id", kind="stable").drop(columns="_measure_id")


def _validate_inputs(df_personnel: pd.DataFrame, df_fitness: pd.DataFrame) -> None:
    if df_personnel.empty:
        raise ValueError("가상 장병 데이터가 비어 있습니다.")
    if df_fitness.empty:
        raise ValueError("체력 측정 데이터가 비어 있습니다.")
    if SOLDIER_ID_COLUMN not in df_personnel.columns:
        raise ValueError(f"장병 데이터에 필수 컬럼이 없습니다: {SOLDIER_ID_COLUMN}")
    soldier_ids = df_personnel[SOLDIER_ID_COLUMN]
    blank_ids = soldier_ids.isna() | soldier_ids.astype(str).str.strip().eq("")
    if blank_ids.any() or soldier_ids.duplicated().any():
        raise ValueError("장병 군번은 비어 있지 않고 고유해야 합니다.")
    missing = [column for column in (*IDENTITY_COLUMNS, *FITNESS_COLUMNS) if column not in df_fitness.columns]
    if missing:
        raise ValueError(f"체력 데이터에 필수 컬럼이 없습니다: {', '.join(missing)}")
    fitness_ids = df_fitness[FITNESS_ID_COLUMN]
    if fitness_ids.isna().any() or fitness_ids.duplicated().any():
        raise ValueError("체력 데이터의 MESURE_ID는 비어 있지 않고 고유해야 합니다.")
    fitness = df_fitness.loc[:, FITNESS_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if fitness.isna().any().any() or not np.isfinite(fitness.to_numpy()).all():
        raise ValueError("체력 지표에는 유효한 숫자만 있어야 합니다.")
    if (fitness["BMI"] <= 0).any() or (fitness["CARDIO"] <= 0).any():
        raise ValueError("체력 데이터의 BMI와 CARDIO는 0보다 커야 합니다.")


def calculate_injury_risk(
    df_personnel: pd.DataFrame,
    df_fitness: pd.DataFrame,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
) -> pd.DataFrame:
    """장병을 회원별 가장 최근 측정과 연결하고 부상 위험 그룹과 기대 부상 건수를 붙입니다.

    회원 한 명당 장병 한 명이 있다고 보고, 최근 측정을 MESURE_ID 순서로 장병에게 하나씩 연결합니다.
    BMI·심폐지구력의 백분위 경계는 전체 측정으로 정하고, 상대 위험도는 장병 평균 1로 맞추므로
    EXPECTED_INJURY_COUNT의 합은 `injuries_per_person × 장병 수`가 됩니다.

    Raises:
        ValueError: 입력이 비었거나 필수 컬럼·값이 잘못되었을 때, 장병 수와 회원 수가 다를 때
    """
    if not math.isfinite(injuries_per_person) or injuries_per_person < 0:
        raise ValueError("injuries_per_person은 0 이상의 숫자여야 합니다.")
    _validate_inputs(df_personnel, df_fitness)

    bmi_cuts, cardio_cuts = measurement_cuts(df_fitness)
    latest = select_latest_measurements(df_fitness)
    if len(df_personnel) != len(latest):
        raise ValueError(
            "가상 장병 수와 체력 데이터의 회원 수가 같아야 합니다 "
            f"(장병 {len(df_personnel):,}명, 회원 {len(latest):,}명)."
        )

    measurements = latest.loc[:, FITNESS_COLUMNS].apply(pd.to_numeric).reset_index(drop=True)
    for column in IDENTITY_COLUMNS:
        measurements.insert(len(measurements.columns), column, latest[column].to_numpy())
    linked = pd.concat([df_personnel.reset_index(drop=True), measurements], axis=1)

    linked["BMI_LEVEL"] = classify_level(linked["BMI"], bmi_cuts)
    linked["CARDIO_LEVEL"] = classify_level(linked["CARDIO"], cardio_cuts)
    linked[RISK_GROUP_ID_COLUMN] = assign_risk_group_ids(linked["BMI"], linked["CARDIO"], bmi_cuts, cardio_cuts)
    # 평균을 1로 맞춰 집단 간 위험도 비율은 유지하고, 전체 평균은 injuries_per_person이 되게 한다.
    raw_risk = linked[RISK_GROUP_ID_COLUMN].map(group_risks())
    linked["RELATIVE_INJURY_RISK"] = raw_risk / raw_risk.mean()
    # 기대 부상 건수는 그룹 표의 값을 그대로 써서 저장되는 그룹 표와 어긋나지 않게 한다.
    # Poisson 평균은 1을 넘어도 되므로 상한 검사를 하지 않는다.
    groups = build_risk_group_table(linked[RISK_GROUP_ID_COLUMN], injuries_per_person)
    linked[EXPECTED_COUNT_COLUMN] = linked[RISK_GROUP_ID_COLUMN].map(
        groups.set_index(RISK_GROUP_ID_COLUMN)[EXPECTED_COUNT_COLUMN]
    )
    return linked


def build_final_measurements(df_fitness: pd.DataFrame, linked: pd.DataFrame) -> pd.DataFrame:
    """모든 측정에 그 회원의 군번(SOLDIER_ID)과 부상 위험 그룹 번호를 붙입니다."""
    soldier_by_member = linked.set_index(MEMBER_ID_COLUMN)[SOLDIER_ID_COLUMN]
    return df_fitness.assign(**{
        SOLDIER_ID_COLUMN: df_fitness[MEMBER_ID_COLUMN].map(soldier_by_member),
        RISK_GROUP_ID_COLUMN: assign_measurement_risk_groups(df_fitness),
    })


def summarize_linked_categories(linked: pd.DataFrame) -> pd.DataFrame:
    """장병의 BMI·심폐지구력 구간별 인원수와 비율을 집계합니다."""
    summary_rows = []
    for group_name, column, labels in (
        ("BMI 구간", "BMI_LEVEL", _LEVEL_LABELS),
        ("CARDIO 구간", "CARDIO_LEVEL", _LEVEL_LABELS),
    ):
        if column not in linked.columns:
            raise ValueError(f"연계 데이터에 필수 컬럼이 없습니다: {column}")
        counts = linked[column].value_counts().reindex(labels, fill_value=0)
        for category, label in labels.items():
            count = int(counts[category])
            summary_rows.append({
                "분류": group_name,
                "구간": label,
                "인원수(명)": count,
                "비율(%)": count / len(linked) * 100 if len(linked) else 0.0,
            })
    return pd.DataFrame(summary_rows)


def run(
    personnel_path: Path,
    fitness_path: Path,
    fitness_definition_path: Path,
    risk_group_definition_path: Path,
    output_path: Path,
    risk_group_output_path: Path,
    fitness_output_path: Path,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
) -> None:
    """최근 측정을 연계하고 부상 위험 그룹·기대 부상 건수를 계산해 저장합니다.

    Args:
        personnel_path: 가상 장병 명단 (SOLDIER_PERSONNEL)
        fitness_path: 전처리된 측정 데이터 (REFINED)
        fitness_definition_path: 최종 측정 데이터 정의서 (KS_NFA_FINAL_DEFINITION.csv)
        risk_group_definition_path: 부상 위험 그룹 정의서 (INJURY_RISK_GROUP_DEFINITION.csv)
        output_path: 장병 연계 결과 저장 경로 (부상 생성 단계의 입력)
        risk_group_output_path: 부상 위험 그룹 표 저장 경로
        fitness_output_path: 군번·그룹 번호를 붙인 최종 측정 데이터 저장 경로
        injuries_per_person: 장병 1명당 연간 평균 부상 건수
    """
    df_personnel = read_text_csv(personnel_path)
    df_fitness = read_text_csv(fitness_path)
    linked = calculate_injury_risk(df_personnel, df_fitness, injuries_per_person)
    groups = build_risk_group_table(linked[RISK_GROUP_ID_COLUMN], injuries_per_person)
    measurements = build_final_measurements(df_fitness, linked)

    write_csv(linked, output_path)
    write_by_definition(groups, risk_group_definition_path, risk_group_output_path)
    write_by_definition(measurements, fitness_definition_path, fitness_output_path)

    logger.info("입력 %s: 장병 %s명", display_path(personnel_path), f"{len(df_personnel):,}")
    logger.info(
        "입력 %s: 측정 %s건, 회원 %s명",
        display_path(fitness_path), f"{len(df_fitness):,}", f"{df_fitness[MEMBER_ID_COLUMN].nunique():,}",
    )
    logger.info(
        "기대 부상 건수 합 %s건 (1인당 %s건)",
        f"{linked[EXPECTED_COUNT_COLUMN].sum():,.1f}", injuries_per_person,
    )
    logger.info("장병 BMI·CARDIO 구간별 인원수 및 비율\n%s", summarize_linked_categories(linked).to_string(index=False))
    logger.info("저장(장병 연계): %s", display_path(output_path))
    logger.info("저장(부상 위험 그룹): %s", display_path(risk_group_output_path))
    logger.info("저장(최종 측정): %s", display_path(fitness_output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    parser = argparse.ArgumentParser(
        description="가상 장병을 회원별 최근 체력 측정과 연결하고 기대 부상 건수를 계산합니다."
    )
    parser.add_argument(
        "--injuries-per-person", type=non_negative_float, default=INJURIES_PER_PERSON_YEAR,
        help=f"장병 1명당 연간 평균 부상 건수 (기본값: {INJURIES_PER_PERSON_YEAR})",
    )
    args = parser.parse_args()

    setup_logging(caller_name(__file__))
    run(
        SYNTHETIC_PERSONNEL_PATH,
        INTERMEDIATE_REFINED,
        DEFINITION_KS_NFA_FINAL,
        DEFINITION_INJURY_RISK_GROUP,
        LINKED_INJURY_RISK_PATH,
        PROCESSED_INJURY_RISK_GROUP_PATH,
        PROCESSED_FITNESS_PATH,
        args.injuries_per_person,
    )


if __name__ == "__main__":
    main()
