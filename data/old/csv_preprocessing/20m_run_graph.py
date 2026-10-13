from config import CSV_DATA_DIR
from dashboard.py.error_handlers import safe_execution
from dashboard.py.loader import load_csv_data

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from scipy.optimize import minimize
from scipy.special import log_ndtr
from scipy.stats import norm, truncnorm

FILE_NAME = "KS_NFA_TOTAL_CARDIO_DEDUPED"
DATA_DIR = CSV_DATA_DIR
INPUT_PATH = DATA_DIR / f"{FILE_NAME}.csv"
OUTPUT_DIR = DATA_DIR / f"{FILE_NAME}_shuttle_interval_results"
AGE_COLUMN = "AGE"
SHUTTLE_COLUMN = "20M_RUN"
RANDOM_SEED = 20261008
HOLDOUT_FRACTION = 0.2
AVAILABLE_FONTS = {font.name for font in font_manager.fontManager.ttflist}
for korean_font in ("Malgun Gothic", "NanumGothic", "Gulim", "Noto Sans CJK KR"):
    if korean_font in AVAILABLE_FONTS:
        plt.rcParams["font.family"] = korean_font
        break
plt.rcParams["axes.unicode_minus"] = False
AGE_GROUPS = {
    "19-24": {
        "minimum_age": 19,
        "maximum_age": 24,
        "cutoffs": [41, 52, 62],
    },
}


def log_difference(log_larger: np.ndarray, log_smaller: np.ndarray) -> np.ndarray:
    return log_larger + np.log(-np.expm1(log_smaller - log_larger))


def interval_log_probability(
    lower: np.ndarray,
    upper: np.ndarray,
    mean: float,
    standard_deviation: float,
) -> np.ndarray:
    lower_z = (lower - mean) / standard_deviation
    upper_z = (upper - mean) / standard_deviation
    log_probability = np.empty(lower.shape, dtype=float)
    right_censored = np.isposinf(upper)
    log_probability[right_censored] = log_ndtr(-lower_z[right_censored])

    finite_interval = ~right_censored
    upper_tail = finite_interval & (lower_z >= 0)
    lower_tail = finite_interval & (lower_z < 0)
    log_probability[upper_tail] = log_difference(
        log_ndtr(-lower_z[upper_tail]),
        log_ndtr(-upper_z[upper_tail]),
    )
    log_probability[lower_tail] = log_difference(
        log_ndtr(upper_z[lower_tail]),
        log_ndtr(lower_z[lower_tail]),
    )
    return log_probability


