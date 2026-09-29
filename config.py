# config.py
import os
from pathlib import Path

# 민감 정보는 저장소에 기록하지 않고 실행 환경에서 주입합니다.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 코드에서 직접 사용하는 경로만 공개합니다.
_ROOT_DIR = Path(__file__).resolve().parent
DB_DIR = _ROOT_DIR / "data" / "database"
CSV_DATA_DIR = _ROOT_DIR / "data" / "csv_file" / "csv_data"
CSV_DEFINE_DIR = _ROOT_DIR / "data" / "csv_file" / "csv_define"
CSV_FINAL_DIR = DB_DIR / "db_final"
SPECS_JSON_PATH = _ROOT_DIR / "data" / "csv_file" / "standard_specs.json"

# 대시보드 리소스
BASE64_DIR = _ROOT_DIR / "dashboard" / "img" / "base64.json"
CSS_PATH = _ROOT_DIR / "dashboard" / "style.css"

DIR_DICT = {
    "_ROOT_DIR": _ROOT_DIR,
    "DB_DIR": DB_DIR,
    "CSV_DATA_DIR": CSV_DATA_DIR,
    "CSV_DEFINE_DIR": CSV_DEFINE_DIR,
    "CSV_FINAL_DIR": CSV_FINAL_DIR,
    "SPECS_JSON_PATH": SPECS_JSON_PATH,
    "BASE64_DIR": BASE64_DIR,
    "CSS_PATH": CSS_PATH,
}

