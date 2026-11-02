"""상담·후속조치와 부상 후속조치 기록을 읽고 저장합니다.

- 상담·후속조치(followup_records)와 부상 후속조치(injury_followup)는 DB 모드면 DB(fitness_followups,
  injury_followups)에 INSERT/UPDATE하고, CSV 모드면 MANAGEMENT_DIR의 CSV에 씁니다(dashboard.data_source).
  운동 지도 계획·참여 기록은 2026-10-30 회의 결정으로 뺐습니다.
- 어느 쪽이든 화면에는 같은 모양(COMMON + FIELDS 컬럼, 값은 모두 문자열, 빈 값은 '')으로 돌려줍니다.
  DB 기록 번호는 자동 정수, 날짜는 YYYY-MM-DD, 시각은 KST ISO 문자열입니다.
- DB 읽기는 캐시하고 저장할 때마다 비웁니다(저장 직후 바로 보이도록).
- 수정은 화면을 연 뒤 다른 곳에서 바뀌었는지 UPDATED_AT으로 확인합니다(CSV는 파일 잠금, DB는 UPDATE 조건).
"""

import os
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy import text

from config import MANAGEMENT_DIR
from dashboard.data_source import CSV, resolve_source
from dashboard.db import read_uncached, transaction

COMMON=['RECORD_ID','SOLDIER_ID','CREATED_AT','UPDATED_AT']
FIELDS={
    'followup_records':['ASSIGNEE','COUNSELING_DATE','COUNSELING_CONTENT','ACTION_CONTENT','NEXT_CHECK_DATE','STATUS','COMPLETED_DATE'],
    'injury_followup':['INJURY_ID','CHECK_DATE','STATUS','ACTION_CONTENT','RECOVERY_STATUS','RESTRICTION','RESTRICTION_START','RESTRICTION_END','NOTE'],
}
STATUSES=['점검 대기','진행 중','완료','취소']

# DB에 테이블이 있는 기록 종류 -> 테이블 이름(setup_database.DB_TABLE_NAMES와 같게)
DB_TABLES={'followup_records':'fitness_followups','injury_followup':'injury_followups'}
DATE_FIELDS={'COUNSELING_DATE','NEXT_CHECK_DATE','COMPLETED_DATE','CHECK_DATE','RESTRICTION_START','RESTRICTION_END'}
INT_FIELDS={'INJURY_ID'}
KST=ZoneInfo('Asia/Seoul')
CONFLICT_MESSAGE='다른 화면에서 기록이 변경됐습니다. 새로고침 후 다시 수정하세요.'


def uses_db(kind: str, source: str | None=None) -> bool:
    """이 기록 종류를 DB에서 읽고 쓰는지(DB 모드이고 DB 테이블이 있는 종류인지) 돌려줍니다."""
    return kind in DB_TABLES and resolve_source(source)!=CSV


def _select_sql(kind: str) -> str:
    """기록을 화면 컬럼 순서로 읽는 SQL. 부상 후속조치는 군번이 없어 부상 기록과 이어 군번을 붙인다."""
    fields=', '.join(f't.{field.lower()}' for field in FIELDS[kind])
    if kind=='injury_followup':
        soldier,join='i.soldier_id','JOIN injuries i ON i.injury_id = t.injury_id'
    else:
        soldier,join='t.soldier_id',''
    return (f'SELECT t.record_id, {soldier}, t.created_at, t.updated_at, {fields} FROM {DB_TABLES[kind]} t {join} '
            'ORDER BY t.updated_at, t.record_id')


def _as_text(value) -> str:
    """DB 값을 CSV로 읽던 때와 같은 문자열로 바꿉니다(빈 값 '', 날짜 YYYY-MM-DD, 시각 KST ISO)."""
    if value is None or (not isinstance(value,(str,date)) and pd.isna(value)):
        return ''
    if isinstance(value,datetime):
        return value.astimezone(KST).isoformat(timespec='microseconds')
    if isinstance(value,date):
        return value.isoformat()
    return str(value)


@st.cache_data(show_spinner=False)
def _load_records_db(kind: str) -> pd.DataFrame:
    columns=COMMON+FIELDS[kind]
    frame=read_uncached(_select_sql(kind))
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return frame[columns].map(_as_text)


