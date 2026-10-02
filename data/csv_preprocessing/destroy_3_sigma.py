
from config import (
    CSV_DATA_DIR,
)
from dashboard.py.error_handlers import safe_execution
from dashboard.py.loader import (
    load_csv_data,
)

import pandas as pd


DATA_DIR = CSV_DATA_DIR
FIT_PATH = DATA_DIR / "FIT.csv"
CLEAN_PATH = DATA_DIR / "FIT_outlier_removed.csv"
OUTLIER_PATH = DATA_DIR / "FIT_destroy_outlier.csv"
EXCLUDED_COLUMNS = {"YEAR_MONTH", "PERSON_CODE"}
FILTER_RULE = (
    "YEAR_MONTH, PERSON_CODE를 제외한 수치형 열 중 하나라도 평균 ± 3표준편차 "
    "범위를 벗어나거나 SHUTTLE_RUN_20M이 5이하면 제외"
)


@safe_execution(error_message="이상치 제거 실패", error_type="error", reraise=True)
def main():
    if not FIT_PATH.exists():
        raise FileNotFoundError(f"FIT.csv 파일을 찾을 수 없습니다: {FIT_PATH}")

    df = load_csv_data(FIT_PATH, keep_default_na=False)
    numeric_columns = [
        column for column in df.columns if column not in EXCLUDED_COLUMNS
    ]
    numeric_df = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    outlier_rows = pd.Series(False, index=df.index)
    outlier_reasons = {index: [] for index in df.index}

    for column in numeric_columns:
        values = numeric_df[column]
        if values.notna().sum() < 2:
            continue

        mean = values.mean()
        standard_deviation = values.std()
        lower_bound = mean - 3 * standard_deviation
        upper_bound = mean + 3 * standard_deviation
        below_lower_bound = values.notna() & (values < lower_bound)
        above_upper_bound = values.notna() & (values > upper_bound)
        outlier_rows |= below_lower_bound | above_upper_bound

        for index in values.index[below_lower_bound]:
            outlier_reasons[index].append(
                f"{column}={values.at[index]:.2f}가 하한 {lower_bound:.2f} 미만 "
                f"(평균={mean:.2f}, 표준편차={standard_deviation:.2f})"
            )
        for index in values.index[above_upper_bound]:
            outlier_reasons[index].append(
                f"{column}={values.at[index]:.2f}가 상한 {upper_bound:.2f} 초과 "
                f"(평균={mean:.2f}, 표준편차={standard_deviation:.2f})"
            )

    shuttle_zero_rows = numeric_df["SHUTTLE_RUN_20M"].eq(0)
    outlier_rows |= shuttle_zero_rows
    for index in numeric_df.index[shuttle_zero_rows]:
        outlier_reasons[index].append(
            "SHUTTLE_RUN_20M=0이므로 제외 (허용 기준: 0 초과)"
        )

    clean_df = df.loc[~outlier_rows].copy()
    clean_df["OUTLIER_FILTER_RULE"] = FILTER_RULE
    clean_df.to_csv(CLEAN_PATH, index=False, encoding="utf-8-sig")

    outlier_df = df.loc[outlier_rows].copy()
    outlier_df["OUTLIER_REASON"] = outlier_rows[outlier_rows].index.map(
        lambda index: "; ".join(outlier_reasons[index])
    )
    outlier_df.to_csv(OUTLIER_PATH, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()