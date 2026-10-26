"""19~24세 남성 체력 등급 기준(국민체력100)을 한곳에 모아 둔 모듈입니다.

거의 바뀌지 않고 크기도 작은 값이라 CSV(이전 data/definitions/grade3_male_19_24.csv) 대신 코드로 둡니다.
data/experiments의 실험 스크립트와 data/scripts/analysis가 같은 기준을 쓰도록 여기서 가져다 씁니다.
"""

import math

import pandas as pd

# 기준을 적용하는 대상
SEX = "M"
AGE_MIN, AGE_MAX = 19, 24

# 체력 4종목의 등급별 하한. GRADE_CUTS[종목][등급] = 그 등급 이상이 되는 최소값(이상이면 해당 등급 이상).
# 값을 모르는 등급은 None으로 두고, 알게 되면 채우거나 등급(예: 1)을 키로 추가한다.
# 3등급 하한(미달 여부의 기준)은 이전 grade3_male_19_24.csv 값이다.
# 심폐지구력(VO₂max)은 2018 한국스포츠개발원 보고서 표 39의 공식 컷 42.0 / 44.8 / 47.6이다.
GRADE_CUTS: dict[str, dict[int, float | None]] = {
    "STRENGTH": {3: 51.8, 2: 57.2, 1: 62.6},      # 근력(상대악력, %)
    "ENDURANCE": {3: 42.0, 2: 48.0, 1: 55.0},     # 근지구력(교차윗몸일으키기, 회)
    "CARDIO": {3: 42.0, 2: 44.8, 1: 47.6},  # 심폐지구력(VO₂max, ml/kg/min)
    "FLEXIBILITY": {3: 6.1, 2: 11.1, 1: 16.1},    # 유연성(앉아윗몸앞으로굽히기, cm)
}
FITNESS_EXERCISES = tuple(GRADE_CUTS)

# 체격 항목은 등급 하한이 아니라 정상 범위로 판정한다: (하한, 하한 포함 여부, 상한, 상한 포함 여부)
RANGE_STANDARDS: dict[str, tuple[float, bool, float, bool]] = {
    "BMI": (18.5, True, 25.0, False),                  # 18.5 이상 25 미만
    "BODY_FAT_PERCENTAGE": (7.0, False, 27.0, False),  # 7 초과 27 미만(%)
}

_DESCRIPTIONS = {
    "STRENGTH": ("근력", "%"),
    "ENDURANCE": ("근지구력", "회"),
    "CARDIO": ("심폐지구력(VO₂max)", "ml/kg/min"),
    "FLEXIBILITY": ("유연성", "cm"),
    "BMI": ("BMI", math.nan),  # 단위 없음(이전 CSV의 빈칸과 같게 NaN)
    "BODY_FAT_PERCENTAGE": ("체지방률", "%"),
}
# 이전 CSV의 rule 값: 하한·상한 포함 여부를 문자열로 나타낸다.
_RANGE_RULES = {
    (True, False): "min_inclusive_max_exclusive",
    (False, False): "min_exclusive_max_exclusive",
    (True, True): "min_inclusive_max_inclusive",
    (False, True): "min_exclusive_max_inclusive",
}


def grade_cut(exercise: str, grade: int) -> float:
    """체력 종목의 등급 하한을 반환합니다.

    Raises:
        ValueError: 그 종목이나 등급의 하한이 없거나 아직 채워지지 않았을 때
    """
    value = GRADE_CUTS.get(exercise, {}).get(grade)
    if value is None or not math.isfinite(value):
        raise ValueError(
            f"{exercise}의 {grade}등급 하한이 없습니다. data/scripts/fitness_standards.py의 GRADE_CUTS를 채우세요."
        )
    return value


def grade_cut_table(grades: tuple[int, ...] = (3, 2), exercises: tuple[str, ...] = FITNESS_EXERCISES) -> pd.DataFrame:
    """종목별 등급 하한 표를 반환합니다. 컬럼은 영문속성명과 '{등급}등급컷'입니다.

    Raises:
        ValueError: 요청한 등급의 하한이 하나라도 비어 있을 때(비어 있는 것을 모두 알려 줌)
    """
    missing = [
        f"{exercise} {grade}등급" for exercise in exercises for grade in grades
        if GRADE_CUTS.get(exercise, {}).get(grade) is None
    ]
    if missing:
        raise ValueError(
            f"등급 하한이 비어 있습니다: {', '.join(missing)}. data/scripts/fitness_standards.py의 GRADE_CUTS를 채우세요."
        )
    return pd.DataFrame([
        {"영문속성명": exercise, **{f"{grade}등급컷": grade_cut(exercise, grade) for grade in grades}}
        for exercise in exercises
    ])


def grade3_standards() -> pd.DataFrame:
    """이전 grade3_male_19_24.csv와 같은 컬럼·순서의 3등급 기준표를 반환합니다.

    컬럼: sex, age_min, age_max, exercise, description, rule, min_value, max_value, unit
    """
    rows = []
    for exercise in FITNESS_EXERCISES:
        description, unit = _DESCRIPTIONS[exercise]
        rows.append((SEX, AGE_MIN, AGE_MAX, exercise, description, "min_inclusive", grade_cut(exercise, 3), math.nan, unit))
    for exercise, (low, low_inclusive, high, high_inclusive) in RANGE_STANDARDS.items():
        description, unit = _DESCRIPTIONS[exercise]
        rows.append((SEX, AGE_MIN, AGE_MAX, exercise, description,
                     _RANGE_RULES[(low_inclusive, high_inclusive)], low, high, unit))
    return pd.DataFrame(rows, columns=[
        "sex", "age_min", "age_max", "exercise", "description", "rule", "min_value", "max_value", "unit",
    ])
