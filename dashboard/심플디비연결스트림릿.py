"""공용 DB 조회 함수를 사용한 간단한 장병 정보 검색 화면."""

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.db import run_query


def main() -> None:
    """이름·장병번호로 PostgreSQL의 장병 명단을 조회합니다."""
    st.set_page_config(page_title='장병 정보 조회 · DB', page_icon='🪖', layout='wide')
    st.title('🪖 장병 정보 조회')
    st.caption('공용 run_query()를 사용해 DB의 soldiers 테이블을 조회합니다.')
    with st.form('soldier_search'):
        keyword = st.text_input('이름·장병번호 검색', placeholder='비워 두면 전체 장병을 조회합니다.').strip()
        st.form_submit_button('조회', type='primary')
    sql = '''SELECT soldier_id, soldier_name, rank_name, unit_name, region_name
             FROM soldiers'''
    params = {}
    if keyword:
        # 입력값을 SQL 문장에 직접 합치지 않고 바인딩합니다.
        sql += ' WHERE strpos(soldier_name, :keyword) > 0 OR strpos(soldier_id::text, :keyword) > 0'
        params['keyword'] = keyword
    sql += ' ORDER BY soldier_name, soldier_id'
    try:
        with st.spinner('장병 정보를 조회하고 있습니다…'):
            data = run_query(sql, params=params)
    except ModuleNotFoundError:
        st.error('DB 연결 드라이버가 설치되어 있지 않습니다. 아래 명령으로 설치한 뒤 재실행하세요.')
        st.code('python -m pip install "psycopg[binary]"', language='powershell')
        st.stop()
    except (ValueError, SQLAlchemyError, pd.errors.DatabaseError):
        # 예외 원문에 연결 문자열 등 접속 정보가 포함될 수 있어 출력하지 않습니다.
        st.error('DB 조회에 실패했습니다. dashboard/.env의 접속 설정, 네트워크와 soldiers 테이블을 확인하세요.')
        st.stop()
    st.success('DB 조회 완료')
    st.metric('조회 인원', f'{len(data):,}명')
    labels = {'SOLDIER_ID':'장병번호', 'SOLDIER_NAME':'이름', 'RANK_NAME':'계급',
              'UNIT_NAME':'부대', 'REGION_NAME':'지역'}
    st.dataframe(data.rename(columns=labels), hide_index=True, width='stretch')
    if data.empty:
        st.info('검색 조건에 해당하는 장병이 없습니다.')
    st.caption('같은 검색 결과는 공용 DB 함수의 기본 설정에 따라 10분간 캐시됩니다.')


if __name__ == '__main__':
    main()
