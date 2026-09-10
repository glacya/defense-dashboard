# config.py
import os
from pathlib import Path

# 절대 경로 없이 순수 상대 경로 사용 (프로젝트 루트에서 실행 기준)
DB_DIR = Path("data/database")
DB_DATA_DIR = DB_DIR / "db_data"
DB_FINAL_DIR = DB_DIR / "db_final"

CSV_DIR = Path("csv_file")
CSV_DATA_DIR = CSV_DIR / "csv_data"
CSV_DEFINE_DIR = CSV_DIR / "csv_define"
CSV_FINAL_DIR = CSV_DIR / "csv_final"
COMPLETE_DIR = CSV_FINAL_DIR  # pipeline.py 호환용

TEST_DIR = Path("test_py_folder")

ORACLE_DIR = Path("C:/Users/user/AI/instantclient_23_26")
GEMINI_API_KEY = "실제_본인_API_키_입력"
SPECS_JSON_PATH = CSV_DIR / "standard_specs.json"

# DB 및 환경 변수 설정
DB_LOCAL = "scott/tiger@localhost:1521/orcl"
os.environ["PATH"] = str(ORACLE_DIR) + ";" + os.environ.get("PATH", "")

DIR_LIST = [
    DB_DIR, DB_DATA_DIR, DB_FINAL_DIR,
    CSV_DIR, CSV_DATA_DIR, CSV_DEFINE_DIR, CSV_FINAL_DIR,
    TEST_DIR
]

# 디렉토리 자동 생성
for dir_path in DIR_LIST:
    dir_path.mkdir(parents=True, exist_ok=True)