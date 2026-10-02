from config import (
    CSV_DATA_DIR,
)
from dashboard.py.error_handlers import safe_execution
from dashboard.py.loader import (
    load_csv_data,
)

import numpy as np
import pandas as pd


DATA_DIR = CSV_DATA_DIR
FIT_PATH = DATA_DIR / "FIT_outlier_removed.csv"
OUTPUT_PATH = DATA_DIR / "description_result.csv"



@safe_execution(error_message="심폐지구력 중복 제거 실패", error_type="error", reraise=True)
def main():
    if not FIT_PATH.exists():
        raise FileNotFoundError(f"FIT.csv 파일을 찾을 수 없습니다: {FIT_PATH}")

    text_columns = ["CROSS_SIT_UP", "SEAT_4_BEND"]
    test_columns = [
        "TREADMILL",
        "STEP_TEST",
        "SHUTTLE_RUN_20M",
    ]
    numeric_columns = [*test_columns, *text_columns]
    df = load_csv_data(
        FIT_PATH,
        encoding="utf-8-sig",
        keep_default_na=False,
        dtype={column: "string" for column in text_columns},
    )
    # datafram으로 모든열을 읽어옴
    columns = [
        column
        for column in df.columns
        if column not in {"AGE_20_29","SEX_CODE","YEAR_MONTH", "PERSON_CODE"}
    ]
    test_presence = df[test_columns].astype("string").apply(
        lambda column: column.str.strip().ne("")
    ).fillna(False)
    valid_rows = test_presence.sum(axis=1).eq(1)
    numeric_df = df.loc[valid_rows, columns].copy()
    for column in numeric_columns:
        numeric_df[column] = pd.to_numeric(numeric_df[column], errors="coerce")
    desdf = numeric_df.describe(include=['number'])
    desdf = np.trunc(desdf * 100) / 100
    desdf.to_csv(OUTPUT_PATH, encoding='utf-8-sig', float_format="%.2f")

if __name__ == "__main__":
    main()
