"""분석 결과 테이블 저장 모듈.

저장 방식은 STORAGE_BACKEND로 고릅니다.
- "csv": output_dir/{name}.csv 로 저장합니다. (기본)
- "db" : DB_ENGINE에 name을 테이블 이름으로 저장합니다. output_dir은 쓰지 않습니다.

분석 스크립트는 save_table()만 호출하므로, 저장 방식을 바꿔도 분석 코드는 그대로 둡니다.
"""

from pathlib import Path

import pandas as pd

from data.scripts.utils import write_csv

# ---------------------------------------------------------------------------
# 저장 설정
# ---------------------------------------------------------------------------

STORAGE_BACKEND = "csv"  # "csv" 또는 "db"
DB_ENGINE = None  # db 사용 시 SQLAlchemy engine. 예: create_engine("postgresql://user:pw@host/db")
DB_IF_EXISTS = "replace"  # 같은 이름의 테이블이 있을 때: "replace" / "append" / "fail"


def save_table(df: pd.DataFrame, name: str, output_dir: Path | None = None) -> str:
    """데이터프레임을 설정된 저장소에 저장하고, 저장 위치(파일 경로 또는 테이블 이름)를 돌려줍니다.

    Args:
        df: 저장할 데이터
        name: 파일 이름(확장자 제외) 또는 DB 테이블 이름
        output_dir: csv 저장 시 저장할 폴더 (db에서는 무시)

    Raises:
        ValueError: 저장 방식이 잘못되었거나 필요한 설정이 없을 때
    """
    if STORAGE_BACKEND == "csv":
        if output_dir is None:
            raise ValueError("csv 저장에는 output_dir이 필요합니다.")
        path = Path(output_dir) / f"{name}.csv"
        write_csv(df, path)
        return str(path)

    if STORAGE_BACKEND == "db":
        if DB_ENGINE is None:
            raise ValueError("db 저장에는 DB_ENGINE 설정이 필요합니다.")
        df.to_sql(name, con=DB_ENGINE, if_exists=DB_IF_EXISTS, index=False)
        return name

    raise ValueError(f'STORAGE_BACKEND는 "csv" 또는 "db"여야 합니다: {STORAGE_BACKEND}')