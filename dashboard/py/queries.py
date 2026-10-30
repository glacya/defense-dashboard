"""화면별 DB 조회(SQL)를 한곳에 모읍니다.

화면에 필요한 결과만 받도록 집계(GROUP BY)·필터(WHERE)·한 장병 조회를 SQL에서 끝냅니다.
테이블 전체를 받아 pandas로 줄이지 않습니다. 결과는 dashboard.db.run_query가 캐시합니다(읽기 전용, 만료 없음).
화면 입력값(장병, 회차, 유형 등)은 모두 :이름 params로 넘깁니다.

공통 부분
- LATEST_CTE: 장병별 최신 측정 1건(측정일, 같으면 MESURE_ID가 큰 것)과 저장된 종목 등급·백분위·유형
- judged_cte(): 측정별 판정(회차, 미달 수, 1차 값, 최근 3회 지속 미달, 집중관리 사유). 종목 등급은
  분석 단계가 measurement_classifications에 저장한 값(0~3, 0은 미달)을 쓴다.
"""

import pandas as pd

from dashboard.db import run_query

HIGH_BMI = 25

# 장병별 최신 측정 1건
LATEST_CTE = """
latest AS (
    SELECT DISTINCT ON (m.soldier_id)
        m.soldier_id, m.mesure_id, m.mesure_de, m.age, m.bmi,
        m.strength, m.endurance, m.cardio, m.flexibility,
        c.average_percentile_grade, c.cluster,
        c.strength_grade, c.endurance_grade, c.cardio_grade, c.flexibility_grade,
        c.strength_percentile, c.endurance_percentile, c.cardio_percentile, c.flexibility_percentile
    FROM fitness_measurements m
    JOIN measurement_classifications c USING (mesure_id)
    ORDER BY m.soldier_id, m.mesure_de DESC, m.mesure_id DESC
)"""

# 측정별 판정. {where}에는 한 장병만 볼 때 'WHERE m.soldier_id = :soldier_id'를 넣는다
# (창 함수가 장병 단위라 미리 걸러도 결과가 같다). 회차 조건은 창 함수 뒤(바깥 쿼리)에서 건다.
_JUDGED_CTE = """
graded AS (
    SELECT m.mesure_id, m.soldier_id, m.mesure_de, m.age, m.height, m.weight, m.bmi, m.body_fat_percentage,
        m.strength, m.endurance, m.cardio, m.flexibility,
        c.average_percentile_grade, c.cluster,
        c.strength_grade, c.endurance_grade, c.cardio_grade, c.flexibility_grade,
        (c.strength_grade = 0)::int + (c.endurance_grade = 0)::int
            + (c.cardio_grade = 0)::int + (c.flexibility_grade = 0)::int AS fail_count,
        ROW_NUMBER() OVER (PARTITION BY m.soldier_id ORDER BY m.mesure_de, m.mesure_id) AS round
    FROM fitness_measurements m
    JOIN measurement_classifications c USING (mesure_id)
    {where}
),
windowed AS (
    SELECT g.*,
        FIRST_VALUE(g.mesure_id) OVER first_round AS first_mesure_id,
        FIRST_VALUE(g.fail_count) OVER first_round AS first_fail_count,
        FIRST_VALUE(g.strength) OVER first_round AS strength_first_value,
        FIRST_VALUE(g.endurance) OVER first_round AS endurance_first_value,
        FIRST_VALUE(g.cardio) OVER first_round AS cardio_first_value,
        FIRST_VALUE(g.flexibility) OVER first_round AS flexibility_first_value,
        FIRST_VALUE(g.strength_grade) OVER first_round AS strength_first_grade,
        FIRST_VALUE(g.endurance_grade) OVER first_round AS endurance_first_grade,
        FIRST_VALUE(g.cardio_grade) OVER first_round AS cardio_first_grade,
        FIRST_VALUE(g.flexibility_grade) OVER first_round AS flexibility_first_grade,
        -- 그 회차까지 최근 세 회차가 모두 미달이면 지속 미달
        COUNT(*) OVER recent = 3 AND bool_and(g.strength_grade = 0) OVER recent AS strength_persistent,
        COUNT(*) OVER recent = 3 AND bool_and(g.endurance_grade = 0) OVER recent AS endurance_persistent,
        COUNT(*) OVER recent = 3 AND bool_and(g.cardio_grade = 0) OVER recent AS cardio_persistent,
        COUNT(*) OVER recent = 3 AND bool_and(g.flexibility_grade = 0) OVER recent AS flexibility_persistent
    FROM graded g
    WINDOW first_round AS (PARTITION BY g.soldier_id ORDER BY g.round),
        recent AS (PARTITION BY g.soldier_id ORDER BY g.round ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
),
reasons AS (
    SELECT w.*,
        w.bmi >= :high_bmi AND (w.strength_grade = 0 OR w.cardio_grade = 0) AS high_bmi_fail,
        w.fail_count >= 2 AS multiple_fail,
        w.fail_count > w.first_fail_count AS worsened,
        w.strength_persistent OR w.endurance_persistent OR w.cardio_persistent OR w.flexibility_persistent
            AS persistent_fail
    FROM windowed w
),
judged AS (
    SELECT r.*, r.high_bmi_fail OR r.multiple_fail OR r.worsened OR r.persistent_fail AS managed
    FROM reasons r
)"""


