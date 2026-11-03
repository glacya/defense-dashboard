"""개인 운동 추천 로더의 DB 모드를 검증합니다. 실제 DB에는 접속하지 않습니다."""

import pandas as pd

from dashboard.py import personal_exercise_recommendations as recommendations


def test_db_mode_joins_tables_and_builds_texts(monkeypatch):
    """등급·군집을 params로 넘겨 JOIN 쿼리 하나로 읽고, 지침·근거 문장을 붙이는지 확인합니다."""
    calls = []

    def fake_query(sql, params=None, ttl=None):
        calls.append((sql, params))
        return pd.DataFrame({
            'AVERAGE_PERCENTILE_GRADE': [1, 1], 'CLUSTER': [0, 0], 'RECOMMENDATION_RANK': [1, 2],
            'TYPE_NAME': ['유형1: 근력 약점형'] * 2, 'IMPROVEMENT_FOCUS': ['근력'] * 2,
            'RECOMMENDED_EXERCISE': ['턱걸이', '스쿼트'], 'RELATIVE_GAP': [-28.28, -28.28], 'BODY_PARTS': ['?? | ?', '?? | ???'],
        })

    monkeypatch.setattr(recommendations, 'run_query', fake_query)

    result = recommendations.load_recommendation(1, 0)

    sql, params = calls[0]
    assert params == {'grade': 1, 'cluster': 0}
    assert 'JOIN exercise_classifications' in sql and 'ORDER BY r.recommendation_rank' in sql
    assert result.RECOMMENDED_EXERCISE.tolist() == ['턱걸이', '스쿼트']
    assert result.RECOMMENDATION_BASIS.iloc[0].startswith('1등급 군집 0: 근력 상대 편차 -28.28%p')
    assert result.TRAINING_GUIDANCE.iloc[0].startswith('1등급 기준 동작 난이도 3')


def test_texts_follow_type_and_allocation(monkeypatch):
    """지침은 등급별 목표 난이도로, 근거의 배분은 유형의 추천 운동 수로 만드는지 확인합니다."""
    strong = pd.DataFrame({
        'AVERAGE_PERCENTILE_GRADE': [3] * 8, 'CLUSTER': [1] * 8, 'RECOMMENDATION_RANK': list(range(1, 9)),
        'TYPE_NAME': ['유형2: 근력 강점형'] * 8,
        'IMPROVEMENT_FOCUS': ['유연성'] * 4 + ['근지구력'] * 2 + ['심폐지구력'] * 2,
        'RECOMMENDED_EXERCISE': [f'운동{i}' for i in range(8)], 'RELATIVE_GAP': [1.5] * 8, 'BODY_PARTS': ['무릎'] * 8,
    })
    monkeypatch.setattr(recommendations, 'run_query', lambda sql, params=None, ttl=None: strong)

    result = recommendations.load_recommendation(3, 1)

    assert recommendations.training_guidance(2).startswith('2등급 기준 동작 난이도 2')
    assert result.RECOMMENDATION_BASIS.iloc[0] == (
        '3등급 군집 1: 유연성 상대 편차 +1.50%p; 강점 요소 제외 후 상대 편차가 낮은 순 4/2/2개 배분. 등급별 난이도는 수동 규칙입니다.')


def test_weak_type_basis_counts_exercises(monkeypatch):
    weak = pd.DataFrame({
        'AVERAGE_PERCENTILE_GRADE': [1] * 8, 'CLUSTER': [0] * 8, 'RECOMMENDATION_RANK': list(range(1, 9)),
        'TYPE_NAME': ['유형1: 근력 약점형'] * 8, 'IMPROVEMENT_FOCUS': ['근력'] * 8,
        'RECOMMENDED_EXERCISE': [f'운동{i}' for i in range(8)], 'RELATIVE_GAP': [-28.28] * 8, 'BODY_PARTS': ['무릎'] * 8,
    })
    monkeypatch.setattr(recommendations, 'run_query', lambda sql, params=None, ttl=None: weak)

    assert recommendations.load_recommendation(1, 0).RECOMMENDATION_BASIS.iloc[0] == (
        '1등급 군집 0: 근력 상대 편차 -28.28%p; 유형에 명시된 약점 요소 운동 8개. 등급별 난이도는 수동 규칙입니다.')


def test_injury_filter_matches_individual_parts_and_keeps_order():
    frame = pd.DataFrame({'RECOMMENDED_EXERCISE': ['A', 'B', 'C'],
                          'BODY_PARTS': ['어깨 | 팔', '고관절 | 무릎', '전완 | 손목']})
    injuries = pd.DataFrame({'INJURY_LOCATION': ['어깨', '어깨', '손목']})
    allowed, excluded = recommendations.split_by_injuries(frame, injuries)
    assert allowed.RECOMMENDED_EXERCISE.tolist() == ['B']
    assert excluded.RECOMMENDED_EXERCISE.tolist() == ['A', 'C']
    assert excluded.EXCLUSION_REASON.tolist() == ['어깨', '손목']
    allowed, excluded = recommendations.split_by_injuries(frame, pd.DataFrame())
    assert len(allowed) == 3 and excluded.empty
    _, excluded = recommendations.split_by_injuries(frame, pd.DataFrame({'INJURY_LOCATION': ['팔']}))
    assert excluded.RECOMMENDED_EXERCISE.tolist() == ['A']
