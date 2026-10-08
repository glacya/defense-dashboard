"""통합 측정 CSV에서 키와 BMI 조건에 맞는 입대 후보 데이터를 추립니다."""

from config import CSV_DATA_DIR

import pandas as pd


INPUT_FILENAME = "KS_NFA_TOTAL_CARDIO_DEDUPED.csv"
INPUT_PATH = CSV_DATA_DIR / INPUT_FILENAME
OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_ENLISTMENT_CANDIDATES.csv"
AGE_COLUMN = "AGE"
HEIGHT_COLUMN = "HEIGHT"
BMI_COLUMN = "BMI"
AGE_MIN = 19
AGE_MAX = 24
HEIGHT_MIN_CM = 159
HEIGHT_MAX_CM_EXCLUSIVE = 204
BMI_MIN = 18.5
BMI_MAX_EXCLUSIVE = 40.0


def read_input() -> pd.DataFrame:
    """통합 CSV를 모든 값을 문자열로 읽습니다."""
    return pd.read_csv(
        INPUT_PATH,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )


def filter_population(data: pd.DataFrame) -> pd.DataFrame:
    """남성으로 사전 선별된 데이터에서 19~24세 행만 반환합니다."""
    age = pd.to_numeric(data[AGE_COLUMN].str.strip(), errors="coerce")
    return data.loc[age.between(AGE_MIN, AGE_MAX)].copy()


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"입력 CSV 파일이 없습니다: {INPUT_PATH}")

    data = read_input()
    required_columns = {AGE_COLUMN, HEIGHT_COLUMN, BMI_COLUMN}
    missing_columns = sorted(required_columns.difference(data.columns))
    if missing_columns:
        raise ValueError(f"입력 CSV에 필수 컬럼이 없습니다: {', '.join(missing_columns)}")

    total_rows = len(data)
    candidates = filter_population(data)
    height = pd.to_numeric(
        candidates[HEIGHT_COLUMN].str.strip(),
        errors="coerce",
    )
    bmi = pd.to_numeric(candidates[BMI_COLUMN].str.strip(), errors="coerce")

    bmi_in_range = bmi.ge(BMI_MIN) & bmi.lt(BMI_MAX_EXCLUSIVE)

    selected_rows = (
        height.ge(HEIGHT_MIN_CM)
        & height.lt(HEIGHT_MAX_CM_EXCLUSIVE)
        & bmi_in_range
    )
    selected = candidates.loc[selected_rows].copy()

    selected.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    valid_measurements = height.notna() & bmi.notna()
    print(f"원본 파일: {INPUT_FILENAME}, 전체 {total_rows:,}행")
    print(f"사전 선별된 {AGE_MIN}~{AGE_MAX}세 측정행: {len(candidates):,}행")
    print(f"키/BMI 유효 측정행: {int(valid_measurements.sum()):,}행")
    print(f"입대 후보 조건 충족: {len(selected):,}행")
    print(
        f"조건: {HEIGHT_MIN_CM}cm <= 키 < {HEIGHT_MAX_CM_EXCLUSIVE}cm, "
        f"BMI {BMI_MIN} <= BMI < {BMI_MAX_EXCLUSIVE}"
    )
    print(f"저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