def judged_cte(one_soldier: bool = False) -> str:
    """판정 CTE(graded → windowed → reasons → judged)입니다. one_soldier면 :soldier_id 한 명만 계산합니다."""
    return _JUDGED_CTE.format(where="WHERE m.soldier_id = :soldier_id" if one_soldier else "")


# ---------------------------------------------------------------- 메인(대시보드 홈)

# 지역·부대별 인원, 미달 인원(4종목 중 하나라도 미달), 2종목 이상 미달 인원,
# 체력 수준(4종목 중 가장 낮은 등급, 미달이 있으면 4등급)별 인원
HOME_UNITS_SQL = f"""
WITH {LATEST_CTE},
levels AS (
    SELECT s.region_name, s.unit_name,
        (l.strength_grade = 0)::int + (l.endurance_grade = 0)::int
            + (l.cardio_grade = 0)::int + (l.flexibility_grade = 0)::int AS fail_count,
        CASE WHEN LEAST(l.strength_grade, l.endurance_grade, l.cardio_grade, l.flexibility_grade) = 0 THEN 4
             ELSE GREATEST(l.strength_grade, l.endurance_grade, l.cardio_grade, l.flexibility_grade) END AS fitness_level
    FROM latest l
    JOIN soldiers s USING (soldier_id)
)
SELECT region_name, unit_name,
    count(*) AS total,
    count(*) FILTER (WHERE fail_count >= 1) AS failed,
    count(*) FILTER (WHERE fail_count >= 2) AS multiple_failed,
    count(*) FILTER (WHERE fitness_level = 1) AS level_1,
    count(*) FILTER (WHERE fitness_level = 2) AS level_2,
    count(*) FILTER (WHERE fitness_level = 3) AS level_3,
    count(*) FILTER (WHERE fitness_level = 4) AS level_4
FROM levels
GROUP BY region_name, unit_name
ORDER BY region_name COLLATE "C", unit_name COLLATE "C"
"""

# 부상 부위별·심각도별 건수와 전체 건수·부상 장병 수(GROUPING SETS로 한 번에)
HOME_INJURIES_SQL = """
SELECT injury_location, severity,
    count(*) AS injuries,
    count(DISTINCT soldier_id) AS injured_soldiers
FROM injuries
GROUP BY GROUPING SETS ((injury_location), (severity), ())
"""

# 미달 확률 경계1~3등급(안전 제외) 장병 수
NON_SAFE_COUNT_SQL = """
SELECT count(*) AS soldiers FROM soldier_failure_probabilities WHERE failure_probability >= :threshold
"""

FITNESS_TYPES_SQL = """
SELECT average_percentile_grade, cluster, type_name
FROM fitness_types
ORDER BY average_percentile_grade, cluster
"""

# 선택 유형(최신 측정 기준) 장병의 종목별 평균 백분위(백분위는 분석 단계가 전체 측정 안에서 매긴 값)
HOME_TYPE_PROFILE_SQL = f"""
WITH {LATEST_CTE}
SELECT count(*) AS members,
    avg(strength_percentile) AS strength, avg(endurance_percentile) AS endurance,
    avg(cardio_percentile) AS cardio, avg(flexibility_percentile) AS flexibility
FROM latest
WHERE average_percentile_grade = :grade AND cluster = :cluster
"""

