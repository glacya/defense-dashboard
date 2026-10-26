"""최종 데이터에서 독자 참고용 샘플(data/samples/)을 만듭니다.

장병을 무작위로 골라(기본 100명) 그 장병의 최종 체력 측정(1명당 3건)·장병 명단·부상 기록만 남깁니다.
장병·부상 데이터는 새로 생성하지 않고 합성 단계(synthesis/)가 만든 결과에서 뽑으므로, 세 샘플의 군번이 서로 맞습니다.
샘플은 데이터 형태를 보여 주기 위한 것이라 파이프라인이나 다른 코드의 입력으로 쓰지 않습니다.
그래서 샘플 경로는 paths.py가 아니라 이 모듈에만 두고, 파이프라인에도 넣지 않습니다(직접 실행).
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

from config import SAMPLE_DIR
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_KS_NFA_FINAL,
    DEFINITION_SOLDIER_INJURY,
    DEFINITION_SOLDIER_PERSONNEL,
    PROCESSED_FITNESS_PATH,
    SYNTHETIC_INJURY_PATH,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.utils import positive_int, read_text_csv, require_columns, write_by_definition

logger = logging.getLogger(__name__)

SAMPLE_SOLDIER_COUNT = 100
DEFAULT_SEED = 42
SOLDIER_ID_COLUMN = "SOLDIER_ID"

FITNESS_SAMPLE_PATH = SAMPLE_DIR / "KS_NFA_PROCESSED_SAMPLE.csv"
PERSONNEL_SAMPLE_PATH = SAMPLE_DIR / "SOLDIER_PERSONNEL_SAMPLE.csv"
INJURY_SAMPLE_PATH = SAMPLE_DIR / "SOLDIER_INJURY_SAMPLE.csv"

# (원본, 정의서, 샘플) 순서. 측정 -> 명단 -> 부상
SAMPLE_TARGETS = (
    (PROCESSED_FITNESS_PATH, DEFINITION_KS_NFA_FINAL, FITNESS_SAMPLE_PATH),
    (SYNTHETIC_PERSONNEL_PATH, DEFINITION_SOLDIER_PERSONNEL, PERSONNEL_SAMPLE_PATH),
    (SYNTHETIC_INJURY_PATH, DEFINITION_SOLDIER_INJURY, INJURY_SAMPLE_PATH),
)


def choose_soldiers(soldier_ids: pd.Series, count: int, seed: int = DEFAULT_SEED) -> set[str]:
    """서로 다른 군번 중 count개를 무작위로 고릅니다.

    Raises:
        ValueError: 군번 종류가 count보다 적을 때
    """
    unique_ids = pd.Series(soldier_ids.unique())
    if count > len(unique_ids):
        raise ValueError(f"장병이 {len(unique_ids):,}명뿐이라 {count:,}명을 고를 수 없습니다.")
    return set(unique_ids.sample(n=count, random_state=seed))


def filter_by_soldiers(df: pd.DataFrame, soldier_ids: set[str]) -> pd.DataFrame:
    """고른 장병의 행만 원래 순서와 값 그대로 남깁니다."""
    require_columns(df, [SOLDIER_ID_COLUMN])
    return df[df[SOLDIER_ID_COLUMN].isin(soldier_ids)]


def build_samples(
    fitness: pd.DataFrame,
    personnel: pd.DataFrame,
    injuries: pd.DataFrame,
    count: int = SAMPLE_SOLDIER_COUNT,
    seed: int = DEFAULT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """체력 측정에서 장병 count명을 골라 세 데이터의 샘플(측정, 명단, 부상)을 반환합니다.

    Raises:
        ValueError: 고른 장병 중 명단에 없는 장병이 있을 때
    """
    require_columns(fitness, [SOLDIER_ID_COLUMN], "체력 측정 데이터")
    soldier_ids = choose_soldiers(fitness[SOLDIER_ID_COLUMN], count, seed)
    personnel_sample = filter_by_soldiers(personnel, soldier_ids)
    missing = soldier_ids - set(personnel_sample[SOLDIER_ID_COLUMN])
    if missing:
        raise ValueError(f"장병 명단에 없는 군번이 {len(missing):,}개 있습니다.")
    return (
        filter_by_soldiers(fitness, soldier_ids),
        personnel_sample,
        filter_by_soldiers(injuries, soldier_ids),
    )


def run(
    targets: tuple[tuple[Path, Path, Path], ...] = SAMPLE_TARGETS,
    count: int = SAMPLE_SOLDIER_COUNT,
    seed: int = DEFAULT_SEED,
) -> None:
    """최종 체력 측정·장병 명단·부상 기록을 읽어 장병 count명분 샘플을 정의서 컬럼대로 저장합니다.

    Args:
        targets: (원본, 정의서, 샘플) 경로 세 쌍. 측정 -> 명단 -> 부상 순서
        count: 뽑을 장병 수
        seed: 난수 시드

    값은 문자열 그대로 읽고 써서 샘플의 각 행이 원본 행과 같게 합니다.
    """
    fitness, personnel, injuries = (read_text_csv(source) for source, _, _ in targets)
    samples = build_samples(fitness, personnel, injuries, count, seed)
    for sample, (source, definition, sample_path) in zip(samples, targets):
        write_by_definition(sample, definition, sample_path)
        logger.info("%s -> %s: %s행", display_path(source), display_path(sample_path), f"{len(sample):,}")
    logger.info("장병 %s명 무작위 추출 (시드 %s)", f"{count:,}", seed)


def main() -> None:
    """최종 데이터의 기본 경로에서 data/samples/의 샘플 세 개를 다시 만듭니다."""
    parser = argparse.ArgumentParser(description="최종 데이터에서 독자 참고용 샘플을 만듭니다.")
    parser.add_argument(
        "-n", "--count", type=positive_int, default=SAMPLE_SOLDIER_COUNT,
        help=f"뽑을 장병 수 (기본값: {SAMPLE_SOLDIER_COUNT})",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"난수 시드 (기본값: {DEFAULT_SEED})")
    args = parser.parse_args()

    setup_logging(caller_name(__file__))
    run(SAMPLE_TARGETS, args.count, args.seed)


if __name__ == "__main__":
    main()
