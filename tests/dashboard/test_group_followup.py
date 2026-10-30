"""그룹 후속조치의 일괄 저장과 실패 시 기존 기록 보존을 검증합니다."""

import pytest

from dashboard.py import management_store as store


@pytest.fixture(autouse=True)
def csv_mode(monkeypatch):
    """이 파일은 CSV 저장 방식을 검사하므로 CSV 모드로 고정합니다(DB 모드는 test_management_store_db.py)."""
    monkeypatch.setenv('DASHBOARD_DATA_SOURCE', 'csv')


def _values():
    return dict(ASSIGNEE='담당자',COUNSELING_DATE='2026-10-29',COUNSELING_CONTENT='공통 상담',
                ACTION_CONTENT='공통 후속조치',NEXT_CHECK_DATE='2026-11-01',STATUS='점검 대기',COMPLETED_DATE='')


def test_group_preserves_existing_and_deduplicates(tmp_path):
    """기존 기록을 보존하고 그룹 내 중복 장병에게는 한 건만 추가하는지 확인합니다."""
    store.save_record('followup_records',dict(_values(),SOLDIER_ID='old'),directory=tmp_path)
    assert store.save_followups_batch(['a','b','a'],_values(),tmp_path)==2
    frame=store.load_records('followup_records',tmp_path)
    assert frame.SOLDIER_ID.tolist()==['old','a','b']
    assert frame.RECORD_ID.nunique()==3
    assert frame.ACTION_CONTENT.eq('공통 후속조치').all()


def test_validation_prevents_partial_save(tmp_path):
    """그룹 중 잘못된 장병번호가 있으면 아무 기록도 저장하지 않는지 확인합니다."""
    with pytest.raises(ValueError):
        store.save_followups_batch(['a',''],_values(),tmp_path)
    assert not (tmp_path/'followup_records.csv').exists()


def test_failed_replace_preserves_original(tmp_path,monkeypatch):
    """최종 파일 교체 실패 시 기존 파일과 잠금 정리가 보장되는지 확인합니다."""
    store.save_followups_batch(['old'],_values(),tmp_path)
    original=(tmp_path/'followup_records.csv').read_bytes()
    def fail(*args):
        raise OSError('교체 실패')
    monkeypatch.setattr(store.os,'replace',fail)
    with pytest.raises(OSError):
        store.save_followups_batch(['a','b'],_values(),tmp_path)
    assert (tmp_path/'followup_records.csv').read_bytes()==original
    assert not (tmp_path/'.write.lock').exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_existing_lock_is_preserved(tmp_path):
    """다른 저장이 진행 중이면 그 잠금을 지우지 않고 저장을 거부하는지 확인합니다."""
    (tmp_path/'.write.lock').touch()
    with pytest.raises(ValueError,match='다른 저장'):
        store.save_followups_batch(['a'],_values(),tmp_path)
    assert (tmp_path/'.write.lock').exists()
