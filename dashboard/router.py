"""페이지 등록과 라우팅을 정의합니다. 각 페이지는 URL을 가지므로 링크와 뒤로가기가 동작합니다."""

from importlib import import_module
from typing import Callable

import streamlit as st

from dashboard.common.formatting import NAV_STATE_KEY

# (표시 이름, 아이콘, 페이지 모듈, URL 경로)
NAV_ITEMS = (
    ("대시보드 홈", ":material/home:", "dashboard.views.mainpage", "home"),
    ("부대 현황", ":material/domain:", "dashboard.views.p04_unit_status", "units"),
    ("전체 체력 현황", ":material/monitoring:", "dashboard.views.p01_fitness_overview", "fitness-overview"),
    ("미달·악화 대상자", ":material/fitness_center:", "dashboard.views.p02_management_targets", "management-targets"),
    ("개인 장병 상세", ":material/person_search:", "dashboard.views.p03_personal_detail", "personal-detail"),
    ("부상 현황", ":material/healing:", "dashboard.views.p06_injury_overview", "injury-overview"),
    ("체력 지도·후속조치", ":material/assignment:", "dashboard.views.p07_guidance_followup", "guidance-followup"),
    ("부상 후속조치", ":material/medical_services:", "dashboard.views.p08_injury_followup", "injury-followup"),
)


def _page_renderer(module_name: str) -> Callable[[], None]:
    """선택된 페이지가 실행될 때만 그 화면 모듈을 가져옵니다."""

    def render() -> None:
        page_module = import_module(module_name)
        page_module.render()

    return render


def build_pages():
    """st.Page 객체를 만들고, 사이드바 메뉴를 직접 그릴 때 쓸 목록을 세션에 보관합니다."""
    pages = []
    links = []
    for index, (title, icon, module_name, path) in enumerate(NAV_ITEMS):
        page = st.Page(
            _page_renderer(module_name),
            title=title,
            icon=icon,
            url_path=path,
            default=index == 0,
        )
        pages.append(page)
        links.append((title, icon, page))
    st.session_state[NAV_STATE_KEY] = links
    return pages


def build_navigation(pages):
    """기본 메뉴는 숨기고 라우팅만 수행합니다. 메뉴는 app.py에서 직접 그립니다."""
    return st.navigation(pages, position="hidden")