def build_observations(
    data: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, int],
    pd.DataFrame,
]:
    age = pd.to_numeric(data[AGE_COLUMN], errors="coerce")
    shuttle = pd.to_numeric(data[SHUTTLE_COLUMN], errors="coerce")
    raw_shuttle = data[SHUTTLE_COLUMN].astype("string").str.strip()
    frames = []
    in_scope_age = pd.Series(False, index=data.index)

    for group_name, group in AGE_GROUPS.items():
        group_age = age.between(group["minimum_age"], group["maximum_age"])
        in_scope_age |= group_age
        integer_score = pd.Series(
            np.isclose(shuttle.fillna(-1), np.round(shuttle.fillna(-1))),
            index=data.index,
        )
        selected = group_age & shuttle.notna() & shuttle.ge(0) & integer_score
        group_data = pd.DataFrame(
            {
                "source_index": data.index[selected],
                "age_group": group_name,
                "observed": shuttle.loc[selected].astype(float).to_numpy(),
            }
        )
        frames.append(group_data)

    observations = pd.concat(frames, ignore_index=True)
    if observations.empty:
        raise ValueError("19~24세에 유효한 0 이상 정수 셔틀런 기록이 없습니다.")

    blank_score = in_scope_age & raw_shuttle.eq("")
    non_numeric_score = in_scope_age & raw_shuttle.ne("") & shuttle.isna()
    negative_score = in_scope_age & shuttle.notna() & shuttle.lt(0)
    nonnegative_numeric = in_scope_age & shuttle.notna() & shuttle.ge(0)
    integer_score = pd.Series(
        np.isclose(shuttle.fillna(-1), np.round(shuttle.fillna(-1))),
        index=data.index,
    )
    non_integer_score = nonnegative_numeric & ~integer_score
    invalid_masks = {
        "셔틀런 기록 공란": blank_score,
        "셔틀런 기록 비숫자": non_numeric_score,
        "셔틀런 기록 음수": negative_score,
        "셔틀런 기록 비정수": non_integer_score,
    }
    invalid_frames = [
        data.loc[mask].assign(
            원본_행_인덱스=data.index[mask],
            셔틀런_원본_값=raw_shuttle.loc[mask].to_numpy(),
            검토_제외_사유=reason,
        )
        for reason, mask in invalid_masks.items()
        if mask.any()
    ]
    if invalid_frames:
        invalid_rows = pd.concat(invalid_frames, axis=0).sort_values(
            "원본_행_인덱스"
        )
    else:
        invalid_rows = data.iloc[0:0].copy()
        invalid_rows["원본_행_인덱스"] = pd.Series(dtype="int64")
        invalid_rows["셔틀런_원본_값"] = pd.Series(dtype="string")
        invalid_rows["검토_제외_사유"] = pd.Series(dtype="string")
    invalid_rows = invalid_rows.rename(
        columns={
            "원본_행_인덱스": "원본 행 인덱스",
            "셔틀런_원본_값": "셔틀런 원본 값",
            "검토_제외_사유": "검토 제외 사유",
        }
    )
    record_counts = {
        "source_row_count": len(data),
        "out_of_age_range_count": int((~in_scope_age).sum()),
        "blank_count": int(blank_score.sum()),
        "non_numeric_count": int(non_numeric_score.sum()),
        "negative_count": int(negative_score.sum()),
        "non_integer_count": int(non_integer_score.sum()),
        "valid_observation_count": len(observations),
    }

    lower = np.empty(len(observations), dtype=float)
    upper = np.empty(len(observations), dtype=float)
    for group_name, group in AGE_GROUPS.items():
        group_rows = observations["age_group"].eq(group_name).to_numpy()
        cutoffs = group["cutoffs"]
        for row_index in np.flatnonzero(group_rows):
            observed = observations.at[row_index, "observed"]
            if observed in cutoffs:
                cutoff_index = cutoffs.index(int(observed))
                lower[row_index] = observed
                upper[row_index] = (
                    cutoffs[cutoff_index + 1]
                    if cutoff_index + 1 < len(cutoffs)
                    else np.inf
                )
            else:
                lower[row_index] = max(0.0, observed - 0.5)
                upper[row_index] = observed + 0.5

    group_codes = observations["age_group"].map(
        {group_name: code for code, group_name in enumerate(AGE_GROUPS)}
    ).to_numpy(dtype=int)
    return observations, lower, upper, group_codes, record_counts, invalid_rows


def fit_interval_regression(
    observations: pd.DataFrame,
    lower: np.ndarray,
    upper: np.ndarray,
    group_codes: np.ndarray,
) -> tuple[np.ndarray, float]:
    group_count = len(AGE_GROUPS)
    initial_means = [
        observations.loc[observations["age_group"] == group_name, "observed"].mean()
        for group_name in AGE_GROUPS
    ]
    initial_standard_deviation = observations["observed"].std(ddof=1)

    def negative_log_likelihood(parameters: np.ndarray) -> float:
        means = parameters[:group_count]
        standard_deviation = float(np.exp(parameters[-1]))
        log_likelihood = np.empty(len(observations), dtype=float)

        for group_code, mean in enumerate(means):
            selected = group_codes == group_code
            log_likelihood[selected] = interval_log_probability(
                lower[selected],
                upper[selected],
                float(mean),
                standard_deviation,
            )
            # Latent counts are non-negative, so fit a normal distribution truncated at zero.
            log_likelihood[selected] -= norm.logsf(
                (0.0 - float(mean)) / standard_deviation
            )

        if not np.isfinite(log_likelihood).all():
            return np.finfo(float).max
        return -float(log_likelihood.sum())

    initial_parameters = np.array(
        [*initial_means, np.log(max(initial_standard_deviation, 1e-3))]
    )
    result = minimize(
        negative_log_likelihood,
        initial_parameters,
        method="L-BFGS-B",
        bounds=[(None, None)] * group_count + [(-5, 5)],
    )
    if not result.success:
        raise RuntimeError(f"구간 검열 정규모형 추정에 실패했습니다: {result.message}")

    return result.x[:group_count], float(np.exp(result.x[-1]))


