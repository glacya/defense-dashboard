import pandas as pd

from dashboard.common.formatting import format_timestamp
from dashboard.py.management_forms import display_records


def test_format_timestamp_uses_requested_second_precision():
    assert format_timestamp('2026-11-02T15:27:11.197000+09:00') == '2026-11-02 15:27:11'


def test_display_records_replaces_internal_id_with_name_and_formats_timestamps():
    records = pd.DataFrame({
        'RECORD_ID': ['internal-id'],
        'SOLDIER_ID': ['soldier-1'],
        'CREATED_AT': ['2026-11-02T15:27:11.197000+09:00'],
        'UPDATED_AT': ['2026-11-02T15:28:11.197000+09:00'],
        'STATUS': ['진행 중'],
    })

    display = display_records(records, {'soldier-1': '홍길동'})

    assert '기록 번호' not in display.columns
    assert display.loc[0, '이름'] == '홍길동'
    assert display.loc[0, '최초 저장일'] == '2026-11-02 15:27:11'
    assert display.loc[0, '최종 수정일'] == '2026-11-02 15:28:11'