def _db_params(kind: str, record: dict) -> dict:
    """화면 입력(문자열)을 DB 값으로 바꿉니다. 빈 칸은 NULL, 날짜는 date, 번호는 int."""
    params={}
    for field in FIELDS[kind]:
        value=str(record.get(field,''))
        if value=='':
            params[field.lower()]=None
        elif field in DATE_FIELDS:
            params[field.lower()]=date.fromisoformat(value)
        elif field in INT_FIELDS:
            params[field.lower()]=int(value)
        else:
            params[field.lower()]=value
    if kind!='injury_followup':
        params['soldier_id']=record['SOLDIER_ID']
    return params


def _db_columns(kind: str) -> list[str]:
    """INSERT할 컬럼(기록 번호·시각 제외). 부상 후속조치에는 군번 컬럼이 없다."""
    columns=[field.lower() for field in FIELDS[kind]]
    return columns if kind=='injury_followup' else ['soldier_id',*columns]


def _insert_sql(kind: str) -> str:
    columns=_db_columns(kind)
    return (f'INSERT INTO {DB_TABLES[kind]} ({", ".join(columns)}, created_at, updated_at) '
            f'VALUES ({", ".join(":"+column for column in columns)}, :now, :now)')


def _save_record_db(kind: str, record: dict, record_id: str, expected_updated: str) -> str:
    """기록 하나를 INSERT하거나, 화면을 연 뒤 바뀌지 않았을 때만 UPDATE합니다."""
    params=dict(_db_params(kind,record),now=datetime.now(KST))
    with transaction() as session:
        if kind=='injury_followup':
            # 군번 컬럼이 없으므로 고른 부상이 그 장병의 것인지 확인한다.
            owner=session.execute(text('SELECT 1 FROM injuries WHERE injury_id = :injury_id AND soldier_id = :soldier_id'),
                                  {'injury_id':params['injury_id'],'soldier_id':record['SOLDIER_ID']}).first()
            if owner is None:
                raise ValueError('선택 장병의 부상 기록이 아닙니다.')
        if not record_id:
            saved=session.execute(text(_insert_sql(kind)+' RETURNING record_id'),params).scalar_one()
        else:
            try:
                params.update(record_id=int(record_id),expected=datetime.fromisoformat(expected_updated))
            except ValueError as error:
                raise ValueError(CONFLICT_MESSAGE) from error
            assignments=', '.join(f'{column} = :{column}' for column in _db_columns(kind) if column!='soldier_id')
            # 기록의 장병은 바꿀 수 없다(체력 후속조치는 군번이 같아야 수정됨).
            owner=' AND soldier_id = :soldier_id' if kind!='injury_followup' else ''
            result=session.execute(text(f'UPDATE {DB_TABLES[kind]} SET {assignments}, updated_at = :now '
                                        f'WHERE record_id = :record_id AND updated_at = :expected{owner}'),params)
            if result.rowcount!=1:
                raise ValueError(CONFLICT_MESSAGE)
            saved=params['record_id']
    _clear_record_caches()
    return str(saved)


# 메인 화면 완료율: 기록 전체를 받지 않고 DB에서 센다.
# - 체력: 미달 확률이 기준 이상(경계1~3등급)인 장병 중 완료 기록이 하나라도 있는 장병 수
# - 부상: 부상별 가장 최근 기록(확인일, 같으면 수정 시각)이 완료인 부상 수
COMPLETION_SQL = """
SELECT
    (SELECT count(*) FROM fitness_followups) AS fitness_records,
    (SELECT count(DISTINCT f.soldier_id)
        FROM fitness_followups f
        JOIN soldier_failure_probabilities p USING (soldier_id)
        WHERE f.status = '완료' AND p.failure_probability >= :threshold) AS fitness_completed,
    (SELECT count(*) FROM injury_followups) AS injury_records,
    (SELECT count(*)
        FROM (SELECT DISTINCT ON (injury_id) status
              FROM injury_followups
              ORDER BY injury_id, check_date DESC, updated_at DESC) latest
        WHERE status = '완료') AS injury_completed
"""


