"""회차별 집중관리 판정(측정값·신상 포함)과 기준 설명을 읽습니다.

DB 모드는 캐시된 판정표(fitness_judgment.load_judged_measurements)에 표시용 컬럼을 붙이고,
CSV 모드는 analysis2가 만든 CSV를 원본 측정·명단과 연결합니다.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL
from dashboard.py.fitness_judgment import EVENTS, REASONS, event_labels, join_labels, load_judged_measurements
from data.scripts.utils import require_columns

FLAG_COLUMNS = [*REASONS, 'MANAGED']
TEXT_COLUMNS = ['SELECTION_REASONS', 'FAILED_EVENTS', 'NEW_FAILED_EVENTS', 'PERSISTENT_EVENTS']
PEOPLE_COLUMNS = ['SOLDIER_ID', 'SOLDIER_NAME', 'REGION_NAME', 'RANK_NAME', 'UNIT_NAME']
# 측정 원본(fitness_measurements)의 컬럼. p02가 1차 측정값을 찾을 때 쓴다.
MEASUREMENT_COLUMNS = ['MESURE_ID', 'SOLDIER_ID', 'AGE', *EVENTS, 'HEIGHT', 'WEIGHT', 'BMI',
                       'BODY_FAT_PERCENTAGE', 'MESURE_DE', 'EXPECTED_INJURY_COUNT_PER_YEAR']
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


def _link(targets: pd.DataFrame, source: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    """판정에 원본 측정값과 신상을 붙이고 판정값을 검사합니다(CSV 모드)."""
    require_columns(targets,['MESURE_ID','SOLDIER_ID','ROUND','MANAGED','HIGH_BMI_FAIL','MULTIPLE_FAIL','WORSENED','PERSISTENT_FAIL','BMI_GROUP','FAIL_COUNT','SELECTION_REASONS','FAILED_EVENTS','NEW_FAILED_EVENTS','PERSISTENT_EVENTS'])
    require_columns(people,PEOPLE_COLUMNS)
    for column in FLAG_COLUMNS:
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
    linked=linked.drop(columns='_merge').merge(people[PEOPLE_COLUMNS],on='SOLDIER_ID',how='left',validate='many_to_one')
    if linked.SOLDIER_NAME.isna().any():
        raise ValueError('장병 명단과 연결되지 않는 기록이 있습니다.')
    for column in TEXT_COLUMNS:
        linked[column]=linked[column].fillna('')
    return linked


@st.cache_data(show_spinner=False)
def _read(paths: tuple[str,...], versions: tuple[int,...]) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    targets=pd.read_csv(paths[0],dtype={'SOLDIER_ID':'string','MESURE_ID':'string','FIRST_MESURE_ID':'string'})
    source=pd.read_csv(paths[1],dtype={'SOLDIER_ID':'string','MESURE_ID':'string'})
    people=pd.read_csv(paths[2],dtype='string')
    metadata=json.loads(Path(paths[3]).read_text(encoding='utf-8'))
    return _link(targets,source,people),source,metadata


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_targets_db() -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    judged=load_judged_measurements()
    source=judged[MEASUREMENT_COLUMNS].sort_values('MESURE_ID',key=lambda ids: ids.astype('int64')).reset_index(drop=True)
    metadata={'생성일시':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),**METADATA_TEXT}
    return build_targets(judged),source,metadata


def load_targets(source: str | None = None) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    """회차별 집중관리 판정(측정값·신상 포함), 원본 측정, 기준 설명을 돌려줍니다."""
    if resolve_source(source) != CSV:
        return _load_targets_db()
    from data.scripts.paths import PROCESSED_MANAGEMENT_TARGETS_DIR, PROCESSED_FITNESS_PATH, SYNTHETIC_PERSONNEL_PATH
    files=[PROCESSED_MANAGEMENT_TARGETS_DIR/'management_targets.csv',PROCESSED_FITNESS_PATH,
           SYNTHETIC_PERSONNEL_PATH,PROCESSED_MANAGEMENT_TARGETS_DIR/'metadata.json']
    return _read(tuple(str(p) for p in files),tuple(p.stat().st_mtime_ns for p in files))