# 선택 유형(최신 측정 기준) 장병에게 실제로 처방된 운동 상위 6개
HOME_TYPE_PRESCRIPTIONS_SQL = f"""
WITH {LATEST_CTE}
SELECT d.prescription AS exercise, count(*) AS prescriptions
FROM latest l
JOIN exercise_prescriptions p USING (mesure_id)
JOIN exercise_prescription_details d USING (prescription_type_id)
WHERE l.average_percentile_grade = :grade AND l.cluster = :cluster
GROUP BY d.prescription
ORDER BY prescriptions DESC, d.prescription COLLATE "C"
LIMIT 6
"""


def load_home_units() -> pd.DataFrame:
    """지역·부대별 인원·미달·체력 수준 분포(약 20행)."""
    return run_query(HOME_UNITS_SQL)


def load_home_injuries() -> dict:
    """부상 요약: 전체 건수, 부상 장병 수, 부위별·심각도별 건수(건수 많은 순, 같으면 이름 순)."""
    rows = run_query(HOME_INJURIES_SQL)
    total = rows.loc[rows.INJURY_LOCATION.isna() & rows.SEVERITY.isna()].iloc[0]

    def counts(column: str) -> pd.DataFrame:
        part = rows.loc[rows[column].notna(), [column, "INJURIES"]]
        return part.sort_values(["INJURIES", column], ascending=[False, True], kind="stable").reset_index(drop=True)

    return {"injuries": int(total.INJURIES), "injured_soldiers": int(total.INJURED_SOLDIERS),
            "locations": counts("INJURY_LOCATION"), "severities": counts("SEVERITY")}


def load_non_safe_count(threshold: float) -> int:
    """미달 확률이 threshold 이상(경계1~3등급)인 장병 수."""
    return int(run_query(NON_SAFE_COUNT_SQL, {"threshold": threshold}).SOLDIERS.iloc[0])


def load_fitness_types() -> pd.DataFrame:
    """유형 16개(등급, 군집, 유형명)."""
    return run_query(FITNESS_TYPES_SQL)


def load_home_type_profile(grade: int, cluster: int) -> pd.Series:
    """선택 유형 장병 수(MEMBERS)와 종목별 평균 백분위(STRENGTH 등). 해당 장병이 없으면 평균은 0."""
    row = run_query(HOME_TYPE_PROFILE_SQL, {"grade": grade, "cluster": cluster}).iloc[0]
    return row.fillna(0)


def load_home_type_prescriptions(grade: int, cluster: int) -> pd.DataFrame:
    """선택 유형 장병에게 처방된 운동 상위 6개(EXERCISE, PRESCRIPTIONS)."""
    return run_query(HOME_TYPE_PRESCRIPTIONS_SQL, {"grade": grade, "cluster": cluster})


# ---------------------------------------------------------------- p01 전체 체력 현황

# 집계 단위: 전체는 'ALL', 지역·부대별은 그 컬럼(허용 목록에서만 넣으므로 SQL에 넣어도 안전)
OVERVIEW_GROUPS = {None: "'ALL'", "REGION_NAME": "s.region_name", "UNIT_NAME": "s.unit_name"}

# 회차별: 측정 인원, 미달 인원(1종목 이상), 집중관리 인원, 집계 단위의 장병 수
OVERVIEW_ROUNDS_SQL = """
WITH {judged},
grouped AS (
    SELECT j.*, {group} AS grp
    FROM judged j
    JOIN soldiers s USING (soldier_id)
),
population AS (
    SELECT grp, count(DISTINCT soldier_id) AS total_soldiers
    FROM grouped
    GROUP BY grp
)
SELECT g.grp, g.round, p.total_soldiers,
    count(*) AS measured,
    count(*) FILTER (WHERE g.fail_count >= 1) AS failed,
    count(*) FILTER (WHERE g.managed) AS managed
FROM grouped g
JOIN population p USING (grp)
GROUP BY g.grp, g.round, p.total_soldiers
ORDER BY g.grp COLLATE "C", g.round
"""

