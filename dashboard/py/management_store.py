"""지도·참여·후속조치·부상 관리 CSV를 원자적으로 저장합니다."""

import os
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from config import MANAGEMENT_DIR

COMMON=['RECORD_ID','SOLDIER_ID','CREATED_AT','UPDATED_AT']
FIELDS={
    'exercise_plans':['ASSIGNEE','EXERCISE','START_DATE','END_DATE','PLANNED_SESSIONS','STATUS','NOTE'],
    'exercise_participation':['PLAN_ID','SESSION_DATE','ATTENDED','DURATION_MINUTES','ACTUAL_CONTENT','NOTE'],
    'followup_records':['ASSIGNEE','COUNSELING_DATE','COUNSELING_CONTENT','ACTION_CONTENT','NEXT_CHECK_DATE','STATUS','COMPLETED_DATE'],
    'injury_followup':['INJURY_ID','CHECK_DATE','RECOVERY_STATUS','RESTRICTION','RESTRICTION_START','RESTRICTION_END','NOTE'],
}
STATUSES=['점검 대기','진행 중','완료','취소']


def load_records(kind: str, directory: Path=MANAGEMENT_DIR) -> pd.DataFrame:
    """없는 파일은 빈 테이블로 반환하고 손상된 기존 파일은 덮어쓰지 않습니다."""
    columns=COMMON+FIELDS[kind]
    path=directory/f'{kind}.csv'
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame=pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    if list(frame.columns)!=columns or frame.RECORD_ID.duplicated().any():
        raise ValueError(f'{path.name}: 컬럼 또는 기록 식별자 오류')
    return frame


def validate(kind: str, record: dict) -> None:
    """필수 입력·날짜·상태·수량을 검사합니다."""
    if not str(record.get('SOLDIER_ID','')).strip():
        raise ValueError('장병을 선택하세요.')
    required={'exercise_plans':['ASSIGNEE','EXERCISE','START_DATE','END_DATE'],
        'exercise_participation':['PLAN_ID','SESSION_DATE','ACTUAL_CONTENT'],
        'followup_records':['ASSIGNEE','COUNSELING_DATE','ACTION_CONTENT','NEXT_CHECK_DATE'],
        'injury_followup':['INJURY_ID','CHECK_DATE','RECOVERY_STATUS']}[kind]
    for field in required:
        if not str(record.get(field,'')).strip():
            raise ValueError(f'필수 항목을 입력하세요: {field}')
    for field in FIELDS[kind]:
        value=record.get(field,'')
        if value and (field.endswith('_DATE') or field in ['RESTRICTION_START','RESTRICTION_END']):
            date.fromisoformat(str(value))
    for start,end in [('START_DATE','END_DATE'),('RESTRICTION_START','RESTRICTION_END')]:
        if record.get(end) and not record.get(start):
            raise ValueError('종료일을 입력하면 시작일도 필요합니다.')
        if record.get(start) and record.get(end) and record[end]<record[start]:
            raise ValueError('종료일이 시작일보다 빠릅니다.')
    if 'STATUS' in FIELDS[kind] and record.get('STATUS') not in STATUSES:
        raise ValueError('잘못된 진행 상태입니다.')
    if kind=='exercise_plans' and int(record['PLANNED_SESSIONS'])<1:
        raise ValueError('예정 횟수는 1회 이상이어야 합니다.')
    if kind=='exercise_participation':
        if record.get('ATTENDED') not in ['Y','N'] or int(record.get('DURATION_MINUTES',0))<0:
            raise ValueError('참여 여부 또는 운동 시간이 잘못되었습니다.')
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
                record_id: str='', expected_updated: str='') -> str:
    """잠금·변경 충돌 확인·임시 파일 교체로 기록을 추가하거나 수정합니다."""
    validate(kind,record)
    directory.mkdir(parents=True,exist_ok=True)
    lock=directory/'.write.lock'
    try:
        descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError('다른 저장이 진행 중입니다. 잠시 후 다시 시도하세요.') from error
    temp=None
    try:
        os.close(descriptor)
        frame=load_records(kind,directory)
        if kind=='exercise_participation':
            plans=load_records('exercise_plans',directory)
            linked=plans.loc[plans.RECORD_ID.eq(record['PLAN_ID'])&plans.SOLDIER_ID.eq(record['SOLDIER_ID'])]
            if linked.empty:
                raise ValueError('선택 장병의 지도 계획을 찾을 수 없습니다.')
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
                         directory: Path=MANAGEMENT_DIR) -> int:
    """그룹 전체를 검증한 뒤 기존 후속조치 파일에 한 번에 추가합니다."""
    targets=list(dict.fromkeys(soldier_ids))
    if not targets:
        raise ValueError('후속조치를 등록할 장병이 없습니다.')
    for soldier in targets:
        validate('followup_records',dict(values,SOLDIER_ID=soldier))
    directory.mkdir(parents=True,exist_ok=True)
    lock=directory/'.write.lock'
    try:
        descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError('다른 저장이 진행 중입니다. 잠시 후 다시 시도하세요.') from error
    temp=None
    try:
        os.close(descriptor)
        frame=load_records('followup_records',directory)
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
