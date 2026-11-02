"""회차별 집중관리 판정(측정값·신상 포함)과 기준 설명을 만듭니다.

판정 행은 SQL(dashboard.py.queries의 판정 CTE)에서 받고, 표시용 컬럼(종목 이름·선정 사유 등)만 pandas로 붙입니다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS, REASONS, event_labels, join_labels

# 판정표에만 있는 계산용 컬럼(개인 상세가 쓰는 1차 값 등)은 결과에서 뺀다.
INTERNAL_SUFFIXES = ('_FIRST_VALUE', '_FIRST_GRADE', '_PERSISTENT')
METADATA_TEXT = {
    '기준': '측정 당시 남성 19~24세 기준. 연령 범위 밖·누락은 종목 판정 불가.',
    '대상': '네 조건의 합집합. 회차별 장병 한 번만 집계. 소속별 비교 없음.',
    '시간': '악화는 1차 대비 선택 회차. 지속 미달은 선택 회차까지 최근 세 회차. 미래 측정 미사용.',
    '누락': 'False는 선정 조건이 확인되지 않음이며 건강·통과 보장이 아님. 미달 개수는 네 종목 모두 판정 가능할 때만 확정.',
    'BMI': '낮음 <18.5, 보통 18.5 이상 25 미만, 높음 25 이상. 보통은 정상·비만전단계 포함.',
    '상세': '이 파일은 대상 여부를 보존하기 위해 비대상 측정도 포함. 측정값·신상은 원본과 식별자로 연결.',
}


def build_targets(judged: pd.DataFrame) -> pd.DataFrame:
    """판정표에 BMI 구간, 1차 대비 미달 수 변화, 미달·신규 미달·지속 미달 종목 이름, 선정 사유를 붙입니다."""
    data = judged.copy()
    data['BMI_GROUP'] = np.select([data.BMI.lt(18.5), data.BMI.lt(25)], ['낮음', '보통'], '높음')
    data['FAIL_COUNT_CHANGE'] = data.FAIL_COUNT - data.FIRST_FAIL_COUNT
    labels = event_labels()
    failed = {event: data[f'{event}_GRADE'].eq(0) for event in EVENTS}
    data['FAILED_EVENTS'] = join_labels(failed, labels)
    data['NEW_FAILED_EVENTS'] = join_labels(
        {event: failed[event] & data[f'{event}_FIRST_GRADE'].ne(0) for event in EVENTS}, labels)
    data['PERSISTENT_EVENTS'] = join_labels({event: data[f'{event}_PERSISTENT'] for event in EVENTS}, labels)
    data['SELECTION_REASONS'] = join_labels({flag: data[flag] for flag in REASONS}, REASONS)
    internal = [column for column in data if column.endswith(INTERNAL_SUFFIXES)] + ['FIRST_FAIL_COUNT']
    return data.drop(columns=internal)


def prepare_judgments(raw: pd.DataFrame) -> pd.DataFrame:
    """SQL 판정 행(queries.judged_cte)의 측정일을 화면이 쓰던 yyyymmdd 숫자로 바꿉니다."""
    return raw.assign(MESURE_DE=raw.MESURE_DE.astype('int64'))


def load_round_targets(round_number: int) -> pd.DataFrame:
    """선택 회차의 집중관리 대상자(판정 + 신상 + 종목 이름·선정 사유 등 표시용 컬럼)."""
    return build_targets(prepare_judgments(queries.load_round_targets(round_number)))


def targets_metadata() -> dict:
    """선정 기준 설명(화면 안내용)."""
    return {'생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), **METADATA_TEXT}
