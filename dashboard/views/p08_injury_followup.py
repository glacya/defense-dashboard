"""8번 화면: 부상 이력 기반으로 회복 상태와 운동 제한을 기록합니다."""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.common.filters import render_personnel_cards
from dashboard.py.management_store import load_records
from dashboard.py.management_forms import display_records, editor
from dashboard.py import queries
from dashboard.common.table_widgets import render_dataframe


def _load_page_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="injury-followup-data") as executor:
        people_future = executor.submit(queries.load_roster)
        injuries_future = executor.submit(queries.load_injuries)
        records_future = executor.submit(load_records, 'injury_followup')
        people = people_future.result()
        injuries = injuries_future.result()
        records = records_future.result()
    return people, injuries, records


def render() -> None:
    """부상 원본에 있는 장병과 부상 식별자 기준으로 후속 확인을 저장합니다."""
    # st.caption('장병 체력관리 / 08')
    st.title('부상 후속조치 관리')
    st.write('부상 이력에 연결해 실제 확인한 회복 상태와 운동 제한을 기록합니다.')
    if notice:=st.session_state.pop('management_notice',None):
        st.success(notice)
    try:
        # 장병 명단은 다른 화면과 함께 쓰는 캐시. 군번 고유·부상-장병 연결은 DB의 PK·FK가 보장한다.
        people, injuries, records = _load_page_data()
        people=people.astype({'SOLDIER_ID':str})
        # 후속조치 기록은 문자열 ID이므로 조인 키만 맞춘다.
        injuries=injuries.astype({'INJURY_ID':str,'SOLDIER_ID':str})
    except (OSError,ValueError,SQLAlchemyError) as error:
        st.error(f'부상 관리 자료를 읽을 수 없습니다: {error}');st.stop()
    st.caption('부상 이력이 있는 장병을 조회하며, 후속조치 기록은 부상 번호로 연결합니다. 신상·부상 원본은 합성 자료입니다.')
    active=records.merge(injuries[['INJURY_ID','SOLDIER_ID']],on=['INJURY_ID','SOLDIER_ID'],how='inner',validate='many_to_one')
    has_archived_records=len(records)!=len(active)
    if 'REGION_NAME' not in people.columns:  # 지역 컬럼이 없으면 지역 카드 하나로 묶어 표시
        people=people.assign(REGION_NAME='전체')
    soldier_names=dict(zip(people.SOLDIER_ID,people.SOLDIER_NAME))
    people=people.loc[people.SOLDIER_ID.isin(injuries.SOLDIER_ID)]
    selection=render_personnel_cards(people,'injury_followup')
    is_filtered=len(selection.scoped)!=len(people)
    if is_filtered:
        people=selection.scoped
        injuries=injuries.loc[injuries.SOLDIER_ID.isin(people.SOLDIER_ID)]
        active=active.loc[active.SOLDIER_ID.isin(people.SOLDIER_ID)]
    visible_records=records.loc[records.SOLDIER_ID.isin(people.SOLDIER_ID)] if is_filtered else records
    st.caption(f'조회 조건: 지역·부대·계급 카드 선택 · {people.SOLDIER_ID.nunique():,}명' if is_filtered else '조회 조건: 전체')
    latest=active.sort_values(['CHECK_DATE','UPDATED_AT']).drop_duplicates('INJURY_ID',keep='last')
    with st.container(key='injury-followup-summary'):
        for col,label,value in zip(st.columns(4),['부상 이력 장병','부상 건수','확인 기록이 있는 부상','최신 기록상 회복 확인'],
            [f'{injuries.SOLDIER_ID.nunique():,}명',f'{len(injuries):,}건',f'{latest.INJURY_ID.nunique():,}건',f'{int(latest.RECOVERY_STATUS.eq("회복 확인").sum()):,}건']):
            col.metric(label,value,border=True)
    st.caption('회복 상태는 부상별 최신 확인 기록 기준입니다. 확인 기록이 없으면 회복 여부를 알 수 없습니다.')
    if has_archived_records:
        st.warning('현재 부상 원본과 연결되지 않는 과거 관리 기록이 있습니다. 기록을 보존하고 아래에서 제공합니다.')
    with st.expander('조회 부대 부상 후속조치 기록 및 보관 이력 포함'):
        visible_display=display_records(visible_records,soldier_names)
        if visible_records.empty:
            st.info('기록 없음')
        else:
            render_dataframe(visible_display,hide_index=True,width='stretch')
        st.download_button('부대 부상 후속조치 다운로드(CSV)',visible_display.to_csv(index=False).encode('utf-8-sig'),'부상후속조치.csv','text/csv')
    people=people.loc[people.SOLDIER_ID.isin(injuries.SOLDIER_ID)]
    st.subheader('부상 이력 장병')
    search=st.text_input('이름 또는 군번으로 검색')
    if search:
        people=people.loc[people.SOLDIER_NAME.str.contains(search,regex=False)|people.SOLDIER_ID.str.contains(search,regex=False)]
    st.metric('조회 대상 인원',f'{people.SOLDIER_ID.nunique():,}명',border=True)
    if people.empty:
        st.info('기록 없음: 부상 이력이 있는 장병 중 조회 조건에 해당하는 사람이 없습니다.');st.stop()
    lookup=people.set_index('SOLDIER_ID')
    soldier=st.selectbox('장병 선택',people.SOLDIER_ID.tolist(),format_func=lambda sid:f'{lookup.loc[sid,"SOLDIER_NAME"]} · {sid}')
    person=lookup.loc[soldier]
    st.subheader(f'{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}')
    render_dataframe(injuries.loc[injuries.SOLDIER_ID.eq(soldier)].rename(columns={'INJURY_ID':'부상 번호','SOLDIER_ID':'군번','INJURY_CATEGORY':'부상 대분류','INJURY_LOCATION':'부상 부위','SEVERITY':'심각도','PREVENTABILITY':'예방 가능 여부'}),hide_index=True,width='stretch')
    editor('injury_followup',soldier,{'injury_followup':records},injuries,soldier_names)
