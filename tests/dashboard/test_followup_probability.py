"""후속조치 확률 등급의 경계값과 잘못된 입력 처리를 검증합니다."""

import pandas as pd
import pytest

from dashboard.py.followup_probability import classify_probabilities


def test_risk_boundaries():
    """30·50·70% 경계값은 각각 높은 경계 등급에 포함되는지 확인합니다."""
    values = [0, .2999, .3, .4999, .5, .6999, .7, 1]
    result = classify_probabilities(pd.DataFrame({
        'SOLDIER_ID': [str(i) for i in range(len(values))], 'FAILURE_PROBABILITY': values,
    }))
    assert result.RISK_LEVEL.tolist() == ['안전', '안전', '경계1등급', '경계1등급',
                                          '경계2등급', '경계2등급', '경계3등급', '경계3등급']
    assert result.FOLLOWUP_TARGET.tolist() == [False, False, True, True, True, True, True, True]


@pytest.mark.parametrize('value', [None, '', 'invalid', -.1, 1.1, float('inf')])
def test_invalid_probability(value):
    """결측·범위 밖 확률이 안전 등급으로 잘못 분류되지 않는지 확인합니다."""
    with pytest.raises(ValueError):
        classify_probabilities(pd.DataFrame({'SOLDIER_ID': ['a'], 'FAILURE_PROBABILITY': [value]}))


def test_duplicate_soldier():
    """같은 장병의 예측이 중복되면 인원 집계 전에 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match='중복'):
        classify_probabilities(pd.DataFrame({'SOLDIER_ID': ['a', 'a'], 'FAILURE_PROBABILITY': [.3, .7]}))
