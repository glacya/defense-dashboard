from config import (
    CSV_DATA_DIR,
)
from dashboard.py.error_handlers import safe_execution
from dashboard.py.loader import (
    load_csv_data,
)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import log_ndtr
from scipy.stats import norm


DATA_DIR = CSV_DATA_DIR
INPUT_PATH = DATA_DIR / "FIT_outlier_removed.csv"
OUTPUT_DIR = DATA_DIR / "shuttle_interval_results"
AGE_COLUMN = "AGE_20_29"
SHUTTLE_COLUMN = "SHUTTLE_RUN_20M"
AGE_GROUPS = {
    "19-24": {"minimum_age": 19, "maximum_age": 24, "cutoffs": [41, 52, 62]},
    "25-29": {"minimum_age": 25, "maximum_age": 29, "cutoffs": [34, 44, 54]},
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


def build_observations(data: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    age = pd.to_numeric(data[AGE_COLUMN], errors="coerce")
    shuttle = pd.to_numeric(data[SHUTTLE_COLUMN], errors="coerce")
    frames = []

    for group_name, group in AGE_GROUPS.items():
        selected = age.between(group["minimum_age"], group["maximum_age"]) & shuttle.notna()
        group_data = pd.DataFrame(
            {
                "age_group": group_name,
                "observed": shuttle.loc[selected].astype(float),
            }
        )
        frames.append(group_data)

    observations = pd.concat(frames, ignore_index=True)
    if observations.empty or observations["age_group"].nunique() != len(AGE_GROUPS):
        raise ValueError("두 연령대에 모두 유효한 셔틀런 기록이 있어야 합니다.")

    lower = observations["observed"].to_numpy(copy=True)
    upper = lower.copy()
    for row_index, row in observations.iterrows():
        cutoffs = AGE_GROUPS[row["age_group"]]["cutoffs"]
        for cutoff_index, cutoff in enumerate(cutoffs):
            if np.isclose(row["observed"], cutoff):
                lower[row_index] = cutoff
                upper[row_index] = (
                    cutoffs[cutoff_index + 1]
                    if cutoff_index + 1 < len(cutoffs)
                    else np.inf
                )
                break

    group_codes = observations["age_group"].map(
        {group_name: code for code, group_name in enumerate(AGE_GROUPS)}
    ).to_numpy(dtype=int)
    return observations, lower, upper, group_codes


def fit_interval_regression(
    observations: pd.DataFrame,
    lower: np.ndarray,
    upper: np.ndarray,
    group_codes: np.ndarray,
) -> tuple[np.ndarray, float]:
    exact = np.isclose(lower, upper)
    initial_means = [
        observations.loc[observations["age_group"] == group_name, "observed"].mean()
        for group_name in AGE_GROUPS
    ]
    initial_standard_deviation = observations["observed"].std(ddof=1)

    def negative_log_likelihood(parameters: np.ndarray) -> float:
        means = parameters[: len(AGE_GROUPS)]
        standard_deviation = np.exp(parameters[-1])
        log_likelihood = np.empty(len(observations), dtype=float)

        for group_code, mean in enumerate(means):
            selected = group_codes == group_code
            selected_exact = selected & exact
            selected_interval = selected & ~exact
            log_likelihood[selected_exact] = norm.logpdf(
                lower[selected_exact], loc=mean, scale=standard_deviation
            )
            log_likelihood[selected_interval] = interval_log_probability(
                lower[selected_interval],
                upper[selected_interval],
                mean,
                standard_deviation,
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
        bounds=[(None, None)] * len(AGE_GROUPS) + [(-5, 5)],
    )
    if not result.success:
        raise RuntimeError(f"구간 회귀 추정에 실패했습니다: {result.message}")

    return result.x[: len(AGE_GROUPS)], float(np.exp(result.x[-1]))


def make_distribution_table(
    observations: pd.DataFrame,
    lower: np.ndarray,
    upper: np.ndarray,
    means: np.ndarray,
    standard_deviation: float,
) -> pd.DataFrame:
    interval_censored = ~np.isclose(lower, upper)
    rows = []

    for group_code, (group_name, group) in enumerate(AGE_GROUPS.items()):
        group_mask = observations["age_group"].eq(group_name).to_numpy()
        values = observations.loc[group_mask, "observed"]
        mean = float(means[group_code])
        model_quantiles = norm.ppf(
            [0.05, 0.25, 0.50, 0.75, 0.95], loc=mean, scale=standard_deviation
        )
        observed_quantiles = values.quantile([0.05, 0.25, 0.50, 0.75, 0.95])
        rows.append(
            {
                "age_group": group_name,
                "n": len(values),
                "interval_censored_n": int(interval_censored[group_mask].sum()),
                "observed_mean": values.mean(),
                "observed_sd": values.std(ddof=1),
                "observed_p05": observed_quantiles.loc[0.05],
                "observed_p25": observed_quantiles.loc[0.25],
                "observed_median": observed_quantiles.loc[0.50],
                "observed_p75": observed_quantiles.loc[0.75],
                "observed_p95": observed_quantiles.loc[0.95],
                "interval_model_mean": mean,
                "interval_model_sd": standard_deviation,
                "model_p05": model_quantiles[0],
                "model_p25": model_quantiles[1],
                "model_median": model_quantiles[2],
                "model_p75": model_quantiles[3],
                "model_p95": model_quantiles[4],
                "grade_3_cutoff": group["cutoffs"][0],
                "grade_2_cutoff": group["cutoffs"][1],
                "grade_1_cutoff": group["cutoffs"][2],
            }
        )

    return pd.DataFrame(rows)


def save_distribution_plot(
    observations: pd.DataFrame,
    means: np.ndarray,
    standard_deviation: float,
) -> None:
    figure, axes = plt.subplots(1, len(AGE_GROUPS), figsize=(13, 5), sharey=True)

    for group_code, (axis, (group_name, group)) in enumerate(
        zip(axes, AGE_GROUPS.items())
    ):
        values = observations.loc[
            observations["age_group"] == group_name, "observed"
        ].to_numpy()
        mean = means[group_code]
        x_min = min(float(values.min()), mean - 4 * standard_deviation)
        x_max = max(float(values.max()), mean + 4 * standard_deviation)
        x = np.linspace(x_min, x_max, 500)
        bins = np.arange(np.floor(values.min()) - 0.5, np.ceil(values.max()) + 1.5)

        axis.hist(values, bins=bins, density=True, alpha=0.35, label="Observed")
        axis.plot(
            x,
            norm.pdf(x, loc=mean, scale=standard_deviation),
            linewidth=2,
            label="Interval regression",
        )
        for cutoff, label in zip(group["cutoffs"], ["Grade 3", "Grade 2", "Grade 1"]):
            axis.axvline(cutoff, linestyle="--", linewidth=1, label=f"{label}: {cutoff}")

        axis.set_title(f"Age {group_name} (n={len(values):,})")
        axis.set_xlabel("20 m shuttle-run count")
        axis.grid(axis="y", alpha=0.2)
        axis.legend(fontsize=8)

    axes[0].set_ylabel("Density")
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "shuttle_interval_distribution.png", dpi=160)
    plt.close(figure)


@safe_execution(error_message="셔틀런 그래프 생성 실패", error_type="error", reraise=True)
def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"입력 CSV를 찾을 수 없습니다: {INPUT_PATH}")

    data = load_csv_data(INPUT_PATH)
    required_columns = {AGE_COLUMN, SHUTTLE_COLUMN}
    missing_columns = required_columns.difference(data.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(sorted(missing_columns))}")

    observations, lower, upper, group_codes = build_observations(data)
    means, standard_deviation = fit_interval_regression(
        observations, lower, upper, group_codes
    )
    summary = make_distribution_table(
        observations, lower, upper, means, standard_deviation
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(
        OUTPUT_DIR / "shuttle_interval_distribution.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.2f",
    )
    save_distribution_plot(observations, means, standard_deviation)
    print(f"분포표 저장: {OUTPUT_DIR / 'shuttle_interval_distribution.csv'}")
    print(f"비교 그래프 저장: {OUTPUT_DIR / 'shuttle_interval_distribution.png'}")


if __name__ == "__main__":
    main()