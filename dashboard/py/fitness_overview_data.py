"""전체 체력 현황용 분석 CSV와 생성 기준을 읽습니다."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from data.scripts.paths import PROCESSED_FITNESS_OVERVIEW_DIR
from data.scripts.utils import require_columns


@st.cache_data(show_spinner=False)
def _read_tables(directory: str, versions: tuple[int, ...]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    folder = Path(directory)
    rounds = pd.read_csv(folder / 'round_summary.csv')
    events = pd.read_csv(folder / 'event_summary.csv')
    require_columns(rounds, ['회차','전체장병수','측정인원','판정가능인원','판정불완전인원','미달인원','미달률','관리대상인원'])
    require_columns(events, ['회차','종목','단위','평균','표준편차','유효측정인원','판정가능인원','판정불가인원','미달인원','미달률','1등급인원','2등급인원','3등급인원'])
    if rounds.duplicated(['회차']).any() or events.duplicated(['회차','종목']).any():
        raise ValueError('분석 집계 키가 중복되었습니다.')
    metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    return rounds, events, metadata


def load_overview() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """파일 갱신 시 캐시를 무효화하고 필수 컬럼을 검증합니다."""
    files = ['round_summary.csv','event_summary.csv','metadata.json']
    versions = tuple((PROCESSED_FITNESS_OVERVIEW_DIR / name).stat().st_mtime_ns for name in files)
    return _read_tables(str(PROCESSED_FITNESS_OVERVIEW_DIR), versions)


@st.cache_data(show_spinner=False)
def _read_multiple_fail_counts(path: str, version: int) -> pd.Series:
    data = pd.read_csv(path, dtype={'SOLDIER_ID':'string'})
    require_columns(data, ['SOLDIER_ID','ROUND','FAIL_COUNT'])
    if data.duplicated(['SOLDIER_ID','ROUND']).any():
        raise ValueError('장병·회차 판정이 중복되었습니다.')
    return data.loc[data.FAIL_COUNT.ge(2)].groupby('ROUND').SOLDIER_ID.nunique()


def load_multiple_fail_counts() -> pd.Series:
    """분석 판정 CSV에서 회차별 2개 이상 종목 미달 인원을 읽습니다."""
    path = PROCESSED_FITNESS_OVERVIEW_DIR / 'measurement_judgments.csv'
    return _read_multiple_fail_counts(str(path), path.stat().st_mtime_ns)


@st.cache_data(show_spinner=False)
def _read_overview_target_counts(path: str, version: int) -> pd.DataFrame:
    """개인 판정에서 회차별 복수 미달·복수 관리 조건 인원을 집계합니다."""
    data = pd.read_csv(path, dtype={'SOLDIER_ID':'string'})
    flags = ['HIGH_BMI_FAIL','MULTIPLE_FAIL','WORSENED','PERSISTENT_FAIL']
    require_columns(data, ['SOLDIER_ID','ROUND','FAIL_COUNT',*flags])
    if data.duplicated(['SOLDIER_ID','ROUND']).any():
        raise ValueError('장병·회차 판정이 중복되었습니다.')
    for flag in flags:
        mapped = data[flag].astype('string').str.lower().map({'true':True,'false':False})
        if mapped.isna().any():
            raise ValueError(f'{flag}: 잘못된 관리 판정값')
        data[flag] = mapped.astype(bool)
    data['미달인원'] = data.FAIL_COUNT.ge(2)
    data['관리대상인원'] = data[flags].sum(axis=1).ge(2)
    return data.groupby('ROUND')[['미달인원','관리대상인원']].sum()


def load_overview_target_counts() -> pd.DataFrame:
    """파일 갱신을 감지해 전체현황의 새 인원 기준을 집계합니다."""
    path = PROCESSED_FITNESS_OVERVIEW_DIR / 'measurement_judgments.csv'
    return _read_overview_target_counts(str(path), path.stat().st_mtime_ns)
