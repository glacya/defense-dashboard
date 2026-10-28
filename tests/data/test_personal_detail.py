"""개인별 측정값 변화와 등급 개선·하락·판정 불가를 검증합니다."""

import pandas as pd
import pytest

from data.scripts.analysis.analysis2.personal_detail import build_changes
from data.scripts.analysis.analysis2.management_targets import build_targets
from data.scripts.fitness_standards import FITNESS_EXERCISES, grade_cut


def records():
    """세 회차에 미달 해소·신규 미달·연령 범위 밖이 있는 장병입니다."""
    rows=[]
    for number in (1,2,3):
        row={'MESURE_ID':str(number),'SOLDIER_ID':'001','MESURE_DE':f'20260{number}01','AGE':20,'BMI':25,
             **{event:grade_cut(event,3) for event in FITNESS_EXERCISES}}
        row['STRENGTH']=50 if number==1 else 65
        row['CARDIO']=48 if number==1 else 40
        if number==3:
            row['AGE']=25
        rows.append(row)
    return pd.DataFrame(rows)


def test_grade_direction_and_resolved_failures():
    source=records()
    result=build_changes(source,build_targets(source)).set_index('MESURE_ID')
    assert result.loc['2','STRENGTH_CHANGE']==15
    assert result.loc['2','STRENGTH_GRADE_CHANGE']=='개선'
    assert result.loc['2','CARDIO_GRADE_CHANGE']=='하락'
    assert result.loc['2','IMPROVED_EVENTS']=='근력'
    assert result.loc['1','STRENGTH_CHANGE']==0
    assert result.loc['1','STRENGTH_GRADE_CHANGE']=='유지'
    assert result.loc['3','STRENGTH_GRADE_CHANGE']=='판정 불가'
    assert result.loc['3','IMPROVED_EVENTS']==''
    assert result.loc['2','FIRST_MESURE_ID']=='1'


def test_missing_value_not_improvement():
    source=records()
    source.loc[1,'STRENGTH']=None
    result=build_changes(source,build_targets(source)).set_index('MESURE_ID')
    assert pd.isna(result.loc['2','STRENGTH_CHANGE'])
    assert result.loc['2','STRENGTH_GRADE_CHANGE']=='판정 불가'
    assert result.loc['2','IMPROVED_EVENTS']==''


def test_mismatching_measurement_rejected():
    source=records()
    targets=build_targets(source)
    targets.loc[0,'MESURE_ID']='missing'
    with pytest.raises(ValueError,match='불일치'):
        build_changes(source,targets)
