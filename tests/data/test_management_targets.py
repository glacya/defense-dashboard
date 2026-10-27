"""집중관리 대상의 BMI 경계·다중 사유·시간순 판정을 확인합니다."""

import pandas as pd

from data.scripts.analysis.management_targets import build_targets
from data.scripts.fitness_standards import FITNESS_EXERCISES, grade_cut


def sample():
    """BMI와 반복 미달 조건을 분리하는 표본입니다."""
    rows=[]
    for soldier,bmi in [('001',25.0),('002',24.99),('003',26.0)]:
        for number in (1,2,3):
            row={'MESURE_ID':f'{soldier}-{number}','SOLDIER_ID':soldier,'MESURE_DE':f'20260{number}01','AGE':20,'BMI':bmi,
                 **{event:grade_cut(event,3) for event in FITNESS_EXERCISES}}
            if soldier!='003':
                row['STRENGTH']=0
                if number==3:
                    row['CARDIO']=0
            rows.append(row)
    return pd.DataFrame(rows)


def test_bmi_boundary_and_actual_failure():
    data=build_targets(sample()).set_index('MESURE_ID')
    assert data.loc['001-1','HIGH_BMI_FAIL']
    assert data.loc['001-1','MANAGED']
    assert not data.loc['002-1','HIGH_BMI_FAIL']
    assert not data.loc['003-1','HIGH_BMI_FAIL']
    assert data.loc['001-1','BMI_GROUP']=='높음'
    assert data.loc['002-1','BMI_GROUP']=='보통'


def test_multiple_reasons_one_row_and_no_future_leak():
    data=build_targets(sample())
    row=data.set_index('MESURE_ID').loc['001-3']
    assert all(row[flag] for flag in ['HIGH_BMI_FAIL','MULTIPLE_FAIL','WORSENED','PERSISTENT_FAIL'])
    assert row['FAIL_COUNT_CHANGE']==1
    assert row['NEW_FAILED_EVENTS']=='심폐지구력'
    assert row['PERSISTENT_EVENTS']=='근력'
    assert len(row.SELECTION_REASONS.split(' · '))==4
    assert not data.duplicated(['SOLDIER_ID','ROUND']).any()
    assert not data.loc[data.ROUND.lt(3),'PERSISTENT_FAIL'].any()


def test_unknown_age_or_missing_measurement_not_selected_as_bmi_failure():
    source=sample()
    source.loc[source.SOLDIER_ID.eq('001'),'AGE']=25
    source.loc[source.SOLDIER_ID.eq('002'),'STRENGTH']=None
    result=build_targets(source).set_index('MESURE_ID')
    assert not result.loc['001-1','HIGH_BMI_FAIL']
    assert pd.isna(result.loc['001-1','FAIL_COUNT'])
    assert result.loc['002-1','EVALUATED_COUNT']==3
    assert not result.loc['002-1','MANAGED']