# 회차×종목별: 측정 인원, 평균, 표준편차, 미달 인원, 1·2·3등급 인원
OVERVIEW_EVENTS_SQL = """
WITH {judged},
grouped AS (
    SELECT j.*, {group} AS grp
    FROM judged j
    JOIN soldiers s USING (soldier_id)
)
SELECT g.grp, g.round, e.event,
    count(*) AS measured,
    avg(e.value) AS mean,
    stddev_samp(e.value) AS std,
    count(*) FILTER (WHERE e.grade = 0) AS failed,
    count(*) FILTER (WHERE e.grade = 1) AS grade_1,
    count(*) FILTER (WHERE e.grade = 2) AS grade_2,
    count(*) FILTER (WHERE e.grade = 3) AS grade_3
FROM grouped g
CROSS JOIN LATERAL (VALUES
    ('STRENGTH', g.strength, g.strength_grade),
    ('ENDURANCE', g.endurance, g.endurance_grade),
    ('CARDIO', g.cardio, g.cardio_grade),
    ('FLEXIBILITY', g.flexibility, g.flexibility_grade)
) AS e(event, value, grade)
GROUP BY g.grp, g.round, e.event
ORDER BY g.grp COLLATE "C", g.round
"""

MEASURE_PERIOD_SQL = "SELECT min(mesure_de) AS first_date, max(mesure_de) AS last_date FROM fitness_measurements"


def _overview_sql(template: str, group_column: str | None) -> str:
    if group_column not in OVERVIEW_GROUPS:
        raise ValueError(f"지원하지 않는 조직 구분입니다: {group_column}")
    return template.format(judged=judged_cte(), group=OVERVIEW_GROUPS[group_column])


def load_overview_rounds(group_column: str | None = None) -> pd.DataFrame:
    """회차별(지역·부대별이면 그룹·회차별) 요약. 전체는 3행, 그룹별은 그룹 수 × 3행."""
    return run_query(_overview_sql(OVERVIEW_ROUNDS_SQL, group_column), {"high_bmi": HIGH_BMI})


def load_overview_events(group_column: str | None = None) -> pd.DataFrame:
    """회차×종목별(지역·부대별이면 그룹까지) 요약. 종목 코드는 EVENT 컬럼(STRENGTH 등)."""
    return run_query(_overview_sql(OVERVIEW_EVENTS_SQL, group_column), {"high_bmi": HIGH_BMI})


def load_measure_period() -> pd.Series:
    """측정일 범위(FIRST_DATE, LAST_DATE, yyyymmdd 문자열)."""
    return run_query(MEASURE_PERIOD_SQL).iloc[0]


# ---------------------------------------------------------------- 장병 명단(p02·p03·p06·p07·p08 공용)

ROSTER_SQL = """
SELECT soldier_id, soldier_name, region_name, unit_name, rank_name, front_rear_classification
FROM soldiers
ORDER BY soldier_id COLLATE "C"
"""


def load_roster() -> pd.DataFrame:
    """장병 명단 전체(3,582행, 신상 컬럼만)."""
    return run_query(ROSTER_SQL)


# ---------------------------------------------------------------- p02 미달·악화 대상자, p03 개인 상세

ROUND_NUMBERS_SQL = """
SELECT DISTINCT round
FROM (SELECT ROW_NUMBER() OVER (PARTITION BY soldier_id ORDER BY mesure_de, mesure_id) AS round
      FROM fitness_measurements) numbered
ORDER BY round
"""

# 선택 회차의 측정 인원, 집중관리 인원, 사유별 인원(사유는 겹침)
ROUND_SUMMARY_SQL = f"""
WITH {judged_cte()}
SELECT count(*) AS measured,
    count(*) FILTER (WHERE managed) AS managed,
    count(*) FILTER (WHERE high_bmi_fail) AS high_bmi_fail,
    count(*) FILTER (WHERE multiple_fail) AS multiple_fail,
    count(*) FILTER (WHERE worsened) AS worsened,
    count(*) FILTER (WHERE persistent_fail) AS persistent_fail
FROM judged
WHERE round = :round
"""

# 선택 회차의 집중관리 대상자(판정 + 신상)
ROUND_TARGETS_SQL = f"""
WITH {judged_cte()}
SELECT j.*, s.soldier_name, s.region_name, s.unit_name, s.rank_name
FROM judged j
JOIN soldiers s USING (soldier_id)
WHERE j.round = :round AND j.managed
ORDER BY j.soldier_id COLLATE "C"
"""

