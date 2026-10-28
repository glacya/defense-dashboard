"""CSS·JS를 분리한 메인 샘플과 독립 샘플 페이지 4개의 진입점."""

import streamlit as st

from dashboard.py.main_sample import apply_style, render_header, render_overview


def home() -> None:
    """샘플 홈의 요약과 페이지 바로가기를 표시합니다."""
    render_header('메인대시보드', '전체 체력 현황과 관리 대상을 한눈에 확인하세요.')
    render_overview()
    st.subheader('화면 바로가기')
    for col, page in zip(st.columns(4), SAMPLE_PAGES):
        with col, st.container(border=True):
            st.page_link(page, label=page.title)
    st.caption('모든 수치·장병·예측·운동 처방은 샘플 데이터입니다. 실제 데이터 파일은 읽거나 변경하지 않습니다.')


def main() -> None:
    """공통 스타일과 그룹별 사이드바를 적용합니다."""
    st.set_page_config(page_title='장병 체력관리 · 메인샘플', page_icon='🪖', layout='wide')
    apply_style()
    st.sidebar.title('🪖 장병 체력관리')
    st.sidebar.caption('MAIN DASHBOARD · SAMPLE')
    page = st.navigation({
        '메인': [st.Page(home, title='메인샘플', default=True, icon=':material/home:')],
        '조회·분석': SAMPLE_PAGES[:3],
        '운동 지도': SAMPLE_PAGES[3:],
    })
    page.run()


if __name__ == '__main__':
    SAMPLE_PAGES = [st.Page(f'샘플페이지/page{i}.py', title=title) for i, title in enumerate([
        '페이지 1 · 전체 현황', '페이지 2 · 미달·위험 장병',
        '페이지 3 · 개인 상세', '페이지 4 · 운동 처방',
    ], 1)]
    main()
