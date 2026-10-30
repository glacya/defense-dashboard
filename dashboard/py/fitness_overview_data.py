"""전체 체력 현황용 회차·종목 집계와 기준 설명을 읽습니다.

DB 모드는 캐시된 판정표(fitness_judgment.load_judged_measurements)를 pandas로 집계하고,
CSV 모드는 analysis2가 만든 CSV를 읽습니다.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL
from dashboard.py.fitness_judgment import EVENTS, grade_standards, load_judged_measurements
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


def summarize_judged(judged: pd.DataFrame, group_column: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """판정표를 회차별(group_column이 있으면 그룹·회차별)로 집계합니다."""
    keys = ['ROUND'] if group_column is None else [group_column, 'ROUND']
    data = judged.assign(FAILED=judged.FAIL_COUNT.ge(1))
    rounds = data.groupby(keys, sort=True).agg(
        측정인원=('MESURE_ID', 'size'), 미달인원=('FAILED', 'sum'), 관리대상인원=('MANAGED', 'sum'),
    ).reset_index()
    if group_column is None:
        rounds.insert(1, '전체장병수', judged.SOLDIER_ID.nunique())
    else:
        population = judged.groupby(group_column).SOLDIER_ID.nunique().rename('전체장병수')
        rounds = rounds.merge(population, on=group_column)
    rounds['미달률'] = rounds.미달인원 / rounds.측정인원 * 100

    tables = []
    for order, (event, (label, unit)) in enumerate(EVENTS.items()):
        grade = data[f'{event}_GRADE']
        table = data.assign(**{f'_{level}': grade.eq(level) for level in (0, 1, 2, 3)}).groupby(keys, sort=True).agg(
            측정인원=('MESURE_ID', 'size'), 평균=(event, 'mean'), 표준편차=(event, 'std'),
            미달인원=('_0', 'sum'), **{f'{level}등급인원': (f'_{level}', 'sum') for level in (1, 2, 3)},
        ).reset_index()
        table.insert(len(keys), '종목', label)
        table.insert(len(keys) + 1, '단위', unit)
        table.insert(len(keys) + 6, '미달률', table.미달인원 / table.측정인원 * 100)
        table['_ORDER'] = order
        tables.append(table)
    events = pd.concat(tables, ignore_index=True).sort_values([*keys, '_ORDER'], kind='stable').drop(columns='_ORDER')

    round_columns = ['ROUND', '전체장병수', '측정인원', '미달인원', '미달률', '관리대상인원']
    rounds = rounds[keys[:-1] + round_columns]
    renames = {'ROUND': '회차'} if group_column is None else {'ROUND': '회차', group_column: GROUP_LABEL}
    return rounds.rename(columns=renames), events.reset_index(drop=True).rename(columns=renames)


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
    judged = load_judged_measurements()
    rounds, events = summarize_judged(judged)
    dates = pd.to_datetime(judged.MESURE_DE.astype(str), format='%Y%m%d')
    metadata = {
        '생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),  # DB 모드에서는 조회 시각
        '측정시작': dates.min().strftime('%Y-%m-%d'),
        '측정종료': dates.max().strftime('%Y-%m-%d'),
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
    return summarize_judged(load_judged_measurements(), group_column)


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