@st.cache_data(show_spinner=False)
def load_completion_counts(threshold: float) -> dict[str, int]:
    """완료율 계산용 건수(fitness_records, fitness_completed, injury_records, injury_completed). 저장할 때 캐시를 비웁니다."""
    row = read_uncached(COMPLETION_SQL, {'threshold': threshold}).iloc[0]
    return {name.lower(): int(value) for name, value in row.items()}


def _clear_record_caches() -> None:
    """기록을 저장하면 기록 목록과 완료율 집계 캐시를 비워 바로 반영되게 합니다."""
    _load_records_db.clear()
    load_completion_counts.clear()


def load_records(kind: str, directory: Path=MANAGEMENT_DIR, source: str | None=None) -> pd.DataFrame:
    """기록을 읽습니다. CSV 모드에서 없는 파일은 빈 테이블로 반환하고 손상된 기존 파일은 덮어쓰지 않습니다."""
    if uses_db(kind,source):
        return _load_records_db(kind)
    columns=COMMON+FIELDS[kind]
    path=directory/f'{kind}.csv'
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame=pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    if kind=='injury_followup' and list(frame.columns)==[c for c in columns if c not in ['STATUS','ACTION_CONTENT']]:
        frame=frame.assign(STATUS='점검 대기',ACTION_CONTENT='')[columns]
    if list(frame.columns)!=columns or frame.RECORD_ID.duplicated().any():
        raise ValueError(f'{path.name}: 컬럼 또는 기록 식별자 오류')
    return frame


def validate(kind: str, record: dict) -> None:
    """필수 입력·날짜·상태·수량을 검사합니다."""
    if not str(record.get('SOLDIER_ID','')).strip():
        raise ValueError('장병을 선택하세요.')
    required={'followup_records':['ASSIGNEE','COUNSELING_DATE','ACTION_CONTENT','NEXT_CHECK_DATE'],
        'injury_followup':['INJURY_ID','CHECK_DATE','RECOVERY_STATUS']}[kind]
    for field in required:
        if not str(record.get(field,'')).strip():
            raise ValueError(f'필수 항목을 입력하세요: {field}')
    for field in FIELDS[kind]:
        value=record.get(field,'')
        if value and (field.endswith('_DATE') or field in ['RESTRICTION_START','RESTRICTION_END']):
            date.fromisoformat(str(value))
    start,end='RESTRICTION_START','RESTRICTION_END'
    if record.get(end) and not record.get(start):
        raise ValueError('종료일을 입력하면 시작일도 필요합니다.')
    if record.get(start) and record.get(end) and record[end]<record[start]:
        raise ValueError('종료일이 시작일보다 빠릅니다.')
    if 'STATUS' in FIELDS[kind] and record.get('STATUS') not in STATUSES:
        raise ValueError('잘못된 진행 상태입니다.')
    if kind=='injury_followup' and record.get('STATUS')=='완료' and not str(record.get('ACTION_CONTENT','')).strip():
        raise ValueError('완료 처리하려면 후속조치 내용을 입력하세요.')
    if kind=='followup_records':
        if record['NEXT_CHECK_DATE']<record['COUNSELING_DATE']:
            raise ValueError('다음 점검일이 상담일보다 빠릅니다.')
        if record['STATUS']=='완료':
            if not record.get('COMPLETED_DATE'):
                raise ValueError('완료일을 입력하세요.')
            if record['COMPLETED_DATE']<record['COUNSELING_DATE']:
                raise ValueError('완료일이 상담일보다 빠릅니다.')
        elif record.get('COMPLETED_DATE'):
            raise ValueError('완료 상태에서만 완료일을 입력하세요.')


