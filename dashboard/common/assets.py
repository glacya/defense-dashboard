"""style.css와 JS를 페이지에 주입합니다. 엔트리(app.py)에서만 호출합니다."""

from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html as components_html

from config import CSS_PATH, JS_PATH

# True면 파일 수정 시각을 캐시 키로 써서 저장 즉시 반영합니다.
# 배포 환경에서는 False로 두면 매 rerun마다 파일을 읽지 않습니다.
LIVE_RELOAD = True


def _file_version(path: Path) -> tuple[int, int]:
    """파일의 수정 시각과 크기입니다. 파일이 없으면 (0, 0)을 돌려줍니다."""
    if not path.is_file():
        return (0, 0)
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


@st.cache_data(show_spinner=False)
def _read_cached(path: str, version: tuple[int, int]) -> str:
    """version이 바뀌면 키가 달라져 파일을 새로 읽습니다."""
    file = Path(path)
    return file.read_text(encoding="utf-8") if file.is_file() else ""


def load_text(path: Path) -> str:
    """LIVE_RELOAD가 켜져 있으면 수정 시각 기준으로, 꺼져 있으면 캐시를 써서 읽습니다."""
    if LIVE_RELOAD:
        return _read_cached(str(path), _file_version(path))
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def inject_assets() -> None:
    """CSS는 <style>로, JS는 숨김 iframe으로 주입합니다."""
    # st.markdown은 빈 줄에서 HTML 블록이 끊기므로 빈 줄을 제거합니다.
    css = "\n".join(line for line in load_text(CSS_PATH).splitlines() if line.strip())
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    js = load_text(JS_PATH)
    has_code = any(line.strip() and not line.strip().startswith("//") for line in js.splitlines())
    if has_code:
        components_html(f"<script>{js}</script>", height=0)