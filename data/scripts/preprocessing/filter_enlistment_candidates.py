"""통합 측정 CSV에서 키와 BMI 조건에 맞는 입대 후보 데이터를 추립니다."""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_CARDIO_FILTER, INTERMEDIATE_ENLISTMENT_FILTER, PASSED_FILENAME

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 제거 행 파일 이름
REMOVED_MISSING_FILENAME = "removed_missing.csv"
REMOVED_OUTLIER_FILENAME = "removed_outlier.csv"

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


def read_input(path: Path) -> pd.DataFrame:
    """통합 CSV를 모든 값을 문자열로 읽습니다."""
    return pd.read_csv(
        path,
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


def build_removal_reasons(
    index: pd.Index,
    missing_masks: dict[str, pd.Series],
    outlier_masks: dict[str, pd.Series],
) -> pd.Series:
    """행마다 '키 결측; BMI 범위 밖'처럼 걸린 조건을 모두 이어 붙인 제거 사유를 만듭니다."""
    reasons = pd.Series("", index=index, dtype="string")
    labeled_masks = [
        *((mask, f"{column} 결측") for column, mask in missing_masks.items()),
        *((mask, f"{column} 범위 밖") for column, mask in outlier_masks.items()),
    ]
    for mask, label in labeled_masks:
        existing = reasons.loc[mask]
        reasons.loc[mask] = existing.where(existing.eq(""), existing + "; ") + label
    return reasons


def run(input_path: Path, output_dir: Path) -> None:
    """input_path에서 입대 후보 신체 조건을 만족하는 19~24세 행만 골라 output_dir/passed.csv에 저장합니다.

    제거한 행은 사유를 붙여 결측(removed_missing.csv)과 범위 밖 이상치(removed_outlier.csv)로 나눠 저장합니다.
    결측과 이상치가 함께 있는 행은 이상치 파일에만 들어가며, 제거 사유에는 둘 다 적힙니다.
    """
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / PASSED_FILENAME
    missing_removed_path = output_dir / REMOVED_MISSING_FILENAME
    outlier_removed_path = output_dir / REMOVED_OUTLIER_FILENAME
    # 2. 입력 로드 및 필수 컬럼 검사
    data = read_input(input_path)
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

    # 3. 19~24세 행만 남긴다. 원본 통합 단계에서 이미 걸렀으므로 보통 제외되는 행은 없다.
    total_rows = len(data)
    candidates = filter_population(data)
    # 4. 키·체중·BMI·체지방률마다 결측과 범위 밖 값을 표시하고, 어느 것에도 걸리지 않은 행만 통과시킨다.
    missing_masks, outlier_masks = get_measurement_masks(candidates)
    missing_rows = pd.concat(missing_masks, axis=1).any(axis=1)
    outlier_rows = pd.concat(outlier_masks, axis=1).any(axis=1)
    selected_rows = ~missing_rows & ~outlier_rows
    selected = candidates.loc[selected_rows].copy()

    # 5. 제거 행에 사유를 붙여 나눈다. 결측과 이상치가 함께 있는 행은 이상치 파일에만 넣는다.
    reasons = build_removal_reasons(candidates.index, missing_masks, outlier_masks)
    outlier_removed = candidates.loc[outlier_rows].copy()
    outlier_removed["제거 사유"] = reasons.loc[outlier_rows]
    missing_only_rows = missing_rows & ~outlier_rows
    missing_removed = candidates.loc[missing_only_rows].copy()
    missing_removed["제거 사유"] = reasons.loc[missing_only_rows]

    # 6. 저장 후, 통과 + 제거 행 수가 연령 선별 행 수와 같은지 검증한다.
    selected.to_csv(output_path, index=False, encoding="utf-8-sig")
    missing_removed.to_csv(missing_removed_path, index=False, encoding="utf-8-sig")
    outlier_removed.to_csv(outlier_removed_path, index=False, encoding="utf-8-sig")
    if len(selected) + len(missing_removed) + len(outlier_removed) != len(candidates):
        raise RuntimeError("통과/결측 제거/이상치 제거 행 수가 연령 선별 행 수와 일치하지 않습니다.")

    # 7. 요약 로그
    logger.info("입력 %s: 전체 %s행", display_path(input_path), f"{total_rows:,}")
    logger.info(
        "사전 선별된 %d~%d세 측정행: %s행 (연령 범위 밖 %s행 제외)",
        AGE_MIN, AGE_MAX, f"{len(candidates):,}", f"{total_rows - len(candidates):,}",
    )
    logger.info("속성별 결측/이상치:")
    for column in [HEIGHT_COLUMN, WEIGHT_COLUMN, BMI_COLUMN, BODY_FAT_COLUMN]:
        logger.info(
            "  %s: 결측 %s행, 이상치 %s행",
            column, f"{int(missing_masks[column].sum()):,}", f"{int(outlier_masks[column].sum()):,}",
        )
    logger.info(
        "결측 포함 행(중복 제외): %s행, 이상치 포함 행(중복 제외): %s행",
        f"{int(missing_rows.sum()):,}", f"{int(outlier_rows.sum()):,}",
    )
    logger.info(
        "조건: %scm <= 키 <= %scm, %skg <= 체중 <= %skg, %s <= BMI < %s, %s%% < 체지방률 < %s%%",
        HEIGHT_MIN_CM, HEIGHT_MAX_CM, WEIGHT_MIN_KG, WEIGHT_MAX_KG,
        BMI_MIN, BMI_MAX_EXCLUSIVE, BODY_FAT_MIN_EXCLUSIVE, BODY_FAT_MAX_EXCLUSIVE,
    )
    logger.info(
        "입대 후보 조건 충족: %s행 (결측 제거 %s행, 이상치 제거 %s행)",
        f"{len(selected):,}", f"{len(missing_removed):,}", f"{len(outlier_removed):,}",
    )
    logger.info("저장(통과): %s", display_path(output_path))
    logger.info("저장(결측 제거): %s", display_path(missing_removed_path))
    logger.info("저장(이상치 제거): %s", display_path(outlier_removed_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(Path(__file__).stem)
    run(INTERMEDIATE_CARDIO_FILTER / PASSED_FILENAME, INTERMEDIATE_ENLISTMENT_FILTER)


if __name__ == "__main__":
    main()
