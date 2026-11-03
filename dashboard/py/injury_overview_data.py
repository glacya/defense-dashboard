"""부상 현황 화면의 종목×등급 부상 집계, 장병별 부상 건수, 기준 설명을 만듭니다.

집계는 SQL(dashboard.py.queries)에서 끝내고, 빈 조합 채우기·비율 계산 등 화면 표 모양만 pandas로 맞춥니다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS, GRADE_LABELS

METADATA_TEXT = {
    '집계범위': '장병 명단 전체와 보유 부상 기록 전체. 부상자 비율은 부상 기록 1건 이상 장병 수 / 집단 전체 인원 ×100.',
    '등급': '장병별 최신 측정의 종목별 등급. 종합 인증등급이 아님. 남성 19~24세 범위 밖·누락·미측정은 판정 불가.',
    '기간': '부상 발생일이 없어 기간별 집계·발생률·측정 당시 부상 판정은 하지 않음.',
    '합성': '부상 기록은 BMI·심폐 수준을 기반으로 합성됨. 등급별 차이를 실제 부상 위험이나 인과관계로 해석하지 않음.',
    '중복': '같은 장병의 반복 부상은 부상인원 1명, 부상건수 여러 건으로 집계. 서로 다른 종목의 인원을 합산하지 않음.',
}


def injury_grade_table() -> pd.DataFrame:
    """종목×등급별 부상 집계(queries.load_injury_by_grade)를 화면 표로: 모든 조합(인원 0 포함), 종목·등급 순서, 부상자 비율."""
    counts = queries.load_injury_by_grade().set_index(['EVENT', 'GRADE'])
    rows = []
    for event, (label, _) in EVENTS.items():
        for grade, text in GRADE_LABELS.items():
            total, injured, injuries = (int(counts.loc[(event, grade), column]) if (event, grade) in counts.index else 0
                                        for column in ['TOTAL', 'INJURED', 'INJURIES'])
            rows.append({'종목': label, '등급': text, '전체인원': total, '부상인원': injured, '부상건수': injuries,
                         '부상자비율': injured / total * 100 if total else float('nan')})
    return pd.DataFrame(rows)


def injury_people() -> pd.DataFrame:
    """장병 명단(queries.load_roster)에 장병별 부상 건수(없으면 0)를 붙입니다."""
    counts = queries.load_soldier_injury_counts().set_index('SOLDIER_ID').INJURY_COUNT
    roster = queries.load_roster()
    return roster.assign(INJURY_COUNT=roster.SOLDIER_ID.map(counts).fillna(0).astype('int64'))


def injury_metadata() -> dict:
    """집계 기준 설명(화면 안내용)."""
    return {'생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), **METADATA_TEXT}
