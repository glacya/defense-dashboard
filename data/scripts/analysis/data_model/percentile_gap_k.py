"""등급별 데이터에서 '종목 간 백분위 편차'를 입력으로 군집 분석(K-means, 계층적)을 합니다.

기존 percentile_grade 스크립트는 군집 입력으로 종목별 백분위(수준)를 썼습니다.
여기서는 종목끼리 뺀 편차(예: 근력 백분위 - 근지구력 백분위)를 입력으로 써서,
"얼마나 잘하는가"가 아니라 "어느 쪽이 상대적으로 강하고 약한가"(체력 프로필의 모양)로 묶습니다.

- 입력 특성: 종목 4개의 모든 쌍 편차 6개 (STRENGTH-ENDURANCE, STRENGTH-CARDIO, ...).
  INCLUDE_BODY_GAP=True이면 BMI·체지방률 백분위에서 종목 평균 백분위를 뺀 편차 2개를 더합니다.
- 편차는 모두 백분위 포인트 단위라 같은 척도입니다. 그래서 표준화는 하지 않습니다.
- 출력(기준 x 등급마다): 실루엣 계수표, 최적 k(K-means 실루엣 최대)의 군집 라벨 CSV, 군집 중심(편차 평균) 표.
- 주의: 종목 4개의 쌍 편차 6개는 서로 독립이 아니라 실질 차원이 3입니다. 같은 정보를 중복해서 반영하는 점을 감안하세요.

기존 스크립트를 data/scripts/analysis/data_model/percentile_grade.py로 가정하고 import합니다. 경로가 다르면 아래 import를 고치세요.
"""

import logging
from itertools import combinations
from pathlib import Path

import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score

from data.scripts.analysis.data_model.percentile_grade import (  # TODO: 실제 모듈 경로로 교체
    BODY_COLUMNS,
    CRITERIA,
    CRITERIA_COLUMN,
    GRADE_COLUMN,
    GRADES,
    HIERARCHICAL_COLUMN,
    HIERARCHICAL_LINKAGE,
    K_COLUMN,
    K_RANGE,
    KMEANS_COLUMN,
    KMEANS_N_INIT,
    MEASURE_COLUMNS,
    RANDOM_STATE,
    add_percentiles,
    grade_by_criterion,
    load_individuals,
    percentile_column,
)
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER, PASSED_FILENAME
from data.scripts.utils import write_csv

logger = logging.getLogger(__name__)

INCLUDE_BODY_GAP = False  # True: BMI·체지방률 백분위 - 종목 평균 백분위 편차 2개를 추가
CLUSTER_COLUMN = "CLUSTER"


def gap_column(a: str, b: str) -> str:
    """두 종목의 편차 컬럼 이름입니다. (a 백분위 - b 백분위)"""
    return f"{a}_MINUS_{b}"


def gap_feature_columns() -> list[str]:
    """군집 입력으로 쓰는 편차 컬럼 이름 목록입니다."""
    columns = [gap_column(a, b) for a, b in combinations(MEASURE_COLUMNS, 2)]
    if INCLUDE_BODY_GAP:
        columns += [gap_column(name, "EXERCISE_MEAN") for name in BODY_COLUMNS]
    return columns


def add_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """백분위가 붙은 데이터에 종목 간 편차 컬럼을 붙입니다."""
    gaps = {
        gap_column(a, b): df[percentile_column(a)] - df[percentile_column(b)]
        for a, b in combinations(MEASURE_COLUMNS, 2)
    }
    if INCLUDE_BODY_GAP:
        exercise_mean = df[[percentile_column(e) for e in MEASURE_COLUMNS]].mean(axis=1, skipna=False)
        gaps.update({
            gap_column(name, "EXERCISE_MEAN"): df[percentile_column(name)] - exercise_mean
            for name in BODY_COLUMNS
        })
    return df.assign(**{name: values.round(2) for name, values in gaps.items()})


def build_silhouette_table(features: pd.DataFrame) -> pd.DataFrame:
    """군집 수 k마다 K-means와 계층적 군집화의 실루엣 계수를 구합니다. 인원이 k 이하면 결측으로 둡니다."""
    rows = []
    for k in K_RANGE:
        row = {K_COLUMN: k, KMEANS_COLUMN: float("nan"), HIERARCHICAL_COLUMN: float("nan")}
        if len(features) > k:
            km = KMeans(n_clusters=k, n_init=KMEANS_N_INIT, random_state=RANDOM_STATE).fit_predict(features)
            hc = AgglomerativeClustering(n_clusters=k, linkage=HIERARCHICAL_LINKAGE).fit_predict(features)
            row[KMEANS_COLUMN] = round(silhouette_score(features, km), 4)
            row[HIERARCHICAL_COLUMN] = round(silhouette_score(features, hc), 4)
        rows.append(row)
    return pd.DataFrame(rows)


def label_and_profile(df: pd.DataFrame, features: pd.DataFrame, k: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """K-means(k)로 군집 라벨을 붙인 데이터와, 군집별 인원·편차 평균(군집 중심) 표를 돌려줍니다."""
    labels = KMeans(n_clusters=k, n_init=KMEANS_N_INIT, random_state=RANDOM_STATE).fit_predict(features)
    labeled = df.loc[features.index].assign(**{CLUSTER_COLUMN: labels})
    profile = labeled.groupby(CLUSTER_COLUMN)[gap_feature_columns()].mean().round(2)
    profile.insert(0, "인원", labeled.groupby(CLUSTER_COLUMN).size())
    return labeled.reset_index(drop=True), profile.reset_index()


def run(input_path: Path, output_dir: Path) -> None:
    """입력 데이터를 기준·등급별로 나눠, 편차 입력 군집 결과를 output_dir에 저장합니다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    df = add_gaps(add_percentiles(load_individuals(input_path)))

    summary = []
    for key, (label, exercises) in CRITERIA.items():
        graded = grade_by_criterion(df, exercises)
        for grade in GRADES:
            in_grade = graded[graded[GRADE_COLUMN].eq(grade)].reset_index(drop=True)
            features = in_grade[gap_feature_columns()].dropna()  # 편차 중 하나라도 결측이면 제외
            silhouette = build_silhouette_table(features)
            write_csv(silhouette, output_dir / f"grade{grade}_{key}_gap_silhouette.csv")

            if silhouette[KMEANS_COLUMN].notna().any():
                best_k = int(silhouette.loc[silhouette[KMEANS_COLUMN].idxmax(), K_COLUMN])
                best_score = float(silhouette[KMEANS_COLUMN].max())
                labeled, profile = label_and_profile(in_grade, features, best_k)
                write_csv(labeled, output_dir / f"grade{grade}_{key}_gap_k{best_k}.csv")
                write_csv(profile, output_dir / f"grade{grade}_{key}_gap_k{best_k}_profile.csv")
            else:
                best_k, best_score = None, float("nan")
            summary.append({
                CRITERIA_COLUMN: label, "등급": f"{grade}등급", "군집 대상 인원": len(features),
                "최적 k(K-means)": best_k, "실루엣": best_score,
            })
            logger.info("%s %d등급: %s명, 최적 k=%s (실루엣 %s)", label, grade, f"{len(features):,}", best_k, round(best_score, 4))

    write_csv(pd.DataFrame(summary), output_dir / "GAP_SUMMARY.csv")
    logger.info("저장: %s", display_path(output_dir))


def main() -> None:
    setup_logging(caller_name(__file__))
    run(
        INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME,
        Path("data/scripts/analysis/data_model/percentile_gap_cluster"),  # TODO: paths.py 상수로 교체
    )


if __name__ == "__main__":
    main()