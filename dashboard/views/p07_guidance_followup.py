"""7번 화면: 미달·악화 분석 대상자의 체력 지도·후속조치를 관리합니다."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from config import MANAGEMENT_DIR
from dashboard.py.management_store import load_records
from dashboard.py.management_forms import editor, LABELS
from dashboard.py.management_targets_data import load_targets
from data.scripts.analysis.analysis2.fitness_overview import EVENTS
from data.scripts.analysis.analysis2.management_targets import REASONS
from data.scripts.fitness_standards import grade_cut
from data.scripts.paths import SYNTHETIC_PERSONNEL_PATH
from data.scripts.utils import read_text_csv, require_columns

KINDS=['exercise_plans','exercise_participation','followup_records']


def render() -> None:
    """미달·악화 대상과 기존 체력 관리 기록을 분리해 조회합니다."""
    st.caption('장병 체력관리 / 07')
    st.title('체력 지도·후속조치 관리')
    st.write('미달·악화 분석 대상자의 운동 지도·참여와 상담·후속조치를 기록합니다.')
    if notice:=st.session_state.pop('management_notice',None):
        st.success(notice)
    try:
        people=read_text_csv(SYNTHETIC_PERSONNEL_PATH)
        require_columns(people,['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME'])
        if people.SOLDIER_ID.duplicated().any():
            raise ValueError('장병 명단 식별자 중복')
        analysis,_,_=load_targets()
        latest=analysis.sort_values('ROUND',kind='stable').drop_duplicates('SOLDIER_ID',keep='last')
        current_ids=latest.loc[latest.MANAGED,'SOLDIER_ID']
        records={kind:load_records(kind) for kind in KINDS}
    except (OSError,ValueError,KeyError) as error:
        st.error(f'관리 자료를 읽을 수 없습니다: {error}')
        st.code('python -m data.scripts.analysis.analysis2.management_targets',language='powershell')
        st.stop()
    st.sidebar.header('관리 대상')
    chosen=st.sidebar.multiselect('관리 사유',list(REASONS.values()),
        help='선택하지 않으면 전체 사유를 표시합니다. 여러 개 선택하면 하나 이상 해당하는 장병을 표시합니다.')
    eligible=set(current_ids)
    population_analysis=latest.loc[latest.SOLDIER_ID.isin(eligible)]
    st.subheader('관리 사유별 대상 인원')
    st.markdown('''<style>
        div[class*="st-key-selected_reason_"] {
            background-color: #173b70;
            border: 2px solid #2563eb;
            border-radius: 12px;
        }
        div[class*="st-key-selected_reason_"] [data-testid="stMetric"] *,
        div[class*="st-key-selected_reason_"] [data-testid="stCaptionContainer"] * {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
    </style>''',unsafe_allow_html=True)
    for column,(flag,label) in zip(st.columns(4),REASONS.items()):
        selected=label in chosen
        with column.container(border=True,key=f'{"selected" if selected else "unselected"}_reason_{flag}'):
            st.metric(label,f'{population_analysis.loc[population_analysis[flag],"SOLDIER_ID"].nunique():,}명')
            if selected:
                st.caption('✓ 선택됨')
    st.caption('선택한 조회 대상의 장병별 최신 측정 기준입니다. 사유별 인원은 중복될 수 있습니다.')
    if chosen:
        flags=[flag for flag,label in REASONS.items() if label in chosen]
        eligible &= set(population_analysis.loc[population_analysis[flags].any(axis=1),'SOLDIER_ID'])
    st.sidebar.metric('선택 조건 대상 인원',f'{len(eligible & set(people.SOLDIER_ID)):,}명')
    people=people.loc[people.SOLDIER_ID.isin(eligible)].copy()
    basis_columns=['SOLDIER_ID','ROUND','MESURE_DE','AGE','BMI','BMI_GROUP',
                   'FAIL_COUNT','EVALUATED_COUNT','FAILED_EVENTS','SELECTION_REASONS',
                   *EVENTS,*[f'{event}_GRADE' for event in EVENTS]]
    basis=latest[basis_columns]
    people=people.merge(basis,on='SOLDIER_ID',how='left',validate='one_to_one')
    st.caption('대상 자료: 미달·악화 분석 management_targets.csv · 장병별 최신 측정 기준. 과거 기록은 대상 제외 후에도 보존합니다.')
    st.subheader('후속조치 진행 현황')
    col1,col2=st.columns(2)
    owner=col1.selectbox('집계 담당자',['전체',*sorted(records['followup_records'].loc[records['followup_records'].SOLDIER_ID.isin(eligible),'ASSIGNEE'].unique())])
    period=col2.selectbox('집계 기간',['전체','이번 달','올해'],help='상담일 기준으로 기록을 조회합니다. 관리 대상 인원은 왼쪽 관리 사유에 해당하는 전체 장병 수입니다.')
    scope=records['followup_records'].loc[records['followup_records'].SOLDIER_ID.isin(eligible)]
    if owner!='전체':
        scope=scope.loc[scope.ASSIGNEE.eq(owner)]
    today=datetime.now(ZoneInfo('Asia/Seoul')).date()
    if period!='전체':
        dates=pd.to_datetime(scope.COUNSELING_DATE,errors='coerce')
        mask=dates.dt.year.eq(today.year)
        if period=='이번 달':
            mask &= dates.dt.month.eq(today.month)
        scope=scope.loc[mask]
    latest_followup=scope.sort_values(['COUNSELING_DATE','UPDATED_AT'],kind='stable').drop_duplicates('SOLDIER_ID',keep='last')
    total=people.SOLDIER_ID.nunique()
    completed=int(latest_followup.STATUS.eq('완료').sum())
    ongoing=int(latest_followup.STATUS.eq('진행 중').sum())
    waiting=total-completed-ongoing
    for column,label,value in zip(st.columns(5),['관리 대상 인원','완료','진행 중','점검 대기','완료율'],
        [f'{total:,}명',f'{completed:,}명',f'{ongoing:,}명',f'{waiting:,}명',f'{completed/total*100:.1f}%' if total else '해당 없음']):
        column.metric(label,value,border=True)
    st.caption('완료율 = 완료 인원 ÷ 관리 대상 인원. 관리 대상은 선택한 관리 사유에 해당하는 전체 장병이며 중복 집계하지 않습니다. 상태는 담당자·기간 조건에 맞는 장병별 최신 상담 기록 기준입니다. 해당 기록이 없거나 최신 상태가 점검 대기·취소이면 점검 대기에 포함합니다.')
    if not scope.empty:
        counts=scope.STATUS.value_counts().rename_axis('상태').reset_index(name='건수')
        st.plotly_chart(px.bar(counts,x='상태',y='건수',text='건수'),width='stretch')
    else:
        st.info('장병 정보는 연결되어 있습니다. 현재 범위의 후속조치 입력 기록이 아직 0건입니다.')
    with st.expander('후속조치 전체 명단·점검 예정'):
        view=scope.copy()
        view['점검기한경과']=(view.NEXT_CHECK_DATE.lt(today.isoformat())&~view.STATUS.isin(['완료','취소']))
        st.dataframe(view.rename(columns=LABELS),hide_index=True,width='stretch')
    st.sidebar.header('관리할 장병')
    search=st.sidebar.text_input('이름·장병번호 검색')
    shown=people.loc[people.SOLDIER_NAME.str.contains(search,regex=False)|people.SOLDIER_ID.str.contains(search,regex=False)] if search else people
    st.sidebar.metric('검색 결과 인원',f'{shown.SOLDIER_ID.nunique():,}명')
    if shown.empty:
        st.info('조회 대상 또는 검색 조건에 맞는 장병이 없습니다. 기존 기록은 보존되어 있습니다.');st.stop()
    lookup=shown.set_index('SOLDIER_ID')
    soldier=st.sidebar.selectbox('장병 선택',shown.SOLDIER_ID.tolist(),format_func=lambda sid:f'{lookup.loc[sid,"SOLDIER_NAME"]} · {sid}')
    person=lookup.loc[soldier]
    with st.container(border=True):
        st.subheader('선택 장병 정보')
        st.write(f'**{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}**')
        st.caption(f'장병번호: {soldier} · 신상은 합성 자료입니다.')
        if pd.notna(person.ROUND):
            measured=pd.to_datetime(str(person.MESURE_DE).removesuffix('.0'),format='%Y%m%d',errors='coerce')
            measured_label=measured.strftime('%Y-%m-%d') if pd.notna(measured) else '확인 필요'
            st.caption(f'최신 {int(person.ROUND)}차 측정 · 측정일 {measured_label}')
            age=f'{int(person.AGE)}세' if pd.notna(person.AGE) else '정보 없음'
            bmi=f'{person.BMI:.2f}' if pd.notna(person.BMI) else '정보 없음'
            fail=f'{int(person.FAIL_COUNT)}개' if pd.notna(person.FAIL_COUNT) else '판정 불완전'
            for col,label,value in zip(st.columns(3),['측정 당시 나이','BMI','미달 종목 수'],[age,bmi,fail]):
                col.metric(label,value)
            st.write('미달 종목: '+(person.FAILED_EVENTS or '확인된 미달 없음'))
            st.write('선정 사유: '+(person.SELECTION_REASONS or '현재 선정 조건 없음'))
            measurements=[]
            for event,(label,unit) in EVENTS.items():
                grade=person[f'{event}_GRADE']
                measurements.append({'종목':label,'측정값':person[event],'단위':unit,
                    '등급':'판정 불가' if pd.isna(grade) else '3등급 미만' if grade==0 else f'{int(grade)}등급',
                    '3등급 하한':grade_cut(event,3)})
            st.dataframe(pd.DataFrame(measurements),hide_index=True,width='stretch')
            if person.EVALUATED_COUNT<4:
                st.caption('판정 불가 종목이 있습니다. 미달 개수가 빈칸이면 전 종목 통과로 해석하지 않습니다.')
        else:
            st.info('현재 분석에 연결된 측정 자료가 없는 기존 기록 보유자입니다. 관리 기록은 유지됩니다.')
        if soldier not in set(current_ids):
            st.caption('현재 선정 대상에서는 제외되었지만 기존 관리 기록을 조회하고 있습니다.')
    st.caption('상단 완료율은 왼쪽 조회 대상 범위에 담당자·기간 필터를 적용한 집계입니다. 아래 기록은 선택 장병 기준입니다.')
    labels=['운동 지도 계획','운동 참여 기록','상담·후속조치']
    for tab,kind in zip(st.tabs(labels),KINDS):
        with tab:
            editor(kind,soldier,records,pd.DataFrame(columns=['SOLDIER_ID']))
    with st.expander('입력 자료 보관 안내'):
        st.write(f'저장 위치: {MANAGEMENT_DIR}')
        st.write('입력 기록은 별도 CSV에 저장하며 분석 재실행으로 초기화하지 않습니다. 실제 확인한 체력 지도·상담 내용만 입력합니다. 부상 회복·운동 제한은 8번에서 관리합니다.')
        st.caption('여러 화면에서 동시에 수정하면 충돌을 안내합니다. 최신 기록을 다시 읽고 수정하세요. 원본 신상·부상은 합성 자료입니다.')

    st.subheader('선택 조건에 해당하는 장병 명단')
    st.write('관리 사유: '+(' / '.join(chosen) if chosen else '전체'))
    st.caption(f'총 {shown.SOLDIER_ID.nunique():,}명 · 아래 명단에 있는 장병만 왼쪽 장병 선택에 표시됩니다.')
    roster_columns=['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME','ROUND','FAIL_COUNT','SELECTION_REASONS']
    roster=shown[roster_columns].rename(columns={
        'SOLDIER_ID':'장병번호','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속',
        'ROUND':'최신 측정 회차','FAIL_COUNT':'미달 종목 수','SELECTION_REASONS':'선정 사유'})
    st.dataframe(roster,hide_index=True,width='stretch')