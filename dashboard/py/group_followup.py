"""현재 등급·운동유형 그룹에 공통 후속조치를 등록하는 입력 화면입니다."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.py.management_store import STATUSES, save_followups_batch


def render_group_followup(people: pd.DataFrame) -> None:
    """검색어와 무관하게 현재 등급·운동유형 조건의 전체 장병에게 등록합니다."""
    targets=people.drop_duplicates('SOLDIER_ID')
    count=len(targets)
    st.subheader('그룹 후속조치 등록')
    st.write(f'현재 선택한 등급·운동유형에 해당하는 **{count:,}명**에게 같은 후속조치를 등록합니다.')
    st.caption('그룹 인원은 저장 시점에 확정됩니다. 장병별 독립 기록으로 추가되며 기존 기록을 덮어쓰지 않습니다. 등록 후 장병별 화면에서 각각 수정할 수 있습니다.')
    st.dataframe(targets[['SOLDIER_ID','SOLDIER_NAME','UNIT_NAME','RISK_LEVEL','TYPE_NAME']].rename(columns={
        'SOLDIER_ID':'장병번호','SOLDIER_NAME':'이름','UNIT_NAME':'부대','RISK_LEVEL':'대상자 등급','TYPE_NAME':'운동유형'}),
        hide_index=True,width='stretch')
    if not count:
        st.info('선택 조건에 해당하는 장병이 없습니다. 등급 또는 운동유형 조건을 변경하세요.')
        return
    today=datetime.now(ZoneInfo('Asia/Seoul')).date()
    with st.form('group-followup-form'):
        owner=st.text_input('담당자',key='group-followup-owner').strip()
        left,right=st.columns(2)
        counseling=left.date_input('상담일',value=today,key='group-followup-counseling')
        check=right.date_input('다음 점검일',value=today,key='group-followup-check')
        counseling_content=st.text_area('공통 상담 내용',key='group-followup-counseling-content').strip()
        action=st.text_area('공통 후속조치 내용',key='group-followup-action').strip()
        left,right=st.columns(2)
        status=left.selectbox('진행 상태',STATUSES,key='group-followup-status')
        completed=right.date_input('완료일 (완료 상태만 입력)',value=None,key='group-followup-completed')
        st.caption('다음 점검일은 상담일 이후로 지정하세요. 완료 상태일 때만 완료일을 입력합니다.')
        if st.form_submit_button(f'{count:,}명에게 후속조치 등록',type='primary'):
            values=dict(ASSIGNEE=owner,COUNSELING_DATE=counseling.isoformat(),
                        COUNSELING_CONTENT=counseling_content,ACTION_CONTENT=action,
                        NEXT_CHECK_DATE=check.isoformat(),STATUS=status,
                        COMPLETED_DATE=completed.isoformat() if completed else '')
            try:
                saved=save_followups_batch(targets.SOLDIER_ID.tolist(),values)
                st.session_state['management_notice']=f'그룹 {saved:,}명에게 후속조치를 등록했습니다.'
                st.rerun()
            except (OSError,ValueError,KeyError) as error:
                st.error(f'그룹 후속조치를 저장하지 못했습니다: {error}')