def mean_interval_log_likelihood(
    observations: pd.DataFrame,
    lower: np.ndarray,
    upper: np.ndarray,
    group_codes: np.ndarray,
    means: np.ndarray,
    standard_deviation: float,
) -> float:
    log_likelihood = np.empty(len(observations), dtype=float)
    for group_code, mean in enumerate(means):
        selected = group_codes == group_code
        log_likelihood[selected] = interval_log_probability(
            lower[selected],
            upper[selected],
            float(mean),
            standard_deviation,
        )
        log_likelihood[selected] -= norm.logsf(
            (0.0 - float(mean)) / standard_deviation
        )
    if not np.isfinite(log_likelihood).all():
        raise ValueError("검증 표본의 로그우도가 유한하지 않습니다.")
    return float(log_likelihood.mean())


def sample_latent_values(
    lower: np.ndarray,
    upper: np.ndarray,
    mean: float,
    standard_deviation: float,
    random_generator: np.random.Generator,
) -> np.ndarray:
    return truncnorm.rvs(
        (lower - mean) / standard_deviation,
        (upper - mean) / standard_deviation,
        loc=mean,
        scale=standard_deviation,
        random_state=random_generator,
    )


def make_distribution_table(
    observations: pd.DataFrame,
    latent_values: np.ndarray,
    means: np.ndarray,
    standard_deviation: float,
    holdout_log_likelihood: float,
    holdout_count: int,
    record_counts: dict[str, int],
) -> pd.DataFrame:
    rows = []
    for group_code, (group_name, group) in enumerate(AGE_GROUPS.items()):
        selected = observations["age_group"].eq(group_name).to_numpy()
        observed = observations.loc[selected, "observed"]
        latent = latent_values[selected]
        mean = float(means[group_code])
        rows.append(
            {
                "age_group": group_name,
                "n": len(observed),
                **record_counts,
                "cutoff_41_n": int(observed.eq(group["cutoffs"][0]).sum()),
                "cutoff_52_n": int(observed.eq(group["cutoffs"][1]).sum()),
                "cutoff_62_n": int(observed.eq(group["cutoffs"][2]).sum()),
                "observed_mean": observed.mean(),
                "observed_sd": observed.std(ddof=1),
                "latent_model_mean": mean,
                "latent_model_sd": standard_deviation,
                "generated_latent_mean": float(np.mean(latent)),
                "generated_latent_sd": float(np.std(latent, ddof=1)),
                "generated_z_mean": float(np.mean((latent - mean) / standard_deviation)),
                "generated_z_sd": float(
                    np.std((latent - mean) / standard_deviation, ddof=1)
                ),
                "holdout_n": holdout_count,
                "holdout_mean_log_likelihood": holdout_log_likelihood,
                "random_seed": RANDOM_SEED,
                "status": "provisional_synthetic_indicator",
            }
        )
    return pd.DataFrame(rows)


