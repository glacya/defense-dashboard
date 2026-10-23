import numpy as np
import pandas as pd
import pytest

from data.scripts.synthesis.generate_linkage_injury import (
    FITNESS_COLUMNS,
    calculate_injury_risk,
    summarize_linked_categories,
)
from data.scripts.synthesis.generate_synthetic_injuries import generate_injury_data
from data.scripts.synthesis.generate_synthetic_personnels import (
    run as generate_personnel_data,
)


def make_fitness_data() -> pd.DataFrame:
    return pd.DataFrame({
        "MESURE_ID": [101, 102, 103, 104],
        "STRENGTH": [40.0, 50.0, 60.0, 70.0],
        "ENDURANCE": [30.0, 40.0, 50.0, 60.0],
        "CARDIO": [20.0, 30.0, 40.0, 50.0],
        "FLEXIBILITY": [-5.0, 0.0, 5.0, 10.0],
        "HEIGHT": [160.0, 170.0, 180.0, 190.0],
        "WEIGHT": [50.0, 60.0, 70.0, 80.0],
        "BMI": [17.0, 22.0, 27.0, 32.0],
        "BODY_FAT_PERCENTAGE": [10.0, 15.0, 20.0, 25.0],
    })


def test_personnel_generation_matches_fitness_count_and_only_writes_identity(
    tmp_path,
):
    fitness_path = tmp_path / "fitness.csv"
    output_path = tmp_path / "personnel.csv"
    pd.DataFrame({"MESURE_ID": [11, 12, 13]}).to_csv(
        fitness_path, index=False, encoding="utf-8-sig"
    )

    generate_personnel_data(output_path, fitness_path=fitness_path)

    personnel = pd.read_csv(output_path, encoding="utf-8-sig")
    assert len(personnel) == 3
    assert personnel.columns.tolist() == ["SOLDIER_ID", "SOLDIER_NAME"]
    assert personnel["SOLDIER_ID"].is_unique


def test_linkage_normalizes_risk_and_calculates_probability():
    personnel = pd.DataFrame({
        "SOLDIER_ID": ["1", "2", "3", "4"],
        "SOLDIER_NAME": ["가", "나", "다", "라"],
    })
    fitness = make_fitness_data()

    linked = calculate_injury_risk(personnel, fitness, injury_rate=10, seed=1)

    assert len(linked) == len(personnel)
    assert set(FITNESS_COLUMNS).issubset(linked.columns)
    assert linked["MESURE_ID"].tolist() == fitness["MESURE_ID"].tolist()
    assert linked["SOLDIER_ID"].tolist() == personnel["SOLDIER_ID"].tolist()
    assert linked["SOLDIER_NAME"].tolist() == personnel["SOLDIER_NAME"].tolist()
    assert {"REGION_NAME", "UNIT_NAME", "RANK_NAME"}.issubset(linked.columns)
    pd.testing.assert_frame_equal(
        linked.loc[:, FITNESS_COLUMNS],
        fitness.loc[:, FITNESS_COLUMNS],
    )
    assert {"BMI_CATEGORY", "CARDIO_LEVEL"}.issubset(linked.columns)
    assert linked["RELATIVE_INJURY_RISK"].mean() == pytest.approx(1.0)
    np.testing.assert_allclose(
        linked["INJURY_PROBABILITY"],
        linked["RELATIVE_INJURY_RISK"] * 0.1,
    )
    assert linked["INJURY_PROBABILITY"].between(0, 1).all()


def test_linked_category_summary_reports_counts_and_percentages():
    linked = pd.DataFrame({
        "BMI_CATEGORY": ["UNDERWEIGHT", "NORMAL", "OVERWEIGHT", "OBESE"],
        "CARDIO_LEVEL": ["LOW", "MODERATE", "MODERATE", "HIGH"],
    })

    summary = summarize_linked_categories(linked)

    bmi_summary = summary[summary["분류"] == "BMI 구간"].set_index("구간")
    assert bmi_summary["인원수(명)"].to_dict() == {
        "저체중": 1,
        "정상": 1,
        "과체중": 1,
        "비만": 1,
    }
    assert bmi_summary["비율(%)"].to_dict() == {
        "저체중": 25.0,
        "정상": 25.0,
        "과체중": 25.0,
        "비만": 25.0,
    }

    cardio_summary = summary[summary["분류"] == "CARDIO 구간"].set_index("구간")
    assert cardio_summary["인원수(명)"].to_dict() == {
        "하위 25%": 1,
        "중간 50%": 2,
        "상위 25%": 1,
    }
    assert cardio_summary["비율(%)"].to_dict() == {
        "하위 25%": 25.0,
        "중간 50%": 50.0,
        "상위 25%": 25.0,
    }


def test_linkage_rejects_personnel_and_fitness_row_count_mismatch():
    personnel = pd.DataFrame({
        "SOLDIER_ID": ["1"],
        "SOLDIER_NAME": ["가"],
    })

    with pytest.raises(ValueError, match="수가 같아야"):
        calculate_injury_risk(personnel, make_fitness_data())


def test_injury_generation_allows_repeat_injuries_with_poisson_counts():
    personnel = pd.DataFrame({
        "군번": [f"soldier-{index}" for index in range(100)],
        "이름": [f"장병-{index}" for index in range(100)],
        "부대": ["A"] * 100,
        "계급": ["일병"] * 100,
        "INJURY_PROBABILITY": [1.0] * 100,
    })

    injuries = generate_injury_data(personnel, seed=3)

    injury_counts = injuries.groupby("군번").size()
    assert injuries["군번"].nunique() < len(injuries)
    assert injury_counts.max() > 1
    assert not injuries.duplicated(["군번", "부상세부부위"]).any()


def test_zero_injury_intensity_generates_no_injuries():
    personnel = pd.DataFrame({
        "군번": ["never"],
        "이름": ["없음"],
        "부대": ["A"],
        "계급": ["일병"],
        "INJURY_PROBABILITY": [0.0],
    })

    injuries = generate_injury_data(personnel, seed=3)

    assert injuries.empty


def test_linkage_rejects_invalid_baseline_rate():
    personnel = pd.DataFrame({
        "SOLDIER_ID": ["1"],
        "SOLDIER_NAME": ["가"],
    })
    fitness = make_fitness_data().iloc[:1]

    with pytest.raises(ValueError, match="injury_rate"):
        calculate_injury_risk(personnel, fitness, injury_rate=101)
