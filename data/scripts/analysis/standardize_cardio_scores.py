"""심폐지구력 3개 종목(트레드밀·스텝검사·20m 왕복 오래달리기) 기록을 종목별 Z점수로 바꿔 하나의 점수로 합칩니다.

트레드밀·스텝검사는 VO2max(mL/kg/min), 20m 왕복 오래달리기는 횟수라 단위가 다르므로,
종목마다 평균과 표준편차로 표준화한 뒤 CARDIO_Z 한 컬럼에 모읍니다.
종목을 고른 집단의 심폐능력이 비슷하다고 가정합니다. 세 종목 모두 값이 클수록 좋은 기록입니다.

20m 왕복 오래달리기는 등급 컷오프(41·52·62회)에서 측정을 멈춘 기록이 몰려 있으므로,
estimate_shuttle_run_latent_scores의 절단 정규 구간 모형으로 잠재 횟수를 추정해 보정한 값을 표준화합니다.
현재 파이프라인에서 쓰지 않는 탐색용 단계입니다.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import truncnorm

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_CARDIO_ZSCORE, INTERMEDIATE_THREE_MEASURES
from data.scripts.analysis.estimate_shuttle_run_latent_scores import (
    build_observations,
    fit_interval_regression,
)
from data.scripts.preprocessing.remove_missings_and_outliers import CARDIO_COLUMNS

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 파일 이름
SCORED_FILENAME = "KS_NFA_CARDIO_ZSCORE.csv"
STATS_FILENAME = "cardio_zscore_stats.csv"

SHUTTLE_COL = "20M_RUN"
EVENT_COL = "CARDIO_EVENT"
VALUE_COL = "CARDIO_VALUE"
ADJUSTED_VALUE_COL = "CARDIO_VALUE_ADJ"
RAW_Z_COL = "CARDIO_Z_RAW"
Z_COL = "CARDIO_Z"
Z_DECIMALS = 4
METHOD_SAMPLE = "표본 평균·표준편차"
METHOD_SHUTTLE_MODEL = "절단 정규 구간 모형(컷오프 보정)"


def read_input(path: Path) -> pd.DataFrame:
    """입력 CSV를 모든 값을 문자열로 읽습니다."""
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def identify_cardio_event(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """행마다 기록된 심폐 종목 이름과 그 값을 (종목, 값)으로 반환합니다.

    결측치·이상치 제거 단계에서 종목이 정확히 하나인 행만 남겼으므로, 그렇지 않은 행이 있으면 오류를 냅니다.
    """
    missing = [column for column in CARDIO_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

    present = df[CARDIO_COLUMNS].apply(lambda column: column.str.strip().ne(""))
    event_counts = present.sum(axis=1)
    if event_counts.ne(1).any():
        raise ValueError(f"심폐 종목이 정확히 하나가 아닌 행이 {int(event_counts.ne(1).sum()):,}개 있습니다.")

    events = present.idxmax(axis=1)
    values = pd.Series(
        [df.at[index, event] for index, event in events.items()], index=df.index, dtype="string"
    )
    numeric = pd.to_numeric(values.str.strip(), errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"심폐 종목 값이 숫자가 아닌 행이 {int(numeric.isna().sum()):,}개 있습니다.")
    return events, numeric


def compute_event_stats(events: pd.Series, values: pd.Series) -> pd.DataFrame:
    """종목별 행 수, 평균, 표준편차(표본, ddof=1), 왜도를 CARDIO_COLUMNS 순서로 반환합니다."""
    stats = values.groupby(events).agg(N="size", MEAN="mean", STD="std", SKEW="skew")
    stats = stats.reindex([column for column in CARDIO_COLUMNS if column in stats.index])
    if stats["N"].lt(2).any() or stats["STD"].eq(0).any():
        raise ValueError("표본이 2개 미만이거나 표준편차가 0인 종목이 있어 표준화할 수 없습니다.")
    stats.index.name = EVENT_COL
    return stats


def estimate_shuttle_latent(data: pd.DataFrame) -> tuple[pd.Series, float, float]:
    """20m 왕복 오래달리기 행마다 보정한 잠재 횟수와, 모형이 추정한 잠재 분포의 (평균, 표준편차)를 반환합니다.

    컷오프 기록은 다음 컷오프까지의 구간, 나머지는 [기록-0.5, 기록+0.5) 구간으로 보고 모형을 추정한 뒤,
    각 행의 값은 그 구간 안의 조건부 기댓값으로 정합니다.
    estimate_shuttle_run_latent_scores는 구간 안에서 난수를 뽑지만, 같은 기록인 사람이 다른 점수를 받지 않도록
    여기서는 기댓값을 씁니다.
    """
    shuttle_rows = data.loc[data[SHUTTLE_COL].str.strip().ne("")]
    observations, lower, upper, group_codes, _, _ = build_observations(shuttle_rows)
    if len(observations) != len(shuttle_rows):
        raise ValueError(
            f"모형에서 제외된 {SHUTTLE_COL} 행이 {len(shuttle_rows) - len(observations):,}개 있습니다. "
            "(19~24세 0 이상 정수 기록만 쓸 수 있습니다.)"
        )

    means, standard_deviation = fit_interval_regression(observations, lower, upper, group_codes)
    mean = float(means[0])
    expected = truncnorm.mean(
        (lower - mean) / standard_deviation,
        (upper - mean) / standard_deviation,
        loc=mean,
        scale=standard_deviation,
    )
    latent = pd.Series(np.asarray(expected), index=observations["source_index"].to_numpy())
    return latent, mean, standard_deviation


def run(input_path: Path, output_dir: Path) -> None:
    """input_path의 심폐 종목 기록을 종목별 Z점수로 바꿔 output_dir에 저장합니다.

    KS_NFA_CARDIO_ZSCORE.csv는 입력 컬럼 뒤에 다음 컬럼을 붙인 파일입니다.
    - CARDIO_EVENT: 종목 컬럼 이름, CARDIO_VALUE: 원래 값
    - CARDIO_VALUE_ADJ: 보정 값(오래달리기만 잠재 횟수, 나머지는 원래 값)
    - CARDIO_Z_RAW: 원래 값의 표본 Z점수, CARDIO_Z: 보정 값의 Z점수(사용할 점수)
    cardio_zscore_stats.csv는 종목별로 CARDIO_Z에 쓴 평균·표준편차와 원래 값의 표본 통계입니다.
    평균과 표준편차는 회원이 아니라 행(측정) 단위로 계산합니다.
    """
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    scored_path = output_dir / SCORED_FILENAME
    stats_path = output_dir / STATS_FILENAME
    # 2. 입력 로드 후 행마다 종목과 값을 구한다.
    data = read_input(input_path).reset_index(drop=True)
    events, values = identify_cardio_event(data)
    sample_stats = compute_event_stats(events, values)

    # 3. 오래달리기는 잠재 횟수로 보정하고, 그 평균·표준편차는 모형 추정값을 쓴다.
    adjusted = values.copy()
    is_shuttle = events.eq(SHUTTLE_COL)
    used_stats = sample_stats[["MEAN", "STD"]].assign(METHOD=METHOD_SAMPLE)
    if is_shuttle.any():
        latent, shuttle_mean, shuttle_std = estimate_shuttle_latent(data)
        adjusted.loc[is_shuttle] = latent.reindex(data.index[is_shuttle]).to_numpy()
        used_stats.loc[SHUTTLE_COL] = [shuttle_mean, shuttle_std, METHOD_SHUTTLE_MODEL]

    # 4. 원래 값과 보정 값을 각각 표준화한다.
    raw_z = (values - events.map(sample_stats["MEAN"])) / events.map(sample_stats["STD"])
    z_scores = (adjusted - events.map(used_stats["MEAN"])) / events.map(used_stats["STD"])

    # 5. 저장
    scored = data.copy()
    scored[EVENT_COL] = events
    scored[VALUE_COL] = values
    scored[ADJUSTED_VALUE_COL] = adjusted.round(Z_DECIMALS)
    scored[RAW_Z_COL] = raw_z.round(Z_DECIMALS)
    scored[Z_COL] = z_scores.round(Z_DECIMALS)
    scored.to_csv(scored_path, index=False, encoding="utf-8-sig")
    stats_table = used_stats.join(sample_stats.add_prefix("SAMPLE_"))
    stats_table.to_csv(stats_path, encoding="utf-8-sig")

    # 6. 요약 로그
    logger.info("입력 %s: %s행", display_path(input_path), f"{len(data):,}")
    for event, row in stats_table.iterrows():
        logger.info(
            "  %s: %s행, 표준화 평균 %.2f·표준편차 %.2f (%s), 원래 값 평균 %.2f·표준편차 %.2f·왜도 %.2f",
            event, f"{int(row['SAMPLE_N']):,}", row["MEAN"], row["STD"], row["METHOD"],
            row["SAMPLE_MEAN"], row["SAMPLE_STD"], row["SAMPLE_SKEW"],
        )
    for event in stats_table.index:
        selected = events.eq(event)
        logger.info(
            "  %s %s: 평균 %.3f, 표준편차 %.3f, 범위 %.2f ~ %.2f",
            event, Z_COL, z_scores[selected].mean(), z_scores[selected].std(),
            z_scores[selected].min(), z_scores[selected].max(),
        )
    logger.info("저장(점수): %s", display_path(scored_path))
    logger.info("저장(종목별 통계): %s", display_path(stats_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_THREE_MEASURES, INTERMEDIATE_CARDIO_ZSCORE)


if __name__ == "__main__":
    main()
