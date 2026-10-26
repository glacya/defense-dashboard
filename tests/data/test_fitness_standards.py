"""체력 등급 기준 모듈(data/scripts/fitness_standards.py)을 테스트합니다."""

import pytest

from data.scripts.fitness_standards import grade3_standards, grade_cut


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


def test_grade_cut_rejects_unknown_grade():
    """정의되지 않은 등급의 하한을 요청하면 채울 곳을 알려 주며 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="GRADE_CUTS"):
        grade_cut("STRENGTH", 4)