def make_cutoff_diagnostics(
    observations: pd.DataFrame,
    means: np.ndarray,
    standard_deviation: float,
) -> pd.DataFrame:
    rows = []
    for group_code, (group_name, group) in enumerate(AGE_GROUPS.items()):
        observed = observations.loc[
            observations["age_group"].eq(group_name), "observed"
        ]
        mean = float(means[group_code])
        for cutoff_index, cutoff in enumerate(group["cutoffs"]):
            upper_bound = (
                group["cutoffs"][cutoff_index + 1]
                if cutoff_index + 1 < len(group["cutoffs"])
                else np.inf
            )
            interval_upper = (
                norm.cdf((upper_bound - mean) / standard_deviation)
                if np.isfinite(upper_bound)
                else 1.0
            )
            interval_lower = norm.cdf((cutoff - mean) / standard_deviation)
            truncation_constant = norm.cdf(mean / standard_deviation)
            rows.append(
                {
                    "age_group": group_name,
                    "cutoff": cutoff,
                    "observed_at_cutoff_n": int(observed.eq(cutoff).sum()),
                    "observed_at_cutoff_rate": float(observed.eq(cutoff).mean()),
                    "observed_one_below_n": int(observed.eq(cutoff - 1).sum()),
                    "observed_one_above_n": int(observed.eq(cutoff + 1).sum()),
                    "assumed_latent_interval_lower": cutoff,
                    "assumed_latent_interval_upper_exclusive": (
                        upper_bound if np.isfinite(upper_bound) else "infinity"
                    ),
                    "model_probability_in_assumed_interval": (
                        interval_upper - interval_lower
                    )
                    / truncation_constant,
                }
            )
    return pd.DataFrame(rows)


def save_distribution_plot(
    observations: pd.DataFrame,
    latent_values: np.ndarray,
    means: np.ndarray,
    standard_deviation: float,
) -> None:
    group_name = next(iter(AGE_GROUPS))
    group_data = observations.loc[observations["age_group"] == group_name]
    observed = group_data["observed"].to_numpy(dtype=float)
    mean = float(means[0])
    latent_z = (latent_values - mean) / standard_deviation
    x_min = 0.0
    x_max = max(float(observed.max()), float(latent_values.max()), mean + 4 * standard_deviation)
    x_values = np.linspace(x_min, x_max, 800)
    bin_edges = np.arange(-0.5, np.ceil(x_max) + 1.5)
    normalization = norm.sf((0.0 - mean) / standard_deviation)

    figure, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(
        observed,
        bins=bin_edges,
        density=True,
        alpha=0.4,
        label="관측 정수 횟수",
    )
    axes[0].hist(
        latent_values,
        bins=bin_edges,
        density=True,
        histtype="step",
        linewidth=1.8,
        label="구간 내 생성 잠재값 (가상)",
    )
    axes[0].plot(
        x_values,
        norm.pdf(x_values, loc=mean, scale=standard_deviation) / normalization,
        linewidth=2,
        label="절단 정규모형",
    )
    for cutoff in AGE_GROUPS[group_name]["cutoffs"]:
        axes[0].axvline(cutoff, linestyle="--", linewidth=1, label=f"컷오프 {cutoff}")
    axes[0].set_title(f"19~24세 셔틀런 원기록과 가상 잠재값 (n={len(observed):,})")
    axes[0].set_xlabel("20m 왕복 오래달리기 횟수")
    axes[0].set_ylabel("확률밀도")
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].legend(fontsize=8)

    axes[1].hist(
        latent_z,
        bins=40,
        density=True,
        alpha=0.4,
        label="가상 표준점수",
    )
    z_lower = max(-4.0, -mean / standard_deviation)
    z_values = np.linspace(z_lower, 4, 500)
    axes[1].plot(
        z_values,
        norm.pdf(z_values) / normalization,
        linewidth=2,
        label="비음수 절단 정규모형 참고곡선",
    )
    axes[1].set_title("가상 표준점수 분포 (모형 가정의 결과)")
    axes[1].set_xlabel("가상 심폐능력 표준점수 (z)")
    axes[1].set_ylabel("확률밀도")
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].legend(fontsize=8)

    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "shuttle_interval_distribution_provisional.png", dpi=160)
    plt.close(figure)


