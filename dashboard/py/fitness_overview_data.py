"""전체 체력 현황용 회차·종목 집계와 기준 설명을 읽습니다.

DB 모드는 회차별·회차×종목별 집계를 SQL(dashboard.py.queries)에서 끝내고 결과 행(수~수백 행)만 받습니다.
CSV 모드는 analysis2가 만든 CSV를 읽습니다(전환 기간용).
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL
from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS, grade_standards
from data.scripts.utils import require_columns

GROUP_COLUMNS = {"REGION_NAME", "UNIT_NAME"}
GROUP_LABEL = "그룹"
METADATA_TEXT = {
    '기준': '측정 당시 남성 19~24세 기준 적용; 연령 범위 밖·누락은 판정 불가',
    '표본': '원본 측정 전체 보존; 첫 측정 19~24세로 제한하는 실험 보고서와 구분',
    '관리대상': 'BMI≥25이면서 근력 또는 심폐 미달 OR 선택 회차 2개 이상 미달 OR 1차 대비 미달 수 증가 OR 동일 종목 최근 3회 지속 미달; 중복 제거',
    '집계범위': '전체 장병 기준; 소속·비교집단 구분 없음. 각 회차 측정 인원을 함께 표시',
}
# 예전 CSV의 유효측정인원(값이 있는 인원)은 빈 값이 없어 측정인원과 같다.
CSV_EVENT_RENAMES = {'유효측정인원': '측정인원'}


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


@st.cache_data(show_spinner=False)
def _read_tables(directory: str, versions: tuple[int, ...]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    folder = Path(directory)
    rounds = pd.read_csv(folder / 'round_summary.csv')
    events = pd.read_csv(folder / 'event_summary.csv').rename(columns=CSV_EVENT_RENAMES)
    require_columns(rounds, ['회차','전체장병수','측정인원','미달인원','미달률','관리대상인원'])
    require_columns(events, ['회차','종목','단위','측정인원','평균','표준편차','미달인원','미달률','1등급인원','2등급인원','3등급인원'])
    if rounds.duplicated(['회차']).any() or events.duplicated(['회차','종목']).any():
        raise ValueError('분석 집계 키가 중복되었습니다.')
    metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    return rounds, events, metadata


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_overview_db() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rounds, events = summary_tables(queries.load_overview_rounds(), queries.load_overview_events())
    period = queries.load_measure_period()
    metadata = {
        '생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),  # DB 모드에서는 조회 시각
        '측정시작': pd.to_datetime(period.FIRST_DATE, format='%Y%m%d').strftime('%Y-%m-%d'),
        '측정종료': pd.to_datetime(period.LAST_DATE, format='%Y%m%d').strftime('%Y-%m-%d'),
        **METADATA_TEXT,
        '등급기준': grade_standards(),
    }
    return rounds, events, metadata


def load_overview(source: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """전체 장병의 회차별·종목별 집계와 기준 설명을 돌려줍니다."""
    if resolve_source(source) != CSV:
        return _load_overview_db()
    from data.scripts.paths import PROCESSED_FITNESS_OVERVIEW_DIR
    files = ['round_summary.csv','event_summary.csv','metadata.json']
    versions = tuple((PROCESSED_FITNESS_OVERVIEW_DIR / name).stat().st_mtime_ns for name in files)
    return _read_tables(str(PROCESSED_FITNESS_OVERVIEW_DIR), versions)


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _load_group_summary_db(group_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return summary_tables(queries.load_overview_rounds(group_column), queries.load_overview_events(group_column),
                          grouped=True)


def load_group_summary(group_column: str, source: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """지역 또는 부대별·회차별 집계를 돌려줍니다(장병의 현재 소속 기준)."""
    if group_column not in GROUP_COLUMNS:
        raise ValueError(f"지원하지 않는 조직 구분입니다: {group_column}")
    if resolve_source(source) != CSV:
        return _load_group_summary_db(group_column)
    from dashboard.main_data import load_main_data
    measurements, _ = load_main_data(CSV)
    rounds, events = summarize_by_group(measurements, group_column)
    return rounds, events.rename(columns=CSV_EVENT_RENAMES)


def summarize_by_group(
    measurements: pd.DataFrame,
    group_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전체 체력 측정치를 지역 또는 부대별·회차별로 집계합니다(CSV 모드, analysis2 판정 사용)."""
    from data.scripts.analysis.analysis2.fitness_overview import judge_measurements, summarize

    if group_column not in GROUP_COLUMNS:
        raise ValueError(f"지원하지 않는 조직 구분입니다: {group_column}")
    required = {"SOLDIER_ID", "MESURE_ID", "MESURE_DE", "AGE", group_column}
    missing = sorted(required - set(measurements.columns))
    if missing:
        raise ValueError(f"조직별 체력 집계에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    if measurements.empty:
        raise ValueError("조직별 체력 집계에 사용할 측정 자료가 없습니다.")

    source = measurements.copy()
    source["MESURE_DE"] = pd.to_datetime(source["MESURE_DE"]).dt.strftime("%Y%m%d")
    judged = judge_measurements(source)
    personnel = measurements[["SOLDIER_ID", group_column]].drop_duplicates("SOLDIER_ID")
    round_tables = []
    event_tables = []

    for group_name, group_people in personnel.groupby(group_column, dropna=False, sort=True):
        soldier_ids = set(group_people["SOLDIER_ID"])
        group_measurements = judged.loc[judged["SOLDIER_ID"].isin(soldier_ids)]
        group_rounds, group_events = summarize(
            group_measurements,
            group_people[["SOLDIER_ID"]],
        )
        label = "미지정" if pd.isna(group_name) else str(group_name)
        group_rounds.insert(0, GROUP_LABEL, label)
        group_events.insert(0, GROUP_LABEL, label)
        round_tables.append(group_rounds)
        event_tables.append(group_events)

    return pd.concat(round_tables, ignore_index=True), pd.concat(event_tables, ignore_index=True)
