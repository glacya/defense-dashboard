"""가상 장병을 회원별 가장 최근 체력 측정과 연결하고 기대 부상 건수(Poisson λ)를 계산합니다.

원본 연구는 BMI와 심폐지구력을 각각 백분위 3구간(하위 25%·중간 50%·상위 25%)으로 나눈 3 × 3 = 9개 집단의
부상 위험만 알려 줍니다. 집단 경계에서 값이 갑자기 바뀌지 않도록, 각 집단의 가운데 백분위(12.5·50·87.5)에
집단 값을 두고 그 사이를 선형 보간해 측정마다 연간 기대 부상 건수를 정합니다.
최종 측정 데이터(FINAL)에는 측정마다 군번과 이 값을 붙입니다.
"""

import argparse
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_KS_NFA_FINAL,
    INTERMEDIATE_REFINED,
    LINKED_INJURY_RISK_PATH,
    PROCESSED_FITNESS_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.utils import non_negative_float, read_text_csv, write_by_definition, write_csv

logger = logging.getLogger(__name__)

# 원본 연구처럼 BMI와 심폐지구력을 모두 백분위로 나눈다: 하위 25%(LOW)·중간 50%(MODERATE)·상위 25%(HIGH).
LEVELS = ("LOW", "MODERATE", "HIGH")
LOWER_PERCENTILE, UPPER_PERCENTILE = 0.25, 0.75
# 보간 격자점: 각 구간의 가운데 백분위(12.5, 50, 87.5). 원본 연구의 집단 값을 이 위치의 값으로 본다.
GRID_PERCENTILES = (
    LOWER_PERCENTILE / 2 * 100,
    (LOWER_PERCENTILE + UPPER_PERCENTILE) / 2 * 100,
    (UPPER_PERCENTILE + 1) / 2 * 100,
)

