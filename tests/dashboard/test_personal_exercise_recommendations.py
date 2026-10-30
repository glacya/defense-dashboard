"""개인 운동 추천 로더의 DB 모드를 검증합니다. 실제 DB에는 접속하지 않습니다."""

import pandas as pd
import pytest

from dashboard.py import personal_exercise_recommendations as recommendations


def test_db_mode_joins_tables_and_builds_texts(monkeypatch):
    """등급·군집을 params로 넘겨 JOIN 쿼리 하나로 읽고, 지침·근거 문장을 붙이는지 확인합니다."""
    calls = []

    def fake_query(sql, params=None, ttl=None):
        calls.append((sql, params))
        return pd.DataFrame({
            'AVERAGE_PERCENTILE_GRADE': [1, 1], 'CLUSTER': [0, 0], 'RECOMMENDATION_RANK': [1, 2],
            'TYPE_NAME': ['유형0: 근력 약점형'] * 2, 'IMPROVEMENT_FOCUS': ['근력'] * 2,
            'RECOMMENDED_EXERCISE': ['턱걸이', '스쿼트'], 'RELATIVE_GAP': [-28.28, -28.28],
        })

    monkeypatch.setattr(recommendations, 'run_query', fake_query)

    result = recommendations.load_recommendation(1, 0, 'db')

    sql, params = calls[0]
    assert params == {'grade': 1, 'cluster': 0}
    assert 'JOIN exercise_classifications' in sql and 'ORDER BY r.recommendation_rank' in sql
    assert result.RECOMMENDED_EXERCISE.tolist() == ['턱걸이', '스쿼트']
    assert result.RECOMMENDATION_BASIS.iloc[0].startswith('1등급 군집 0: 근력 상대 편차 -28.28%p')
    assert result.TRAINING_GUIDANCE.iloc[0].startswith('1등급 기준 동작 난이도 3')


def test_duplicated_exercise_is_rejected(monkeypatch):
    frame = pd.DataFrame({
        'AVERAGE_PERCENTILE_GRADE': [1, 1], 'CLUSTER': [0, 0], 'RECOMMENDATION_RANK': [1, 2],
        'TYPE_NAME': ['유형0: 근력 약점형'] * 2, 'IMPROVEMENT_FOCUS': ['근력'] * 2,
        'RECOMMENDED_EXERCISE': ['턱걸이', '턱걸이'], 'RELATIVE_GAP': [-1.0, -1.0],
    })
    monkeypatch.setattr(recommendations, 'run_query', lambda sql, params=None, ttl=None: frame)

    with pytest.raises(ValueError, match='중복'):
        recommendations.load_recommendation(1, 0, 'db')
