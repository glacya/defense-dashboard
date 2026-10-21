"""국민체력100 월별 측정 데이터(KS_NFA_FTNESS_MESURE_*.csv)에서 19~24세 남성 행만 모아 하나의 CSV로 저장합니다.

장병 연령대와 비슷한 일반인 기록을 대시보드의 비교 기준으로 쓰기 위한 전처리 단계입니다.
출력 컬럼과 순서는 통합 정의서의 영문속성명을 따릅니다.
BMI는 키와 체중으로 계산하고, 운동 처방은 본운동만 남깁니다.
심폐지구력(CARDIO)은 세 종목(20m 왕복 오래달리기·트레드밀·스텝검사)의 VO₂max 출력 중 기록된 값 하나를 씁니다.
두 종목 이상 기록된 행은 오래달리기 값을 쓰고, 확인할 수 있도록 따로 저장합니다.
BMI를 계산할 수 없는 행과 트레드밀 심박수가 거꾸로 기입된 행은 제거합니다.
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_KS_NFA_MERGED,
    DEFINITION_KS_NFA_RAW,
    INTERMEDIATE_MERGED,
    INTERMEDIATE_MULTI_CARDIO,
    RAW_DIR,
)

logger = logging.getLogger(__name__)

# 원본 월별 파일만 읽는다. 다른 CSV가 raw 폴더에 섞여 있어도 원본으로 잘못 읽지 않도록 이름 패턴을 좁게 지정한다.
INPUT_PATTERN = "KS_NFA_FTNESS_MESURE_*.csv"
# 공공데이터 원본은 UTF-8(BOM)과 CP949가 섞여 있을 수 있어 순서대로 시도
_ENCODINGS = ("utf-8-sig", "cp949")

# 대상자 조건
AGE_COLUMN = "MESURE_AGE_CO"
SEX_COLUMN = "SEXDSTN_FLAG_CD"
AGE_MIN, AGE_MAX = 19, 24

# 측정 항목 컬럼. MESURE_IEM_{번호}_VALUE의 번호가 측정 항목을 뜻함
HEIGHT_COLUMN = "MESURE_IEM_001_VALUE"
WEIGHT_COLUMN = "MESURE_IEM_002_VALUE"
BMI_COLUMN = "MESURE_IEM_018_VALUE"
BMI_OUTPUT_COLUMN = "BMI"
BODY_FAT_COLUMN = "MESURE_IEM_003_VALUE"
MEMBER_ID_COLUMN = "MBER_SEQ_NO_VALUE"
PRESCRIPTION_COLUMN = "MVM_PRSCRPTN_CN"
MESURE_DE_COLUMN = "MESURE_DE"
MESURE_SEQ_NO_COLUMN = "MESURE_SEQ_NO"

# 트레드밀 심박수 컬럼 (bpm). 기입 오류 판정에만 쓰고 결과에는 남기지 않는다.
TREADMILL_REST_HR_COLUMN = "MESURE_IEM_031_VALUE"  # 안정시
TREADMILL_3MIN_HR_COLUMN = "MESURE_IEM_032_VALUE"  # 3분
TREADMILL_6MIN_HR_COLUMN = "MESURE_IEM_033_VALUE"  # 6분
TREADMILL_HR_COLUMNS = (TREADMILL_REST_HR_COLUMN, TREADMILL_3MIN_HR_COLUMN, TREADMILL_6MIN_HR_COLUMN)

# 심폐 종목별 VO₂max 출력 컬럼. 순서가 두 종목 이상 기록됐을 때의 우선순위다.
# 오래달리기는 횟수(MESURE_IEM_020)가 아니라 시스템이 회귀식으로 환산한 VO₂max(030)를 써서 세 종목의 단위를 맞춘다.
# 오래달리기를 우선하는 이유: 공식 VO₂max 등급 컷이 오래달리기 환산값으로 만들어졌기 때문(2018 한국스포츠개발원 보고서).
CARDIO_SOURCE_COLUMNS = {
    "20M_RUN": "MESURE_IEM_030_VALUE",
    "TRAD": "MESURE_IEM_035_VALUE",
    "STEP": "MESURE_IEM_037_VALUE",
}
CARDIO_OUTPUT_COLUMN = "CARDIO"
# 심폐 종목이 두 개 이상 기록된 행을 따로 저장할 때 덧붙이는 컬럼
CARDIO_COUNT_COLUMN = "심폐 종목 수"
CARDIO_SELECTED_COLUMN = "선택한 종목"

# 출력 컬럼 -> 원본 컬럼. None은 원본에서 가져오지 않고 계산하는 컬럼
OUTPUT_SOURCE_COLUMNS = {
    "M_CODE": MEMBER_ID_COLUMN,
    "AGE": AGE_COLUMN,
    "REL_GRIP": "MESURE_IEM_028_VALUE",
    "CROSS_UP": "MESURE_IEM_019_VALUE",
    CARDIO_OUTPUT_COLUMN: None,
    "SIT_REACH": "MESURE_IEM_012_VALUE",
    PRESCRIPTION_COLUMN: PRESCRIPTION_COLUMN,
    "HEIGHT": HEIGHT_COLUMN,
    "WEIGHT": WEIGHT_COLUMN,
    BMI_OUTPUT_COLUMN: None,
    "BODY_FAT_PERCENTAGE": BODY_FAT_COLUMN,
    "MESURE_DE": MESURE_DE_COLUMN,
    "M_SEQ_NO": MESURE_SEQ_NO_COLUMN,
}

# 운동 처방 값 형식: '준비운동:A / 본운동:B / 정리운동:C' (일부 단계는 없을 수 있음)
# 항목 안에도 '손목 펴기/굽히기'처럼 '/'가 쓰이므로 단계 구분자는 공백을 포함한 ' / '로 본다.
_PRESCRIPTION_SEP = " / "
_PRESCRIPTION_STAGES = ("준비운동", "본운동", "정리운동", "마무리운동")
_MAIN_STAGE = "본운동"


def load_definition_columns(path: Path, name_column: str) -> list[str]:
    """정의서에서 컬럼명을 읽고 비어 있거나 중복된 이름을 거부합니다."""
    definition = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if name_column not in definition.columns:
        raise ValueError(f"{path.name}에 '{name_column}' 컬럼이 없습니다.")

    names = definition[name_column].str.strip()
    if names.empty or names.eq("").any():
        raise ValueError(f"{path.name}의 '{name_column}' 값은 비워둘 수 없습니다.")
    duplicates = names[names.duplicated()].unique().tolist()
    if duplicates:
        raise ValueError(
            f"{path.name}의 '{name_column}' 값이 중복되었습니다: {', '.join(duplicates)}"
        )
    return names.tolist()


def read_csv(path: Path) -> pd.DataFrame:
    """CSV 파일을 모든 값을 문자열로 읽어 반환합니다.

    빈 칸을 NaN이 아닌 빈 문자열로 유지해야 이후 `.str.strip()` 등을 그대로 쓸 수 있으므로
    dtype=str, keep_default_na=False로 읽습니다.

    Raises:
        ValueError: _ENCODINGS의 어떤 인코딩으로도 읽을 수 없을 때
    """
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 판별할 수 없습니다: {path}")


def filter_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """나이가 AGE_MIN~AGE_MAX이고 성별이 남성(M)인 행만 반환합니다."""
    candidate_mask, _, _ = get_candidate_masks(df)
    return df[candidate_mask]


def get_candidate_masks(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """대상자, 여성, 연령 범위 밖 행을 구분하는 마스크를 반환합니다.

    나이는 AGE_MIN~AGE_MAX 사이의 정수여야 대상자로 봅니다.
    """
    # 나이가 숫자가 아니거나 비어 있는 행, 정수가 아닌 행(예: 19.5)도 연령 범위 밖으로 분류합니다.
    # 범위 검사만 하면 19.5 같은 값이 통과하므로 정수 조건을 함께 둔다.
    age = pd.to_numeric(df[AGE_COLUMN].str.strip(), errors="coerce")
    in_age_range = age.between(AGE_MIN, AGE_MAX) & age.mod(1).eq(0)
    sex = df[SEX_COLUMN].str.strip()
    return in_age_range & sex.eq("M"), sex.eq("F"), ~in_age_range


def load_candidates(files: list[Path]) -> tuple[pd.DataFrame, int]:
    """파일들을 하나씩 읽어 대상자 행만 합칩니다.

    월별 파일 전체(약 670MB)를 한 번에 합치지 않고, 파일마다 먼저 걸러서 메모리 사용량을 줄입니다.

    Returns:
        (대상자 행을 합친 DataFrame, 걸러내기 전 전체 행 수)

    Raises:
        ValueError: 첫 파일과 컬럼 수가 다른 파일이 있을 때
    """
    ref_cols = None
    frames = []
    total = 0
    total_female = 0
    total_outside_age_range = 0
    total_excluded = 0
    for path in files:
        # 파일 하나를 읽고, 첫 파일의 헤더를 기준으로 컬럼 구성이 같은지 확인한다.
        df = read_csv(path)
        if ref_cols is None:
            ref_cols = list(df.columns)
        elif list(df.columns) != ref_cols:
            # 컬럼 수가 같으면 일부 파일의 헤더 이름만 깨진 것으로 보고 첫 파일의 헤더로 맞춘다.
            if len(df.columns) != len(ref_cols):
                raise ValueError(
                    f"{path.name}: 컬럼 수가 다릅니다 ({len(df.columns)} != {len(ref_cols)})"
                )
            diff = [(a, b) for a, b in zip(df.columns, ref_cols) if a != b]
            logger.warning("%s: 헤더 불일치 %s -> 기준 헤더로 교체", path.name, diff)
            df.columns = ref_cols
        # 19~24세 남성 행만 남기고, 제외한 건수는 로그용으로 센다.
        candidate_mask, female_mask, outside_age_range_mask = get_candidate_masks(df)
        cand = df[candidate_mask]
        female_count = int(female_mask.sum())
        outside_age_range_count = int(outside_age_range_mask.sum())
        # 성별·나이 필터 중 하나라도 걸린 행 (두 조건에 모두 걸린 행은 한 번만 센다)
        excluded_count = len(df) - len(cand)
        frames.append(cand)
        total += len(df)
        total_female += female_count
        total_outside_age_range += outside_age_range_count
        total_excluded += excluded_count
        logger.info(
            "%s: %s행 -> %s행 (제외 %s행: 여성 %s행, 나이 범위 밖 %s행)",
            path.name, f"{len(df):,}", f"{len(cand):,}",
            f"{excluded_count:,}", f"{female_count:,}", f"{outside_age_range_count:,}",
        )
    logger.info(
        "전체 제외 현황: 여성 %s행, 나이 범위 밖 %s행 (두 건수는 서로 겹칠 수 있음)",
        f"{total_female:,}", f"{total_outside_age_range:,}",
    )
    logger.info(
        "성별·나이 필터 중 하나라도 걸려 제외된 행: %s행 (전체 %s행 중 대상자 %s행)",
        f"{total_excluded:,}", f"{total:,}", f"{total - total_excluded:,}",
    )
    return pd.concat(frames, ignore_index=True), total


def calc_bmi(df: pd.DataFrame) -> pd.Series:
    """BMI = 체중(kg) / 신장(m)^2 를 소수점 둘째 자리까지 계산합니다.

    신장·체중 중 하나라도 비어 있거나 숫자가 아니면, 또는 신장이 0 이하이면 NaN을 반환합니다.
    """
    height = pd.to_numeric(df[HEIGHT_COLUMN].str.strip(), errors="coerce")
    weight = pd.to_numeric(df[WEIGHT_COLUMN].str.strip(), errors="coerce")
    # 신장이 0이면 나눗셈 결과가 inf가 되어 isna()로 걸러지지 않으므로 미리 NaN으로 바꿔 둔다.
    height = height.where(height > 0)
    return (weight / (height / 100) ** 2).round(2)


def find_treadmill_hr_errors(df: pd.DataFrame) -> pd.Series:
    """트레드밀 3분·6분 심박수가 모두 안정시 심박수보다 낮은 행(기입 오류)을 True로 표시합니다.

    운동을 할수록 심박수가 올라가야 정상인데, 2022년 5~6월 KSPO 송파 일부 센터처럼
    값이 거꾸로 입력된 기록이 있다. 이런 행은 심박수로 계산하는 VO₂max(TRAD)도 믿을 수 없다.
    세 값 중 하나라도 비어 있거나 숫자가 아니면 판정할 수 없으므로 오류로 보지 않는다.
    """
    rest, after_3min, after_6min = (
        pd.to_numeric(df[column].str.strip(), errors="coerce") for column in TREADMILL_HR_COLUMNS
    )
    # NaN과의 비교는 False이므로, 값이 빠진 행은 자동으로 오류에서 제외된다.
    return (after_3min < rest) & (after_6min < rest)


def select_cardio(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """행마다 심폐 종목 VO₂max 출력 중 하나를 골라 (CARDIO 값, 기록된 종목 수, 고른 종목 이름)을 반환합니다.

    한 종목만 기록됐으면 그 값을, 두 종목 이상이면 CARDIO_SOURCE_COLUMNS 순서상 앞선 종목(오래달리기)의 값을 씁니다.
    한 종목도 기록되지 않았으면 값과 종목 이름을 빈 문자열로 둡니다.
    """
    values = df[list(CARDIO_SOURCE_COLUMNS.values())].apply(lambda column: column.str.strip())
    values.columns = list(CARDIO_SOURCE_COLUMNS)
    present = values.ne("")
    count = present.sum(axis=1)

    cardio = pd.Series("", index=df.index, dtype=object)
    selected = pd.Series("", index=df.index, dtype=object)
    # 우선순위가 낮은 종목부터 덮어쓰면, 마지막에는 기록된 종목 중 우선순위가 가장 높은 값이 남는다.
    for event in reversed(list(CARDIO_SOURCE_COLUMNS)):
        cardio = cardio.mask(present[event], values[event])
        selected = selected.mask(present[event], event)
    return cardio, count, selected


def split_stages(value: str) -> list[tuple[str | None, str]]:
    """운동 처방 문자열을 단계별로 나눕니다.

    예: '준비운동:A / 본운동:B' -> [('준비운동', 'A'), ('본운동', 'B')]
    단계 이름이 _PRESCRIPTION_STAGES에 없는 조각은 단계를 None으로 둡니다.
    """
    stages = []
    for seg in value.split(_PRESCRIPTION_SEP):
        label, sep, body = seg.partition(":")
        label = label.strip()
        if sep and label in _PRESCRIPTION_STAGES:
            stages.append((label, body.strip()))
        else:
            stages.append((None, seg))
    return stages


def extract_main_exercise(values: pd.Series) -> pd.Series:
    """운동 처방에서 본운동 내용만 남깁니다. 본운동이 없으면 빈 문자열을 넣습니다.

    형식이 예상과 다른 값의 개수는 경고 로그로 남깁니다.
    """
    results = []
    malformed = 0
    for value in values:
        stages = split_stages(value) if value.strip() else []
        if any(label is None for label, _ in stages):
            malformed += 1
        results.append(next((body for label, body in stages if label == _MAIN_STAGE), ""))
    if malformed:
        logger.warning("운동 처방 형식이 다른 값 %s개", f"{malformed:,}")
    return pd.Series(results, index=values.index)


def run(
    raw_dir: Path,
    source_definition_path: Path,
    output_definition_path: Path,
    output_path: Path,
    multi_cardio_path: Path,
) -> None:
    """raw_dir의 원본 월별 파일을 합쳐 output_path에 저장합니다.

    Args:
        raw_dir: *.csv 원본 파일이 있는 폴더
        source_definition_path: 원본 컬럼 정의서 (컬럼영문명 컬럼 필요)
        output_definition_path: 통합 결과 정의서 (영문속성명 컬럼 필요). 출력 컬럼 순서를 정함
        output_path: 결과 CSV 경로
        multi_cardio_path: 심폐 종목이 두 개 이상 기록된 행을 확인용으로 저장할 CSV 경로.
            이 행들은 output_path에도 오래달리기 값으로 들어간다.

    Raises:
        FileNotFoundError: raw_dir에 원본 파일이 없을 때
        ValueError: 정의서와 코드의 컬럼 매핑이 맞지 않을 때
    """
    # 1. 정의서 검사: 코드의 컬럼 매핑(OUTPUT_SOURCE_COLUMNS)이 두 정의서와 맞는지 확인한다.
    #    원본(약 670MB)을 모두 읽은 뒤에 실패하지 않도록 가장 먼저 검사한다.
    source_columns = load_definition_columns(source_definition_path, "컬럼영문명")
    output_columns = load_definition_columns(output_definition_path, "영문속성명")
    required_output_columns = set(OUTPUT_SOURCE_COLUMNS)
    missing_output_columns = sorted(required_output_columns.difference(output_columns))
    if missing_output_columns:
        raise ValueError(
            f"통합 정의서에 필수 컬럼이 없습니다: {', '.join(missing_output_columns)}"
        )
    mapped_source_columns = {
        source_column for source_column in OUTPUT_SOURCE_COLUMNS.values() if source_column is not None
    } | set(CARDIO_SOURCE_COLUMNS.values())
    undefined_source_columns = sorted(mapped_source_columns.difference(source_columns))
    if undefined_source_columns:
        raise ValueError(
            "통합 출력 매핑의 원본 컬럼이 원본 정의서에 없습니다: "
            f"{', '.join(undefined_source_columns)}"
        )

    # 2. 원본 파일 목록 수집 (KS_NFA_FTNESS_MESURE_*.csv만)
    files = sorted(raw_dir.glob(INPUT_PATTERN))
    if not files:
        raise FileNotFoundError(f"{display_path(raw_dir)}에 {INPUT_PATTERN} 파일이 없습니다.")
    logger.info("원본 파일 %d개 읽기 시작: %s", len(files), display_path(raw_dir))

    # 3. 파일별로 읽으면서 19~24세 남성 행만 모은다.
    candidate, total = load_candidates(files)

    # 4. 합친 데이터에 매핑과 트레드밀 기입 오류 판정에 필요한 원본 컬럼이 모두 있는지 확인한다.
    required_input_columns = {
        source_column
        for output_column, source_column in OUTPUT_SOURCE_COLUMNS.items()
        if output_column in output_columns and source_column is not None
    } | set(TREADMILL_HR_COLUMNS) | set(CARDIO_SOURCE_COLUMNS.values())
    missing_input_columns = sorted(required_input_columns.difference(candidate.columns))
    if missing_input_columns:
        raise ValueError(
            f"원본 CSV에 정의서 컬럼이 없습니다: {', '.join(missing_input_columns)}"
        )

    # 5. 통합 정의서 순서대로 출력 컬럼을 만든다.
    #    원본 컬럼은 이름만 바꿔 옮기고, BMI는 키·체중으로 새로 계산하고, 심폐지구력은 세 종목 중 하나를 고른다.
    cardio, cardio_count, cardio_selected = select_cardio(candidate)
    merged = pd.DataFrame(index=candidate.index)
    for output_column in output_columns:
        source_column = OUTPUT_SOURCE_COLUMNS[output_column]
        if source_column is not None:
            merged[output_column] = candidate[source_column]
        elif output_column == BMI_OUTPUT_COLUMN:
            merged[output_column] = calc_bmi(candidate)
        elif output_column == CARDIO_OUTPUT_COLUMN:
            merged[output_column] = cardio
        else:
            raise ValueError(f"통합 컬럼의 원본 매핑이 정의되지 않았습니다: {output_column}")
    # 6. 운동 처방은 본운동 내용만 남긴다.
    merged[PRESCRIPTION_COLUMN] = extract_main_exercise(
        merged[PRESCRIPTION_COLUMN]
    )

    # 7. BMI 계산 불가 행과 트레드밀 심박수 기입 오류 행을 제거한 뒤 저장
    # BMI를 계산할 수 없는 행은 측정값이 모두 비어 있는 행이라 분석에 쓸 수 없으므로 제거한다.
    no_bmi = merged[BMI_OUTPUT_COLUMN].isna()
    # 심박수 컬럼은 결과에 남기지 않으므로, 컬럼을 버리기 전인 이 단계에서 판정한다.
    treadmill_error = find_treadmill_hr_errors(candidate)
    kept = ~no_bmi & ~treadmill_error
    merged = merged.loc[kept, output_columns]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Excel에서 한글이 깨지지 않도록 BOM을 붙여 저장
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")

    # 8. 심폐 종목이 두 개 이상 기록된 행은 통합 결과에 남기되, 확인할 수 있도록 세 종목 값과 고른 종목을 붙여 따로 저장한다.
    multi_cardio_rows = kept & cardio_count.gt(1)
    multi_cardio = merged.loc[multi_cardio_rows[kept]].copy()
    for event, source_column in CARDIO_SOURCE_COLUMNS.items():
        multi_cardio[event] = candidate.loc[multi_cardio.index, source_column]
    multi_cardio[CARDIO_COUNT_COLUMN] = cardio_count.loc[multi_cardio.index]
    multi_cardio[CARDIO_SELECTED_COLUMN] = cardio_selected.loc[multi_cardio.index]
    multi_cardio_path.parent.mkdir(parents=True, exist_ok=True)
    multi_cardio.to_csv(multi_cardio_path, index=False, encoding="utf-8-sig")

    # 9. 요약 로그
    logger.info("파일: %d개, 전체: %s행", len(files), f"{total:,}")
    logger.info("BMI 계산 불가로 제거: %s행", f"{no_bmi.sum():,}")
    logger.info(
        "트레드밀 컬럼 값 기입 오류로 제거: %s행 (3분·6분 심박수가 모두 안정시보다 낮음, BMI 계산 불가와 겹치는 행 %s행)",
        f"{treadmill_error.sum():,}", f"{(treadmill_error & no_bmi).sum():,}",
    )
    logger.info("심폐지구력(%s) 선택 결과 (저장 행 기준):", CARDIO_OUTPUT_COLUMN)
    for event in CARDIO_SOURCE_COLUMNS:
        logger.info("  %s: %s행", event, f"{int((kept & cardio_selected.eq(event)).sum()):,}")
    logger.info("  기록 없음(빈칸): %s행", f"{int((kept & cardio_count.eq(0)).sum()):,}")
    logger.info("  두 종목 이상 기록(오래달리기 우선): %s행", f"{int(multi_cardio_rows.sum()):,}")
    logger.info("저장: %s (%s행)", display_path(output_path), f"{len(merged):,}")
    logger.info("저장(심폐 종목 두 개 이상): %s (%s행)", display_path(multi_cardio_path), f"{len(multi_cardio):,}")


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(RAW_DIR, DEFINITION_KS_NFA_RAW, DEFINITION_KS_NFA_MERGED, INTERMEDIATE_MERGED, INTERMEDIATE_MULTI_CARDIO)


if __name__ == "__main__":
    main()