# BMI 구간 × 심폐지구력 구간별 상대 위험도 (원본 연구의 값). INJURY_RISK[BMI 구간][심폐 구간]
# 값의 절대 크기는 상관없다. 장병 평균이 1이 되도록 나눈 뒤 1인당 부상 건수(0.3)를 곱하므로 비율만 쓰인다.
# 가중치는 아래 논문의 표 4-6에서 발췌하였다.
# National Research Council. (2006). Assessing fitness for military enlistment: Physical, medical, and mental health standards. The National Academies Press. https://doi.org/10.17226/11511
INJURY_RISK: dict[str, dict[str, float | None]] = {
    "LOW": {"HIGH": 16.5, "MODERATE": 21.4, "LOW": 28.7},
    "MODERATE": {"HIGH": 19.6, "MODERATE": 19.3, "LOW": 25.1},
    "HIGH": {"HIGH": 20.5, "MODERATE": 19.8, "LOW": 26.5},
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
RELATIVE_RISK_COLUMN = "RELATIVE_INJURY_RISK"
EXPECTED_COUNT_COLUMN = "EXPECTED_INJURY_COUNT_PER_YEAR"
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


def percentile_ranks(values: pd.Series, reference: pd.Series) -> pd.Series:
    """reference 분포 안에서 각 값의 백분위(0~100)를 반환합니다.

    같은 값이 여러 개면 그 값들이 차지하는 순위의 가운데를 씁니다.
    """
    ordered = np.sort(reference.to_numpy(dtype=float))
    below = np.searchsorted(ordered, values.to_numpy(dtype=float), side="left")
    at_or_below = np.searchsorted(ordered, values.to_numpy(dtype=float), side="right")
    return pd.Series((below + at_or_below) / 2 / len(ordered) * 100, index=values.index)


def risk_weight_grid() -> np.ndarray:
    """INJURY_RISK를 [BMI 구간][심폐 구간] 순서(LOW, MODERATE, HIGH)의 3 × 3 배열로 반환합니다.

    Raises:
        ValueError: 비어 있거나(None) 0 이하인 가중치가 있을 때
    """
    invalid = [
        f"{bmi_level}·{cardio_level}"
        for bmi_level in LEVELS for cardio_level in LEVELS
        if INJURY_RISK[bmi_level][cardio_level] is None or not INJURY_RISK[bmi_level][cardio_level] > 0
    ]
    if invalid:
        raise ValueError(
            "INJURY_RISK의 가중치가 비어 있거나 0 이하입니다 "
            f"(BMI·심폐 {', '.join(invalid)}). link_fitness_and_injury_risk.py의 INJURY_RISK를 채우세요."
        )
    return np.array([[INJURY_RISK[bmi_level][cardio_level] for cardio_level in LEVELS] for bmi_level in LEVELS])


def interpolate_risk(bmi_percentiles: pd.Series, cardio_percentiles: pd.Series) -> pd.Series:
    """BMI·심폐 백분위로 상대 위험도를 쌍선형 보간합니다(정규화 전 값).

    격자점(GRID_PERCENTILES)에서는 INJURY_RISK 값과 같고, 격자 바깥은 가장 가까운 끝 값으로 고정합니다.
    """
    grid = risk_weight_grid()
    nodes = np.array(GRID_PERCENTILES)
    bmi = bmi_percentiles.to_numpy(dtype=float)
    cardio = cardio_percentiles.to_numpy(dtype=float)
    # np.interp는 범위 밖을 끝 값으로 고정한다. BMI 방향의 선형 가중치 × 각 BMI 행을 심폐 방향으로 보간한 값.
    risk = sum(
        np.interp(bmi, nodes, np.eye(len(LEVELS))[row]) * np.interp(cardio, nodes, grid[row])
        for row in range(len(LEVELS))
    )
    return pd.Series(risk, index=bmi_percentiles.index)


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


def measurement_injury_risks(
    df_fitness: pd.DataFrame,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
) -> pd.DataFrame:
    """모든 측정의 BMI·심폐 백분위, 상대 위험도, 연간 기대 부상 건수를 df_fitness와 같은 인덱스로 반환합니다.

    백분위는 전체 측정 안에서 구합니다. 상대 위험도는 회원별 최근 측정(장병) 평균이 1이 되도록 나누고,
    같은 배율을 최근이 아닌 측정에도 씁니다. 기대 부상 건수는 정의서 자릿수(소수 6자리)로 반올림합니다.
    """
    bmi = pd.to_numeric(df_fitness["BMI"])
    cardio = pd.to_numeric(df_fitness["CARDIO"])
    risks = pd.DataFrame({
        "BMI_PERCENTILE": percentile_ranks(bmi, bmi),
        "CARDIO_PERCENTILE": percentile_ranks(cardio, cardio),
    })
    raw_risk = interpolate_risk(risks["BMI_PERCENTILE"], risks["CARDIO_PERCENTILE"])
    latest_index = select_latest_measurements(df_fitness).index
    risks[RELATIVE_RISK_COLUMN] = raw_risk / raw_risk.loc[latest_index].mean()
    risks[EXPECTED_COUNT_COLUMN] = (injuries_per_person * risks[RELATIVE_RISK_COLUMN]).round(EXPECTED_COUNT_DECIMALS)
    return risks


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
    """장병을 회원별 가장 최근 측정과 연결하고 그 측정의 연간 기대 부상 건수를 붙입니다.

    회원 한 명당 장병 한 명이 있다고 보고, 최근 측정을 MESURE_ID 순서로 장병에게 하나씩 연결합니다.
    장병의 기대 부상 건수는 최종 측정 데이터에 저장되는 그 측정의 값과 같고,
    합은 `injuries_per_person × 장병 수`가 됩니다(소수 6자리 반올림 차이만 있음).
    BMI_LEVEL·CARDIO_LEVEL(전체 측정의 25·75 백분위수로 나눈 구간)은 로그 요약에만 씁니다.

    Raises:
        ValueError: 입력이 비었거나 필수 컬럼·값이 잘못되었을 때, 장병 수와 회원 수가 다를 때
    """
    if not math.isfinite(injuries_per_person) or injuries_per_person < 0:
        raise ValueError("injuries_per_person은 0 이상의 숫자여야 합니다.")
    _validate_inputs(df_personnel, df_fitness)

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

    fitness = df_fitness.loc[:, ["BMI", "CARDIO"]].apply(pd.to_numeric)
    linked["BMI_LEVEL"] = classify_level(linked["BMI"], percentile_cuts(fitness["BMI"]))
    linked["CARDIO_LEVEL"] = classify_level(linked["CARDIO"], percentile_cuts(fitness["CARDIO"]))
    risks = measurement_injury_risks(df_fitness, injuries_per_person).loc[latest.index].reset_index(drop=True)
    return pd.concat([linked, risks], axis=1)


def build_final_measurements(
    df_fitness: pd.DataFrame,
    linked: pd.DataFrame,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
) -> pd.DataFrame:
    """모든 측정에 그 회원의 군번(SOLDIER_ID)과 연간 기대 부상 건수를 붙입니다."""
    soldier_by_member = linked.set_index(MEMBER_ID_COLUMN)[SOLDIER_ID_COLUMN]
    return df_fitness.assign(**{
        SOLDIER_ID_COLUMN: df_fitness[MEMBER_ID_COLUMN].map(soldier_by_member),
        EXPECTED_COUNT_COLUMN: measurement_injury_risks(df_fitness, injuries_per_person)[EXPECTED_COUNT_COLUMN],
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
    output_path: Path,
    fitness_output_path: Path,
    injuries_per_person: float = INJURIES_PER_PERSON_YEAR,
) -> None:
    """최근 측정을 연계하고 측정별 연간 기대 부상 건수를 계산해 저장합니다.

    Args:
        personnel_path: 가상 장병 명단 (SOLDIER_PERSONNEL)
        fitness_path: 전처리된 측정 데이터 (REFINED)
        fitness_definition_path: 최종 측정 데이터 정의서 (KS_NFA_FINAL_DEFINITION.csv)
        output_path: 장병 연계 결과 저장 경로 (부상 생성 단계의 입력)
        fitness_output_path: 군번·기대 부상 건수를 붙인 최종 측정 데이터 저장 경로
        injuries_per_person: 장병 1명당 연간 평균 부상 건수
    """
    df_personnel = read_text_csv(personnel_path)
    df_fitness = read_text_csv(fitness_path)
    linked = calculate_injury_risk(df_personnel, df_fitness, injuries_per_person)
    measurements = build_final_measurements(df_fitness, linked, injuries_per_person)

    write_csv(linked, output_path)
    write_by_definition(measurements, fitness_definition_path, fitness_output_path)

    logger.info("입력 %s: 장병 %s명", display_path(personnel_path), f"{len(df_personnel):,}")
    logger.info(
        "입력 %s: 측정 %s건, 회원 %s명",
        display_path(fitness_path), f"{len(df_fitness):,}", f"{df_fitness[MEMBER_ID_COLUMN].nunique():,}",
    )
    expected = linked[EXPECTED_COUNT_COLUMN]
    logger.info(
        "장병 기대 부상 건수 합 %s건 (1인당 %s건, 장병별 %.6f~%.6f)",
        f"{expected.sum():,.1f}", injuries_per_person, expected.min(), expected.max(),
    )
    logger.info("장병 BMI·CARDIO 구간별 인원수 및 비율\n%s", summarize_linked_categories(linked).to_string(index=False))
    logger.info("저장(장병 연계): %s", display_path(output_path))
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
        LINKED_INJURY_RISK_PATH,
        PROCESSED_FITNESS_PATH,
        args.injuries_per_person,
    )


if __name__ == "__main__":
    main()
