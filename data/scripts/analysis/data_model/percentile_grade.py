"""체력 백분위 평균으로 1~4등급을 나눠 등급별 CSV와 등급별 인원 비율표를 저장합니다.

- 대상: passed.csv에서 같은 M_CODE의 파일상 첫 행만 남긴 개인별 데이터. 1·2등급 제외나 처방 필터는 쓰지 않고 전체 인원을 등급으로 나눕니다.
- 백분위: 종목마다 전체 인원 안에서 값이 클수록 높은 100분위(0~100, 클수록 양호)로 바꿉니다.
- 등급 기준은 CRITERIA에 둔 것만 계산합니다(지금은 근력·심폐지구력 백분위의 평균).
  근력·근지구력·심폐지구력(3items), 근력·근지구력·심폐지구력·유연성(4items) 기준도 주석을 풀면 같이 계산합니다.
- 등급(평균 백분위 기준): 1등급 상위 0~30%(평균 70 이상), 2등급 30~50%(50 이상 70 미만),
  3등급 50~70%(30 이상 50 미만), 4등급 70~100%(30 미만).
  GRADE_BASIS를 "rank"로 바꾸면 평균 백분위의 값이 아니라 "평균 백분위의 순위"로 상위 30·50·70%를 자릅니다(등급 비율이 30/20/20/30으로 고정).
- 군집 수 탐색: 등급별 CSV마다 군집 수 k=3~7에 대해 K-means와 계층적 군집화의 실루엣 계수를 구합니다.
  입력은 종목 4개의 100분위와 BMI·체지방률의 100분위(낮을수록 양호해 방향을 뒤집음) 6개입니다.
- 출력: 기준마다 1~4등급 CSV 4개, 전체 대비 각 등급 인원 비율표 1개, 등급별 CSV마다 실루엣 계수표 1개.
"""

import logging
from pathlib import Path

import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER, PASSED_FILENAME
from data.scripts.utils import write_csv

logger = logging.getLogger(__name__)

# 입력 컬럼
ID_COLUMN = "M_CODE"  # 개인 식별번호
PRESCRIPTION_COLUMN = "MVM_PRSCRPTN_CN"  # 운동처방 내용

# 체력 종목 -> 실제 측정 컬럼 (TODO: passed.csv의 컬럼 이름에 맞게 확인)
MEASURE_COLUMNS = {
    "STRENGTH": "REL_GRIP",  # 근력(상대악력)
    "ENDURANCE": "CROSS_UP",  # 근지구력
    "CARDIO": "CARDIO",  # 심폐지구력
    "FLEXIBILITY": "SIT_REACH",  # 유연성
}
EXERCISE_LABELS = {"STRENGTH": "근력", "ENDURANCE": "근지구력", "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성"}

# 낮을수록 양호한 신체 항목 -> 실제 측정 컬럼 (TODO: passed.csv의 컬럼 이름에 맞게 확인)
BODY_COLUMNS = {
    "BMI": "BMI",
    "BODY_FAT": "BODY_FAT_PERCENTAGE",
}

# 등급 기준: 키는 파일 이름에 쓰는 이름, 값은 (표시 이름, 평균을 낼 종목)
CRITERIA = {
    "2items": ("2종목(근력·심폐지구력)", ("STRENGTH", "CARDIO")),
    "3items": ("3종목(근력·근지구력·심폐지구력)", ("STRENGTH", "ENDURANCE", "CARDIO")),
    "4items": ("4종목(근력·근지구력·심폐지구력·유연성)", ("STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY")),
}

# 평균 백분위 값으로 등급을 나눌 때의 하한: 1등급 70 이상, 2등급 50 이상, 3등급 30 이상, 나머지 4등급
GRADE_SCORE_CUTS = (70.0, 50.0, 30.0)
# 순위로 나눌 때의 상위 비율(%) 상한: 1등급 상위 30%, 2등급 50%, 3등급 70%, 나머지 4등급
GRADE_RANK_CUTS = (30.0, 50.0, 70.0)
GRADES = (1, 2, 3, 4)
GRADE_BASIS = "score"  # "score": 평균 백분위 값 기준 / "rank": 평균 백분위 순위 기준

# 군집 수 탐색 설정
K_RANGE = range(3, 8)  # 군집 수 k = 3~7
KMEANS_N_INIT = 10
RANDOM_STATE = 42
HIERARCHICAL_LINKAGE = "ward"

# 이 단계에서 새로 만드는 컬럼
AVERAGE_PERCENTILE_COLUMN = "AVG_PERCENTILE"
GRADE_COLUMN = "GRADE"

# 출력 표의 컬럼 이름
CRITERIA_COLUMN = "등급 기준"
GRADE_LABEL_COLUMN = "등급"
K_COLUMN = "군집수k"
KMEANS_COLUMN = "K-means"
HIERARCHICAL_COLUMN = "계층적 군집화"


