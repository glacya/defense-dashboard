"""심폐지구력(CARDIO, VO₂max)에 공식 등급 컷을 적용해 등급별 비율과 각 컷 미만 인원 비율을 표로 정리합니다. (탐색용 임시 스크립트)

공식 컷은 국민체력100 남자 19~24세 VO₂max 기준(2018 한국스포츠개발원 보고서 표 39) 42.0 / 44.8 / 47.6이며,
각 컷 이상이면 3·2·1등급입니다. 컷은 30·50·70 백분위로 설계되었으므로 컷 미만 비율이 30·50·70%에 가까울수록 설계와 맞습니다.
현재 파이프라인에서 쓰지 않습니다.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER, INTERMEDIATE_OFFICIAL_CUT_RATIOS, PASSED_FILENAME

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 파일 이름
RATIOS_FILENAME = "cardio_grade_ratios.csv"

CARDIO_COLUMN = "CARDIO"
# (3등급, 2등급, 1등급) 공식 컷. 설계상 30·50·70 백분위다.
OFFICIAL_VO2_CUTS = (42.0, 44.8, 47.6)
DESIGN_BELOW_PCT = (30.0, 50.0, 70.0)
GRADE_LABELS = ["등외", "3등급", "2등급", "1등급"]
DECIMALS = 4


def read_cardio(path: Path) -> pd.Series:
    """입력 CSV의 심폐지구력 컬럼을 숫자로 읽습니다.

    Raises:
        ValueError: CARDIO 컬럼이 없거나, 빈 값·숫자가 아닌 값이 있을 때. 결측치는 전처리 2단계에서 이미 제거된다.
    """
    data = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if CARDIO_COLUMN not in data.columns:
        raise ValueError(f"{CARDIO_COLUMN} 컬럼이 없습니다.")
    cardio = pd.to_numeric(data[CARDIO_COLUMN].str.strip(), errors="coerce")
    if cardio.isna().any():
        raise ValueError(f"{CARDIO_COLUMN}이 비어 있거나 숫자가 아닌 행이 {int(cardio.isna().sum()):,}개 있습니다.")
    return cardio


def build_grade_ratios(cardio: pd.Series, cuts: tuple[float, float, float] = OFFICIAL_VO2_CUTS) -> pd.DataFrame:
    """등급별 인원과 비율, 각 컷 미만 인원과 비율을 설계 비율과 함께 한 표로 만듭니다."""
    grades = pd.cut(cardio, [-np.inf, *cuts, np.inf], right=False, labels=GRADE_LABELS)
    counts = grades.value_counts().reindex(GRADE_LABELS)
    rows = [
        {"구분": f"{label} 비율", "기준": "", "N": int(counts[label]), "PCT": counts[label] / len(cardio) * 100, "설계_PCT": np.nan}
        for label in reversed(GRADE_LABELS)
    ]
    for label, cut, design in zip(["3등급", "2등급", "1등급"], cuts, DESIGN_BELOW_PCT):
        below = cardio.lt(cut)
        rows.append({
            "구분": f"{label} 미만",
            "기준": f"{CARDIO_COLUMN} < {cut:g}",
            "N": int(below.sum()),
            "PCT": below.mean() * 100,
            "설계_PCT": design,
        })
    return pd.DataFrame(rows)


def run(input_path: Path, output_dir: Path) -> None:
    """input_path의 심폐지구력에 공식 VO₂max 컷을 적용해 등급 비율 표를 output_dir에 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    ratios_path = output_dir / RATIOS_FILENAME
    # 2. 입력 로드 후 등급 비율 표를 만들어 저장한다.
    cardio = read_cardio(input_path)
    ratios = build_grade_ratios(cardio)
    ratios.round(DECIMALS).to_csv(ratios_path, index=False, encoding="utf-8-sig")

    # 3. 요약 로그
    logger.info(
        "입력 %s: %s행, %s 평균 %.2f, 표준편차 %.2f",
        display_path(input_path), f"{len(cardio):,}", CARDIO_COLUMN, cardio.mean(), cardio.std(),
    )
    for _, row in ratios.iterrows():
        design = "" if pd.isna(row["설계_PCT"]) else f" (설계 {row['설계_PCT']:.0f}%)"
        logger.info("  %s: %s명, %.1f%%%s", row["구분"], f"{row['N']:,}", row["PCT"], design)
    logger.info("저장(등급 비율): %s", display_path(ratios_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME, INTERMEDIATE_OFFICIAL_CUT_RATIOS)


if __name__ == "__main__":
    main()