def save_record(kind: str, record: dict, directory: Path=MANAGEMENT_DIR,
                record_id: str='', expected_updated: str='', source: str | None=None) -> str:
    """기록을 추가하거나 수정합니다. DB는 트랜잭션, CSV는 잠금·변경 충돌 확인·임시 파일 교체로 저장합니다."""
    validate(kind,record)
    if uses_db(kind,source):
        return _save_record_db(kind,record,record_id,expected_updated)
    directory.mkdir(parents=True,exist_ok=True)
    lock=directory/'.write.lock'
    try:
        descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError('다른 저장이 진행 중입니다. 잠시 후 다시 시도하세요.') from error
    temp=None
    try:
        os.close(descriptor)
        frame=load_records(kind,directory,CSV)
        now=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='microseconds')
        if record_id:
            old=frame.loc[frame.RECORD_ID.eq(record_id)]
            if len(old)!=1 or old.iloc[0].UPDATED_AT!=expected_updated:
                raise ValueError('다른 화면에서 기록이 변경됐습니다. 새로고침 후 다시 수정하세요.')
            if old.iloc[0].SOLDIER_ID!=record['SOLDIER_ID']:
                raise ValueError('기록의 장병을 변경할 수 없습니다.')
            created=old.iloc[0].CREATED_AT
        else:
            record_id=uuid4().hex
            created=now
        row={field:str(record.get(field,'')) for field in FIELDS[kind]}
        row.update(RECORD_ID=record_id,SOLDIER_ID=record['SOLDIER_ID'],CREATED_AT=created,UPDATED_AT=now)
        frame=frame.loc[~frame.RECORD_ID.eq(record_id)]
        frame=pd.concat([frame,pd.DataFrame([row])],ignore_index=True)[COMMON+FIELDS[kind]]
        temp=directory/f'.{uuid4().hex}.tmp'
        frame.to_csv(temp,index=False,encoding='utf-8-sig')
        os.replace(temp,directory/f'{kind}.csv')
        return record_id
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
        lock.unlink(missing_ok=True)


def save_followups_batch(soldier_ids: list[str], values: dict,
                         directory: Path=MANAGEMENT_DIR, source: str | None=None) -> int:
    """그룹 전체를 검증한 뒤 후속조치를 한 번에 추가합니다(하나라도 실패하면 아무것도 저장하지 않음)."""
    targets=list(dict.fromkeys(soldier_ids))
    if not targets:
        raise ValueError('후속조치를 등록할 장병이 없습니다.')
    for soldier in targets:
        validate('followup_records',dict(values,SOLDIER_ID=soldier))
    if uses_db('followup_records',source):
        now=datetime.now(KST)
        rows=[dict(_db_params('followup_records',dict(values,SOLDIER_ID=soldier)),now=now) for soldier in targets]
        with transaction() as session:
            session.execute(text(_insert_sql('followup_records')),rows)
        _clear_record_caches()
        return len(targets)
    directory.mkdir(parents=True,exist_ok=True)
    lock=directory/'.write.lock'
    try:
        descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError('다른 저장이 진행 중입니다. 잠시 후 다시 시도하세요.') from error
    temp=None
    try:
        os.close(descriptor)
        frame=load_records('followup_records',directory,CSV)
        now=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='microseconds')
        rows=[]
        for soldier in targets:
            row={field:str(values.get(field,'')) for field in FIELDS['followup_records']}
            row.update(RECORD_ID=uuid4().hex,SOLDIER_ID=soldier,CREATED_AT=now,UPDATED_AT=now)
            rows.append(row)
        frame=pd.concat([frame,pd.DataFrame(rows)],ignore_index=True)[COMMON+FIELDS['followup_records']]
        temp=directory/f'.{uuid4().hex}.tmp'
        frame.to_csv(temp,index=False,encoding='utf-8-sig')
        os.replace(temp,directory/'followup_records.csv')
        return len(targets)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
        lock.unlink(missing_ok=True)


def followup_metrics(frame: pd.DataFrame) -> dict:
    """취소를 제외한 후속조치 건수를 분모로 완료율을 계산합니다."""
    active=frame.loc[frame.STATUS.ne('취소')]
    complete=int(active.STATUS.eq('완료').sum())
    return {'전체':len(frame),'대상':len(active),'완료':complete,'진행':int(active.STATUS.eq('진행 중').sum()),
            '대기':int(active.STATUS.eq('점검 대기').sum()),'취소':int(frame.STATUS.eq('취소').sum()),
            '완료율':complete/len(active)*100 if len(active) else None}