def percentile_column(exercise: str) -> str:
    """종목의 백분위 컬럼 이름입니다."""
    return f"{exercise}_PERCENTILE"


def load_individuals(path: Path) -> pd.DataFrame:
    """passed.csv를 읽어 같은 M_CODE의 파일상 첫 행만 남기고 체력 컬럼을 숫자로 바꿉니다.

    Raises:
        ValueError: 필요한 컬럼이 없을 때
    """
    # utf-8-sig: 헤더 앞의 BOM 제거
    df = pd.read_csv(path, encoding="utf-8-sig")
    required = [ID_COLUMN, PRESCRIPTION_COLUMN, *MEASURE_COLUMNS.values(), *BODY_COLUMNS.values()]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{path.name}에 필요한 컬럼이 없습니다: {', '.join(missing)}")

    df = df.drop_duplicates(subset=ID_COLUMN, keep="first").reset_index(drop=True)
    for column in (*MEASURE_COLUMNS.values(), *BODY_COLUMNS.values()):
        df[column] = pd.to_numeric(df[column], errors="coerce")  # 숫자가 아닌 값은 결측으로 둔다.
    return df


def cluster_feature_columns() -> list[str]:
    """군집 분석에 쓰는 100분위 컬럼 6개(종목 4개 + BMI·체지방률)의 이름입니다."""
    return [percentile_column(name) for name in (*MEASURE_COLUMNS, *BODY_COLUMNS)]


def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """종목마다 100분위(0~100, 클수록 양호)를 붙입니다. 결측은 결측으로 두고 나머지 인원 안에서 순위를 매깁니다.

    BMI·체지방률은 낮을수록 양호하므로 값이 작을수록 100분위가 커지게 방향을 뒤집습니다.
    """
    percentiles = {
        percentile_column(exercise): df[column].rank(pct=True) * 100
        for exercise, column in MEASURE_COLUMNS.items()
    }
    percentiles.update({
        percentile_column(name): df[column].rank(ascending=False, pct=True) * 100
        for name, column in BODY_COLUMNS.items()
    })
    return df.assign(**percentiles)


def assign_grades(average: pd.Series) -> pd.Series:
    """평균 백분위로 1~4등급을 나눕니다. 평균이 없는 행은 등급도 비워 둡니다.

    Raises:
        ValueError: GRADE_BASIS가 "score"나 "rank"가 아닐 때
    """
    if GRADE_BASIS == "score":
        high, middle, low = GRADE_SCORE_CUTS
        bins, labels, right = [-float("inf"), low, middle, high, float("inf")], [4, 3, 2, 1], False
        values = average
    elif GRADE_BASIS == "rank":
        # 평균 백분위가 높은 순서로 상위 몇 %인지를 구한다.
        top, second, third = GRADE_RANK_CUTS
        bins, labels, right = [0.0, top, second, third, 100.0], [1, 2, 3, 4], True
        values = average.rank(ascending=False, pct=True) * 100
    else:
        raise ValueError(f'GRADE_BASIS는 "score" 또는 "rank"여야 합니다: {GRADE_BASIS}')
    return pd.cut(values, bins=bins, labels=labels, right=right).astype("Int64")


def grade_by_criterion(df: pd.DataFrame, exercises: tuple[str, ...]) -> pd.DataFrame:
    """기준 종목들의 평균 백분위와 등급을 붙입니다. 기준 종목 중 하나라도 결측인 행은 등급을 매기지 않고 제외합니다."""
    columns = [percentile_column(exercise) for exercise in exercises]
    average = df[columns].mean(axis=1, skipna=False)
    graded = df.assign(**{AVERAGE_PERCENTILE_COLUMN: average.round(2)})
    graded = graded[average.notna()].copy()
    graded[GRADE_COLUMN] = assign_grades(average[average.notna()])
    return graded.reset_index(drop=True)


