"""style1.css와 test1.js를 페이지에 한 번 주입합니다. 엔트리(app.py)에서만 호출합니다."""

from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html as components_html

from config import CSS_PATH, JS_PATH


@st.cache_data(show_spinner=False)
def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def inject_assets() -> None:
    """CSS는 markdown으로, JS는 숨김 컴포넌트로 적용합니다."""
    # st.markdown은 빈 줄에서 HTML 블록이 끊기므로 빈 줄을 제거합니다.
    css = "\n".join(line for line in load_text(CSS_PATH).splitlines() if line.strip())
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    js = load_text(JS_PATH)
    has_code = any(line.strip() and not line.strip().startswith("//") for line in js.splitlines())
    if has_code:
        components_html(f"<script>{js}</script>", height=0)