# 한 장병의 모든 회차 판정 + 신상 + 체력유형
SOLDIER_JUDGMENTS_SQL = f"""
WITH {judged_cte(one_soldier=True)}
SELECT j.*, s.soldier_name, s.region_name, s.unit_name, s.rank_name, t.type_name
FROM judged j
JOIN soldiers s USING (soldier_id)
LEFT JOIN fitness_types t USING (average_percentile_grade, cluster)
ORDER BY j.round
"""

# 회차별 전체 평균(개인 측정값과 비교용)
ROUND_MEANS_SQL = """
WITH numbered AS (
    SELECT m.*, ROW_NUMBER() OVER (PARTITION BY m.soldier_id ORDER BY m.mesure_de, m.mesure_id) AS round
    FROM fitness_measurements m
)
SELECT round, count(*) AS measured,
    avg(strength) AS strength, avg(endurance) AS endurance, avg(cardio) AS cardio, avg(flexibility) AS flexibility
FROM numbered
GROUP BY round
ORDER BY round
"""

SOLDIER_INJURIES_SQL = "SELECT * FROM injuries WHERE soldier_id = :soldier_id ORDER BY injury_id"

# 선택 측정의 종목별 백분위와, 같은 유형(등급·군집)인 전체 측정의 평균 백분위
MEASUREMENT_PROFILE_SQL = """
SELECT 'personal' AS profile, 1 AS members,
    strength_percentile AS strength, endurance_percentile AS endurance,
    cardio_percentile AS cardio, flexibility_percentile AS flexibility
FROM measurement_classifications
WHERE mesure_id = :mesure_id
UNION ALL
SELECT 'type', count(*),
    avg(c.strength_percentile), avg(c.endurance_percentile), avg(c.cardio_percentile), avg(c.flexibility_percentile)
FROM measurement_classifications c
JOIN measurement_classifications selected
    ON selected.average_percentile_grade = c.average_percentile_grade AND selected.cluster = c.cluster
WHERE selected.mesure_id = :mesure_id
"""


def load_round_numbers() -> list[int]:
    """측정 회차 번호(1, 2, 3)."""
    return [int(number) for number in run_query(ROUND_NUMBERS_SQL).ROUND]


def load_round_summary(round_number: int) -> pd.Series:
    """선택 회차 요약 1행(MEASURED, MANAGED, 사유별 인원)."""
    return run_query(ROUND_SUMMARY_SQL, {"round": round_number, "high_bmi": HIGH_BMI}).iloc[0]


def load_round_targets(round_number: int) -> pd.DataFrame:
    """선택 회차 집중관리 대상자의 판정 행(가공 전)."""
    return run_query(ROUND_TARGETS_SQL, {"round": round_number, "high_bmi": HIGH_BMI})


def load_soldier_judgments(soldier_id: str) -> pd.DataFrame:
    """한 장병의 회차별 판정 행(가공 전, 회차 순)."""
    return run_query(SOLDIER_JUDGMENTS_SQL, {"soldier_id": soldier_id, "high_bmi": HIGH_BMI})


def load_round_means() -> pd.DataFrame:
    """회차별 측정 인원(MEASURED)과 종목별 평균(STRENGTH 등)."""
    return run_query(ROUND_MEANS_SQL)


def load_soldier_injuries(soldier_id: str) -> pd.DataFrame:
    """한 장병의 부상 기록."""
    return run_query(SOLDIER_INJURIES_SQL, {"soldier_id": soldier_id})


def load_measurement_profile(mesure_id) -> tuple[pd.Series, pd.Series, int]:
    """(선택 측정 백분위, 같은 유형 평균 백분위, 같은 유형 측정 수). 종목 순서는 STRENGTH, ENDURANCE, CARDIO, FLEXIBILITY."""
    rows = run_query(MEASUREMENT_PROFILE_SQL, {"mesure_id": int(mesure_id)}).set_index("PROFILE")
    if "personal" not in rows.index:
        raise ValueError("선택 측정의 백분위 자료가 없습니다.")
    events = ["STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY"]
    return rows.loc["personal", events], rows.loc["type", events], int(rows.loc["type", "MEMBERS"])


# ---------------------------------------------------------------- p06 부상 현황

