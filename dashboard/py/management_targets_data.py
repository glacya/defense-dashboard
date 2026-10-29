"""집중관리 판정과 원본 측정·가상 장병 명단을 연결합니다."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from data.scripts.paths import PROCESSED_MANAGEMENT_TARGETS_DIR, PROCESSED_FITNESS_PATH, SYNTHETIC_PERSONNEL_PATH
from data.scripts.utils import require_columns


@st.cache_data(show_spinner=False)
def _read(paths: tuple[str,...], versions: tuple[int,...]) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    targets=pd.read_csv(paths[0],dtype={'SOLDIER_ID':'string','MESURE_ID':'string','FIRST_MESURE_ID':'string'})
    source=pd.read_csv(paths[1],dtype={'SOLDIER_ID':'string','MESURE_ID':'string'})
    people=pd.read_csv(paths[2],dtype='string')
    require_columns(targets,['MESURE_ID','SOLDIER_ID','ROUND','MANAGED','HIGH_BMI_FAIL','MULTIPLE_FAIL','WORSENED','PERSISTENT_FAIL','BMI_GROUP','FAIL_COUNT','EVALUATED_COUNT','SELECTION_REASONS','FAILED_EVENTS','NEW_FAILED_EVENTS','PERSISTENT_EVENTS'])
    require_columns(people,['SOLDIER_ID','SOLDIER_NAME','REGION_NAME','RANK_NAME','UNIT_NAME'])
    for column in ['MANAGED','HIGH_BMI_FAIL','MULTIPLE_FAIL','WORSENED','PERSISTENT_FAIL']:
        mapped=targets[column].astype('string').str.lower().map({'true':True,'false':False})
        if mapped.isna().any():
            raise ValueError(f'{column}: 잘못된 관리 판정값')
        targets[column]=mapped.astype(bool)
    if targets.duplicated(['SOLDIER_ID','ROUND']).any():
        raise ValueError('장병·회차가 중복되었습니다.')
    # 판정은 MESURE_ID와 SOLDIER_ID를 함께 확인해 다른 장병의 기록 연결을 방지합니다.
    linked=targets.merge(source,on=['MESURE_ID','SOLDIER_ID'],how='left',validate='one_to_one',indicator=True)
    if linked['_merge'].ne('both').any():
        raise ValueError('판정과 원본 측정이 맞지 않습니다. 분석 CSV를 다시 생성하세요.')
    linked=linked.drop(columns='_merge').merge(
        people[['SOLDIER_ID','SOLDIER_NAME','REGION_NAME','RANK_NAME','UNIT_NAME']],
        on='SOLDIER_ID',how='left',validate='many_to_one'
    )
    if linked.SOLDIER_NAME.isna().any():
        raise ValueError('장병 명단과 연결되지 않는 기록이 있습니다.')
    for column in ['SELECTION_REASONS','FAILED_EVENTS','NEW_FAILED_EVENTS','PERSISTENT_EVENTS']:
        linked[column]=linked[column].fillna('')
    metadata=json.loads(Path(paths[3]).read_text(encoding='utf-8'))
    return linked,source,metadata


def load_targets() -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    """자료 갱신을 감지해 읽고 캐시합니다."""
    files=[PROCESSED_MANAGEMENT_TARGETS_DIR/'management_targets.csv',PROCESSED_FITNESS_PATH,
           SYNTHETIC_PERSONNEL_PATH,PROCESSED_MANAGEMENT_TARGETS_DIR/'metadata.json']
    return _read(tuple(str(p) for p in files),tuple(p.stat().st_mtime_ns for p in files))
