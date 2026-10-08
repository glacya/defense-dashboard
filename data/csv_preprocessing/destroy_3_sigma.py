
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
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages

SHUTTLE_RUN_20M = "20M_RUN"

FILE_NAME = "KS_NFA_TOTAL_CARDIO_DEDUPED"
DATA_DIR = CSV_DATA_DIR
FIT_PATH = DATA_DIR / f"{FILE_NAME}.csv"
CLEAN_PATH = DATA_DIR / f"{FILE_NAME}_outlier_removed.csv"
OUTLIER_PATH = DATA_DIR / f"{FILE_NAME}_destroy_outlier.csv"
REPORT_PATH = DATA_DIR / f"{FILE_NAME}_outlier_distribution.pdf"
EXCLUDED_COLUMNS = {"YEAR_MONTH", "PERSON_CODE"}
# None이면 사용 가능한 모든 숫자형 속성에 적용합니다. 일부만 적용하려면 컬럼명을 지정하세요.
THREE_SIGMA_COLUMNS: tuple[str, ...] | None = None
AVAILABLE_FONTS = {font.name for font in font_manager.fontManager.ttflist}
for korean_font in ("Malgun Gothic", "NanumGothic", "Gulim", "Noto Sans CJK KR"):
    if korean_font in AVAILABLE_FONTS:
        plt.rcParams["font.family"] = korean_font
        break
plt.rcParams["axes.unicode_minus"] = False
FILTER_RULE = (
    f"선택한 속성 중 하나라도 평균 ± 3표준편차 범위를 벗어나거나 "
    f"{SHUTTLE_RUN_20M}=0이면 제외"
)


def save_distribution_report(
    numeric_df: pd.DataFrame,
    numeric_columns: list[str],
    removed_by_column: dict[str, pd.Series],
    three_sigma_columns: list[str],
) -> None:
    """속성별 분포와 해당 속성의 제외 구간을 PDF로 저장합니다."""
    plotted_columns = 0
    with PdfPages(REPORT_PATH) as pdf:
        for column in numeric_columns:
            values = numeric_df[column].dropna()
            if len(values) < 2:
                continue

            removed_mask = removed_by_column[column].loc[values.index]
            observations = values.to_numpy(dtype=float)
            removed_values = values.loc[removed_mask].to_numpy(dtype=float)
            mean = float(values.mean())
            standard_deviation = float(values.std())
            applies_three_sigma = column in three_sigma_columns
            bin_edges = np.histogram_bin_edges(observations, bins="auto")
            bin_widths = np.diff(bin_edges)
            total_density = np.histogram(observations, bins=bin_edges)[0] / (
                len(observations) * bin_widths
            )
            removed_density = np.histogram(removed_values, bins=bin_edges)[0] / (
                len(observations) * bin_widths
            )

            figure, axis = plt.subplots(figsize=(10, 6))
            axis.stairs(
                total_density,
                bin_edges,
                fill=True,
                alpha=0.35,
                label="전체 데이터",
            )
            axis.stairs(
                removed_density,
                bin_edges,
                fill=True,
                alpha=0.7,
                color="tab:red",
                label="이 속성에서 제외된 데이터",
            )

            lower_bound = mean - 3 * standard_deviation
            upper_bound = mean + 3 * standard_deviation
            if standard_deviation > 0:
                x_values = np.linspace(bin_edges[0], bin_edges[-1], 500)
                normal_density = np.exp(
                    -0.5 * ((x_values - mean) / standard_deviation) ** 2
                ) / (standard_deviation * np.sqrt(2 * np.pi))
                axis.plot(
                    x_values,
                    normal_density,
                    color="black",
                    linewidth=2,
                    label="정규분포 참고 곡선",
                )
                if applies_three_sigma:
                    axis.axvline(
                        lower_bound,
                        color="tab:orange",
                        linestyle="--",
                        label="-3σ / +3σ 기준",
                    )
                    axis.axvline(upper_bound, color="tab:orange", linestyle="--")
            elif applies_three_sigma:
                axis.axvline(
                    mean,
                    color="tab:orange",
                    linestyle="--",
                    label="표준편차 0 (제외 기준선)",
                )

            if column == SHUTTLE_RUN_20M:
                axis.axvline(
                    0,
                    color="tab:purple",
                    linestyle=":",
                    label="왕복 오래달리기 0 기록 제외 기준",
                )

            removed_count = int(removed_mask.sum())
            removed_rate = removed_count / len(values) * 100
            stats_text = (
                f"평균: {mean:.2f}\n표준편차: {standard_deviation:.2f}"
            )
            if applies_three_sigma:
                stats_text += f"\n±3σ 범위: [{lower_bound:.2f}, {upper_bound:.2f}]"
            stats_text += (
                f"\n이 속성 제외: {removed_count:,}개 ({removed_rate:.2f}%)"
            )
            axis.set_title(f"{column} 분포 및 제외 데이터")
            axis.set_xlabel(column)
            axis.set_ylabel("확률밀도")
            axis.text(
                0.99,
                0.97,
                stats_text,
                transform=axis.transAxes,
                ha="right",
                va="top",
                bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "gray"},
            )
            axis.legend()
            figure.tight_layout()
            pdf.savefig(figure)
            plt.close(figure)
            plotted_columns += 1

    if plotted_columns == 0:
        raise ValueError("분포 보고서에 표시할 숫자형 속성이 없습니다.")


