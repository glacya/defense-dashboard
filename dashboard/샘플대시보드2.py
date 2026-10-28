"""SQLite를 사용하는 샘플11·샘플22의 메인 진입 파일."""

import sqlite3

import streamlit as st

from dashboard.py.main_sample import apply_style, render_header
from dashboard.py.sample_db import initialize_db


def home() -> None:
    """DB 샘플의 역할과 화면 이동을 제공합니다."""
    render_header('샘플대시보드2', 'SQLite 기반 장병 체력관리 · 모든 데이터는 더미데이터입니다.')
    st.write('왼쪽 메뉴에서 DB로 조회하는 전체 현황과 미달·위험 장병 화면을 선택하세요.')
    for col, page in zip(st.columns(2), PAGES):
        with col, st.container(border=True):
            st.page_link(page, label=page.title)
    with st.expander('CSV 샘플과 DB 샘플의 차이'):
        st.write('최초 실행에만 더미 CSV를 SQLite에 넣습니다. 이후 페이지 조회는 SQL로 DB에서 읽습니다.')
        st.code('load_soldiers() → pd.read_sql_query() → DataFrame → 카드·그래프·표')
        st.caption('조회 결과는 30초간 캐시됩니다. 즉시 반영하려면 각 페이지에서 DB 데이터 새로고침을 누르세요.')


def main() -> None:
    """샘플 DB를 준비하고 공통 사이드바에서 페이지를 실행합니다."""
    st.set_page_config(page_title='샘플대시보드2 · SQLite', page_icon='🪖', layout='wide')
    apply_style()
    try:
        initialize_db()
    except (OSError, ValueError, sqlite3.Error) as error:
        st.error(f'샘플 DB를 준비하지 못했습니다: {error}')
        st.stop()
    st.sidebar.title('🪖 장병 체력관리')
    st.sidebar.caption('SQLITE · SAMPLE DATA')
    selected = st.navigation({
        '메인': [st.Page(home, title='샘플대시보드2', default=True)],
        'DB 조회 샘플': PAGES,
    })
    selected.run()


if __name__ == '__main__':
    PAGES = [
        st.Page('샘플페이지/샘플11.py', title='샘플11 · 전체 현황'),
        st.Page('샘플페이지/샘플22.py', title='샘플22 · 미달·위험 장병'),
    ]
    main()
