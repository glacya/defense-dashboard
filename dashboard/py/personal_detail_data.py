"""개인 상세용 1차 대비 변화 자료와 부상 기록을 검증해 읽습니다.

DB 모드는 캐시된 판정표(fitness_judgment.load_judged_measurements)의 1차 값으로 변화를 계산하고,
CSV 모드는 analysis2가 만든 CSV를 읽습니다.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL, run_query
from dashboard.py.fitness_judgment import EVENTS, event_labels, join_labels, load_judged_measurements
from dashboard.py.management_targets_data import load_targets
from dashboard.py.roster_data import INJURIES_SQL
from data.scripts.utils import require_columns

INJURY_COLUMNS = ['INJURY_ID','SOLDIER_ID','INJURY_CATEGORY','INJURY_LOCATION','PREVENTABILITY','SEVERITY']
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


@st.cache_data(show_spinner=False)
def _read_extra(directory: str, stamps: tuple[int,...], injury_path: str) -> tuple[pd.DataFrame,pd.DataFrame,dict,bool]:
    folder=Path(directory)
    changes=pd.read_csv(folder/'personal_changes.csv',dtype={'MESURE_ID':'string','SOLDIER_ID':'string','FIRST_MESURE_ID':'string'})
    metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    injury=Path(injury_path)
    present=injury.exists()
    injuries=pd.read_csv(injury,dtype='string') if present else pd.DataFrame(columns=INJURY_COLUMNS)
    return changes,injuries,metadata,present


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _read_extra_db() -> tuple[pd.DataFrame,pd.DataFrame,dict,bool]:
    metadata={'생성일시':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),**METADATA_TEXT}
    return build_changes(load_judged_measurements()),run_query(INJURIES_SQL),metadata,True


def load_personal(source: str | None = None) -> tuple[pd.DataFrame,pd.DataFrame,dict,bool]:
    """집중관리 판정(측정값 포함)에 1차 대비 변화를 붙이고, 부상 기록과 기준 설명을 함께 돌려줍니다."""
    source=resolve_source(source)
    data,_,_=load_targets(source)
    if source!=CSV:
        changes,injuries,metadata,present=_read_extra_db()
    else:
        from data.scripts.paths import PROCESSED_PERSONAL_DETAIL_DIR, SYNTHETIC_INJURY_PATH
        files=[PROCESSED_PERSONAL_DETAIL_DIR/'personal_changes.csv',PROCESSED_PERSONAL_DETAIL_DIR/'metadata.json']
        stamps=tuple(p.stat().st_mtime_ns for p in files)+(SYNTHETIC_INJURY_PATH.stat().st_mtime_ns if SYNTHETIC_INJURY_PATH.exists() else -1,)
        changes,injuries,metadata,present=_read_extra(str(PROCESSED_PERSONAL_DETAIL_DIR),stamps,str(SYNTHETIC_INJURY_PATH))
    require_columns(changes,['MESURE_ID','SOLDIER_ID','IMPROVED_EVENTS'])
    require_columns(injuries,INJURY_COLUMNS)
    if injuries.INJURY_ID.duplicated().any():
        raise ValueError('부상 식별자 중복')
    extra=[c for c in changes if c not in data or c in ['MESURE_ID','SOLDIER_ID']]
    merged=data.merge(changes[extra],on=['MESURE_ID','SOLDIER_ID'],how='left',validate='one_to_one',indicator=True)
    if merged['_merge'].ne('both').any():
        raise ValueError('변화 자료와 측정 자료가 일치하지 않습니다. 분석을 다시 실행하세요.')
    merged=merged.drop(columns='_merge')
    merged['IMPROVED_EVENTS']=merged.IMPROVED_EVENTS.fillna('')
    return merged,injuries,metadata,present
