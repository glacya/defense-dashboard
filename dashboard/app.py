"""대시보드 엔트리: 페이지 설정, CSS/JS 주입, 사이드바 로고, 라우팅 실행."""

import streamlit as st

from common.assets import inject_assets
from config import DASHBOARD_DIR
from dashboard.router import build_navigation

st.set_page_config(
    page_title="장병 체력·부상관리 대시보드",
    page_icon="🪖",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_assets()
st.logo(str(DASHBOARD_DIR / "img" / "personnel_health.svg"))
build_navigation().run()