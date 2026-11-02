"""전체 체력 현황용 회차·종목 집계와 기준 설명을 읽습니다.

회차별·회차×종목별 집계는 SQL(dashboard.py.queries)에서 끝내고 결과 행(수~수백 행)만 받습니다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.db import DEFAULT_TTL
from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS, grade_standards

GROUP_COLUMNS = {"REGION_NAME", "UNIT_NAME"}
GROUP_LABEL = "그룹"
METADATA_TEXT = {
    '기준': '측정 당시 남성 19~24세 기준 적용; 연령 범위 밖·누락은 판정 불가',
    '표본': '원본 측정 전체 보존; 첫 측정 19~24세로 제한하는 실험 보고서와 구분',
    '관리대상': 'BMI≥25이면서 근력 또는 심폐 미달 OR 선택 회차 2개 이상 미달 OR 1차 대비 미달 수 증가 OR 동일 종목 최근 3회 지속 미달; 중복 제거',
    '집계범위': '전체 장병 기준; 소속·비교집단 구분 없음. 각 회차 측정 인원을 함께 표시',
}


def summary_tables(rounds: pd.DataFrame, events: pd.DataFrame,
                   grouped: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SQL 집계 결과(queries.load_overview_rounds/events)를 화면 표 모양(한글 컬럼, 종목 이름·단위, 미달률)으로 바꿉니다."""
    keys = [GROUP_LABEL] if grouped else []
    renames = {'GRP': GROUP_LABEL, 'ROUND': '회차', 'TOTAL_SOLDIERS': '전체장병수', 'MEASURED': '측정인원',
               'FAILED': '미달인원', 'MANAGED': '관리대상인원', 'MEAN': '평균', 'STD': '표준편차',
               'GRADE_1': '1등급인원', 'GRADE_2': '2등급인원', 'GRADE_3': '3등급인원'}
    rounds = rounds.rename(columns=renames)
    rounds['미달률'] = rounds.미달인원 / rounds.측정인원 * 100
    rounds = rounds[keys + ['회차', '전체장병수', '측정인원', '미달인원', '미달률', '관리대상인원']]

    order = {event: index for index, event in enumerate(EVENTS)}
    events = events.rename(columns=renames)
    events = events.assign(
        종목=events.EVENT.map(lambda event: EVENTS[event][0]),
        단위=events.EVENT.map(lambda event: EVENTS[event][1]),
        미달률=events.미달인원 / events.측정인원 * 100,
        _ORDER=events.EVENT.map(order),
    ).sort_values([*keys, '회차', '_ORDER'], kind='stable')
    columns = ['회차', '종목', '단위', '측정인원', '평균', '표준편차', '미달인원', '미달률', '1등급인원', '2등급인원', '3등급인원']
    return rounds.reset_index(drop=True), events[keys + columns].reset_index(drop=True)


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def load_overview() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """전체 장병의 회차별·종목별 집계와 기준 설명을 돌려줍니다."""
    rounds, events = summary_tables(queries.load_overview_rounds(), queries.load_overview_events())
    period = queries.load_measure_period()
    metadata = {
        '생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),  # 조회 시각
        '측정시작': pd.to_datetime(period.FIRST_DATE, format='%Y%m%d').strftime('%Y-%m-%d'),
        '측정종료': pd.to_datetime(period.LAST_DATE, format='%Y%m%d').strftime('%Y-%m-%d'),
        **METADATA_TEXT,
        '등급기준': grade_standards(),
    }
    return rounds, events, metadata


def load_group_summary(group_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """지역 또는 부대별·회차별 집계를 돌려줍니다(장병의 현재 소속 기준)."""
    if group_column not in GROUP_COLUMNS:
        raise ValueError(f"지원하지 않는 조직 구분입니다: {group_column}")
    return _load_group_summary(group_column)


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_group_summary(group_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return summary_tables(queries.load_overview_rounds(group_column), queries.load_overview_events(group_column),
                          grouped=True)
