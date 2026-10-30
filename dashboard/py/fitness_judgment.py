"""측정별 미달·집중관리 판정표를 SQL 한 번으로 읽어 캐시하는 공용 부분입니다(B 그룹 로더가 함께 씀).

종목 등급(0~3, 0은 미달)은 분석 단계가 measurement_classifications에 저장해 두므로 여기서 계산하지 않습니다.
빈 값·나이 범위는 DB 제약(NOT NULL)과 전처리(19~24세)가 보장하므로 따로 처리하지 않습니다.
- 회차(round): 장병별 측정일 순서(같은 날이면 MESURE_ID 순서)
- 미달 수(fail_count): 등급 0인 종목 수
- 집중관리: BMI 25 이상이면서 근력 또는 심폐 미달(high_bmi_fail), 2개 종목 이상 미달(multiple_fail),
  1차 대비 미달 수 증가(worsened), 같은 종목 최근 3회 연속 미달(persistent_fail) 중 하나(managed)
"""

import pandas as pd
import streamlit as st

from dashboard.db import DEFAULT_TTL, run_query
from data.scripts.fitness_standards import grade_cut

EVENTS = {'STRENGTH': ('근력', '%'), 'ENDURANCE': ('근지구력', '회'),
          'CARDIO': ('심폐지구력', 'mL/kg/min'), 'FLEXIBILITY': ('유연성', 'cm')}
REASONS = {'HIGH_BMI_FAIL': 'BMI≥25·근력 또는 심폐 미달', 'MULTIPLE_FAIL': '2개 이상 종목 미달',
           'WORSENED': '1차 대비 미달 종목 수 증가', 'PERSISTENT_FAIL': '동일 종목 최근 3회 지속 미달'}
GRADE_LABELS = {1: '1등급', 2: '2등급', 3: '3등급', 0: '3등급 미만'}
HIGH_BMI = 25
JOIN_SEPARATOR = ' · '

_CODES = [event.lower() for event in EVENTS]


def _each(template: str, separator: str = ', ') -> str:
    """종목마다 template의 {e}를 소문자 종목 코드로 바꿔 이어 붙입니다."""
    return separator.join(template.format(e=code) for code in _CODES)


JUDGED_SQL = f"""
WITH ordered AS (
    SELECT m.*, s.soldier_name, s.region_name, s.unit_name, s.rank_name,
        {_each('c.{e}_grade')},
        ROW_NUMBER() OVER (PARTITION BY m.soldier_id ORDER BY m.mesure_de, m.mesure_id) AS round
    FROM fitness_measurements m
    JOIN soldiers s USING (soldier_id)
    JOIN measurement_classifications c USING (mesure_id)
),
windowed AS (
    SELECT o.*,
        FIRST_VALUE(o.mesure_id) OVER first_round AS first_mesure_id,
        {_each('FIRST_VALUE(o.{e}) OVER first_round AS {e}_first_value')},
        {_each('FIRST_VALUE(o.{e}_grade) OVER first_round AS {e}_first_grade')},
        {_each('(COUNT(*) OVER recent = 3 AND bool_and(o.{e}_grade = 0) OVER recent) AS {e}_persistent')}
    FROM ordered o
    WINDOW first_round AS (PARTITION BY o.soldier_id ORDER BY o.round),
        recent AS (PARTITION BY o.soldier_id ORDER BY o.round ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
),
counted AS (
    SELECT w.*,
        {_each('(w.{e}_grade = 0)::int', ' + ')} AS fail_count,
        {_each('(w.{e}_first_grade = 0)::int', ' + ')} AS first_fail_count
    FROM windowed w
)
SELECT c.*,
    c.bmi >= :high_bmi AND (c.strength_grade = 0 OR c.cardio_grade = 0) AS high_bmi_fail,
    c.fail_count >= 2 AS multiple_fail,
    c.fail_count > c.first_fail_count AS worsened,
    ({_each('c.{e}_persistent', ' OR ')}) AS persistent_fail
FROM counted c
ORDER BY c.soldier_id COLLATE "C", c.round
"""


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def load_judged_measurements() -> pd.DataFrame:
    """측정 1건 = 1행인 판정표(측정값·신상·등급·1차 값·판정 플래그)를 군번·회차 순으로 돌려줍니다."""
    judged = run_query(JUDGED_SQL, {'high_bmi': HIGH_BMI})
    judged['MANAGED'] = judged[list(REASONS)].any(axis=1)
    judged['MESURE_DE'] = judged.MESURE_DE.astype('int64')  # CSV로 읽던 때처럼 yyyymmdd 숫자
    return judged


def join_labels(conditions: dict[str, pd.Series], labels: dict[str, str]) -> pd.Series:
    """행마다 조건이 참인 항목의 이름을 ' · '로 잇습니다(conditions와 labels는 같은 키)."""
    frame = pd.DataFrame(conditions)
    return frame.apply(lambda row: JOIN_SEPARATOR.join(labels[key] for key, hit in row.items() if hit), axis=1)


def event_labels() -> dict[str, str]:
    """종목 코드 -> 한글 이름."""
    return {event: label for event, (label, _) in EVENTS.items()}


def grade_standards() -> dict[str, dict[str, float]]:
    """종목별 1~3등급 하한(화면 안내용, 예전 metadata.json의 등급기준과 같은 모양)."""
    return {event: {str(level): grade_cut(event, level) for level in (1, 2, 3)} for event in EVENTS}
