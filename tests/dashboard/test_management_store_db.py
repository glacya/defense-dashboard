"""관리 기록의 DB 모드(INSERT/UPDATE, 읽기 캐시)를 검증합니다. 실제 DB에는 접속하지 않습니다."""

from contextlib import contextmanager
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from dashboard.py import management_store as store


class FakeResult:
    def __init__(self, rowcount=1, first=(1,), scalar=7):
        self.rowcount, self._first, self._scalar = rowcount, first, scalar

    def first(self):
        return self._first

    def scalar_one(self):
        return self._scalar


class FakeSession:
    """실행한 SQL과 값을 기록하고, 정해 둔 결과를 돌려주는 가짜 세션."""

    def __init__(self):
        self.calls = []
        self.update_rowcount = 1
        self.owner = (1,)

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if sql.startswith('SELECT 1 FROM injuries'):
            return FakeResult(first=self.owner)
        if sql.startswith('UPDATE'):
            return FakeResult(rowcount=self.update_rowcount)
        return FakeResult()


@pytest.fixture
def session(monkeypatch):
    """DB 모드로 두고 transaction()이 가짜 세션을 쓰게 합니다. 읽기 캐시도 비웁니다."""
    monkeypatch.setenv('DASHBOARD_DATA_SOURCE', 'db')
    fake = FakeSession()

    @contextmanager
    def fake_transaction():
        yield fake

    monkeypatch.setattr(store, 'transaction', fake_transaction)
    store._load_records_db.clear()
    yield fake
    store._load_records_db.clear()


def _followup(**changes):
    values = {'SOLDIER_ID': 's1', 'ASSIGNEE': '담당자', 'COUNSELING_DATE': '2026-10-27', 'COUNSELING_CONTENT': '',
              'ACTION_CONTENT': '운동 지도', 'NEXT_CHECK_DATE': '2026-10-30', 'STATUS': '진행 중', 'COMPLETED_DATE': ''}
    return {**values, **changes}


def test_db_records_are_read_as_csv_like_text(session, monkeypatch):
    """DB 값(정수 번호, 날짜, UTC 시각, NULL)을 CSV 때와 같은 문자열로 바꾸고, 저장하면 캐시를 비우는지 확인합니다."""
    reads = []
    row = {'RECORD_ID': pd.Series(['7'], dtype='string'), 'SOLDIER_ID': pd.Series(['s1'], dtype='string'),
           'CREATED_AT': [datetime(2026, 10, 30, 1, 2, 3, 4, tzinfo=timezone.utc)],
           'UPDATED_AT': [datetime(2026, 10, 30, 1, 2, 3, 4, tzinfo=timezone.utc)],
           'ASSIGNEE': ['담당자'], 'COUNSELING_DATE': [date(2026, 10, 27)], 'COUNSELING_CONTENT': [None],
           'ACTION_CONTENT': ['운동 지도'], 'NEXT_CHECK_DATE': [date(2026, 10, 30)], 'STATUS': ['진행 중'],
           'COMPLETED_DATE': [None]}
    monkeypatch.setattr(store, 'read_uncached', lambda sql: reads.append(sql) or pd.DataFrame(row))

    records = store.load_records('followup_records')
    store.load_records('followup_records')

    assert records.columns.tolist() == store.COMMON + store.FIELDS['followup_records']
    assert records.iloc[0].tolist() == ['7', 's1', '2026-10-30T10:02:03.000004+09:00', '2026-10-30T10:02:03.000004+09:00',
                                        '담당자', '2026-10-27', '', '운동 지도', '2026-10-30', '진행 중', '']
    assert len(reads) == 1  # 두 번째는 캐시
    store.save_record('followup_records', _followup())
    store.load_records('followup_records')
    assert len(reads) == 2  # 저장하면 캐시를 비운다


def test_injury_records_get_soldier_from_injuries(session, monkeypatch):
    """부상 후속조치에는 군번 컬럼이 없어 부상 기록과 이어 군번을 붙이는지 확인합니다."""
    sqls = []
    monkeypatch.setattr(store, 'read_uncached', lambda sql: sqls.append(sql) or pd.DataFrame())

    records = store.load_records('injury_followup')

    assert 'JOIN injuries i ON i.injury_id = t.injury_id' in sqls[0] and 'i.soldier_id' in sqls[0]
    assert records.empty and records.columns.tolist() == store.COMMON + store.FIELDS['injury_followup']


def test_new_record_is_inserted_with_typed_values(session):
    record_id = store.save_record('followup_records', _followup())

    sql, params = session.calls[0]
    assert sql.startswith('INSERT INTO fitness_followups (soldier_id, assignee') and sql.endswith('RETURNING record_id')
    assert params['counseling_date'] == date(2026, 10, 27) and params['counseling_content'] is None
    assert params['soldier_id'] == 's1' and params['now'].tzinfo is not None
    assert record_id == '7'


def test_update_requires_unchanged_record(session):
    """화면을 연 뒤 다른 곳에서 바뀌었으면(UPDATE 0행) 저장하지 않고 알리는지 확인합니다."""
    expected = '2026-10-30T10:02:03.000004+09:00'
    assert store.save_record('followup_records', _followup(), record_id='7', expected_updated=expected) == '7'
    sql, params = session.calls[-1]
    assert 'WHERE record_id = :record_id AND updated_at = :expected AND soldier_id = :soldier_id' in sql
    assert params['record_id'] == 7 and params['expected'] == datetime.fromisoformat(expected)

    session.update_rowcount = 0
    with pytest.raises(ValueError, match='다른 화면에서 기록이 변경'):
        store.save_record('followup_records', _followup(), record_id='7', expected_updated=expected)


def test_injury_followup_must_belong_to_selected_soldier(session):
    """고른 부상이 그 장병의 것이 아니면 저장하지 않는지 확인합니다."""
    record = {'SOLDIER_ID': 's1', 'INJURY_ID': '3', 'CHECK_DATE': '2026-10-30', 'STATUS': '점검 대기',
              'RECOVERY_STATUS': '확인 중'}
    session.owner = None

    with pytest.raises(ValueError, match='선택 장병의 부상'):
        store.save_record('injury_followup', record)

    assert len(session.calls) == 1 and session.calls[0][1] == {'injury_id': 3, 'soldier_id': 's1'}


def test_group_followups_are_inserted_in_one_statement(session):
    saved = store.save_followups_batch(['a', 'b', 'a'], _followup())

    (sql, rows), = session.calls
    assert saved == 2 and sql.startswith('INSERT INTO fitness_followups') and 'RETURNING' not in sql
    assert [row['soldier_id'] for row in rows] == ['a', 'b']


def test_csv_mode_does_not_touch_db(session, tmp_path, monkeypatch):
    """CSV 모드면 DB를 읽지 않고 MANAGEMENT_DIR의 CSV를 쓰는지 확인합니다."""
    monkeypatch.setenv('DASHBOARD_DATA_SOURCE', 'csv')
    monkeypatch.setattr(store, 'read_uncached', lambda sql: pytest.fail('DB를 읽으면 안 됩니다.'))

    assert store.load_records('followup_records', tmp_path).empty
    assert store.save_record('followup_records', _followup(), tmp_path)
    assert not session.calls and len(store.load_records('followup_records', tmp_path)) == 1
