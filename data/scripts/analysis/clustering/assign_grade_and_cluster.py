"""학습된 K-means 모델로 측정마다 평균 백분위 등급과 군집을 정하고, 등급·군집별 유형명 표를 저장합니다.

모델은 Git에 넣어 둔 것을 그대로 씁니다(학습은 train_cluster_model.py).
측정 데이터(KS_NFA_PROCESSED)에는 컬럼을 붙이지 않고, MESURE_ID로 연결되는 별도 테이블을 만듭니다.

[입력] intermediate/clustering/grade_1.csv ~ grade_4.csv, CLUSTER_MODEL_DIR/k_means_grade_{등급}.joblib
[출력]
  processed/MEASUREMENT_CLASSIFICATION.csv : MESURE_ID, AVERAGE_PERCENTILE_GRADE, CLUSTER,
                                             {종목}_GRADE(체력 등급 0~3), {종목}_PERCENTILE(전체 측정 안 백분위) (측정마다 한 행)
  processed/FITNESS_TYPE.csv               : AVERAGE_PERCENTILE_GRADE, CLUSTER, TYPE_NAME,
                                             {종목}_RELATIVE(군집 중심의 종목별 상대 편차, 소수 둘째 자리) (등급·군집마다 한 행)
  processed/clustering/grade_{등급}_relative_profile.csv / .png : 군집별 상대 체력편차 표·히트맵

실행: python -m data.scripts.analysis.clustering.assign_grade_and_cluster
"""

import logging
from pathlib import Path

import joblib
from matplotlib import colormaps, font_manager
from matplotlib.figure import Figure
import pandas as pd

from data.scripts.analysis.clustering.cluster_features import (
    CLUSTER_COLUMN,
    GRADE_COLUMN,
    GRADES,
    ID_COLUMN,
    MEASURE_NAMES,
    build_gap_features,
    grade_file_path,
    load_graded_csv,
    model_path,
    percentile_column,
)
from data.scripts.analysis.clustering.train_cluster_model import EXERCISE_LABELS, relative_profile
from data.scripts.fitness_standards import fitness_grade
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    CLUSTER_MODEL_DIR,
    DEFINITION_FITNESS_TYPE,
    DEFINITION_MEASUREMENT_CLASSIFICATION,
    INTERMEDIATE_CLUSTERING,
    PROCESSED_FITNESS_TYPE_PATH,
    PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
)
from data.scripts.utils import write_by_definition

logger = logging.getLogger(__name__)

TYPE_NAME_COLUMN = "TYPE_NAME"
# 대시보드가 종목 등급·백분위를 다시 계산하지 않도록 측정별 분류 표에 함께 저장한다.
PERCENTILE_DECIMALS = 2  # 정의서 DECIMAL(5,2): 100.00까지 담음
RELATIVE_DECIMALS = 2  # FITNESS_TYPE의 상대 편차(정의서 DECIMAL(5,2))


def grade_column(name: str) -> str:
    """종목 이름의 체력 등급 컬럼 이름입니다(예: STRENGTH_GRADE)."""
    return f"{name}_GRADE"


def load_bundles(model_dir: Path) -> dict[int, dict]:
    """등급별 모델 번들을 모두 불러옵니다.

    Raises:
        FileNotFoundError: 모델 파일이 하나라도 없을 때
    """
    bundles = {}
    for grade in GRADES:
        path = model_path(model_dir, grade)
        if not path.exists():
            raise FileNotFoundError(f"모델 파일이 없습니다. train_cluster_model.py를 먼저 실행하세요: {path}")
        bundles[grade] = joblib.load(path)
    return bundles


def classify_grade(df: pd.DataFrame, grade: int, bundle: dict) -> pd.DataFrame:
    """한 등급의 측정에 군집 번호를 붙여 MESURE_ID, 평균 백분위 등급, 군집, 종목별 체력 등급·백분위를 돌려줍니다.

    종목 백분위가 하나라도 없어 편차를 만들 수 없는 측정은 군집이 비어 있습니다.
    """
    classified = pd.DataFrame({ID_COLUMN: df[ID_COLUMN], GRADE_COLUMN: grade}, index=df.index)
    for name in MEASURE_NAMES:
        classified[grade_column(name)] = fitness_grade(df[name], name)
        classified[percentile_column(name)] = df[percentile_column(name)].round(PERCENTILE_DECIMALS)
    features = build_gap_features(df)
    if not features.empty:
        labels = bundle["kmeans"].predict(features[bundle["feature_columns"]])
        classified = classified.join(pd.DataFrame({CLUSTER_COLUMN: labels}, index=features.index))
    else:
        classified[CLUSTER_COLUMN] = pd.NA
    return classified