INJURY_SUMMARY_SQL = """
SELECT (SELECT count(*) FROM soldiers) AS total_soldiers,
    count(*) AS injuries,
    count(DISTINCT soldier_id) AS injured_soldiers,
    (SELECT count(*) FROM (SELECT soldier_id FROM injuries GROUP BY soldier_id HAVING count(*) >= 2) repeated)
        AS repeated_soldiers
FROM injuries
"""

# 지역·부대·계급 필터(비우면 전체)를 건 부상 건수를 부위별, 심각도별, 지역별, 부대별, 계급별, 전체로 한 번에
# (집계한 컬럼 외에는 NULL. 원본에는 빈 값이 없으므로 NULL이 아닌 컬럼이 그 행의 기준이다)
INJURY_DISTRIBUTION_SQL = """
SELECT i.injury_location, i.severity, s.region_name, s.unit_name, s.rank_name, count(*) AS injuries
FROM injuries i
JOIN soldiers s USING (soldier_id)
WHERE (CAST(:regions AS text[]) IS NULL OR s.region_name = ANY(CAST(:regions AS text[])))
  AND (CAST(:units AS text[]) IS NULL OR s.unit_name = ANY(CAST(:units AS text[])))
  AND (CAST(:ranks AS text[]) IS NULL OR s.rank_name = ANY(CAST(:ranks AS text[])))
GROUP BY GROUPING SETS ((i.injury_location), (i.severity), (s.region_name), (s.unit_name), (s.rank_name), ())
"""

# 최신 측정의 종목별 등급 × 부상(등급별 전체 인원, 부상 장병 수, 부상 건수)
INJURY_BY_GRADE_SQL = f"""
WITH {LATEST_CTE},
injury_counts AS (
    SELECT soldier_id, count(*) AS injury_count FROM injuries GROUP BY soldier_id
),
per_soldier AS (
    SELECT l.*, COALESCE(c.injury_count, 0) AS injury_count
    FROM latest l
    LEFT JOIN injury_counts c USING (soldier_id)
)
SELECT e.event, e.grade,
    count(*) AS total,
    count(*) FILTER (WHERE p.injury_count > 0) AS injured,
    sum(p.injury_count)::int AS injuries
FROM per_soldier p
CROSS JOIN LATERAL (VALUES
    ('STRENGTH', p.strength_grade), ('ENDURANCE', p.endurance_grade),
    ('CARDIO', p.cardio_grade), ('FLEXIBILITY', p.flexibility_grade)
) AS e(event, grade)
GROUP BY e.event, e.grade
"""

SOLDIER_INJURY_COUNTS_SQL = "SELECT soldier_id, count(*) AS injury_count FROM injuries GROUP BY soldier_id"


def load_injury_summary() -> pd.Series:
    """전체 장병 수, 부상 건수, 부상 장병 수, 2건 이상 부상 장병 수(1행)."""
    return run_query(INJURY_SUMMARY_SQL).iloc[0]


def load_injury_distribution(regions: list[str], units: list[str], ranks: list[str]) -> pd.DataFrame:
    """필터를 건 부상 건수(GROUPING SETS 결과). 빈 목록은 그 조건을 걸지 않습니다."""
    params = {"regions": regions or None, "units": units or None, "ranks": ranks or None}
    return run_query(INJURY_DISTRIBUTION_SQL, params)


def distribution_counts(distribution: pd.DataFrame, column: str | None) -> pd.DataFrame | int:
    """load_injury_distribution 결과에서 한 기준(column)의 건수 표를, column이 None이면 전체 건수를 꺼냅니다."""
    keys = ["INJURY_LOCATION", "SEVERITY", "REGION_NAME", "UNIT_NAME", "RANK_NAME"]
    if column is None:
        total = distribution.loc[distribution[keys].isna().all(axis=1), "INJURIES"]
        return int(total.iloc[0]) if len(total) else 0
    return distribution.loc[distribution[column].notna(), [column, "INJURIES"]].reset_index(drop=True)


def load_injury_by_grade() -> pd.DataFrame:
    """종목(EVENT)·등급(GRADE)별 전체 인원(TOTAL), 부상 장병 수(INJURED), 부상 건수(INJURIES). 인원이 없는 조합은 없음."""
    return run_query(INJURY_BY_GRADE_SQL)


