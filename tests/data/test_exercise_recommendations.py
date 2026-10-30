"""체력 유형별 추천 운동(build_exercise_recommendations)을 검증합니다."""

import pandas as pd
import pytest

from data.scripts.analysis.clustering import build_exercise_recommendations as module
from data.scripts.analysis.clustering.build_exercise_recommendations import (
    build_body_parts,
    build_exercise_classifications,
    build_recommendations,
    recommendation_basis,
    training_guidance,
    type_focus,
)
from data.scripts.paths import (
    DEFINITION_EXERCISE_BODY_PART,
    DEFINITION_EXERCISE_CLASSIFICATION,
    DEFINITION_RECOMMENDED_EXERCISE,
)
from data.scripts.utils import load_definition_columns

# 체력 요소마다 난이도 1·2·3 후보를 하나씩(처방번호는 요소 순서 × 10 + 난이도), 근력에는 같은 이름 운동을 하나 더 둔다.
FOCUS_NAMES = list(module.FOCUSES)
RULES = [(index * 10 + level, focus, level, '없음', 'Knee')
         for index, focus in enumerate(FOCUS_NAMES) for level in (1, 2, 3)]
RULES.append((4, '근력', 1, '없음', 'Hip'))


@pytest.fixture
def small_rules(monkeypatch):
    monkeypatch.setattr(module, 'RULES', RULES)
    monkeypatch.setattr(module, 'RECOMMENDATION_COUNT', 2)
    monkeypatch.setattr(module, 'STRONG_QUOTAS', (2, 1, 1))
    names = {rule[0]: f'운동{rule[0]}' for rule in RULES}
    names[4] = names[1]  # 1번과 이름이 같은 운동
    return pd.DataFrame({'PRESCRIPTION_TYPE_ID': list(names), 'PRESCRIPTION': list(names.values())})


def _types(rows):
    return pd.DataFrame([{'AVERAGE_PERCENTILE_GRADE': grade, 'CLUSTER': cluster, 'TYPE_NAME': name,
                          'STRENGTH_RELATIVE': gaps[0], 'ENDURANCE_RELATIVE': gaps[1],
                          'CARDIO_RELATIVE': gaps[2], 'FLEXIBILITY_RELATIVE': gaps[3]}
                         for grade, cluster, name, gaps in rows])


def test_type_focus_reads_weak_and_strong_types():
    assert type_focus('유형0: 근력 약점형') == ('근력', True)
    assert type_focus('유형3: 심폐지구력 강점형') == ('심폐지구력', False)
    with pytest.raises(ValueError, match='해석할 수 없는'):
        type_focus('균형형')


def test_weak_type_gets_exercises_of_its_focus_near_target_difficulty(small_rules):
    """약점형은 그 요소 운동만, 목표 난이도(1등급 3)에 가까운 순으로, 같은 이름 운동은 한 번만 고르는지 확인합니다."""
    classifications = build_exercise_classifications(small_rules)
    types = _types([(1, 0, '유형0: 근력 약점형', (-20, 5, 5, 10))])

    result = build_recommendations(types, classifications, small_rules)

    assert result.RECOMMENDATION_RANK.tolist() == [1, 2]
    assert result.PRESCRIPTION_TYPE_ID.tolist() == [3, 2]  # 근력 난이도 3, 2


def test_strong_type_spreads_over_other_focuses_by_lowest_gap(small_rules):
    """강점형은 강점 요소를 빼고 상대 편차가 낮은 요소부터 배분하고, 같은 이름 운동은 건너뛰는지 확인합니다."""
    classifications = build_exercise_classifications(small_rules)
    # 강점: 근지구력. 나머지 편차 낮은 순: 유연성(-9) > 근력(-5) > 심폐지구력(0). 4등급 목표 난이도 1.
    types = _types([(4, 2, '유형2: 근지구력 강점형', (-5, 20, 0, -9))])

    result = build_recommendations(types, classifications, small_rules)

    assert result.PRESCRIPTION_TYPE_ID.tolist() == [31, 32, 1, 21]
    # 근력 1번과 같은 이름인 4번은 고르지 않는다.
    assert 4 not in result.PRESCRIPTION_TYPE_ID.tolist()


def test_classification_rejects_unknown_prescription(small_rules):
    with pytest.raises(ValueError, match='없는 처방번호'):
        build_exercise_classifications(small_rules.iloc[1:])


def test_body_parts_use_injury_location_names(small_rules):
    parts = build_body_parts()

    assert parts.loc[parts.PRESCRIPTION_TYPE_ID.eq(4), 'BODY_PART'].tolist() == ['고관절']
    assert set(parts.BODY_PART) == {'무릎', '고관절'}


def test_texts_for_dashboard():
    assert training_guidance(2).startswith('2등급 기준 동작 난이도 2')
    assert recommendation_basis(1, 0, '근력', -28.28, '유형0: 근력 약점형') == (
        '1등급 군집 0: 근력 상대 편차 -28.28%p; 유형에 명시된 약점 요소 운동 8개. 등급별 난이도는 수동 규칙입니다.')
    assert '4/2/2개 배분' in recommendation_basis(3, 1, '유연성', 1.5, '유형1: 근력 강점형')


def test_project_rules_match_definitions():
    """실제 RULES로 만든 표가 정의서 컬럼과 같은지 확인합니다(처방 상세 없이 검사할 수 있는 부분)."""
    details = pd.DataFrame({'PRESCRIPTION_TYPE_ID': [rule[0] for rule in module.RULES], 'PRESCRIPTION': ''})
    assert build_exercise_classifications(details).columns.tolist() == load_definition_columns(DEFINITION_EXERCISE_CLASSIFICATION)
    assert build_body_parts().columns.tolist() == load_definition_columns(DEFINITION_EXERCISE_BODY_PART)
    assert load_definition_columns(DEFINITION_RECOMMENDED_EXERCISE) == [
        'AVERAGE_PERCENTILE_GRADE', 'CLUSTER', 'RECOMMENDATION_RANK', 'PRESCRIPTION_TYPE_ID']