@safe_execution(error_message="이상치 제거 실패", error_type="error", reraise=True)
def main():
    if not FIT_PATH.exists():
        raise FileNotFoundError(f"{FILE_NAME} 파일을 찾을 수 없습니다: {FIT_PATH}")

    df = load_csv_data(FIT_PATH, keep_default_na=False)
    candidate_columns = [
        column for column in df.columns if column not in EXCLUDED_COLUMNS
    ]
    numeric_df = df[candidate_columns].apply(pd.to_numeric, errors="coerce")
    available_numeric_columns = [
        column for column in candidate_columns if numeric_df[column].notna().sum() >= 2
    ]
    if THREE_SIGMA_COLUMNS is None:
        selected_columns = available_numeric_columns
    else:
        missing_columns = [
            column for column in THREE_SIGMA_COLUMNS if column not in candidate_columns
        ]
        non_numeric_columns = [
            column
            for column in THREE_SIGMA_COLUMNS
            if column in candidate_columns
            and column not in available_numeric_columns
        ]
        if missing_columns or non_numeric_columns:
            invalid_columns = [*missing_columns, *non_numeric_columns]
            raise ValueError(
                f"3-sigma 적용 컬럼을 찾을 수 없거나 숫자형 값이 부족합니다: "
                f"{', '.join(invalid_columns)}"
            )
        selected_columns = list(dict.fromkeys(THREE_SIGMA_COLUMNS))

    report_columns = list(selected_columns)
    if (
        SHUTTLE_RUN_20M in available_numeric_columns
        and SHUTTLE_RUN_20M not in report_columns
    ):
        report_columns.append(SHUTTLE_RUN_20M)

    outlier_rows = pd.Series(False, index=df.index)
    outlier_reasons = {index: [] for index in df.index}
    removed_by_column = {}

    for column in report_columns:
        values = numeric_df[column]
        column_removed = pd.Series(False, index=df.index)
        if column in selected_columns and values.notna().sum() >= 2:
            mean = values.mean()
            standard_deviation = values.std()
            lower_bound = mean - 3 * standard_deviation
            upper_bound = mean + 3 * standard_deviation
            below_lower_bound = values.notna() & (values < lower_bound)
            above_upper_bound = values.notna() & (values > upper_bound)
            column_removed |= below_lower_bound | above_upper_bound

            for index in values.index[below_lower_bound]:
                outlier_reasons[index].append(
                    f"{column}={values.at[index]:.2f}가 하한 {lower_bound:.2f} 미만 "
                    f"(평균={mean:.2f}, 표준편차={standard_deviation:.2f})"
                )
            for index in values.index[above_upper_bound]:
                outlier_reasons[index].append(
                    f"{column}={values.at[index]:.2f}가 상한 {upper_bound:.2f} 초과 "
                    f"(평균={mean:.2f}, 표준편차={standard_deviation:.2f})"
                )

        if column == SHUTTLE_RUN_20M:
            column_removed |= values.eq(0)
        removed_by_column[column] = column_removed
        outlier_rows |= column_removed

    shuttle_zero_rows = numeric_df[SHUTTLE_RUN_20M].eq(0)
    outlier_rows |= shuttle_zero_rows
    for index in numeric_df.index[shuttle_zero_rows]:
        outlier_reasons[index].append(
            "SHUTTLE_RUN_20M=0이므로 제외 (허용 기준: 0 초과)"
        )

    save_distribution_report(
        numeric_df,
        report_columns,
        removed_by_column,
        selected_columns,
    )

    clean_df = df.loc[~outlier_rows].copy()
    applied_rule = f"{FILTER_RULE}: {', '.join(selected_columns)}"
    clean_df["OUTLIER_FILTER_RULE"] = applied_rule
    clean_df.to_csv(CLEAN_PATH, index=False, encoding="utf-8-sig")

    outlier_df = df.loc[outlier_rows].copy()
    outlier_df["OUTLIER_REASON"] = outlier_rows[outlier_rows].index.map(
        lambda index: "; ".join(outlier_reasons[index])
    )
    outlier_df.to_csv(OUTLIER_PATH, index=False, encoding="utf-8-sig")
    print(f"3-sigma 적용 컬럼: {', '.join(selected_columns)}")
    print(f"속성별 분포 보고서 저장 완료: {REPORT_PATH}")


if __name__ == "__main__":
    main()