"""페이지 등록과 라우팅을 정의합니다. 각 페이지는 URL을 가지므로 링크와 뒤로가기가 동작합니다."""

import streamlit as st

from dashboard.common.formatting import NAV_STATE_KEY
from dashboard.views import (
    mainpage,
    p01_fitness_overview,
    p02_management_targets,
    p03_personal_detail,
    p04_unit_status,
    p06_injury_overview,
    p07_guidance_followup,
    p08_injury_followup,
)

# (표시 이름, 아이콘, 페이지 함수, URL 경로)
NAV_ITEMS = (
    ("대시보드 홈", ":material/home:", mainpage.render, "home"),
    ("부대 현황", ":material/domain:", p04_unit_status.render, "units"),
    ("전체 체력 현황", ":material/monitoring:", p01_fitness_overview.render, "fitness-overview"),
    ("미달·악화 대상자", ":material/fitness_center:", p02_management_targets.render, "management-targets"),
    ("개인 장병 상세", ":material/person_search:", p03_personal_detail.render, "personal-detail"),
    ("부상 현황", ":material/healing:", p06_injury_overview.render, "injury-overview"),
    ("체력 지도·후속조치", ":material/assignment:", p07_guidance_followup.render, "guidance-followup"),
    ("부상 후속조치", ":material/medical_services:", p08_injury_followup.render, "injury-followup"),
)


def build_navigation():
    """st.Page 객체를 만들고, 메인 페이지가 바로가기 링크로 쓸 수 있도록 세션에 보관합니다."""
    pages = []
    links = []
    for index, (title, icon, func, path) in enumerate(NAV_ITEMS):
        page = st.Page(func, title=title, icon=icon, url_path=path, default=index == 0)
        pages.append(page)
        links.append((title, icon, page))
    st.session_state[NAV_STATE_KEY] = links
    return st.navigation(pages)