"""체력 및 부상 관리 화면에서 재사용하는 기록 입력 폼입니다."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.py.management_store import FIELDS, STATUSES, save_record

LABELS={'RECORD_ID':'기록 번호','SOLDIER_ID':'장병 식별자','CREATED_AT':'최초 저장일','UPDATED_AT':'최종 수정일',
 'ASSIGNEE':'담당자','STATUS':'진행 상태','NOTE':'비고','COUNSELING_DATE':'상담일',
 'COUNSELING_CONTENT':'상담 내용','ACTION_CONTENT':'후속조치 내용','NEXT_CHECK_DATE':'다음 점검일','COMPLETED_DATE':'완료일',
 'INJURY_ID':'부상 번호','CHECK_DATE':'확인일','RECOVERY_STATUS':'회복 상태','RESTRICTION':'확인된 운동 제한',
 'RESTRICTION_START':'제한 시작일','RESTRICTION_END':'제한 종료일'}


def date_value(value, default=None):
    """빈 날짜를 선택 안 함으로 유지합니다."""
    return date.fromisoformat(value) if value else default


def editor(kind: str, soldier: str, all_records: dict, injuries: pd.DataFrame) -> None:
    """선택 장병의 기존 기록을 수정하거나 새 기록을 입력합니다."""
    records=all_records[kind].loc[all_records[kind].SOLDIER_ID.eq(soldier)]
    st.dataframe(records.rename(columns=LABELS),hide_index=True,width='stretch')
    st.download_button('이 기록 CSV 다운로드',records.rename(columns=LABELS).to_csv(index=False).encode('utf-8-sig'),
                       f'{soldier}_{kind}.csv','text/csv',key=f'download_{kind}')
    choices=['새 기록',*records.RECORD_ID.tolist()]
    selected=st.selectbox('입력·수정할 기록',choices,key=f'edit_{kind}_{soldier}',
        format_func=lambda value:value if value=='새 기록' else f'{records.loc[records.RECORD_ID.eq(value),"UPDATED_AT"].iloc[0][:10]} · {value[:8]}')
    old={} if selected=='새 기록' else records.loc[records.RECORD_ID.eq(selected)].iloc[0].to_dict()
    version_key=f'version_{kind}_{soldier}_{selected}'
    if old:
        st.session_state.setdefault(version_key,old['UPDATED_AT'])
    person_injuries=injuries.loc[injuries.SOLDIER_ID.eq(soldier)]
    if kind=='injury_followup' and person_injuries.empty:
        st.info('보유 부상 이력이 없어 연결할 기록이 없습니다. 부상 원본을 확인하세요.');return
    with st.form(f'form_{kind}_{soldier}_{selected}'):
        values={'SOLDIER_ID':soldier}
        fields=FIELDS[kind]
        if kind=='injury_followup':
            fields=[field for field in fields if field!='STATUS']+['STATUS']
        for field in fields:
            label='후속조치 상태' if kind=='injury_followup' and field=='STATUS' else LABELS[field]
            value=old.get(field,'')
            key=f'{kind}_{soldier}_{selected}_{field}'
            if field=='STATUS':
                values[field]=st.selectbox(label,STATUSES,index=STATUSES.index(value) if value in STATUSES else 0,key=key)
            elif field=='INJURY_ID':
                options=person_injuries.INJURY_ID.tolist();lookup=person_injuries.set_index('INJURY_ID')
                values[field]=st.selectbox(label,options,index=options.index(value) if value in options else 0,
                    format_func=lambda v:f'{v} · {lookup.loc[v,"INJURY_LOCATION"]} · {lookup.loc[v,"SEVERITY"]}',key=key)
            elif field.endswith('_DATE') or field in ['RESTRICTION_START','RESTRICTION_END']:
                optional=field in ['COMPLETED_DATE','RESTRICTION_START','RESTRICTION_END']
                chosen=st.date_input(label+(' (선택)' if optional else ''),value=date_value(value,None if optional else datetime.now(ZoneInfo('Asia/Seoul')).date()),key=key)
                values[field]=chosen.isoformat() if chosen else ''
            elif field=='RECOVERY_STATUS':
                options=['확인 중','회복 중','회복 확인','제한 지속','미확인']
                values[field]=st.selectbox(label,options,index=options.index(value) if value in options else 0,key=key)
            elif field in ['ASSIGNEE']:
                values[field]=st.text_input(label,value=value,key=key).strip()
            else:
                values[field]=st.text_area(label,value=value,key=key).strip()
        if kind=='followup_records':
            st.caption('완료 상태이면 완료일을 입력하세요. 진행 중·대기·취소이면 완료일을 비워 두세요. 다음 점검일은 상담일 이후로 지정합니다.')
        if kind=='injury_followup':
            st.caption('부상 확인 및 조치 방침 기록을 마쳤으면 후속조치 상태를 완료로 선택하세요. 완료 시 후속조치 내용이 필요하며, 회복 상태는 별도로 기록합니다.')
        submitted=st.form_submit_button('새 기록 저장' if selected=='새 기록' else '수정 저장',type='primary')
        if submitted:
            try:
                record_id=save_record(kind,values,record_id='' if selected=='새 기록' else selected,expected_updated=st.session_state.get(version_key,''))
                st.session_state.pop(version_key,None)
                st.session_state['management_notice']=f'저장했습니다. 기록 번호 {record_id[:8]}'
                st.rerun()
            except (OSError,ValueError,KeyError,SQLAlchemyError) as error:
                st.error(f'저장하지 못했습니다: {error}')


