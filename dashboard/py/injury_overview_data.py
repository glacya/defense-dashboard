"""부상 현황 집계와 기존 가상 장병·부상 원본을 읽습니다."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from data.scripts.paths import PROCESSED_INJURY_OVERVIEW_DIR, SYNTHETIC_PERSONNEL_PATH, SYNTHETIC_INJURY_PATH
from data.scripts.utils import require_columns


@st.cache_data(show_spinner=False)
def _read(paths: tuple[str,...], versions: tuple[int,...]) -> tuple:
    personal=pd.read_csv(paths[0],dtype={'SOLDIER_ID':'string','MESURE_ID':'string'})
    grades=pd.read_csv(paths[1]); summary=pd.read_csv(paths[2])
    metadata=json.loads(Path(paths[3]).read_text(encoding='utf-8'))
    people=pd.read_csv(paths[4],dtype='string')
    injuries=pd.read_csv(paths[5],dtype='string')
    require_columns(personal,['SOLDIER_ID','INJURY_COUNT','STRENGTH_GRADE','ENDURANCE_GRADE','CARDIO_GRADE','FLEXIBILITY_GRADE'])
    require_columns(grades,['종목','등급','전체인원','부상인원','부상건수','부상자비율'])
    require_columns(summary,['전체장병수','부상인원','부상건수','부상자비율','반복부상인원'])
    require_columns(people,['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME'])
    require_columns(injuries,['INJURY_ID','SOLDIER_ID','INJURY_CATEGORY','INJURY_LOCATION','SEVERITY','PREVENTABILITY'])
    personal=personal.merge(people,on='SOLDIER_ID',how='left',validate='one_to_one')
    if personal.SOLDIER_NAME.isna().any():
        raise ValueError('분석 장병과 명단 연결 불일치')
    if len(injuries)!=int(summary.iloc[0]['부상건수']) or injuries.SOLDIER_ID.nunique()!=int(summary.iloc[0]['부상인원']):
        raise ValueError('부상 원본이 집계와 다릅니다. 부상 분석을 다시 실행하세요.')
    return personal,grades,summary,metadata,injuries


def load_injury_overview() -> tuple:
    """파일 갱신 시 캐시를 갱신하고 부상 자료를 연결합니다."""
    files=[PROCESSED_INJURY_OVERVIEW_DIR/name for name in ['personal_injury_summary.csv','grade_injury_summary.csv','injury_summary.csv','metadata.json']]
    files += [SYNTHETIC_PERSONNEL_PATH,SYNTHETIC_INJURY_PATH]
    return _read(tuple(str(p) for p in files),tuple(p.stat().st_mtime_ns for p in files))
