"""CSV3의 유형별 추천 연결과 화면 렌더링을 확인합니다."""

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard.py import personal_exercise_recommendations as recommendations


def test_recommendations_use_grade_and_cluster(monkeypatch, tmp_path):
    """군집이 같아도 등급이 다른 운동이 섞이지 않는지 확인합니다."""
    rows = pd.DataFrame([
        [1, 0, '근력', '운동 A', '지침', '근거', 'https://example.com'],
        [1, 0, '근력', '운동 B', '지침', '근거', 'https://example.com'],
        [2, 0, '유연성', '운동 C', '지침', '근거', 'https://example.com'],
    ], columns=['AVERAGE_PERCENTILE_GRADE', 'CLUSTER', 'IMPROVEMENT_FOCUS',
                'RECOMMENDED_EXERCISE', 'TRAINING_GUIDANCE',
                'RECOMMENDATION_BASIS', 'SOURCE_URL'])
    rows.to_csv(tmp_path / 'FITNESS_TYPE_EXERCISE_RECOMMENDATIONS3.csv', index=False)
    monkeypatch.setattr(recommendations, 'PROCESSED_DIR', tmp_path)
    assert recommendations.load_recommendation(1, 0).RECOMMENDED_EXERCISE.tolist() == ['운동 A', '운동 B']
    assert recommendations.load_recommendation(4, 3).empty


def test_render_recommendation():
    """여러 약점에 해당하는 운동 목록과 그림을 오류 없이 표시하는지 확인합니다."""
    app = AppTest.from_string('''
from dashboard.py.personal_exercise_recommendations import render_recommendation
render_recommendation(3, 0)
''').run()
    assert not app.exception
    text = '\n'.join(element.value for element in app.markdown)
    assert '팔굽혀펴기' in text
    assert '낮은 발판 오르기 반복' not in text
    assert '빠르게 걷기' in text
    assert '넙다리 뒤쪽 스트레칭' in text
