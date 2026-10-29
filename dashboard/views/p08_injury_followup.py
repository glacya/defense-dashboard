"""8번 화면: 부상 이력 기반으로 회복 상태와 운동 제한을 기록합니다."""

import streamlit as st

from config import MANAGEMENT_DIR
from dashboard.py.management_store import load_records
from dashboard.py.management_forms import editor, LABELS
from data.scripts.paths import SYNTHETIC_PERSONNEL_PATH, SYNTHETIC_INJURY_PATH
from data.scripts.utils import read_text_csv, require_columns


def render() -> None:
    """부상 원본에 있는 장병과 부상 식별자 기준으로 후속 확인을 저장합니다."""
    st.caption('장병 체력관리 / 08')
    st.title('부상 후속조치 관리')
    st.write('부상 이력에 연결해 실제 확인한 회복 상태와 운동 제한을 기록합니다.')
    if notice:=st.session_state.pop('management_notice',None):
        st.success(notice)
    try:
        people=read_text_csv(SYNTHETIC_PERSONNEL_PATH)
        injuries=read_text_csv(SYNTHETIC_INJURY_PATH)
        require_columns(people,['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME'])
        require_columns(injuries,['INJURY_ID','SOLDIER_ID','INJURY_LOCATION','SEVERITY'])
        if people.SOLDIER_ID.duplicated().any() or injuries.INJURY_ID.duplicated().any():
            raise ValueError('장병 또는 부상 식별자 중복')
        records=load_records('injury_followup')
        if not injuries.SOLDIER_ID.isin(people.SOLDIER_ID).all():
            raise ValueError('장병 명단과 부상 원본 불일치')
    except (OSError,ValueError) as error:
        st.error(f'부상 관리 자료를 읽을 수 없습니다: {error}');st.stop()
    st.caption('대상 자료: SOLDIER_INJURY.csv. 부상 이력이 있는 장병을 조회하며, 후속조치 기록은 부상 번호로 연결합니다. 신상·부상 원본은 합성 자료입니다.')
    active=records.merge(injuries[['INJURY_ID','SOLDIER_ID']],on=['INJURY_ID','SOLDIER_ID'],how='inner',validate='many_to_one')
    has_archived_records=len(records)!=len(active)
    units=sorted(people.UNIT_NAME.dropna().unique().tolist())
    selected_units=st.multiselect('부대 선택',units,
        key='injury_followup_units',placeholder='전체 부대',
        help='선택하지 않으면 전체 부대, 여러 개 선택하면 선택한 부대의 현황과 장병을 조회합니다.')
    if selected_units:
        people=people.loc[people.UNIT_NAME.isin(selected_units)]
        injuries=injuries.loc[injuries.SOLDIER_ID.isin(people.SOLDIER_ID)]
        active=active.loc[active.SOLDIER_ID.isin(people.SOLDIER_ID)]
    visible_records=records.loc[records.SOLDIER_ID.isin(people.SOLDIER_ID)] if selected_units else records
    st.caption('조회 부대: '+(' · '.join(selected_units) if selected_units else '전체 부대'))
    latest=active.sort_values(['CHECK_DATE','UPDATED_AT']).drop_duplicates('INJURY_ID',keep='last')
    for col,label,value in zip(st.columns(4),['부상 이력 장병','부상 건수','확인 기록이 있는 부상','최신 기록상 회복 확인'],
        [f'{injuries.SOLDIER_ID.nunique():,}명',f'{len(injuries):,}건',f'{latest.INJURY_ID.nunique():,}건',f'{int(latest.RECOVERY_STATUS.eq("회복 확인").sum()):,}건']):
        col.metric(label,value,border=True)
    st.caption('회복 상태는 부상별 최신 확인 기록 기준입니다. 확인 기록이 없으면 회복 여부를 알 수 없습니다.')
    if has_archived_records:
        st.warning('현재 부상 원본과 연결되지 않는 과거 관리 기록이 있습니다. 기록을 보존하고 아래에서 제공합니다.')
    with st.expander('조회 부대 부상 후속조치 기록 · 보관 이력 포함'):
        st.dataframe(visible_records.rename(columns=LABELS),hide_index=True,width='stretch')
        st.download_button('조회 부대 부상 후속조치 CSV',visible_records.rename(columns=LABELS).to_csv(index=False).encode('utf-8-sig'),'부상후속조치.csv','text/csv')
    people=people.loc[people.SOLDIER_ID.isin(injuries.SOLDIER_ID)]
    st.subheader('부상 이력 장병')
    search=st.text_input('이름·장병번호 검색')
    if search:
        people=people.loc[people.SOLDIER_NAME.str.contains(search,regex=False)|people.SOLDIER_ID.str.contains(search,regex=False)]
    st.metric('조회 대상 인원',f'{people.SOLDIER_ID.nunique():,}명',border=True)
    if people.empty:
        st.info('부상 이력이 있는 장병 중 조회 조건에 해당하는 사람이 없습니다.');st.stop()
    lookup=people.set_index('SOLDIER_ID')
    soldier=st.selectbox('장병 선택',people.SOLDIER_ID.tolist(),format_func=lambda sid:f'{lookup.loc[sid,"SOLDIER_NAME"]} · {sid}')
    person=lookup.loc[soldier]
    st.subheader(f'{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}')
    st.dataframe(injuries.loc[injuries.SOLDIER_ID.eq(soldier)].rename(columns={'INJURY_ID':'부상 번호','SOLDIER_ID':'장병 식별자','INJURY_CATEGORY':'부상 대분류','INJURY_LOCATION':'부상 부위','SEVERITY':'심각도','PREVENTABILITY':'예방 가능 여부'}),hide_index=True,width='stretch')
    editor('injury_followup',soldier,{'injury_followup':records},injuries)
    st.caption(f'저장: {MANAGEMENT_DIR / "injury_followup.csv"} · 기존 기록은 유지됩니다. 합성 부상 이력으로 회복 상태나 운동 제한을 추정하지 않습니다.')
