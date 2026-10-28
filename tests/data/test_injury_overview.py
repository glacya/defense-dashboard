"""부상 인원·건수 분리와 최신 종목 등급 집계를 검증합니다."""

import pandas as pd
import pytest

from data.scripts.analysis.analysis2.injury_overview import build_tables
from data.scripts.fitness_standards import FITNESS_EXERCISES, grade_cut


def inputs():
    source=pd.DataFrame([
        {'MESURE_ID':'1','SOLDIER_ID':'001','MESURE_DE':'20260101','AGE':20,**{e:grade_cut(e,3) for e in FITNESS_EXERCISES}},
        {'MESURE_ID':'2','SOLDIER_ID':'001','MESURE_DE':'20260201','AGE':20,**{e:grade_cut(e,1) for e in FITNESS_EXERCISES}},
        {'MESURE_ID':'3','SOLDIER_ID':'002','MESURE_DE':'20260101','AGE':25,**{e:grade_cut(e,2) for e in FITNESS_EXERCISES}}])
    people=pd.DataFrame({'SOLDIER_ID':['001','002','003']})
    injuries=pd.DataFrame([{'INJURY_ID':str(i),'SOLDIER_ID':'001','INJURY_CATEGORY':'하지','INJURY_LOCATION':'무릎','SEVERITY':'경증','PREVENTABILITY':'Y'} for i in (1,2)])
    return source,people,injuries


def test_repeated_injuries_latest_grade_and_unmeasured():
    source,people,injuries=inputs()
    personal,grades,summary=build_tables(source,people,injuries)
    r=summary.iloc[0]
    assert r['전체장병수']==3
    assert r['부상인원']==1
    assert r['부상건수']==2
    assert r['반복부상인원']==1
    assert r['부상자비율']==pytest.approx(100/3)
    assert r['측정기록없음']==1
    for _,group in grades.groupby('종목'):
        assert group['전체인원'].sum()==3
        assert group['부상인원'].sum()==1
        assert group['부상건수'].sum()==2
        assert group.loc[group['등급'].eq('1등급'),'부상자비율'].iloc[0]==100
        assert group.loc[group['등급'].eq('판정 불가'),'전체인원'].iloc[0]==2
        assert pd.isna(group.loc[group['등급'].eq('2등급'),'부상자비율'].iloc[0])


def test_empty_injury_file_is_zero_not_missing():
    source,people,injuries=inputs()
    _,_,summary=build_tables(source,people,injuries.iloc[:0])
    assert summary.iloc[0]['부상건수']==0
    assert summary.iloc[0]['부상자비율']==0


def test_unknown_person_and_duplicate_injury_rejected():
    source,people,injuries=inputs()
    with pytest.raises(ValueError,match='중복'):
        build_tables(source,people,pd.concat([injuries,injuries]))
    injuries.loc[0,'SOLDIER_ID']='unknown'
    with pytest.raises(ValueError,match='명단에 없는'):
        build_tables(source,people,injuries)