def load_soldier_injury_counts() -> pd.DataFrame:
    """부상이 있는 장병별 부상 건수."""
    return run_query(SOLDIER_INJURY_COUNTS_SQL)


# ---------------------------------------------------------------- p07 체력 지도·후속조치

# 장병별 1행: 신상 + 다음 회차 미달 확률 + 최신 측정 + 최신 측정의 체력유형
FOLLOWUP_POPULATION_SQL = f"""
WITH {LATEST_CTE}
SELECT s.soldier_id, s.soldier_name, s.region_name, s.unit_name, s.rank_name,
    p.failure_probability,
    l.mesure_id, l.mesure_de, l.age, l.bmi, l.strength, l.endurance, l.cardio, l.flexibility,
    l.average_percentile_grade, l.cluster, t.type_name
FROM soldiers s
LEFT JOIN soldier_failure_probabilities p USING (soldier_id)
LEFT JOIN latest l USING (soldier_id)
LEFT JOIN fitness_types t USING (average_percentile_grade, cluster)
ORDER BY s.soldier_id COLLATE "C"
"""


def load_followup_population() -> pd.DataFrame:
    """장병별 신상·미달 확률·최신 측정·체력유형(3,582행)."""
    return run_query(FOLLOWUP_POPULATION_SQL)


# ---------------------------------------------------------------- p04 부대 현황(필터)

# 측정일 기간(:start~:end, yyyymmdd) 안에서 장병별 가장 최근 측정 1건 + 신상
IN_RANGE_LATEST_CTE = """
in_range_latest AS (
    SELECT DISTINCT ON (m.soldier_id) m.*, s.soldier_name, s.region_name, s.unit_name, s.rank_name
    FROM fitness_measurements m
    JOIN soldiers s USING (soldier_id)
    WHERE m.mesure_de BETWEEN :start AND :end
    ORDER BY m.soldier_id, m.mesure_de DESC, m.mesure_id DESC
)"""

# 필터 선택지: 기간 안 최신 측정 장병의 지역·부대·계급 조합과 나이 범위
FILTER_OPTIONS_SQL = f"""
WITH {IN_RANGE_LATEST_CTE}
SELECT region_name, unit_name, rank_name, min(age) AS age_min, max(age) AS age_max
FROM in_range_latest
GROUP BY region_name, unit_name, rank_name
"""

# 필터를 건 장병별 최신 측정 목록 + 그 측정의 체력유형
FILTERED_LATEST_SQL = f"""
WITH {IN_RANGE_LATEST_CTE}
SELECT l.*, c.average_percentile_grade, c.cluster, t.type_name
FROM in_range_latest l
LEFT JOIN measurement_classifications c USING (mesure_id)
LEFT JOIN fitness_types t USING (average_percentile_grade, cluster)
WHERE l.region_name = ANY(CAST(:regions AS text[]))
  AND l.unit_name = ANY(CAST(:units AS text[]))
  AND l.rank_name = ANY(CAST(:ranks AS text[]))
  AND l.age BETWEEN :age_min AND :age_max
ORDER BY l.mesure_de, l.mesure_id
"""


def load_filter_options(start: str, end: str) -> pd.DataFrame:
    """측정일 기간(yyyymmdd) 안 최신 측정 장병의 지역·부대·계급 조합별 나이 최소·최대."""
    return run_query(FILTER_OPTIONS_SQL, {"start": start, "end": end})


def load_filtered_latest(start: str, end: str, regions: list[str], units: list[str], ranks: list[str],
                         age_range: tuple[int, int]) -> pd.DataFrame:
    """필터를 건 장병별 최신 측정 목록. 지역·부대·계급 중 하나라도 비어 있으면 빈 표(아무것도 고르지 않음)."""
    params = {"start": start, "end": end, "regions": list(regions), "units": list(units), "ranks": list(ranks),
              "age_min": int(age_range[0]), "age_max": int(age_range[1])}
    if not (regions and units and ranks):
        # 빈 문자열은 실제 이름(NOT NULL, 빈 값 없음)과 겹치지 않으므로 결과가 비고 컬럼은 유지된다.
        params.update(regions=[""], units=[""], ranks=[""])
    return run_query(FILTERED_LATEST_SQL, params)
