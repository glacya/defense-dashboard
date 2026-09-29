# config.py
import os
from pathlib import Path

# 절대 경로 없이 순수 상대 경로 사용 (프로젝트 루트에서 실행 기준)
RooT_DIR = Path(__file__).resolve().parent.parent.parent# test_py->data->dashboard
DB_DIR = RooT_DIR / "data/database"
DB_DATA_DIR = DB_DIR / "db_data"
DB_FINAL_DIR = DB_DIR / "db_final"

CSV_DIR =  RooT_DIR / "data/csv_file"
BASE64_DIR = RooT_DIR /"dashboard/img/base64.json"
CSS_PATH =  RooT_DIR /"dashboard/style.css"

# DB 및 환경 변수 설정
# DB_LOCAL = "scott/tiger@localhost:1521/orcl"
# os.environ["PATH"] = str(ORACLE_DIR) + ";" + os.environ.get("PATH", "")

DIR_DICT = {
    'DB_DIR': DB_DIR,
    'DB_DATA_DIR': DB_DATA_DIR,
    'DB_FINAL_DIR': DB_FINAL_DIR,
    'CSV_DIR': CSV_DIR,
    

    'BASE64_DIR': BASE64_DIR,
    'CSS_PATH': CSS_PATH,
}

