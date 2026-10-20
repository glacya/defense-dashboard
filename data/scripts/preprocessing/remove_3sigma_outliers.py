"""숫자형 속성마다 평균 ± 3표준편차를 벗어난 행과 20m 왕복 오래달리기 기록이 0인 행을 제거합니다.

통과 행과 제거 행(사유 포함)을 나눠 저장하고, 속성별 분포와 제거 구간을 PDF 보고서로 남깁니다.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages

from dashboard.py.loader import load_csv_data
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_3SIGMA, INTERMEDIATE_BASIC_REFINEMENT, PASSED_FILENAME

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 파일 이름
REMOVED_FILENAME = "removed.csv"
REPORT_FILENAME = "report.pdf"

SHUTTLE_RUN_20M = "20M_RUN"

EXCLUDED_COLUMNS = {"YEAR_MONTH", "PERSON_CODE", "MESURE_DE"}
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
    report_path: Path,
) -> None:
    """속성별 분포와 해당 속성의 제외 구간을 PDF로 저장합니다."""
    plotted_columns = 0
    with PdfPages(report_path) as pdf:
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


def run(input_path: Path, output_dir: Path) -> None:
    """input_path에서 3σ 이상치를 제거해 output_dir에 통과 행(passed.csv), 제거 행(removed.csv), 분포 보고서(report.pdf)를 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_path = output_dir / PASSED_FILENAME
    outlier_path = output_dir / REMOVED_FILENAME
    report_path = output_dir / REPORT_FILENAME
    # 2. 입력 로드 후 숫자형 컬럼을 고른다 (숫자 값이 2개 이상인 컬럼, EXCLUDED_COLUMNS 제외).
    #    EXCLUDED_COLUMNS의 이름(YEAR_MONTH 등)은 현재 통합 데이터 컬럼과 맞지 않아,
    #    측정일 MESURE_DE(YYYYMMDD)도 숫자형으로 3σ 검사를 받는다.
    df = load_csv_data(input_path, keep_default_na=False)
    candidate_columns = [
        column for column in df.columns if column not in EXCLUDED_COLUMNS
    ]
    numeric_df = df[candidate_columns].apply(pd.to_numeric, errors="coerce")
    available_numeric_columns = [
        column for column in candidate_columns if numeric_df[column].notna().sum() >= 2
    ]
    # 3. 3σ를 적용할 컬럼을 정한다. THREE_SIGMA_COLUMNS가 None이면 숫자형 컬럼 전부에 적용한다.
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

    # 4. 보고서에 그릴 컬럼을 정한다. 20M_RUN=0 제외 기준을 보여주기 위해 20M_RUN은 3σ 대상이 아니어도 포함한다.
    report_columns = list(selected_columns)
    if (
        SHUTTLE_RUN_20M in available_numeric_columns
        and SHUTTLE_RUN_20M not in report_columns
    ):
        report_columns.append(SHUTTLE_RUN_20M)

    # 5. 컬럼마다 평균 ± 3표준편차 밖의 값을 표시하고, 행별 제외 사유를 기록한다.
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

    # 6. 20M_RUN 기록이 0인 행도 제외한다 (허용 기준: 0 초과).
    shuttle_zero_rows = numeric_df[SHUTTLE_RUN_20M].eq(0)
    outlier_rows |= shuttle_zero_rows
    for index in numeric_df.index[shuttle_zero_rows]:
        outlier_reasons[index].append(
            "SHUTTLE_RUN_20M=0이므로 제외 (허용 기준: 0 초과)"
        )

    # 7. 속성별 분포와 제외 구간을 PDF 보고서로 저장한다.
    save_distribution_report(
        numeric_df,
        report_columns,
        removed_by_column,
        selected_columns,
        report_path,
    )

    # 8. 통과 행(적용 규칙 컬럼 추가)과 제외 행(사유 컬럼 추가)을 저장한다.
    clean_df = df.loc[~outlier_rows].copy()
    applied_rule = f"{FILTER_RULE}: {', '.join(selected_columns)}"
    clean_df["OUTLIER_FILTER_RULE"] = applied_rule
    clean_df.to_csv(clean_path, index=False, encoding="utf-8-sig")

    outlier_df = df.loc[outlier_rows].copy()
    outlier_df["OUTLIER_REASON"] = outlier_rows[outlier_rows].index.map(
        lambda index: "; ".join(outlier_reasons[index])
    )
    outlier_df.to_csv(outlier_path, index=False, encoding="utf-8-sig")

    # 9. 요약 로그
    logger.info("3-sigma 적용 컬럼: %s", ", ".join(selected_columns))
    logger.info("속성별 제외 행 수 (한 행이 여러 속성에서 제외될 수 있음):")
    for column, removed in removed_by_column.items():
        logger.info("  %s: %s행", column, f"{int(removed.sum()):,}")
    logger.info(
        "입력 %s: %s행 -> 통과 %s행, 제외 %s행 (%s=0 포함 %s행)",
        display_path(input_path), f"{len(df):,}", f"{len(clean_df):,}", f"{len(outlier_df):,}",
        SHUTTLE_RUN_20M, f"{int(shuttle_zero_rows.sum()):,}",
    )
    logger.info("저장(통과): %s", display_path(clean_path))
    logger.info("저장(제외): %s", display_path(outlier_path))
    logger.info("저장(분포 보고서): %s", display_path(report_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_BASIC_REFINEMENT / PASSED_FILENAME, INTERMEDIATE_3SIGMA)


if __name__ == "__main__":
    main()
