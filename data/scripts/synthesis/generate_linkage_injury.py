"""가상 장병과 체력 측정값을 연결하고 개인별 부상 확률을 계산합니다."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.paths import (
    LINKED_INJURY_RISK_PATH,
    PROCESSED_FITNESS_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.synthesis.generate_synthetic_personnels import (
    assign_personnel_attributes,
)

INJURY_RISK = {
    "UNDERWEIGHT": {"HIGH": 1.3, "MODERATE": 1.7, "LOW": 2.5},
    "NORMAL": {"HIGH": 1.0, "MODERATE": 1.3, "LOW": 1.8},
    "OVERWEIGHT": {"HIGH": 1.2, "MODERATE": 1.6, "LOW": 2.3},
    "OBESE": {"HIGH": 1.5, "MODERATE": 2.1, "LOW": 3.0},
}

PERSONNEL_COLUMNS = {
    "SOLDIER_ID": ("SOLDIER_ID", "군번"),
    "SOLDIER_NAME": ("SOLDIER_NAME", "이름"),
}
FITNESS_ID_COLUMN = "MESURE_ID"

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


def classify_bmi(bmi: pd.Series) -> pd.Series:
    """이미지의 BMI 구간을 이용해 체중 범주를 반환합니다."""
    return pd.Series(
        np.select(
            [bmi < 18.5, bmi < 25.0, bmi < 30.0],
            ["UNDERWEIGHT", "NORMAL", "OVERWEIGHT"],
            default="OBESE",
        ),
        index=bmi.index,
        dtype="object",
    )


def classify_cardio(
    cardio: pd.Series,
    lower_quartile: float,
    upper_quartile: float,
) -> pd.Series:
    """체력 자료의 하위 25%, 중간 50%, 상위 25%에 해당하는 등급을 반환합니다."""
    return pd.Series(
        np.select(
            [cardio <= lower_quartile, cardio < upper_quartile],
            ["LOW", "MODERATE"],
            default="HIGH",
        ),
        index=cardio.index,
        dtype="object",
    )


def summarize_linked_categories(linked: pd.DataFrame) -> pd.DataFrame:
    """연동 데이터의 BMI 및 CARDIO 범주별 인원수와 비율을 집계합니다."""
    category_groups = (
        (
            "BMI 구간",
            "BMI_CATEGORY",
            {
                "UNDERWEIGHT": "저체중",
                "NORMAL": "정상",
                "OVERWEIGHT": "과체중",
                "OBESE": "비만",
            },
        ),
        (
            "CARDIO 구간",
            "CARDIO_LEVEL",
            {"LOW": "하위 25%", "MODERATE": "중간 50%", "HIGH": "상위 25%"},
        ),
    )
    summary_rows = []
    for group_name, column, labels in category_groups:
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


def calculate_injury_risk(
    df_personal: pd.DataFrame,
    df_fitness: pd.DataFrame,
    injury_rate: float = 10.0,
    seed: int = 42,
) -> pd.DataFrame:
    """장병별 체력 지표를 모집단 비율에 맞춰 연결하고 부상 확률을 계산합니다.

    `injury_rate`는 전체 인원 기준 부상 비율(퍼센트)입니다.
    체력 측정 행마다 가상 장병 한 명을 MESURE_ID로 연결합니다.
    """
    if not 0 <= injury_rate <= 100:
        raise ValueError("injury_rate는 0에서 100 사이의 퍼센트여야 합니다.")
    if df_personal.empty:
        raise ValueError("가상 장병 데이터가 비어 있습니다.")
    if df_fitness.empty:
        raise ValueError("체력 측정 데이터가 비어 있습니다.")

    personnel_column_map: dict[str, str] = {}
    for output_column, candidates in PERSONNEL_COLUMNS.items():
        source_column = next(
            (column for column in candidates if column in df_personal.columns),
            None,
        )
        if source_column is None:
            raise ValueError(
                f"장병 데이터에 필수 컬럼이 없습니다: {' 또는 '.join(candidates)}"
            )
        personnel_column_map[source_column] = output_column

    soldier_id_column = next(
        column
        for column in PERSONNEL_COLUMNS["SOLDIER_ID"]
        if column in df_personal.columns
    )
    soldier_ids = df_personal[soldier_id_column]
    if soldier_ids.isna().any() or soldier_ids.duplicated().any():
        raise ValueError("장병 군번은 비어 있지 않고 고유해야 합니다.")

    missing_fitness_columns = [
        column
        for column in (FITNESS_ID_COLUMN, *FITNESS_COLUMNS)
        if column not in df_fitness.columns
    ]
    if missing_fitness_columns:
        raise ValueError(
            f"체력 데이터에 필수 컬럼이 없습니다: {', '.join(missing_fitness_columns)}"
        )
    fitness_ids = df_fitness[FITNESS_ID_COLUMN]
    if fitness_ids.isna().any() or fitness_ids.duplicated().any():
        raise ValueError("체력 데이터의 MESURE_ID는 비어 있지 않고 고유해야 합니다.")
    if len(df_personal) != len(df_fitness):
        raise ValueError(
            "가상 장병 수와 체력 측정 데이터 수가 같아야 합니다 "
            f"(장병 {len(df_personal):,}명, 체력 {len(df_fitness):,}건)."
        )

    fitness = df_fitness.loc[:, FITNESS_COLUMNS].apply(
        pd.to_numeric, errors="coerce"
    )
    if fitness.isna().any().any() or not np.isfinite(fitness.to_numpy()).all():
        raise ValueError("체력 지표에는 유효한 숫자만 있어야 합니다.")
    if (fitness["BMI"] <= 0).any() or (fitness["CARDIO"] <= 0).any():
        raise ValueError("체력 데이터의 BMI와 CARDIO는 0보다 커야 합니다.")

    personnel = (
        df_personal.reset_index(drop=True)
        .rename(columns=personnel_column_map)
        .copy()
    )
    personnel[FITNESS_ID_COLUMN] = fitness_ids.reset_index(drop=True)
    fitness_with_ids = fitness.copy()
    fitness_with_ids[FITNESS_ID_COLUMN] = fitness_ids.to_numpy()
    linked = personnel.merge(
        fitness_with_ids,
        on=FITNESS_ID_COLUMN,
        how="inner",
        sort=False,
        validate="one_to_one",
    )
    if len(linked) != len(df_fitness):
        raise ValueError("MESURE_ID로 연결되지 않은 체력 데이터가 있습니다.")
    linked = assign_personnel_attributes(linked, seed)
    linked["BMI_CATEGORY"] = classify_bmi(linked["BMI"])

    lower_quartile, upper_quartile = fitness["CARDIO"].quantile([0.25, 0.75])
    linked["CARDIO_LEVEL"] = classify_cardio(
        linked["CARDIO"], lower_quartile, upper_quartile
    )
    linked["RELATIVE_INJURY_RISK"] = [
        INJURY_RISK[bmi_category][cardio_level]
        for bmi_category, cardio_level in zip(
            linked["BMI_CATEGORY"], linked["CARDIO_LEVEL"]
        )
    ]

    mean_risk = linked["RELATIVE_INJURY_RISK"].mean()
    linked["RELATIVE_INJURY_RISK"] /= mean_risk
    linked["INJURY_PROBABILITY"] = (
        injury_rate / 100 * linked["RELATIVE_INJURY_RISK"]
    )
    if (linked["INJURY_PROBABILITY"] > 1).any():
        max_probability = linked["INJURY_PROBABILITY"].max()
        raise ValueError(
            "정규화 후 부상 확률이 1을 초과합니다 "
            f"(최대 {max_probability:.4f}). injury_rate를 낮추세요."
        )
    return linked


def run(
    personnel_path: Path,
    fitness_path: Path,
    output_path: Path,
    injury_rate: float = 10.0,
    seed: int = 42,
) -> None:
    """체력을 연계하고 부상 확률을 계산해 결과를 저장합니다."""
    df_personal = pd.read_csv(personnel_path, encoding="utf-8-sig")
    df_fitness = pd.read_csv(fitness_path, encoding="utf-8-sig")
    linked = calculate_injury_risk(df_personal, df_fitness, injury_rate, seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    linked.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"장병 체력·부상확률 데이터 저장 완료: {output_path}")
    print("[연동 데이터 BMI·CARDIO 구간별 인원수 및 비율]")
    print(summarize_linked_categories(linked).to_string(index=False))


def percentage(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("숫자를 입력하세요.") from error
    if not 0 <= parsed <= 100:
        raise argparse.ArgumentTypeError("0에서 100 사이의 퍼센트를 입력하세요.")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="가상 장병에 체력 데이터를 연결하고 개인별 부상 확률을 계산합니다."
    )
    parser.add_argument(
        "-p", "--personnel-csv", type=Path, default=SYNTHETIC_PERSONNEL_PATH,
        help="가상 장병 입력 CSV 경로",
    )
    parser.add_argument(
        "-f", "--fitness-csv", type=Path, default=PROCESSED_FITNESS_PATH,
        help="BMI와 CARDIO를 포함한 처리 체력 데이터 CSV 경로",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=LINKED_INJURY_RISK_PATH,
        help="연계 결과 CSV 경로",
    )
    parser.add_argument(
        "--injury-rate", type=percentage, default=10.0,
        help="전체 인원 기준 목표 부상 비율(퍼센트, 기본값: 10)",
    )
    parser.add_argument("--seed", type=int, default=42, help="난수 시드")
    args = parser.parse_args()
    run(
        args.personnel_csv,
        args.fitness_csv,
        args.output,
        args.injury_rate,
        args.seed,
    )


if __name__ == "__main__":
    main()
