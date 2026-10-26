"""체력 등급 기준 모듈(data/scripts/fitness_standards.py)을 테스트합니다."""

import math

import pytest

from data.scripts import fitness_standards
from data.scripts.fitness_standards import grade3_standards, grade_cut, grade_cut_table


def test_grade3_standards_keep_previous_csv_layout():
    """3등급 기준표가 이전 grade3_male_19_24.csv와 같은 컬럼·종목 순서와 값을 갖는지 확인합니다."""
    table = grade3_standards()

    assert table.columns.tolist() == [
        "sex", "age_min", "age_max", "exercise", "description", "rule", "min_value", "max_value", "unit",
    ]
    assert table["exercise"].tolist() == [
        "STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY", "BMI", "BODY_FAT_PERCENTAGE",
    ]
    # 실험 스크립트가 이 값으로 체력 미달을 판정한다(국민체력100 3등급, 19~24세 남성).
    assert table.set_index("exercise")["min_value"].to_dict() == {
        "STRENGTH": 51.8, "ENDURANCE": 42.0, "CARDIO": 42.0, "FLEXIBILITY": 6.1,
        "BMI": 18.5, "BODY_FAT_PERCENTAGE": 7.0,
    }
    assert table.set_index("exercise").loc["BMI", "rule"] == "min_inclusive_max_exclusive"


def test_grade_cut_rejects_missing_value():
    """값이 비어 있는 등급 하한을 요청하면 채울 곳을 알려 주며 오류를 내는지 확인합니다."""
    assert grade_cut("CARDIO", 2) == 44.8
    with pytest.raises(ValueError, match="GRADE_CUTS"):
        grade_cut("STRENGTH", 2)


def test_grade_cut_table_lists_every_missing_cut():
    """등급 하한 표를 만들 때 비어 있는 하한을 빠짐없이 알려 주는지 확인합니다."""
    with pytest.raises(ValueError, match="STRENGTH 2등급, ENDURANCE 2등급, FLEXIBILITY 2등급"):
        grade_cut_table(grades=(3, 2))


def test_grade_cut_table_uses_values_added_later(monkeypatch):
    """GRADE_CUTS에 등급 하한을 채우면 별도 수정 없이 표에 반영되는지 확인합니다."""
    cuts = {exercise: dict(grades) for exercise, grades in fitness_standards.GRADE_CUTS.items()}
    for exercise, value in (("STRENGTH", 60.0), ("ENDURANCE", 50.0), ("FLEXIBILITY", 10.0)):
        cuts[exercise][2] = value
    monkeypatch.setattr(fitness_standards, "GRADE_CUTS", cuts)

    table = grade_cut_table(grades=(3, 2))

    assert table.columns.tolist() == ["영문속성명", "3등급컷", "2등급컷"]
    assert table.set_index("영문속성명")["2등급컷"].to_dict() == {
        "STRENGTH": 60.0, "ENDURANCE": 50.0, "CARDIO": 44.8, "FLEXIBILITY": 10.0,
    }
    assert not any(math.isnan(value) for value in table["3등급컷"])