@safe_execution(error_message="셔틀런 그래프 생성 실패", error_type="error", reraise=True)
def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"입력 CSV를 찾을 수 없습니다: {INPUT_PATH}")

    data = load_csv_data(INPUT_PATH, keep_default_na=False, dtype=str)
    required_columns = {AGE_COLUMN, SHUTTLE_COLUMN}
    missing_columns = required_columns.difference(data.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(sorted(missing_columns))}")

    (
        observations,
        lower,
        upper,
        group_codes,
        record_counts,
        invalid_rows,
    ) = build_observations(data)
    random_generator = np.random.default_rng(RANDOM_SEED)
    row_count = len(observations)
    if row_count < 5:
        raise ValueError("홀드아웃 검증을 위해 유효 기록이 최소 5개 필요합니다.")

    permutation = random_generator.permutation(row_count)
    holdout_count = max(1, int(round(row_count * HOLDOUT_FRACTION)))
    train_indices = permutation[holdout_count:]
    holdout_indices = permutation[:holdout_count]
    train_means, train_standard_deviation = fit_interval_regression(
        observations.iloc[train_indices].reset_index(drop=True),
        lower[train_indices],
        upper[train_indices],
        group_codes[train_indices],
    )
    holdout_log_likelihood = mean_interval_log_likelihood(
        observations.iloc[holdout_indices].reset_index(drop=True),
        lower[holdout_indices],
        upper[holdout_indices],
        group_codes[holdout_indices],
        train_means,
        train_standard_deviation,
    )

    means, standard_deviation = fit_interval_regression(
        observations, lower, upper, group_codes
    )
    latent_values = sample_latent_values(
        lower,
        upper,
        float(means[0]),
        standard_deviation,
        random_generator,
    )
    latent_z = (latent_values - float(means[0])) / standard_deviation

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    invalid_path = OUTPUT_DIR / "shuttle_records_excluded_for_review.csv"
    invalid_rows.to_csv(invalid_path, index=False, encoding="utf-8-sig")
    result = data.loc[observations["source_index"].to_numpy()].copy().reset_index(drop=True)
    result["원본 행 인덱스"] = observations["source_index"].to_numpy()
    result["셔틀런 관측 횟수"] = observations["observed"].to_numpy()
    result["잠재 횟수 구간 하한"] = lower
    result["잠재 횟수 구간 상한(미포함)"] = upper
    result["가상 심폐능력 횟수"] = latent_values
    result["가상 심폐능력 표준점수"] = latent_z
    result["가상 지표 모형"] = "비음수 절단 정규분포; 컷오프 구간 검열; provisional"
    result["가상 지표 모형 평균"] = float(means[0])
    result["가상 지표 모형 표준편차"] = standard_deviation
    result["가상 지표 난수 시드"] = RANDOM_SEED
    result.to_csv(
        OUTPUT_DIR / "shuttle_latent_scores_provisional.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.4f",
    )

    summary = make_distribution_table(
        observations,
        latent_values,
        means,
        standard_deviation,
        holdout_log_likelihood,
        holdout_count,
        record_counts,
    )
    summary.to_csv(
        OUTPUT_DIR / "shuttle_interval_summary_provisional.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.4f",
    )
    make_cutoff_diagnostics(observations, means, standard_deviation).to_csv(
        OUTPUT_DIR / "shuttle_cutoff_diagnostics_provisional.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.6f",
    )
    save_distribution_plot(
        observations,
        latent_values,
        means,
        standard_deviation,
    )
    print(f"가상 점수(탐색용) 저장: {OUTPUT_DIR / 'shuttle_latent_scores_provisional.csv'}")
    print(f"분석 제외 원본 행 저장: {invalid_path}")
    print(f"모형 요약 저장: {OUTPUT_DIR / 'shuttle_interval_summary_provisional.csv'}")
    print(f"컷오프 진단 저장: {OUTPUT_DIR / 'shuttle_cutoff_diagnostics_provisional.csv'}")
    print(
        "분포 비교 그래프 저장: "
        f"{OUTPUT_DIR / 'shuttle_interval_distribution_provisional.png'}"
    )
    print(
        f"유효 정수 기록 {len(observations):,}건, "
        f"공란 {record_counts['blank_count']:,}건, "
        f"비숫자 {record_counts['non_numeric_count']:,}건, "
        f"음수 {record_counts['negative_count']:,}건, "
        f"비정수 {record_counts['non_integer_count']:,}건, "
        f"연령 대상 외 {record_counts['out_of_age_range_count']:,}건; "
        f"모형 평균={means[0]:.3f}, 표준편차={standard_deviation:.3f}, "
        f"홀드아웃 평균 로그우도={holdout_log_likelihood:.4f}"
    )


if __name__ == "__main__":
    main()
