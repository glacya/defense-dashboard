"""전처리 결과를 최종 정의서 세 개(FINAL, PRESCRIPTION, PRESCRIPTION_DETAIL)의 구성으로 나눠 저장합니다.

- 측정 데이터: 측정 컬럼 이름을 체력 요소 이름(근력·근지구력·유연성)으로 바꾼 뒤 KS_NFA_FINAL_DEFINITION.csv의 컬럼만 정의서 순서대로 남깁니다.
- 운동 처방 유형: 서로 다른 처방 이름마다 처방유형번호(PRESCRIPTION_TYPE_ID)를 붙여 KS_NFA_PRESCRIPTION_DETAIL_DEFINITION.csv 구성으로 저장합니다.
- 운동 처방: 쉼표로 이어진 처방 목록을 처방 하나당 한 행으로 나누고, 처방 이름 대신 처방유형번호를 넣어
  KS_NFA_PRESCRIPTION_DEFINITION.csv 구성으로 저장합니다. 같은 처방 이름이 수만 번 반복되므로 이름은 유형 파일에만 둡니다.
측정 데이터와 운동 처방은 이 단계에서 새로 부여하는 측정식별번호(MESURE_ID)로, 운동 처방과 처방 유형은 처방유형번호로 연결됩니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_KS_NFA_FINAL,
    DEFINITION_KS_NFA_PRESCRIPTION,
    DEFINITION_KS_NFA_PRESCRIPTION_DETAIL,
    INTERMEDIATE_THREE_MEASURES,
    PROCESSED_FITNESS_PATH,
    PROCESSED_PRESCRIPTION_DETAIL_PATH,
    PROCESSED_PRESCRIPTION_PATH,
)
from data.scripts.preprocessing.merge_raw_measurements import load_definition_columns

logger = logging.getLogger(__name__)

DEFINITION_NAME_COLUMN = "영문속성명"

# 입력 컬럼
MESURE_DE_COLUMN = "MESURE_DE"
MEMBER_ID_COLUMN = "M_CODE"
MESURE_SEQ_NO_COLUMN = "M_SEQ_NO"
PRESCRIPTION_LIST_COLUMN = "MVM_PRSCRPTN_CN"

# 이 단계에서 새로 만드는 컬럼
MESURE_ID_COLUMN = "MESURE_ID"
PRESCRIPTION_ID_COLUMN = "PRESCRIPTION_ID"
PRESCRIPTION_TYPE_ID_COLUMN = "PRESCRIPTION_TYPE_ID"
PRESCRIPTION_COLUMN = "PRESCRIPTION"

# 운동 처방 목록의 항목 구분자. 예: '앉았다 일어서기,윗몸올리기 ,팔굽혀펴기'
PRESCRIPTION_SEP = ","

# 통합 데이터의 측정 컬럼 이름 -> 최종 정의서의 체력 요소 이름. 심폐지구력(CARDIO)은 통합 단계부터 같은 이름이다.
FINAL_COLUMN_NAMES = {
    "REL_GRIP": "STRENGTH",
    "CROSS_UP": "ENDURANCE",
    "SIT_REACH": "FLEXIBILITY",
}


def assign_mesure_id(df: pd.DataFrame) -> pd.DataFrame:
    """측정일 -> 회원식별번호 -> 측정일련번호 오름차순으로 정렬하고 MESURE_ID를 1부터 차례로 붙입니다.

    (측정일, 회원식별번호, 측정일련번호)는 원본 데이터셋의 PK이므로, 이 순서로 매긴 번호도 행마다 유일합니다.

    Raises:
        ValueError: 측정일련번호가 정수가 아닌 행이 있을 때
    """
    # 측정일련번호는 문자열로 정렬하면 "10"이 "2"보다 앞에 오므로 숫자로 바꿔 정렬한다.
    seq_no = pd.to_numeric(df[MESURE_SEQ_NO_COLUMN].str.strip(), errors="coerce")
    invalid = seq_no.isna() | seq_no.mod(1).ne(0)
    if invalid.any():
        raise ValueError(f"{MESURE_SEQ_NO_COLUMN}이 정수가 아닌 행이 {int(invalid.sum()):,}개 있습니다.")

    # 측정일은 YYYYMMDD 문자열이라 문자열 순서가 날짜 순서와 같다.
    sorted_df = (
        df.assign(_seq_no=seq_no)
        .sort_values([MESURE_DE_COLUMN, MEMBER_ID_COLUMN, "_seq_no"])
        .drop(columns="_seq_no")
        .reset_index(drop=True)
    )
    sorted_df.insert(0, MESURE_ID_COLUMN, range(1, len(sorted_df) + 1))
    return sorted_df


def split_prescriptions(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """운동 처방 목록을 쉼표로 나눠 처방 하나당 한 행으로 만들고 PRESCRIPTION_ID를 1부터 붙입니다.

    항목 앞뒤 공백은 지우고, 빈 항목(처방이 없는 측정 포함)은 만들지 않습니다.
    같은 측정 안에 같은 처방이 두 번 이상 나오면 처음 나온 것만 남깁니다.
    행 순서는 MESURE_ID 순서, 같은 측정 안에서는 원래 처방 목록의 순서를 따릅니다.

    Returns:
        (PRESCRIPTION_ID, MESURE_ID, PRESCRIPTION 컬럼의 DataFrame, 제거한 중복 처방 수)
    """
    items = (
        df[[MESURE_ID_COLUMN, PRESCRIPTION_LIST_COLUMN]]
        .assign(**{PRESCRIPTION_COLUMN: df[PRESCRIPTION_LIST_COLUMN].str.split(PRESCRIPTION_SEP)})
        .explode(PRESCRIPTION_COLUMN)
    )
    items[PRESCRIPTION_COLUMN] = items[PRESCRIPTION_COLUMN].str.strip()
    items = items[items[PRESCRIPTION_COLUMN].ne("")]
    # 공백을 지운 뒤에 비교해야 '윗몸올리기'와 '윗몸올리기 '를 같은 처방으로 본다.
    duplicated = items.duplicated([MESURE_ID_COLUMN, PRESCRIPTION_COLUMN], keep="first")
    items = items[~duplicated].reset_index(drop=True)
    items.insert(0, PRESCRIPTION_ID_COLUMN, range(1, len(items) + 1))
    return items[[PRESCRIPTION_ID_COLUMN, MESURE_ID_COLUMN, PRESCRIPTION_COLUMN]], int(duplicated.sum())


def assign_prescription_types(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """처방 이름마다 처방유형번호를 붙이고, 처방 행의 이름을 그 번호로 바꿉니다.

    처방유형번호는 처방 이름이 처음 나온 순서대로 1부터 붙입니다. 번호 순서에는 의미가 없습니다.

    Args:
        items: split_prescriptions()의 결과 (PRESCRIPTION_ID, MESURE_ID, PRESCRIPTION)

    Returns:
        (PRESCRIPTION_TYPE_ID, PRESCRIPTION 컬럼의 처방 유형 표,
         PRESCRIPTION을 PRESCRIPTION_TYPE_ID로 바꾼 처방 행)
    """
    names = items[PRESCRIPTION_COLUMN].unique()
    types = pd.DataFrame({PRESCRIPTION_TYPE_ID_COLUMN: range(1, len(names) + 1), PRESCRIPTION_COLUMN: names})
    type_ids = items[PRESCRIPTION_COLUMN].map(dict(zip(names, types[PRESCRIPTION_TYPE_ID_COLUMN])))
    with_type_ids = items.drop(columns=PRESCRIPTION_COLUMN).assign(**{PRESCRIPTION_TYPE_ID_COLUMN: type_ids})
    return types, with_type_ids


def select_definition_columns(df: pd.DataFrame, columns: list[str], definition_name: str) -> pd.DataFrame:
    """정의서의 컬럼만 정의서 순서대로 남깁니다.

    Raises:
        ValueError: 정의서에 있는 컬럼이 df에 없을 때
    """
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"{definition_name}의 컬럼이 데이터에 없습니다: {', '.join(missing_columns)}")
    return df[columns]


def run(
    input_path: Path,
    fitness_definition_path: Path,
    prescription_definition_path: Path,
    prescription_detail_definition_path: Path,
    fitness_output_path: Path,
    prescription_output_path: Path,
    prescription_detail_output_path: Path,
) -> None:
    """input_path를 정렬해 MESURE_ID를 붙인 뒤, 측정 데이터·운동 처방·운동 처방 유형을 각 정의서 구성으로 저장합니다.

    Args:
        input_path: 3회 이상 측정 회원 추출 단계의 결과
        fitness_definition_path: 측정 데이터 정의서 (KS_NFA_FINAL_DEFINITION.csv)
        prescription_definition_path: 운동 처방 정의서 (KS_NFA_PRESCRIPTION_DEFINITION.csv)
        prescription_detail_definition_path: 운동 처방 유형 정의서 (KS_NFA_PRESCRIPTION_DETAIL_DEFINITION.csv)
        fitness_output_path: 측정 데이터 저장 경로
        prescription_output_path: 운동 처방 데이터 저장 경로
        prescription_detail_output_path: 운동 처방 유형 저장 경로

    Raises:
        ValueError: 정의서 컬럼을 만들 수 없을 때, 측정일련번호가 정수가 아닐 때
    """
    # 1. 정의서 세 개의 컬럼 목록과 입력 데이터를 읽는다.
    fitness_columns = load_definition_columns(fitness_definition_path, DEFINITION_NAME_COLUMN)
    prescription_columns = load_definition_columns(prescription_definition_path, DEFINITION_NAME_COLUMN)
    prescription_detail_columns = load_definition_columns(prescription_detail_definition_path, DEFINITION_NAME_COLUMN)
    df = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)

    # 2. 측정일 -> 회원식별번호 -> 측정일련번호 순으로 정렬하고 새 PK인 MESURE_ID를 붙인 뒤, 측정 컬럼을 최종 이름으로 바꾼다.
    df = assign_mesure_id(df).rename(columns=FINAL_COLUMN_NAMES)

    # 3. 측정 데이터: 정의서 컬럼만 정의서 순서대로 남겨 저장한다.
    fitness = select_definition_columns(df, fitness_columns, fitness_definition_path.name)
    dropped_columns = [column for column in df.columns if column not in fitness_columns]
    fitness_output_path.parent.mkdir(parents=True, exist_ok=True)
    fitness.to_csv(fitness_output_path, index=False, encoding="utf-8-sig")

    # 4. 운동 처방: 처방 목록을 처방 하나당 한 행으로 나누고(같은 측정 안의 중복 제거),
    #    처방 이름을 처방유형번호로 바꿔 처방 행과 처방 유형을 각 정의서 순서대로 저장한다.
    split_items, duplicate_count = split_prescriptions(df)
    prescription_types, typed_items = assign_prescription_types(split_items)
    prescriptions = select_definition_columns(
        typed_items, prescription_columns, prescription_definition_path.name
    )
    prescription_details = select_definition_columns(
        prescription_types, prescription_detail_columns, prescription_detail_definition_path.name
    )
    prescription_output_path.parent.mkdir(parents=True, exist_ok=True)
    prescriptions.to_csv(prescription_output_path, index=False, encoding="utf-8-sig")
    prescription_detail_output_path.parent.mkdir(parents=True, exist_ok=True)
    prescription_details.to_csv(prescription_detail_output_path, index=False, encoding="utf-8-sig")

    # 5. 요약 로그
    no_prescription = int(df[PRESCRIPTION_LIST_COLUMN].str.strip().eq("").sum())
    logger.info("입력 %s: %s행", display_path(input_path), f"{len(df):,}")
    logger.info(
        "MESURE_ID 부여: 1 ~ %s (정렬: %s -> %s -> %s 오름차순)",
        f"{len(df):,}", MESURE_DE_COLUMN, MEMBER_ID_COLUMN, MESURE_SEQ_NO_COLUMN,
    )
    logger.info(
        "측정 데이터: 컬럼 %d개, 정의서에 없어 제외한 컬럼: %s",
        len(fitness_columns), ", ".join(dropped_columns) if dropped_columns else "(없음)",
    )
    logger.info(
        "운동 처방 데이터: %s행 (측정 %s건에서 분리, 처방이 비어 있는 측정 %s건)",
        f"{len(prescriptions):,}", f"{len(df) - no_prescription:,}", f"{no_prescription:,}",
    )
    logger.info("같은 측정 안의 중복 처방 제거: %s행", f"{duplicate_count:,}")
    logger.info("운동 처방 유형: %s개 (처방유형번호 1 ~ %s)", f"{len(prescription_details):,}", f"{len(prescription_details):,}")
    logger.info("저장(측정): %s", display_path(fitness_output_path))
    logger.info("저장(운동 처방): %s", display_path(prescription_output_path))
    logger.info("저장(운동 처방 유형): %s", display_path(prescription_detail_output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(
        INTERMEDIATE_THREE_MEASURES,
        DEFINITION_KS_NFA_FINAL,
        DEFINITION_KS_NFA_PRESCRIPTION,
        DEFINITION_KS_NFA_PRESCRIPTION_DETAIL,
        PROCESSED_FITNESS_PATH,
        PROCESSED_PRESCRIPTION_PATH,
        PROCESSED_PRESCRIPTION_DETAIL_PATH,
    )


if __name__ == "__main__":
    main()
