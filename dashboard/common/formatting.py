"""표시·집계에 쓰는 상수와 데이터 가공 함수입니다."""

from __future__ import annotations

import hashlib
from datetime import date

import numpy as np
import pandas as pd

from data.scripts.fitness_standards import GRADE_CUTS, RANGE_STANDARDS

NAV_STATE_KEY = "nav_links"
BMI_CATEGORY_ORDER = ("저체중", "정상", "과체중", "비만")
RANK_ORDER = ("이병", "일병", "상병", "병장")
FITNESS_ITEM_LABELS = {
    "STRENGTH": "근력",
    "ENDURANCE": "근지구력",
    "CARDIO": "심폐지구력",
    "FLEXIBILITY": "유연성",
}
GRADE_LABELS = ("1등급", "2등급", "3등급", "미달")


def filter_signature(*values: object) -> str:
    """필터 조합을 위젯 key에 쓸 짧은 문자열로 바꿉니다."""
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()[:12]


def classify_bmi(values: pd.Series) -> pd.Series:
    return pd.Series(
        np.select([values < 18.5, values < 25, values < 30], ["저체중", "정상", "과체중"], default="비만"),
        index=values.index,
        dtype="string",
    )


def period_mask(dates: pd.Series, start: date, end: date) -> pd.Series:
    """시작일 00:00부터 종료일 23:59:59.999까지 포함하는 마스크입니다."""
    end_of_day = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return dates.between(pd.Timestamp(start), end_of_day)


def latest_measurements(measurements: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """기간 안에서 장병별 가장 최근 측정 한 건을 반환합니다."""
    in_range = measurements.loc[period_mask(measurements["MESURE_DE"], start, end)]
    return (
        in_range.sort_values(["MESURE_DE", "MESURE_ID"], kind="stable")
        .drop_duplicates("SOLDIER_ID", keep="last")
        .reset_index(drop=True)
    )


def add_deficiency_flags(data: pd.DataFrame) -> pd.DataFrame:
    """체력 4종목과 체격 기준을 적용해 미달·등급 컬럼을 추가합니다."""
    result = data.copy()
    for column in FITNESS_ITEM_LABELS:
        values = pd.to_numeric(result[column], errors="coerce")
        result[f"미달_{column}"] = values.lt(GRADE_CUTS[column][3])
        result[f"등급_{column}"] = np.select(
            [values.ge(GRADE_CUTS[column][1]), values.ge(GRADE_CUTS[column][2]), values.ge(GRADE_CUTS[column][3])],
            ["1등급", "2등급", "3등급"],
            default="미달",
        )
    for column, (lower, lower_inclusive, upper, upper_inclusive) in RANGE_STANDARDS.items():
        values = pd.to_numeric(result[column], errors="coerce")
        lower_failed = values.lt(lower) if lower_inclusive else values.le(lower)
        upper_failed = values.gt(upper) if upper_inclusive else values.ge(upper)
        result[f"미달_{column}"] = lower_failed | upper_failed
    fitness_flags = [f"미달_{column}" for column in FITNESS_ITEM_LABELS]
    management_flags = fitness_flags + ["미달_BMI", "미달_BODY_FAT_PERCENTAGE"]
    result["체력미달"] = result[fitness_flags].any(axis=1)
    result["관리대상"] = result[management_flags].any(axis=1)
    return result


def add_measurement_rounds(data: pd.DataFrame) -> pd.DataFrame:
    """장병별 측정일 순서로 개인 측정회차를 부여합니다."""
    result = data.sort_values(["SOLDIER_ID", "MESURE_DE", "MESURE_ID"], kind="stable").copy()
    result["측정회차"] = result.groupby("SOLDIER_ID", sort=False).cumcount() + 1
    return result