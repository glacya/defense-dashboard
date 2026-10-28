"""SQLite 더미 DB 초기화와 두 샘플 화면의 공통 조회 함수."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from config import ROOT_DIR

DB_PATH = ROOT_DIR / 'data' / 'samples' / 'dashboard_demo.sqlite3'
SEED_PATH = ROOT_DIR / 'dashboard' / 'assets' / 'main_sample' / 'sample_soldiers.csv'


def initialize_db(path: Path = DB_PATH) -> None:
    """첫 실행에만 샘플 CSV를 DB 테이블로 복사하며 기존 DB는 유지합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS soldiers (
            soldier_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            rank TEXT NOT NULL, unit TEXT NOT NULL,
            strength INTEGER, endurance INTEGER, cardio INTEGER, flexibility INTEGER,
            fail_count INTEGER, risk_probability INTEGER,
            fitness_type TEXT, exercise TEXT
        )''')
        if connection.execute('SELECT COUNT(*) FROM soldiers').fetchone()[0]:
            return
        data = pd.read_csv(SEED_PATH, encoding='utf-8-sig')
        columns = ['장병번호','이름','계급','부대','근력','근지구력','심폐지구력','유연성',
                   '미달 종목 수','미통과 확률(%)','체력 유형','추천 운동']
        connection.executemany(
            'INSERT INTO soldiers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            data[columns].itertuples(index=False, name=None),
        )
        connection.commit()


@st.cache_data(ttl=30, show_spinner=False)
def load_soldiers(unit: str = '전체', path: str = str(DB_PATH)) -> pd.DataFrame:
    """SQL 결과를 DataFrame으로 반환하며 조건별로 30초간 캐시합니다."""
    sql = '''SELECT soldier_id AS 장병번호, name AS 이름, rank AS 계급, unit AS 부대,
        strength AS 근력, endurance AS 근지구력, cardio AS 심폐지구력,
        flexibility AS 유연성, fail_count AS "미달 종목 수",
        risk_probability AS "미통과 확률(%)", fitness_type AS "체력 유형",
        exercise AS "추천 운동" FROM soldiers'''
    params = ()
    if unit != '전체':
        sql += ' WHERE unit = ?'
        params = (unit,)
    sql += ' ORDER BY soldier_id'
    with closing(sqlite3.connect(path)) as connection:
        return pd.read_sql_query(sql, connection, params=params)


def filtered_db_data() -> pd.DataFrame:
    """공통 부대 필터로 DB를 조회하고 오류를 화면에 표시합니다."""
    unit = st.sidebar.selectbox('조회 부대', ['전체','1중대','2중대','3중대'], key='sample_db_unit')
    if st.sidebar.button('DB 데이터 새로고침'):
        load_soldiers.clear()
    try:
        return load_soldiers(unit)
    except (sqlite3.Error, pd.errors.DatabaseError) as error:
        st.error(f'샘플 DB를 읽을 수 없습니다: {error}')
        st.stop()
