"""부상 기록에 명단 속성을 연결하고 조건을 적용하는 기능을 테스트합니다."""

import pandas as pd
import pytest

from dashboard.py.injury_overview_data import filter_injuries_by_personnel


def test_filter_injuries_by_personnel_applies_all_selected_conditions():
    """지역·부대·계급을 함께 선택하면 모든 조건과 일치하는 부상만 반환하는지 확인합니다."""
    people = pd.DataFrame({
        'SOLDIER_ID': ['a', 'b', 'c'],
        'REGION_NAME': ['북부', '북부', '남부'],
        'UNIT_NAME': ['1대대', '2대대', '1대대'],
        'RANK_NAME': ['병장', '병장', '상병'],
    })
    injuries = pd.DataFrame({
        'INJURY_ID': ['i1', 'i2', 'i3', 'i4'],
        'SOLDIER_ID': ['a', 'a', 'b', 'c'],
    })

    filtered = filter_injuries_by_personnel(
        injuries,
        people,
        regions=['북부'],
        units=['1대대'],
        ranks=['병장'],
    )

    assert filtered['INJURY_ID'].tolist() == ['i1', 'i2']
    assert filtered['REGION_NAME'].tolist() == ['북부', '북부']


def test_filter_injuries_by_personnel_rejects_unmatched_soldier():
    """명단에 없는 장병의 부상 기록은 조용히 제외하지 않고 오류를 내는지 확인합니다."""
    people = pd.DataFrame({
        'SOLDIER_ID': ['a'],
        'REGION_NAME': ['북부'],
        'UNIT_NAME': ['1대대'],
        'RANK_NAME': ['병장'],
    })
    injuries = pd.DataFrame({'SOLDIER_ID': ['missing']})

    with pytest.raises(ValueError, match='부상 기록과 장병 명단 연결 불일치'):
        filter_injuries_by_personnel(injuries, people)
