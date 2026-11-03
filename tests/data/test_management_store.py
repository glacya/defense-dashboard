"""관리 기록의 누적·수정·변경 충돌과 완료율을 검증합니다."""

import pandas as pd
import pytest

from dashboard.py.management_store import save_record,load_records,followup_metrics


@pytest.fixture(autouse=True)
def csv_mode(monkeypatch):
    """이 파일은 CSV 저장 방식을 검사하므로 CSV 모드로 고정합니다(DB 모드는 test_management_store_db.py)."""
    monkeypatch.setenv('DASHBOARD_DATA_SOURCE', 'csv')


def followup(status='진행 중'):
    return {'SOLDIER_ID':'001','ASSIGNEE':'담당자','COUNSELING_DATE':'2026-10-27',
            'COUNSELING_CONTENT':'상태 확인','ACTION_CONTENT':'운동 지도 점검',
            'NEXT_CHECK_DATE':'2026-10-30','STATUS':status,'COMPLETED_DATE':'2026-10-28' if status=='완료' else ''}


def test_persistence_update_and_stale_edit(tmp_path):
    ident=save_record('followup_records',followup(),tmp_path)
    original=load_records('followup_records',tmp_path).iloc[0]
    changed=followup('완료')
    save_record('followup_records',changed,tmp_path,ident,original.UPDATED_AT)
    result=load_records('followup_records',tmp_path)
    assert len(result)==1
    assert result.iloc[0].STATUS=='완료'
    assert result.iloc[0].CREATED_AT==original.CREATED_AT
    with pytest.raises(ValueError,match='変更|변경'):
        save_record('followup_records',followup(),tmp_path,ident,original.UPDATED_AT)
    assert load_records('followup_records',tmp_path).iloc[0].STATUS=='완료'


def test_completion_denominator_excludes_cancelled(tmp_path):
    for status in ['완료','진행 중','취소']:
        save_record('followup_records',followup(status),tmp_path)
    metrics=followup_metrics(load_records('followup_records',tmp_path))
    assert metrics['완료율']==50
    assert metrics['대상']==2
    assert metrics['취소']==1
    assert followup_metrics(pd.DataFrame(columns=['STATUS']))['완료율'] is None


def test_invalid_dates_and_completion_do_not_write(tmp_path):
    bad=followup('완료');bad['COMPLETED_DATE']=''
    with pytest.raises(ValueError,match='완료일'):
        save_record('followup_records',bad,tmp_path)
    bad=followup();bad['NEXT_CHECK_DATE']='2026-10-01'
    with pytest.raises(ValueError,match='점검일'):
        save_record('followup_records',bad,tmp_path)
    assert not (tmp_path/'followup_records.csv').exists()


def test_lock_prevents_concurrent_writes(tmp_path):
    (tmp_path/'.write.lock').write_text('busy')
    with pytest.raises(ValueError,match='저장'):
        save_record('followup_records',followup(),tmp_path)
    assert not (tmp_path/'followup_records.csv').exists()
