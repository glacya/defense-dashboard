"""개인 상세용 회차별 판정과 1차 대비 변화를 만듭니다.

한 장병의 판정 행은 SQL(queries.load_soldier_judgments)에서 받고, 변화 계산과 표시용 컬럼은 pandas로 붙입니다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS, event_labels, join_labels
from dashboard.py.management_targets_data import build_targets, prepare_judgments

METADATA_TEXT = {
    '비교': '1차 대비 각 회차. 측정값 변화는 현재−1차. 등급 변화는 1등급이 가장 높음.',
    '주의': '측정값 변화와 미달·등급 변화는 별개. 판정 불가는 개선·유지로 처리하지 않음.',
}


def _grade_rank(grades: pd.Series) -> pd.Series:
    """등급이 높을수록 큰 값(1등급 4, 2등급 3, 3등급 2, 미달 1)으로 바꿉니다."""
    return grades.where(grades.ne(0), 4).rsub(5)


def build_changes(judged: pd.DataFrame) -> pd.DataFrame:
    """측정마다 1차 대비 측정값 변화, 등급 변화(개선·하락·유지), 미달에서 벗어난 종목을 계산합니다."""
    changes = judged[['MESURE_ID', 'SOLDIER_ID']].copy()
    for event in EVENTS:
        changes[f'{event}_CHANGE'] = judged[event] - judged[f'{event}_FIRST_VALUE']
        difference = _grade_rank(judged[f'{event}_GRADE']) - _grade_rank(judged[f'{event}_FIRST_GRADE'])
        changes[f'{event}_GRADE_CHANGE'] = np.select([difference.gt(0), difference.lt(0)], ['개선', '하락'], '유지')
    improved = {event: judged[f'{event}_FIRST_GRADE'].eq(0) & judged[f'{event}_GRADE'].gt(0) for event in EVENTS}
    changes['IMPROVED_EVENTS'] = join_labels(improved, event_labels())
    return changes


def load_soldier_history(soldier_id: str) -> pd.DataFrame:
    """한 장병의 회차별 판정·신상·체력유형에 1차 대비 변화를 붙여 회차 순으로 돌려줍니다."""
    raw = prepare_judgments(queries.load_soldier_judgments(soldier_id))
    targets = build_targets(raw)
    changes = build_changes(raw)
    keys = ['MESURE_ID', 'SOLDIER_ID']
    extra = [column for column in changes if column not in targets or column in keys]
    return targets.merge(changes[extra], on=keys, how='left', validate='one_to_one')


def personal_metadata() -> dict:
    """비교 기준 설명(화면 안내용)."""
    return {'생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), **METADATA_TEXT}
