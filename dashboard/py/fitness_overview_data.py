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
