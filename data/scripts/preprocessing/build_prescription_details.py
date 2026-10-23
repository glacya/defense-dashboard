"""통합 측정 데이터의 운동 처방 목록에서 서로 다른 처방 이름을 모아 운동 처방 상세(유형) 테이블을 만듭니다.

원본 통합 단계 바로 다음, 행을 걸러 내기 전의 전체 데이터로 만들므로 이후 단계에서 어떤 측정이 남더라도
그 측정의 처방 이름은 모두 이 테이블에 있습니다. 최종 정의서 적용 단계는 처방 행에 이 테이블의 처방유형번호를 붙입니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_KS_NFA_PRESCRIPTION_DETAIL,
    INTERMEDIATE_MERGED,
    PROCESSED_PRESCRIPTION_DETAIL_PATH,
)
from data.scripts.preprocessing.merge_raw_measurements import load_definition_columns

logger = logging.getLogger(__name__)

DEFINITION_NAME_COLUMN = "영문속성명"
# 입력의 운동 처방 목록 컬럼. 예: '앉았다 일어서기,윗몸올리기 ,팔굽혀펴기'
PRESCRIPTION_LIST_COLUMN = "MVM_PRSCRPTN_CN"
PRESCRIPTION_SEP = ","
# 출력 컬럼
PRESCRIPTION_TYPE_ID_COLUMN = "PRESCRIPTION_TYPE_ID"
PRESCRIPTION_COLUMN = "PRESCRIPTION"


def split_prescription_names(prescription_lists: pd.Series) -> pd.Series:
    """처방 목록을 쉼표로 나눠 처방 이름 하나당 한 원소인 Series로 만듭니다. 앞뒤 공백은 지우고 빈 항목은 뺍니다."""
    names = prescription_lists.str.split(PRESCRIPTION_SEP).explode().str.strip()
    return names[names.notna() & names.ne("")]


def build_prescription_types(prescription_lists: pd.Series) -> pd.DataFrame:
    """서로 다른 처방 이름마다 처방유형번호를 붙인 표(PRESCRIPTION_TYPE_ID, PRESCRIPTION)를 만듭니다.

    처방유형번호는 처방 이름이 처음 나온 순서대로 1부터 붙입니다. 번호 순서에는 의미가 없습니다.
    """
    names = split_prescription_names(prescription_lists).unique()
    return pd.DataFrame({
        PRESCRIPTION_TYPE_ID_COLUMN: range(1, len(names) + 1),
        PRESCRIPTION_COLUMN: names,
    })


def run(input_path: Path, definition_path: Path, output_path: Path) -> None:
    """input_path의 운동 처방 목록으로 운동 처방 상세 테이블을 만들어 정의서 컬럼 순서대로 output_path에 저장합니다.

    Raises:
        ValueError: 정의서에 있는 컬럼을 만들 수 없을 때
    """
    # 1. 정의서 컬럼 목록과 입력 데이터를 읽는다.
    columns = load_definition_columns(definition_path, DEFINITION_NAME_COLUMN)
    df = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    # 2. 처방 이름마다 처방유형번호를 붙인다.
    types = build_prescription_types(df[PRESCRIPTION_LIST_COLUMN])
    missing_columns = [column for column in columns if column not in types.columns]
    if missing_columns:
        raise ValueError(f"{definition_path.name}의 컬럼을 만들 수 없습니다: {', '.join(missing_columns)}")
    # 3. 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    types[columns].to_csv(output_path, index=False, encoding="utf-8-sig")

    # 4. 요약 로그
    has_prescription = df[PRESCRIPTION_LIST_COLUMN].str.strip().ne("")
    logger.info(
        "입력 %s: %s행 (처방이 있는 측정 %s행)",
        display_path(input_path), f"{len(df):,}", f"{int(has_prescription.sum()):,}",
    )
    logger.info("운동 처방 상세: %s개 (처방유형번호 1 ~ %s)", f"{len(types):,}", f"{len(types):,}")
    logger.info("저장: %s", display_path(output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_MERGED, DEFINITION_KS_NFA_PRESCRIPTION_DETAIL, PROCESSED_PRESCRIPTION_DETAIL_PATH)


if __name__ == "__main__":
    main()
