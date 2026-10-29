"""최신 측정 기준 운동유형 연결과 16개 유형 식별을 검증합니다."""

import pandas as pd
import pytest

from dashboard.py.followup_fitness_types import attach_fitness_types


def _catalog():
    return pd.DataFrame([{'AVERAGE_PERCENTILE_GRADE': grade, 'CLUSTER': cluster,
                          'TYPE_NAME': f'{grade}-{cluster}'}
                         for grade in range(1, 5) for cluster in range(4)])


def test_same_cluster_different_grade():
    """군집 번호가 같아도 백분위 등급이 다르면 별개 유형인지 확인합니다."""
    people = pd.DataFrame({'SOLDIER_ID': ['a', 'b'], 'MESURE_ID': [10, 20]})
    classifications = pd.DataFrame({'MESURE_ID': [10, 20], 'AVERAGE_PERCENTILE_GRADE': [1, 2], 'CLUSTER': [0, 0]})
    result, types = attach_fitness_types(people, classifications, _catalog())
    assert len(types) == 16
    assert result.FITNESS_TYPE_KEY.tolist() == ['1-0', '2-0']


def test_missing_latest_classification():
    """최신 측정 분류가 없으면 과거 측정 유형으로 대체하지 않는지 확인합니다."""
    people = pd.DataFrame({'SOLDIER_ID': ['a', 'b'], 'MESURE_ID': [20, pd.NA]})
    classifications = pd.DataFrame({'MESURE_ID': [10], 'AVERAGE_PERCENTILE_GRADE': [1], 'CLUSTER': [0]})
    result, _ = attach_fitness_types(people, classifications, _catalog())
    assert len(result) == 2
    assert result.FITNESS_TYPE_KEY.isna().all()


def test_duplicate_measurement():
    """측정 분류 중복으로 장병 수가 늘어나는 것을 막는지 확인합니다."""
    people = pd.DataFrame({'SOLDIER_ID': ['a'], 'MESURE_ID': [10]})
    classifications = pd.DataFrame({'MESURE_ID': [10, 10], 'AVERAGE_PERCENTILE_GRADE': [1, 2], 'CLUSTER': [0, 0]})
    with pytest.raises(ValueError, match='중복'):
        attach_fitness_types(people, classifications, _catalog())
