"""국민체력100 월별 측정 데이터(KS_NFA_FTNESS*.csv)에서 19~24세 남성 행만 모아 KS_NFA_TOTAL.csv로 저장합니다.

장병 연령대와 비슷한 일반인 기록을 대시보드의 비교 기준으로 쓰기 위한 전처리 스크립트입니다.
남기는 컬럼: 회원식별번호, 나이, 측정일, 6개 종목 기록, 운동 처방(본운동만), 키(cm), 체중(kg), BMI, 체지방률
원본 컬럼의 의미는 csv_file/csv_define/KS_NFA_COLUMN_DEFINITION.csv를 참고하세요.
"""

import sys
from pathlib import Path

import pandas as pd

from config import CSV_DATA_DIR

# 입출력
INPUT_PATTERN = "KS_NFA_FTNESS*.csv"
OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_TOTAL.csv"
# 공공데이터 원본은 UTF-8(BOM)과 CP949가 섞여 있을 수 있어 순서대로 시도
_ENCODINGS = ("utf-8-sig", "cp949")

# 대상자 조건
AGE_COL = "MESURE_AGE_CO"
SEX_COL = "SEXDSTN_FLAG_CD"
AGE_MIN, AGE_MAX = 19, 24

# 측정 항목 컬럼. MESURE_IEM_{번호}_VALUE의 번호가 측정 항목을 뜻함
HEIGHT_COL = "MESURE_IEM_001_VALUE"  # 신장(cm)
WEIGHT_COL = "MESURE_IEM_002_VALUE"  # 체중(kg)
BODY_FAT_COL = "MESURE_IEM_003_VALUE"  # 체지방률(%)

# 결과에 남길 종목: {측정 항목 번호: 종목 이름}
EVENTS = {
    28: "상대악력",
    19: "교차윗몸일으키기",
    35: "트레드밀",
    37: "스텝검사",
    20: "20m 왕복 오래달리기",
    12: "앉아 윗몸 앞으로 굽히기",
}

# 원본 컬럼명 -> 결과 컬럼명. 이 딕셔너리의 순서가 결과 CSV의 컬럼 순서가 됨
RENAME = {
    "MBER_SEQ_NO_VALUE": "회원식별번호",
    "MESURE_AGE_CO": "나이",
    "MESURE_DE": "측정일",  # YYYYMMDD 문자열. 문자열 그대로 정렬해도 날짜 순서와 같음
    **{f"MESURE_IEM_{n:03d}_VALUE": f"{name} 종목 기록" for n, name in EVENTS.items()},
    "MVM_PRSCRPTN_CN": "운동 처방",
}

# 운동 처방 값 형식: '준비운동:A / 본운동:B / 정리운동:C' (일부 단계는 없을 수 있음)
# 항목 안에도 '손목 펴기/굽히기'처럼 '/'가 쓰이므로 단계 구분자는 공백을 포함한 ' / '로 본다.
_PRESCRIPTION_SEP = " / "
_PRESCRIPTION_STAGES = ("준비운동", "본운동", "정리운동", "마무리운동")
_MAIN_STAGE = "본운동"


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
    # 나이가 숫자가 아닌 행은 NaN이 되어 between에서 자동으로 제외됨
    age = pd.to_numeric(df[AGE_COL].str.strip(), errors="coerce")
    sex = df[SEX_COL].str.strip()
    return df[age.between(AGE_MIN, AGE_MAX) & (sex == "M")]


def load_candidates(files: list[Path]) -> tuple[pd.DataFrame, int]:
    """파일들을 하나씩 읽어 대상자 행만 합칩니다.

    월별 파일 전체(약 600MB)를 한 번에 합치지 않고, 파일마다 먼저 걸러서 메모리 사용량을 줄입니다.

    Returns:
        (대상자 행을 합친 DataFrame, 걸러내기 전 전체 행 수)

    Raises:
        ValueError: 첫 파일과 컬럼 수가 다른 파일이 있을 때
    """
    ref_cols = None
    frames = []
    total = 0
    for path in files:
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
            print(f"[경고] {path.name}: 헤더 불일치 {diff} -> 기준 헤더로 교체", file=sys.stderr)
            df.columns = ref_cols
        cand = filter_candidates(df)
        frames.append(cand)
        total += len(df)
        print(f"{path.name}: {len(df):,}행 -> {len(cand):,}행")
    return pd.concat(frames, ignore_index=True), total


def calc_bmi(df: pd.DataFrame) -> pd.Series:
    """BMI = 체중(kg) / 신장(m)^2 를 소수점 둘째 자리까지 계산합니다.

    신장·체중 중 하나라도 비어 있거나 숫자가 아니면, 또는 신장이 0 이하이면 NaN을 반환합니다.
    """
    height = pd.to_numeric(df[HEIGHT_COL].str.strip(), errors="coerce")
    weight = pd.to_numeric(df[WEIGHT_COL].str.strip(), errors="coerce")
    # 신장이 0이면 나눗셈 결과가 inf가 되어 isna()로 걸러지지 않으므로 미리 NaN으로 바꿔 둔다.
    height = height.where(height > 0)
    return (weight / (height / 100) ** 2).round(2)


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

    형식이 예상과 다른 값의 개수는 표준 에러로 경고합니다.
    """
    results = []
    malformed = 0
    for value in values:
        stages = split_stages(value) if value.strip() else []
        if any(label is None for label, _ in stages):
            malformed += 1
        results.append(next((body for label, body in stages if label == _MAIN_STAGE), ""))
    if malformed:
        print(f"[경고] 운동 처방 형식이 다른 값 {malformed:,}개", file=sys.stderr)
    return pd.Series(results, index=values.index)


def main() -> None:
    files = sorted(CSV_DATA_DIR.glob(INPUT_PATTERN))
    if not files:
        sys.exit(f"{CSV_DATA_DIR}에 {INPUT_PATTERN} 파일이 없습니다.")

    candidate, total = load_candidates(files)

    merged = candidate[list(RENAME)].rename(columns=RENAME)
    merged["키"] = candidate[HEIGHT_COL]
    merged["체중"] = candidate[WEIGHT_COL]
    merged["BMI"] = calc_bmi(candidate)
    merged["체지방률"] = candidate[BODY_FAT_COL]
    merged["운동 처방"] = extract_main_exercise(merged["운동 처방"])

    # BMI를 계산할 수 없는 행은 측정값이 모두 비어 있는 행이라 분석에 쓸 수 없으므로 제거한다.
    no_bmi = merged["BMI"].isna()
    merged = merged[~no_bmi]
    # Excel에서 한글이 깨지지 않도록 BOM을 붙여 저장
    merged.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"파일: {len(files)}개, 전체: {total:,}행")
    print(f"{OUTPUT_PATH.name}: {len(merged):,}행 (BMI 계산 불가 {no_bmi.sum():,}행 제거)")


if __name__ == "__main__":
    main()
