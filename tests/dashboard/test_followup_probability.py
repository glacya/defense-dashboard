"""후속조치 확률 등급의 경계값을 검증합니다."""

import pandas as pd

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

