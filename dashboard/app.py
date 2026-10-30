import streamlit as st

from common.assets import inject_assets
from dashboard.common.brand import brand_html
from dashboard.common.formatting import NAV_STATE_KEY
from dashboard.router import build_navigation, build_pages

st.set_page_config(
    page_title="장병 체력·부상관리 대시보드",
    page_icon="🪖",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_assets()

pages = build_pages()
nav = build_navigation(pages)

with st.sidebar:
    # 1) 맨 위: 로고
    with st.container(key="sidebar-brand"):
        st.markdown(brand_html("sidebar"), unsafe_allow_html=True)

    # 2) 그 아래: 메뉴 (st.page_link)
    with st.container(key="sidebar-menu"):
        for title, icon, page in st.session_state[NAV_STATE_KEY]:
            st.page_link(page, label=title, icon=icon)

nav.run()