def build_ratio_table(graded_by_criterion: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """기준마다 등급별 인원, 전체 대비 비율(%), 처방이 있는 인원을 표로 만듭니다. 전체는 그 기준으로 등급을 매긴 인원입니다."""
    rows = []
    for key, graded in graded_by_criterion.items():
        total = len(graded)
        has_prescription = graded[PRESCRIPTION_COLUMN].fillna("").astype(str).str.strip().ne("")
        for grade in GRADES:
            in_grade = graded[GRADE_COLUMN].eq(grade)
            rows.append({
                CRITERIA_COLUMN: CRITERIA[key][0],
                GRADE_LABEL_COLUMN: f"{grade}등급",
                "인원": int(in_grade.sum()),
                "전체 대비 비율(%)": round(in_grade.sum() / total * 100, 2),
                "처방 있는 인원": int((in_grade & has_prescription).sum()),
                "전체 인원": total,
            })
    return pd.DataFrame(rows)


def build_silhouette_table(df: pd.DataFrame) -> pd.DataFrame:
    """등급별 데이터에서 군집 수 k마다 K-means와 계층적 군집화의 실루엣 계수를 구합니다.

    군집 입력은 종목 4개와 BMI·체지방률의 100분위 6개이고, 6개 중 하나라도 결측인 행은 제외합니다.
    군집 수가 (인원 - 1) 이상이면 실루엣 계수를 구할 수 없어 빈칸(결측)으로 둡니다.
    """
    features = df[cluster_feature_columns()].dropna()
    rows = []
    for k in K_RANGE:
        row = {K_COLUMN: k, KMEANS_COLUMN: float("nan"), HIERARCHICAL_COLUMN: float("nan")}
        if len(features) > k:
            kmeans_labels = KMeans(n_clusters=k, n_init=KMEANS_N_INIT, random_state=RANDOM_STATE).fit_predict(features)
            hierarchical_labels = AgglomerativeClustering(n_clusters=k, linkage=HIERARCHICAL_LINKAGE).fit_predict(features)
            row[KMEANS_COLUMN] = round(silhouette_score(features, kmeans_labels), 4)
            row[HIERARCHICAL_COLUMN] = round(silhouette_score(features, hierarchical_labels), 4)
        rows.append(row)
    return pd.DataFrame(rows)


def run(input_path: Path, output_dir: Path, ratio_output_path: Path) -> None:
    """input_path의 개인별 체력 데이터를 백분위 평균으로 1~4등급으로 나눠 저장합니다.

    Args:
        input_path: 체력 측정과 운동처방이 들어 있는 passed.csv
        output_dir: 등급별 CSV(기준 수 x 등급 4개)와 같은 수의 실루엣 계수표를 저장할 폴더
        ratio_output_path: 전체 대비 각 등급 인원 비율표 저장 경로

    Raises:
        ValueError: 필요한 컬럼이 없을 때
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ratio_output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. 개인별 첫 행만 남기고, 종목마다 100분위를 붙인다.
    df = add_percentiles(load_individuals(input_path))

    # 2. 기준마다 평균 백분위로 등급을 나눠 등급별 CSV를 저장하고, 각 CSV의 군집 수별 실루엣 계수표도 저장한다.
    graded_by_criterion = {}
    for key, (label, exercises) in CRITERIA.items():
        graded = grade_by_criterion(df, exercises)
        graded_by_criterion[key] = graded
        for grade in GRADES:
            in_grade = graded[graded[GRADE_COLUMN].eq(grade)].reset_index(drop=True)
            write_csv(in_grade, output_dir / f"grade{grade}_{key}.csv")
            silhouette = build_silhouette_table(in_grade)
            write_csv(silhouette, output_dir / f"grade{grade}_{key}_silhouette.csv")
            best = silhouette.loc[silhouette[KMEANS_COLUMN].idxmax()] if silhouette[KMEANS_COLUMN].notna().any() else None
            logger.info(
                "%s %d등급: %s명, K-means 실루엣 최대 %s",
                label, grade, f"{len(in_grade):,}",
                "(계산 불가)" if best is None else f"k={int(best[K_COLUMN])} ({best[KMEANS_COLUMN]})",
            )

    # 3. 전체 대비 각 등급 인원 비율표를 저장한다.
    ratio_table = build_ratio_table(graded_by_criterion)
    write_csv(ratio_table, ratio_output_path)

    # 4. 요약 로그
    logger.info("입력 %s: 개인별 %s명, 등급 기준 %s", display_path(input_path), f"{len(df):,}", GRADE_BASIS)
    for key, (label, _) in CRITERIA.items():
        part = ratio_table[ratio_table[CRITERIA_COLUMN].eq(label)]
        logger.info(
            "%s: 등급 대상 %s명 (결측 제외 %s명) | %s",
            label, f"{len(graded_by_criterion[key]):,}", f"{len(df) - len(graded_by_criterion[key]):,}",
            ", ".join(f"{row[GRADE_LABEL_COLUMN]} {row['인원']:,}명({row['전체 대비 비율(%)']}%)" for _, row in part.iterrows()),
        )
    logger.info("저장(등급별 CSV %d개, 실루엣 계수표 %d개): %s", len(CRITERIA) * len(GRADES), len(CRITERIA) * len(GRADES), display_path(output_dir))
    logger.info("저장(등급 인원 비율표): %s", display_path(ratio_output_path))


def main() -> None:
    """이 단계만 실행합니다. 출력 경로는 프로젝트에 맞게 고칩니다."""
    setup_logging(caller_name(__file__))
    output_dir = Path("data/scripts/analysis/data_model/percentile_grade")  # TODO: paths.py 상수로 교체
    run(
        INTERMEDIATE_ENLISTMENT_FILTER / PASSED_FILENAME,
        output_dir,
        output_dir / "GRADE_RATIO.csv",
    )


if __name__ == "__main__":
    main()