def build_classifications(grade_dir: Path, bundles: dict[int, dict]) -> pd.DataFrame:
    """등급별 CSV 4개를 각 모델로 처리해 측정별 등급·군집 표 하나로 합칩니다(MESURE_ID 순).

    Raises:
        ValueError: 같은 MESURE_ID가 여러 등급 데이터에 있을 때
    """
    pieces = []
    for grade in GRADES:
        csv_path = grade_file_path(grade_dir, grade)
        df = load_graded_csv(csv_path)
        pieces.append(classify_grade(df, grade, bundles[grade]))
        logger.info("%d등급 (%s): 측정 %s건", grade, csv_path.name, f"{len(df):,}")

    classifications = pd.concat(pieces, ignore_index=True)
    duplicated = classifications[ID_COLUMN].duplicated(keep=False)
    if duplicated.any():
        raise ValueError(f"{ID_COLUMN}이 여러 등급에 중복된 측정이 {int(duplicated.sum()):,}행 있습니다.")

    classifications[ID_COLUMN] = classifications[ID_COLUMN].astype(int)
    classifications[GRADE_COLUMN] = classifications[GRADE_COLUMN].astype(int)
    classifications[CLUSTER_COLUMN] = classifications[CLUSTER_COLUMN].astype("Int64")
    return classifications.sort_values(ID_COLUMN, kind="stable").reset_index(drop=True)


def build_fitness_types(bundles: dict[int, dict]) -> pd.DataFrame:
    """실제 모델 중심에서 1·2등급은 최약점, 3·4등급은 최강점만 유형명에 반영합니다.

    동률이면 MEASURE_NAMES 순서의 첫 종목을 사용합니다.
    기존 모델 번들의 유형명과 무관하므로 재학습 없이 새 규칙을 적용합니다.
    """
    rows = []
    for grade in GRADES:
        bundle = bundles[grade]
        centers = pd.DataFrame(bundle['kmeans'].cluster_centers_, columns=bundle['feature_columns'])
        profiles = relative_profile(centers)
        # 저장하는 상대 편차는 군집별 체력편차 표(save_relative_profiles)와 같게 소수 둘째 자리로 반올림한다.
        rounded = profiles.round(RELATIVE_DECIMALS)
        for cluster, profile in profiles.iterrows():
            values = {name: profile[f'{name}_RELATIVE'] for name in MEASURE_NAMES}
            if grade in (1, 2):
                exercise = min(values, key=values.get)
                label = '약점형'
            else:
                exercise = max(values, key=values.get)
                label = '강점형'
            rows.append({
                GRADE_COLUMN: grade,
                CLUSTER_COLUMN: int(cluster),
                TYPE_NAME_COLUMN: f'유형{cluster}: {EXERCISE_LABELS[exercise]} {label}',
                **{f'{name}_RELATIVE': float(rounded.loc[cluster, f'{name}_RELATIVE']) for name in MEASURE_NAMES},
            })
    return pd.DataFrame(rows)


