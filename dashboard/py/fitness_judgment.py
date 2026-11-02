"""체력 판정 화면들이 함께 쓰는 종목·집중관리 사유·등급 이름과 표시용 도우미입니다.

판정 자체(회차, 미달 수, 1차 값, 지속 미달, 집중관리 사유)는 SQL(dashboard.py.queries의 판정 CTE)이 계산합니다.
종목 등급(0~3, 0은 미달)은 분석 단계가 measurement_classifications에 저장해 둔 값을 씁니다.
"""

import pandas as pd

from data.scripts.fitness_standards import grade_cut

EVENTS = {'STRENGTH': ('근력', '%'), 'ENDURANCE': ('근지구력', '회'),
          'CARDIO': ('심폐지구력', 'mL/kg/min'), 'FLEXIBILITY': ('유연성', 'cm')}
REASONS = {'HIGH_BMI_FAIL': 'BMI≥25·근력 또는 심폐 미달', 'MULTIPLE_FAIL': '2개 이상 종목 미달',
           'WORSENED': '1차 대비 미달 종목 수 증가', 'PERSISTENT_FAIL': '동일 종목 최근 3회 지속 미달'}
GRADE_LABELS = {1: '1등급', 2: '2등급', 3: '3등급', 0: '3등급 미만'}
JOIN_SEPARATOR = ' · '


def join_labels(conditions: dict[str, pd.Series], labels: dict[str, str]) -> pd.Series:
    """행마다 조건이 참인 항목의 이름을 ' · '로 잇습니다(conditions와 labels는 같은 키)."""
    frame = pd.DataFrame(conditions)
    if frame.empty:
        return pd.Series("", index=frame.index, dtype=object)
    return frame.apply(lambda row: JOIN_SEPARATOR.join(labels[key] for key, hit in row.items() if hit), axis=1)


def event_labels() -> dict[str, str]:
    """종목 코드 -> 한글 이름."""
    return {event: label for event, (label, _) in EVENTS.items()}


def grade_standards() -> dict[str, dict[str, float]]:
    """종목별 1~3등급 하한(화면 안내용, 예전 metadata.json의 등급기준과 같은 모양)."""
    return {event: {str(level): grade_cut(event, level) for level in (1, 2, 3)} for event in EVENTS}
