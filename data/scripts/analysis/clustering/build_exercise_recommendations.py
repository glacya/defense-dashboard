"""체력 유형(평균 백분위 등급 × 군집)마다 추천 운동 8개를 정하고, 운동 분류·사용 부위와 함께 저장합니다.

체력 요소·동작 난이도·장비·사용 부위는 처방 상세정보 중 일부를 사람이 직접 분류한 것(RULES)입니다.
원본의 전체 운동을 자동 분류하지 않습니다. 상대 편차는 보완 우선순위일 뿐, 절대 미달이나 개인별 운동 적합성을 뜻하지 않습니다.

선택 규칙
- 유형명이 "○○ 약점형"(1·2등급)이면 그 요소 운동 8개.
- "○○ 강점형"(3·4등급)이면 강점 요소를 빼고 상대 편차가 낮은 요소부터 4/2/2개.
- 등급별 목표 난이도(1등급 3, 2등급 2, 3·4등급 1)에 가까운 운동을 우선하고, 같으면 처방번호 순. 같은 이름 운동은 한 번만.

[입력] processed/FITNESS_TYPE.csv(유형명·상대 편차), processed/KS_NFA_PRESCRIPTION_DETAIL.csv(처방 이름)
[출력]
  processed/EXERCISE_CLASSIFICATION.csv : 분류한 운동마다 체력 요소·난이도·장비
  processed/EXERCISE_BODY_PART.csv      : 운동별 사용 부위(부상 부위와 같은 이름)
  processed/RECOMMENDED_EXERCISE.csv    : 유형별 추천 순위 1~8의 처방번호
화면 문장(운동 지침·추천 근거)은 저장하지 않고 training_guidance()·recommendation_basis()로 만듭니다(대시보드가 사용).

실행: python -m data.scripts.analysis.clustering.build_exercise_recommendations
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.analysis.clustering.cluster_features import CLUSTER_COLUMN, GRADE_COLUMN, GRADES
from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_EXERCISE_BODY_PART,
    DEFINITION_EXERCISE_CLASSIFICATION,
    DEFINITION_RECOMMENDED_EXERCISE,
    PROCESSED_EXERCISE_BODY_PART_PATH,
    PROCESSED_EXERCISE_CLASSIFICATION_PATH,
    PROCESSED_FITNESS_TYPE_PATH,
    PROCESSED_PRESCRIPTION_DETAIL_PATH,
    PROCESSED_RECOMMENDED_EXERCISE_PATH,
)
from data.scripts.synthesis.generate_synthetic_injuries import LOCATION_NAMES
from data.scripts.utils import require_columns, write_by_definition

logger = logging.getLogger(__name__)

ID_COLUMN = "PRESCRIPTION_TYPE_ID"
NAME_COLUMN = "PRESCRIPTION"
TYPE_NAME_COLUMN = "TYPE_NAME"
FOCUS_COLUMN = "IMPROVEMENT_FOCUS"
DIFFICULTY_COLUMN = "EXERCISE_DIFFICULTY"
EQUIPMENT_COLUMN = "REQUIRED_EQUIPMENT"
BODY_PART_COLUMN = "BODY_PART"
RANK_COLUMN = "RECOMMENDATION_RANK"

# 체력 요소(한글) -> 측정 종목 코드. FITNESS_TYPE의 상대 편차 컬럼은 {코드}_RELATIVE.
FOCUSES = {"근력": "STRENGTH", "근지구력": "ENDURANCE", "심폐지구력": "CARDIO", "유연성": "FLEXIBILITY"}
WEAK_SUFFIX, STRONG_SUFFIX = "약점형", "강점형"
RECOMMENDATION_COUNT = 8
STRONG_QUOTAS = (4, 2, 2)  # 강점형: 강점 요소를 뺀 세 요소에 상대 편차가 낮은 순으로 배분
TARGET_DIFFICULTY = {1: 3, 2: 2, 3: 1, 4: 1}  # 등급별 목표 동작 난이도(1=기초, 2=일반, 3=도전)
SOURCE_URL = "https://nfa.kspo.or.kr/"

# 처방번호, 체력 요소, 동작 난이도, 장비, 사용 부위(부상 부위 코드, LOCATION_NAMES의 키).
# 분류가 확정된 후보만 추천합니다.
RULES = [
    (179, '근력', 1, '벽', 'Shoulder|Arm|Elbow|Wrist'),
    (470, '근력', 1, '없음', 'Shoulder|Arm|Elbow|Wrist'),
    (9, '근력', 1, '없음', 'Hip|Leg upper|Knee|Ankle'),
    (14, '근력', 1, '없음', 'Back lower|Pelvic region|Hip|Leg upper'),
    (24, '근력', 1, '없음', 'Leg lower|Ankle|Foot/toe'),
    (15, '근력', 2, '없음', 'Shoulder|Arm|Elbow|Wrist|Hand/finger'),
    (10, '근력', 2, '없음', 'Hip|Leg upper|Knee|Ankle'),
    (117, '근력', 2, '덤벨 또는 저항 도구', 'Arm|Elbow|Forearm'),
    (180, '근력', 3, '덤벨', 'Hip|Leg upper|Knee|Ankle'),
    (5, '근력', 3, '철봉', 'Shoulder|Arm|Elbow|Forearm|Hand/finger'),
    (12, '근지구력', 2, '없음', 'Shoulder|Elbow|Back lower|Pelvic region'),
    (20, '근지구력', 2, '없음', 'Shoulder|Elbow|Back lower|Hip'),
    (22, '근지구력', 1, '없음', 'Shoulder|Wrist|Back lower|Hip|Knee'),
    (124, '근지구력', 1, '없음', 'Back lower|Pelvic region'),
    (79, '근지구력', 1, '없음', 'Back lower|Pelvic region'),
    (21, '근지구력', 2, '없음', 'Back lower|Pelvic region|Hip'),
    (140, '근지구력', 2, '없음', 'Back lower|Pelvic region|Hip'),
    (131, '근지구력', 3, '없음', 'Back lower|Pelvic region|Hip'),
    (156, '근지구력', 3, '없음', 'Back lower|Pelvic region|Hip'),
    (135, '근지구력', 3, '없음', 'Shoulder|Wrist|Hip|Knee'),
    (192, '심폐지구력', 1, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (262, '심폐지구력', 1, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (38, '심폐지구력', 1, '실내 자전거', 'Hip|Leg upper|Knee|Leg lower|Ankle'),
    (43, '심폐지구력', 1, '트레드밀', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (101, '심폐지구력', 2, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (39, '심폐지구력', 2, '계단', 'Hip|Leg upper|Knee|Leg lower|Ankle'),
    (17, '심폐지구력', 2, '없음', 'Shoulder|Hip|Leg upper|Knee|Leg lower|Ankle'),
    (37, '심폐지구력', 3, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (44, '심폐지구력', 3, '줄넘기', 'Shoulder|Wrist|Knee|Leg lower|Ankle|Foot/toe'),
    (325, '심폐지구력', 3, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (68, '유연성', 1, '없음', 'Hip|Leg upper|Knee'),
    (70, '유연성', 1, '없음', 'Hip|Leg upper|Knee'),
    (181, '유연성', 1, '없음', 'Leg lower|Ankle'),
    (347, '유연성', 1, '없음', 'Shoulder|Arm'),
    (69, '유연성', 1, '없음', 'Pelvic region|Hip'),
    (100, '유연성', 1, '없음', 'Elbow|Forearm|Wrist'),
    (53, '유연성', 2, '없음', 'Hip|Leg upper'),
    (81, '유연성', 2, '없음', 'Back lower|Pelvic region'),
    (98, '유연성', 2, '없음', 'Shoulder|Back lower'),
    (99, '유연성', 2, '없음', 'Shoulder|Arm'),
]


def relative_column(focus: str) -> str:
    """체력 요소의 상대 편차 컬럼 이름입니다(예: 근력 -> STRENGTH_RELATIVE)."""
    return f"{FOCUSES[focus]}_RELATIVE"


def type_focus(type_name: str) -> tuple[str, bool]:
    """유형명에서 (체력 요소, 약점형 여부)를 읽습니다(예: '유형0: 근력 약점형' -> ('근력', True)).

    Raises:
        ValueError: '○○ 약점형'·'○○ 강점형' 형식이 아닐 때
    """
    matches = [(focus, suffix == WEAK_SUFFIX) for focus in FOCUSES for suffix in (WEAK_SUFFIX, STRONG_SUFFIX)
               if type_name.endswith(f"{focus} {suffix}")]
    if len(matches) != 1:
        raise ValueError(f"해석할 수 없는 체력 유형: {type_name}")
    return matches[0]


def training_guidance(grade: int) -> str:
    """등급별 운동 지침 문장입니다."""
    return (f"{grade}등급 기준 동작 난이도 {TARGET_DIFFICULTY[grade]}에 가까운 운동 우선. "
            "개인별 수행 수준에 맞춰 강도와 반복량을 조절합니다.")


def recommendation_basis(grade: int, cluster: int, focus: str, gap: float, type_name: str) -> str:
    """추천 근거 문장입니다(체력 요소의 상대 편차와 배분 규칙)."""
    _, weak = type_focus(type_name)
    allocation = ("유형에 명시된 약점 요소 운동 8개" if weak
                  else "강점 요소 제외 후 상대 편차가 낮은 순 4/2/2개 배분")
    return f"{grade}등급 군집 {cluster}: {focus} 상대 편차 {gap:+.2f}%p; {allocation}. 등급별 난이도는 수동 규칙입니다."


def build_exercise_classifications(details: pd.DataFrame) -> pd.DataFrame:
    """RULES를 운동 분류 표(처방번호, 체력 요소, 난이도, 장비)로 만듭니다.

    Raises:
        ValueError: 처방 상세정보에 없는 처방번호, 겹치는 처방번호, 모르는 체력 요소가 있을 때
    """
    require_columns(details, [ID_COLUMN])
    known = set(pd.to_numeric(details[ID_COLUMN], errors="raise"))
    ids = [rule[0] for rule in RULES]
    if len(set(ids)) != len(ids):
        raise ValueError("RULES에 같은 처방번호가 여러 번 있습니다.")
    missing = [prescription_id for prescription_id in ids if prescription_id not in known]
    if missing:
        raise ValueError(f"원본 처방 상세정보에 없는 처방번호: {missing}")
    unknown = sorted({rule[1] for rule in RULES} - set(FOCUSES))
    if unknown:
        raise ValueError(f"모르는 체력 요소: {unknown}")
    return pd.DataFrame(
        [rule[:4] for rule in RULES],
        columns=[ID_COLUMN, FOCUS_COLUMN, DIFFICULTY_COLUMN, EQUIPMENT_COLUMN],
    )


def build_body_parts() -> pd.DataFrame:
    """운동별 사용 부위 표(처방번호, 부위)를 만듭니다. 부위는 부상 기록과 같은 한글 이름입니다.

    Raises:
        ValueError: 부상 부위 이름표(LOCATION_NAMES)에 없는 부위가 있을 때
    """
    rows = []
    for prescription_id, _, _, _, parts in RULES:
        for part in parts.split("|"):
            if part not in LOCATION_NAMES:
                raise ValueError(f"처방번호 {prescription_id}의 사용 부위 매핑 오류: {part}")
            rows.append((prescription_id, LOCATION_NAMES[part]))
    return pd.DataFrame(rows, columns=[ID_COLUMN, BODY_PART_COLUMN])


def build_recommendations(fitness_types: pd.DataFrame, classifications: pd.DataFrame,
                          details: pd.DataFrame) -> pd.DataFrame:
    """유형마다 추천 운동 8개(등급, 군집, 순위, 처방번호)를 정합니다.

    Raises:
        ValueError: 등급·군집이 겹치거나 등급이 1~4가 아닐 때, 유형명을 해석할 수 없을 때, 후보가 부족할 때
    """
    keys = [GRADE_COLUMN, CLUSTER_COLUMN]
    require_columns(fitness_types, [*keys, TYPE_NAME_COLUMN, *(relative_column(focus) for focus in FOCUSES)])
    require_columns(details, [ID_COLUMN, NAME_COLUMN])
    if fitness_types.duplicated(keys).any():
        raise ValueError("등급·군집 키가 중복됩니다.")
    names = details.assign(**{ID_COLUMN: pd.to_numeric(details[ID_COLUMN], errors="raise")})
    # 같은 이름의 운동을 한 번만 추천하기 위해 이름을 붙인다.
    candidates = classifications.merge(names[[ID_COLUMN, NAME_COLUMN]], on=ID_COLUMN, how="left", validate="one_to_one")
    rows = []
    for item in fitness_types.to_dict("records"):
        grade = int(item[GRADE_COLUMN])
        if grade not in GRADES:
            raise ValueError("등급은 1~4여야 합니다.")
        focus, weak = type_focus(item[TYPE_NAME_COLUMN])
        if weak:
            quotas = {focus: RECOMMENDATION_COUNT}
        else:
            # 강점 요소를 빼고 상대 편차가 낮은 순(같으면 FOCUSES 순서).
            ordered = sorted((other for other in FOCUSES if other != focus), key=lambda other: item[relative_column(other)])
            quotas = dict(zip(ordered, STRONG_QUOTAS))
        target = TARGET_DIFFICULTY[grade]
        rank = 0
        for selected_focus, quota in quotas.items():
            pool = candidates.loc[candidates[FOCUS_COLUMN].eq(selected_focus)]
            pool = pool.assign(_DISTANCE=(pool[DIFFICULTY_COLUMN] - target).abs())
            selected = pool.sort_values(["_DISTANCE", ID_COLUMN]).drop_duplicates(NAME_COLUMN).head(quota)
            if len(selected) != quota:
                raise ValueError(f"{selected_focus} 추천 후보가 부족합니다.")
            for prescription_id in selected[ID_COLUMN]:
                rank += 1
                rows.append({GRADE_COLUMN: grade, CLUSTER_COLUMN: int(item[CLUSTER_COLUMN]),
                             RANK_COLUMN: rank, ID_COLUMN: int(prescription_id)})
    return pd.DataFrame(rows)


def run(
    fitness_type_path: Path,
    prescription_detail_path: Path,
    classification_definition_path: Path,
    body_part_definition_path: Path,
    recommendation_definition_path: Path,
    classification_output_path: Path,
    body_part_output_path: Path,
    recommendation_output_path: Path,
) -> None:
    """운동 분류·사용 부위·유형별 추천 운동을 정의서대로 저장합니다."""
    fitness_types = pd.read_csv(fitness_type_path, encoding="utf-8-sig")
    details = pd.read_csv(prescription_detail_path, encoding="utf-8-sig")
    classifications = write_by_definition(
        build_exercise_classifications(details), classification_definition_path, classification_output_path)
    body_parts = write_by_definition(build_body_parts(), body_part_definition_path, body_part_output_path)
    recommendations = write_by_definition(
        build_recommendations(fitness_types, classifications, details),
        recommendation_definition_path, recommendation_output_path)
    logger.info("운동 분류 %d개 저장: %s", len(classifications), display_path(classification_output_path))
    logger.info("운동별 사용 부위 %d행 저장: %s", len(body_parts), display_path(body_part_output_path))
    logger.info("유형 %d개의 추천 운동 %d행 저장: %s", len(fitness_types), len(recommendations),
                display_path(recommendation_output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(
        PROCESSED_FITNESS_TYPE_PATH,
        PROCESSED_PRESCRIPTION_DETAIL_PATH,
        DEFINITION_EXERCISE_CLASSIFICATION,
        DEFINITION_EXERCISE_BODY_PART,
        DEFINITION_RECOMMENDED_EXERCISE,
        PROCESSED_EXERCISE_CLASSIFICATION_PATH,
        PROCESSED_EXERCISE_BODY_PART_PATH,
        PROCESSED_RECOMMENDED_EXERCISE_PATH,
    )


if __name__ == "__main__":
    main()
