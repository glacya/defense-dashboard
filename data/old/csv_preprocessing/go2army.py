"""통합 측정 CSV에서 키와 BMI 조건에 맞는 입대 후보 데이터를 추립니다."""

from config import CSV_DATA_DIR

import pandas as pd


INPUT_FILENAME = "KS_NFA_TOTAL_CARDIO_DEDUPED.csv"
INPUT_PATH = CSV_DATA_DIR / INPUT_FILENAME
OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_ENLISTMENT_CANDIDATES.csv"
AGE_COLUMN = "AGE"
HEIGHT_COLUMN = "HEIGHT"
WEIGHT_COLUMN = "KG"
BMI_COLUMN = "BMI"
BODY_FAT_COLUMN = "BODY_FAT"
AGE_MIN = 19
AGE_MAX = 24
HEIGHT_MIN_CM = 159
HEIGHT_MAX_CM = 204
WEIGHT_MIN_KG = 37.92
WEIGHT_MAX_KG = 166.46
BMI_MIN = 15.0
BMI_MAX_EXCLUSIVE = 40.0
BODY_FAT_MIN_EXCLUSIVE = 2.0
BODY_FAT_MAX_EXCLUSIVE = 50.0


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


def get_measurement_masks(
    data: pd.DataFrame,
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """키, 체중, BMI, 체지방률의 결측 및 범위 이상 마스크를 반환합니다."""
    columns = [HEIGHT_COLUMN, WEIGHT_COLUMN, BMI_COLUMN, BODY_FAT_COLUMN]
    text = data[columns].astype("string").apply(lambda column: column.str.strip())
    values = text.apply(lambda column: pd.to_numeric(column, errors="coerce"))
    missing_masks = {
        column: text[column].isna() | text[column].eq("")
        for column in columns
    }

    def outside_range(column: str, invalid_range: pd.Series) -> pd.Series:
        return ~missing_masks[column] & (values[column].isna() | invalid_range)

    outlier_masks = {
        HEIGHT_COLUMN: outside_range(
            HEIGHT_COLUMN,
            values[HEIGHT_COLUMN].lt(HEIGHT_MIN_CM)
            | values[HEIGHT_COLUMN].gt(HEIGHT_MAX_CM),
        ),
        WEIGHT_COLUMN: outside_range(
            WEIGHT_COLUMN,
            values[WEIGHT_COLUMN].lt(WEIGHT_MIN_KG)
            | values[WEIGHT_COLUMN].gt(WEIGHT_MAX_KG),
        ),
        BMI_COLUMN: outside_range(
            BMI_COLUMN,
            values[BMI_COLUMN].lt(BMI_MIN)
            | values[BMI_COLUMN].ge(BMI_MAX_EXCLUSIVE),
        ),
        BODY_FAT_COLUMN: outside_range(
            BODY_FAT_COLUMN,
            values[BODY_FAT_COLUMN].le(BODY_FAT_MIN_EXCLUSIVE)
            | values[BODY_FAT_COLUMN].ge(BODY_FAT_MAX_EXCLUSIVE),
        ),
    }
    return missing_masks, outlier_masks


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"입력 CSV 파일이 없습니다: {INPUT_PATH}")

    data = read_input()
    required_columns = {
        AGE_COLUMN,
        HEIGHT_COLUMN,
        WEIGHT_COLUMN,
        BMI_COLUMN,
        BODY_FAT_COLUMN,
    }
    missing_columns = sorted(required_columns.difference(data.columns))
    if missing_columns:
        raise ValueError(f"입력 CSV에 필수 컬럼이 없습니다: {', '.join(missing_columns)}")

    total_rows = len(data)
    candidates = filter_population(data)
    missing_masks, outlier_masks = get_measurement_masks(candidates)
    missing_rows = pd.concat(missing_masks, axis=1).any(axis=1)
    outlier_rows = pd.concat(outlier_masks, axis=1).any(axis=1)
    selected_rows = ~missing_rows & ~outlier_rows
    selected = candidates.loc[selected_rows].copy()

    selected.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"원본 파일: {INPUT_FILENAME}, 전체 {total_rows:,}행")
    print(f"사전 선별된 {AGE_MIN}~{AGE_MAX}세 측정행: {len(candidates):,}행")
    print("속성별 결측/이상치:")
    for column in [HEIGHT_COLUMN, WEIGHT_COLUMN, BMI_COLUMN, BODY_FAT_COLUMN]:
        print(
            f"  {column}: 결측 {int(missing_masks[column].sum()):,}행, "
            f"이상치 {int(outlier_masks[column].sum()):,}행"
        )
    print(
        f"결측 포함 행(중복 제외): {int(missing_rows.sum()):,}행, "
        f"이상치 포함 행(중복 제외): {int(outlier_rows.sum()):,}행"
    )
    print(f"입대 후보 조건 충족: {len(selected):,}행")
    print(
        f"조건: {HEIGHT_MIN_CM}cm <= 키 <= {HEIGHT_MAX_CM}cm, "
        f"{WEIGHT_MIN_KG}kg <= 체중 <= {WEIGHT_MAX_KG}kg, "
        f"BMI {BMI_MIN} <= BMI < {BMI_MAX_EXCLUSIVE}, "
        f"{BODY_FAT_MIN_EXCLUSIVE}% < 체지방률 < {BODY_FAT_MAX_EXCLUSIVE}%"
    )
    print(f"저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
