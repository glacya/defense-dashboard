"""프로젝트 전역 경로 상수입니다. dashboard와 data 양쪽에서 경로가 필요하면 여기 값을 import해서 씁니다.

모든 경로는 이 파일 위치(프로젝트 루트)를 기준으로 계산하므로 `pip install -e .`(editable)로 설치해야 합니다.
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

# ============================================================================
# data 영역
# ============================================================================
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"  # 원본 KS_NFA_FTNESS_MESURE_*.csv
DEFINITION_DIR = DATA_DIR / "definitions"  # 원본·통합 컬럼 정의서
INTERMEDIATE_DIR = DATA_DIR / "intermediate"  # 전처리 중간 결과물
PROCESSED_DIR = DATA_DIR / "processed" # 최종 정제 데이터
SAMPLE_DIR = DATA_DIR / "samples"  # 가상·샘플 데이터
SYNTHETIC_DIR = DATA_DIR / "synthetic"  # 합성 단계가 만드는 가상 장병 명단·부상 기록
DATA_SCRIPTS_DIR = DATA_DIR / "scripts"
DATA_LOG_DIR = DATA_SCRIPTS_DIR / "logs"
# 대시보드에서 직접 입력하는 기록. 분석 재실행으로 갱신하지 않습니다.
MANAGEMENT_DIR = PROCESSED_DIR / "analysis2" / "management"

# ============================================================================
# dashboard 영역
# ============================================================================
DASHBOARD_DIR = ROOT_DIR / "dashboard"
DB_DIR = DATA_DIR / "database"
DB_FINAL_DIR = DB_DIR / "db_final"
BASE64_DIR = ROOT_DIR / "dashboard" / "img" / "base64.json"
CSS_PATH = ROOT_DIR / "dashboard" / "style.css"
JS_PATH = ROOT_DIR / "dashboard" / "scripts.js"
DIR_DICT = {
    "ROOT_DIR": ROOT_DIR,
    "DB_DIR": DB_DIR,
    "CSV_FINAL_DIR": DB_FINAL_DIR,
    "BASE64_DIR": BASE64_DIR,
    "CSS_PATH": CSS_PATH,
    "JS_PATH": JS_PATH,
}
