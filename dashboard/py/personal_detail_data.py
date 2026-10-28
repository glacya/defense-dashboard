"""개인 상세용 변화 자료와 부상 기록을 검증해 읽습니다."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.py.management_targets_data import load_targets
from data.scripts.paths import PROCESSED_PERSONAL_DETAIL_DIR, SYNTHETIC_INJURY_PATH
from data.scripts.utils import require_columns


@st.cache_data(show_spinner=False)
def _read_extra(directory: str, stamps: tuple[int,...], injury_path: str) -> tuple[pd.DataFrame,pd.DataFrame,dict,bool]:
    folder=Path(directory)
    changes=pd.read_csv(folder/'personal_changes.csv',dtype={'MESURE_ID':'string','SOLDIER_ID':'string','FIRST_MESURE_ID':'string'})
    require_columns(changes,['MESURE_ID','SOLDIER_ID','IMPROVED_EVENTS'])
    metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    injury=Path(injury_path)
    present=injury.exists()
    columns=['INJURY_ID','SOLDIER_ID','INJURY_CATEGORY','INJURY_LOCATION','PREVENTABILITY','SEVERITY']
    injuries=pd.read_csv(injury,dtype='string') if present else pd.DataFrame(columns=columns)
    require_columns(injuries,columns)
    if injuries.INJURY_ID.duplicated().any():
        raise ValueError('부상 식별자 중복')
    return changes,injuries,metadata,present


def load_personal() -> tuple[pd.DataFrame,pd.DataFrame,dict,bool]:
    """측정값은 원본에서, 판정·변화는 분석 파일에서 읽어 연결합니다."""
    data,_,_=load_targets()
    files=[PROCESSED_PERSONAL_DETAIL_DIR/'personal_changes.csv',PROCESSED_PERSONAL_DETAIL_DIR/'metadata.json']
    stamps=tuple(p.stat().st_mtime_ns for p in files)+(SYNTHETIC_INJURY_PATH.stat().st_mtime_ns if SYNTHETIC_INJURY_PATH.exists() else -1,)
    changes,injuries,metadata,present=_read_extra(str(PROCESSED_PERSONAL_DETAIL_DIR),stamps,str(SYNTHETIC_INJURY_PATH))
    extra=[c for c in changes if c not in data or c in ['MESURE_ID','SOLDIER_ID']]
    merged=data.merge(changes[extra],on=['MESURE_ID','SOLDIER_ID'],how='left',validate='one_to_one',indicator=True)
    if merged['_merge'].ne('both').any():
        raise ValueError('변화 자료와 측정 자료가 일치하지 않습니다. 분석을 다시 실행하세요.')
    merged=merged.drop(columns='_merge')
    merged['IMPROVED_EVENTS']=merged.IMPROVED_EVENTS.fillna('')
    return merged,injuries,metadata,present