def save_relative_profiles(bundles: dict[int, dict], output_dir: Path) -> None:
    """모델 중심의 종목별 상대 편차를 등급별 CSV와 공통 색상 척도의 히트맵으로 저장합니다.

    종목 편차는 해당 종목 백분위에서 나머지 세 종목 백분위를 뺀 차이의 평균입니다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    fitness_types = build_fitness_types(bundles).set_index([GRADE_COLUMN, CLUSTER_COLUMN])
    profiles = {}
    for grade in GRADES:
        bundle = bundles[grade]
        # 저장용으로 반올림한 중심 대신 예측에 쓰는 실제 중심으로 계산합니다.
        centers = pd.DataFrame(bundle['kmeans'].cluster_centers_, columns=bundle['feature_columns'])
        profiles[grade] = relative_profile(centers)
    limit = max(1.0, max(float(profile.abs().to_numpy().max()) for profile in profiles.values()))
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    font_name = next((name for name in ['Malgun Gothic', 'NanumGothic', 'Noto Sans CJK KR']
                      if name in available_fonts), 'DejaVu Sans')
    font = font_manager.FontProperties(family=font_name)
    for grade, profile in profiles.items():
        table = profile.copy()
        table.insert(0, TYPE_NAME_COLUMN, [fitness_types.loc[(grade, cluster), TYPE_NAME_COLUMN]
                                         for cluster in table.index])
        table.index.name = CLUSTER_COLUMN
        table.insert(0, GRADE_COLUMN, grade)
        stem = output_dir / f'grade_{grade}_relative_profile'
        table.round(2).to_csv(stem.with_suffix('.csv'), encoding='utf-8-sig')
        figure = Figure(figsize=(7, 5.8), layout='constrained')
        axis = figure.subplots()
        values = profile.to_numpy()
        image = axis.imshow(values, cmap='coolwarm', vmin=-limit, vmax=limit, aspect='auto')
        axis.set_xticks(range(len(MEASURE_NAMES)), [EXERCISE_LABELS[name] for name in MEASURE_NAMES], fontproperties=font)
        axis.set_yticks(range(len(profile)), [f'군집 {cluster}' for cluster in profile.index], fontproperties=font)
        axis.set_title(f'{grade}등급 · 군집별 체력편차', fontproperties=font, pad=14)
        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                value = values[row, column]
                rgba = colormaps['coolwarm']((value + limit) / (2 * limit))
                luminance = sum(weight * channel for weight, channel in zip((.299, .587, .114), rgba[:3]))
                axis.text(column, row, f'{value:+.1f}', ha='center', va='center',
                          color='white' if luminance < .5 else '#172033')
        colorbar = figure.colorbar(image, ax=axis, shrink=.85)
        colorbar.set_label('다른 세 종목 대비 평균 백분위 차이 (%p)', fontproperties=font)
        figure.supxlabel('양수: 상대적 강점 · 음수: 상대적 약점', fontproperties=font, fontsize=10)
        figure.savefig(stem.with_suffix('.png'), dpi=160)
        logger.info('%d등급 군집별 체력편차 표·그림 저장: %s', grade, display_path(stem))


def run(
    grade_dir: Path,
    model_dir: Path,
    classification_definition_path: Path,
    fitness_type_definition_path: Path,
    classification_output_path: Path,
    fitness_type_output_path: Path,
) -> None:
    """측정별 등급·군집 표와 유형명 표를 정의서대로 저장합니다.

    군집을 정할 수 없는 측정(종목 백분위 결측)은 정의서상 비울 수 없으므로 빼고 경고로 남깁니다.
    """
    bundles = load_bundles(model_dir)
    classifications = build_classifications(grade_dir, bundles)
    unclustered = classifications[CLUSTER_COLUMN].isna()
    if unclustered.any():
        logger.warning("군집을 정할 수 없어 뺀 측정: %s건(종목 백분위 결측)", f"{int(unclustered.sum()):,}")
        classifications = classifications[~unclustered]

    write_by_definition(classifications, classification_definition_path, classification_output_path)
    fitness_types = write_by_definition(build_fitness_types(bundles), fitness_type_definition_path, fitness_type_output_path)

    logger.info("측정별 등급·군집 %s건 저장: %s", f"{len(classifications):,}", display_path(classification_output_path))
    logger.info("유형명 %s개 저장: %s", f"{len(fitness_types):,}", display_path(fitness_type_output_path))
    save_relative_profiles(bundles, fitness_type_output_path.parent / 'clustering')


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(
        INTERMEDIATE_CLUSTERING,
        CLUSTER_MODEL_DIR,
        DEFINITION_MEASUREMENT_CLASSIFICATION,
        DEFINITION_FITNESS_TYPE,
        PROCESSED_MEASUREMENT_CLASSIFICATION_PATH,
        PROCESSED_FITNESS_TYPE_PATH,
    )


if __name__ == "__main__":
    main()
