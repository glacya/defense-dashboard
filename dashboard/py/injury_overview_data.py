"""부상 현황 집계(장병별 최신 종목 등급 × 부상)와 가상 장병·부상 원본을 읽습니다.

DB 모드는 캐시된 판정표(fitness_judgment.load_judged_measurements)와 부상 기록을 pandas로 집계하고,
CSV 모드는 analysis2가 만든 CSV를 읽습니다.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL, run_query
from dashboard.py import queries
from dashboard.py.fitness_judgment import EVENTS, GRADE_LABELS, load_judged_measurements
from dashboard.py.roster_data import INJURIES_SQL
from data.scripts.utils import require_columns

PEOPLE_COLUMNS = ['SOLDIER_ID', 'SOLDIER_NAME', 'REGION_NAME', 'UNIT_NAME', 'RANK_NAME']
METADATA_TEXT = {
    '집계범위': '장병 명단 전체와 보유 부상 기록 전체. 부상자 비율은 부상 기록 1건 이상 장병 수 / 집단 전체 인원 ×100.',
    '등급': '장병별 최신 측정의 종목별 등급. 종합 인증등급이 아님. 남성 19~24세 범위 밖·누락·미측정은 판정 불가.',
    '기간': '부상 발생일이 없어 기간별 집계·발생률·측정 당시 부상 판정은 하지 않음.',
    '합성': '부상 기록은 BMI·심폐 수준을 기반으로 합성됨. 등급별 차이를 실제 부상 위험이나 인과관계로 해석하지 않음.',
    '중복': '같은 장병의 반복 부상은 부상인원 1명, 부상건수 여러 건으로 집계. 서로 다른 종목의 인원을 합산하지 않음.',
}


def build_injury_tables(judged: pd.DataFrame, injuries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """장병별 부상 건수, 최신 측정 종목 등급별 부상 집계, 전체 요약을 만듭니다."""
    latest = judged.loc[judged.ROUND.eq(judged.groupby('SOLDIER_ID').ROUND.transform('max'))]
    counts = latest.SOLDIER_ID.map(injuries.SOLDIER_ID.value_counts()).fillna(0).astype('int64')
    latest = latest.assign(INJURY_COUNT=counts, HAS_INJURY=counts.gt(0))
    rows = []
    for event, (label, _) in EVENTS.items():
        for grade, text in GRADE_LABELS.items():
            group = latest.loc[latest[f'{event}_GRADE'].eq(grade)]
            affected = int(group.HAS_INJURY.sum())
            rows.append({'종목': label, '등급': text, '전체인원': len(group), '부상인원': affected,
                         '부상건수': int(group.INJURY_COUNT.sum()),
                         '부상자비율': affected / len(group) * 100 if len(group) else float('nan')})
    affected = int(latest.HAS_INJURY.sum())
    summary = pd.DataFrame([{'전체장병수': len(latest), '부상인원': affected, '부상건수': len(injuries),
                             '부상자비율': affected / len(latest) * 100 if len(latest) else float('nan'),
                             '반복부상인원': int(latest.INJURY_COUNT.ge(2).sum())}])
    personal = latest[[*PEOPLE_COLUMNS, 'INJURY_COUNT']].reset_index(drop=True)
    return personal, pd.DataFrame(rows), summary


def injury_grade_table() -> pd.DataFrame:
    """종목×등급별 부상 집계(queries.load_injury_by_grade)를 화면 표로: 모든 조합(인원 0 포함), 종목·등급 순서, 부상자 비율."""
    counts = queries.load_injury_by_grade().set_index(['EVENT', 'GRADE'])
    rows = []
    for event, (label, _) in EVENTS.items():
        for grade, text in GRADE_LABELS.items():
            total, injured, injuries = (int(counts.loc[(event, grade), column]) if (event, grade) in counts.index else 0
                                        for column in ['TOTAL', 'INJURED', 'INJURIES'])
            rows.append({'종목': label, '등급': text, '전체인원': total, '부상인원': injured, '부상건수': injuries,
                         '부상자비율': injured / total * 100 if total else float('nan')})
    return pd.DataFrame(rows)


def injury_people() -> pd.DataFrame:
    """장병 명단(queries.load_roster)에 장병별 부상 건수(없으면 0)를 붙입니다."""
    counts = queries.load_soldier_injury_counts().set_index('SOLDIER_ID').INJURY_COUNT
    roster = queries.load_roster()
    return roster.assign(INJURY_COUNT=roster.SOLDIER_ID.map(counts).fillna(0).astype('int64'))


def injury_metadata() -> dict:
    """집계 기준 설명(화면 안내용)."""
    return {'생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), **METADATA_TEXT}


def _check(personal: pd.DataFrame, grades: pd.DataFrame, summary: pd.DataFrame, injuries: pd.DataFrame) -> None:
    """집계와 원본 부상 기록이 서로 맞는지 확인합니다(두 모드 공통)."""
    require_columns(personal,[*PEOPLE_COLUMNS,'INJURY_COUNT'])
    require_columns(grades,['종목','등급','전체인원','부상인원','부상건수','부상자비율'])
    require_columns(summary,['전체장병수','부상인원','부상건수','부상자비율','반복부상인원'])
    require_columns(injuries,['INJURY_ID','SOLDIER_ID','INJURY_CATEGORY','INJURY_LOCATION','SEVERITY','PREVENTABILITY'])
    if personal.SOLDIER_NAME.isna().any():
        raise ValueError('분석 장병과 명단 연결 불일치')
    if len(injuries)!=int(summary.iloc[0]['부상건수']) or injuries.SOLDIER_ID.nunique()!=int(summary.iloc[0]['부상인원']):
        raise ValueError('부상 원본이 집계와 다릅니다. 부상 분석을 다시 실행하세요.')


@st.cache_data(show_spinner=False)
def _read(paths: tuple[str,...], versions: tuple[int,...]) -> tuple:
    personal=pd.read_csv(paths[0],dtype={'SOLDIER_ID':'string','MESURE_ID':'string'})
    grades=pd.read_csv(paths[1]); summary=pd.read_csv(paths[2])
    metadata=json.loads(Path(paths[3]).read_text(encoding='utf-8'))
    people=pd.read_csv(paths[4],dtype='string')
    injuries=pd.read_csv(paths[5],dtype='string')
    require_columns(people,PEOPLE_COLUMNS)
    personal=personal.merge(people,on='SOLDIER_ID',how='left',validate='one_to_one')
    # 판정 불가 등급은 DB 모드에 없으므로(빈 값·나이 범위 밖 없음) 같은 등급만 남긴다.
    grades=grades.loc[grades['등급'].isin(GRADE_LABELS.values())].reset_index(drop=True)
    _check(personal,grades,summary,injuries)
    return personal,grades,summary,metadata,injuries


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def _read_db() -> tuple:
    injuries=run_query(INJURIES_SQL)
    personal,grades,summary=build_injury_tables(load_judged_measurements(),injuries)
    metadata={'생성일시':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),**METADATA_TEXT}
    _check(personal,grades,summary,injuries)
    return personal,grades,summary,metadata,injuries


def filter_injuries_by_personnel(
    injuries: pd.DataFrame,
    people: pd.DataFrame,
    regions: list[str] | None = None,
    units: list[str] | None = None,
    ranks: list[str] | None = None,
) -> pd.DataFrame:
    """명단의 지역·부대·계급을 부상 기록에 연결하고 선택 조건을 적용합니다."""
    columns = ['SOLDIER_ID', 'REGION_NAME', 'UNIT_NAME', 'RANK_NAME']
    require_columns(people, columns)
    profile = people[columns]
    joined = injuries.merge(profile, on='SOLDIER_ID', how='left', validate='many_to_one')
    if joined[['REGION_NAME', 'UNIT_NAME', 'RANK_NAME']].isna().any().any():
        raise ValueError('부상 기록과 장병 명단 연결 불일치')

    for column, selected in (
        ('REGION_NAME', regions),
        ('UNIT_NAME', units),
        ('RANK_NAME', ranks),
    ):
        if selected:
            joined = joined.loc[joined[column].isin(selected)]
    return joined


def load_injury_overview(source: str | None = None) -> tuple:
    """장병별 부상 건수, 종목×등급 집계, 전체 요약, 기준 설명, 부상 기록을 돌려줍니다."""
    if resolve_source(source) != CSV:
        return _read_db()
    from data.scripts.paths import PROCESSED_INJURY_OVERVIEW_DIR, SYNTHETIC_PERSONNEL_PATH, SYNTHETIC_INJURY_PATH
    files=[PROCESSED_INJURY_OVERVIEW_DIR/name for name in ['personal_injury_summary.csv','grade_injury_summary.csv','injury_summary.csv','metadata.json']]
    files += [SYNTHETIC_PERSONNEL_PATH,SYNTHETIC_INJURY_PATH]
    return _read(tuple(str(p) for p in files),tuple(p.stat().st_mtime_ns for p in files))
