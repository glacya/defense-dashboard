import logging
from pathlib import Path
import sys
import pandas as pd
import streamlit as st
logger = logging.getLogger(__name__)
import re
_missing_files: list[str] = []

"""  ==========================================
위 코드는 아래와 같습니다.
1. app에서 사용할 Loader의 기능을 하는 함수들을 모아두었습니다.

_load_csv: csv파일(추후 DB)를 불러옵니다.
load_css: CSS 파일을 로드하고 Streamlit에 적용합니다.
load_css_colors: CSS파일의 색상을 로드하여 딕셔너리 형태로 제출합니다.
load_js: js함수 및 파일을 관리하고 불러옵니다.
위 코드는 다음을 위해 작성되었습니다.  
1. 필요한
================== """

# ============================================================================
# PATH 로드 함수
# ============================================================================

from dashboard.py.error_handlers import safe_execution
# ============================================================================
# CSS 로드 함수
# ============================================================================
@safe_execution(error_message="CSS 로드 실패", error_type="error")
def load_css(css_path: str | Path) -> str:
    """CSS 파일을 로드하고 내용을 반환합니다."""
    css_path = Path(css_path)
    if not css_path.exists():
        raise FileNotFoundError(f"CSS 파일을 찾을 수 없습니다: {css_path}")

    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
        return css_content  # ✅ CSS 내용 반환

def load_js(js_path: str | Path) -> str:
    """js코드를 로드하고 반환합니다."""
    js_path = Path(js_path)
    if not js_path.exists():
        raise FileNotFoundError(f"JS 파일을 찾을 수 없습니다.: {js_path}")
    with open(js_path, "r", encoding="utf-8") as f:
        three_js_content = f.read()
        return three_js_content

# ============================================================================
# CSV 로드  함수
# ============================================================================
def _load_csv(
    filename: str, columns: list[str], sample: pd.DataFrame, data_dir: Path
) -> tuple[pd.DataFrame, bool]:
    """CSV 파일을 로드하되, 파일이 없거나 오류 발생 시 sample 데이터를 반환합니다."""
    path = data_dir / filename

    try:
        if not path.exists():
            raise FileNotFoundError(f"파일 없음: {path}")

        df = pd.read_csv(path, encoding="utf-8-sig")
        
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols:
            raise ValueError(f"누락된 컬럼: {', '.join(missing_cols)}")

        return df, True  # 성공 시: (실제 데이터, True)

    except Exception as e:
        _missing_files.append(filename)
        return sample, False  # 실패 시: (샘플 데이터, False)

#색깔 로드 함수
def load_css_colors(css_path: Path) -> dict[str, str]:
    """style.css의 :root에 정의된 --color-* 변수들을 읽어옵니다."""
    colors = {}
    if not css_path.exists():
        return colors

    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()

    # '--color-soft' 전체를 키로 가져옴
    pattern = r"(--color-[\w-]+):\s*([^;]+);"
    matches = re.findall(pattern, content)

    for key, val in matches:
        colors[key.removeprefix("--color-")] = val.strip()

    return colors
  
def get_missing_files() -> list[str]:
  """누락된 파일 목록을 반환합니다."""
  return _missing_files