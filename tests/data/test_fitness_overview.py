"""전체 현황의 판정 경계·분모·중복 제거·시간 순서를 검증합니다."""

import pandas as pd
import pytest

from data.scripts.analysis.analysis2.fitness_overview import judge_measurements, summarize
from data.scripts.fitness_standards import FITNESS_EXERCISES, grade_cut


def records():
    """복합 선정 사유와 판정 불가 기록이 있는 표본입니다."""
    rows=[]
    for soldier in ('001','002'):
        for number in (3,1,2):
            row={'SOLDIER_ID':soldier,'MESURE_ID':f'{soldier}-{number}','MESURE_DE':f'20260{number}01','AGE':20,
                 **{event:grade_cut(event,3) for event in FITNESS_EXERCISES}}
            if soldier=='001':
                row['STRENGTH']=0
                if number==3:
                    row['CARDIO']=0
            else:
                row['FLEXIBILITY']=None
            rows.append(row)
    return pd.DataFrame(rows)


def test_order_boundaries_and_no_future_information():
    result=judge_measurements(records()).set_index('MESURE_ID')
    assert result.loc['001-1','ROUND']==1
    assert result.loc['001-1','CARDIO_GRADE']==3
    assert result.loc['001-1','STRENGTH_GRADE']==0
    assert not result.loc['001-1','MANAGED']
    assert not result.loc['001-2','PERSISTENT_FAIL']
    assert result.loc['001-3','MULTIPLE_FAIL']
    assert result.loc['001-3','WORSENED']
    assert result.loc['001-3','PERSISTENT_FAIL']
    assert pd.isna(result.loc['002-3','FAIL_COUNT'])


def test_denominators_deduplication_and_grade_counts():
    data=judge_measurements(records())
    people=pd.DataFrame({'SOLDIER_ID':['001','002','003'],'UNIT_NAME':['A','A','A']})
    totals,events=summarize(data,people)
    row=totals.loc[totals['회차'].eq(3)].iloc[0]
    assert row['전체장병수']==3
    assert row['측정인원']==2
    assert row['판정가능인원']==1
    assert row['미달률']==100
    assert row['관리대상인원']==1
    assert (events[['1등급인원','2등급인원','3등급인원','미달인원']].sum(axis=1)==events['판정가능인원']).all()
    assert (events['판정가능인원']+events['판정불가인원']).eq(2).all()


def test_outside_age_invalid_date_and_duplicate():
    data=records()
    data.loc[0,'AGE']=25
    result=judge_measurements(data).set_index('MESURE_ID')
    assert result.loc['001-3','EVALUATED_COUNT']==0
    data.loc[0,'MESURE_DE']='20260230'
    with pytest.raises(ValueError,match='측정일'):
        judge_measurements(data)
    data=records()
    data.loc[0,'MESURE_ID']=data.loc[1,'MESURE_ID']
    with pytest.raises(ValueError,match='중복'):
        judge_measurements(data)
