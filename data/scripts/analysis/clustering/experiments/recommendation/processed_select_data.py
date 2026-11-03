"""personal_selected.csv를 모델 입력용(백분위 피처 + 운동처방 라벨)으로 재가공한다.

피처 (모두 0~100 백분위, 높을수록 양호)
  - 측정 4종목: REL_GRIP, CROSS_UP, CARDIO, SIT_REACH (값이 클수록 양호)
  - BMI, BODY_FAT_PERCENTAGE (값이 작을수록 양호 -> 부호를 바꿔 방향을 맞춤)
타깃
  - PRESCRIPTION: 실제 운동처방 (쉼표 구분 문자열, 공백/중복 정리)
"""
import logging
import sys

import pandas as pd

from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER

logger = logging.getLogger(__name__)

DATA_DIR = INTERMEDIATE_ENLISTMENT_FILTER
IN_PATH = DATA_DIR / "personal_selected.csv"
OUT_PATH = DATA_DIR / "processed_select_personal.csv"

ID_COL = "M_CODE"
TARGET_RAW = "MVM_PRSCRPTN_CN"
TARGET_COL = "PRESCRIPTION"

# 값이 클수록 양호
HIGHER_BETTER = ["REL_GRIP", "CROSS_UP", "CARDIO", "SIT_REACH"]
# 값이 작을수록 양호 -> 부호 변경 후 백분위
LOWER_BETTER = ["BMI", "BODY_FAT_PERCENTAGE"]


def to_percentile(series: pd.Series) -> pd.Series:
    """0~100 백분위. 동점은 평균 순위, 결측은 결측 유지."""
    return series.rank(method="average", pct=True) * 100


def clean_prescription(text) -> str:
    """처방 문자열 정리: 항목별 공백 제거(띄어쓰기 표기 통일), 중복 제거, 순서 유지."""
    if pd.isna(text):
        return ""
    items = []
    for item in str(text).split(","):
        item = "".join(item.split())  # '팔 벌려 뛰기' -> '팔벌려뛰기', 양끝 공백 제거
        if item and item not in items:
            items.append(item)
    return ",".join(items)


def process(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({ID_COL: df[ID_COL]})

    for col in HIGHER_BETTER:
        out[f"{col}_PCT"] = to_percentile(df[col])

    for col in LOWER_BETTER:
        out[f"{col}_PCT"] = to_percentile(-df[col])  # 부호 변경: 낮을수록 높은 백분위

    out[TARGET_COL] = df[TARGET_RAW].map(clean_prescription)

    # 피처 결측 또는 라벨이 빈 행 제외
    feature_cols = [f"{c}_PCT" for c in HIGHER_BETTER + LOWER_BETTER]
    before = len(out)
    out = out.dropna(subset=feature_cols)
    out = out[out[TARGET_COL] != ""].reset_index(drop=True)
    logger.info("결측/빈 라벨 제거: %d -> %d", before, len(out))
    pct_cols = [c for c in out.columns if c.endswith("_PCT")]
    out[pct_cols] = out[pct_cols].round(2)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    in_path = sys.argv[1] if len(sys.argv) > 1 else IN_PATH
    out_path = sys.argv[2] if len(sys.argv) > 2 else OUT_PATH

    df = pd.read_csv(in_path, encoding="utf-8-sig")
    result = process(df)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"입력 {len(df):,}행 -> 출력 {len(result):,}행, 저장: {out_path}")