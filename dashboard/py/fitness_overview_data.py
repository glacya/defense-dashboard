"""전체 체력 현황용 분석 CSV와 생성 기준을 읽습니다."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from data.scripts.analysis.analysis2.fitness_overview import judge_measurements, summarize
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


def summarize_by_group(
    measurements: pd.DataFrame,
    group_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전체 체력 측정치를 지역 또는 부대별·회차별로 집계합니다."""
    if group_column not in {"REGION_NAME", "UNIT_NAME"}:
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
        group_rounds.insert(0, "그룹", label)
        group_events.insert(0, "그룹", label)
        round_tables.append(group_rounds)
        event_tables.append(group_events)

    return pd.concat(round_tables, ignore_index=True), pd.concat(event_tables, ignore_index=True)
