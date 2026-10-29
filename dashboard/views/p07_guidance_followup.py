"""7번 화면: 예측 확률의 안전·경계 1~3등급별로 체력 지도·후속조치를 관리합니다."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from config import MANAGEMENT_DIR
from dashboard.py.management_store import load_records
from dashboard.py.management_forms import editor, LABELS
from dashboard.py.followup_probability import RISK_LEVELS, RISK_RANGES, load_probabilities
from dashboard.py.followup_fitness_types import load_fitness_types
from dashboard.py.group_followup import render_group_followup
from data.scripts.analysis.analysis2.fitness_overview import EVENTS
from data.scripts.fitness_standards import grade_cut
from data.scripts.paths import SYNTHETIC_PERSONNEL_PATH, PROCESSED_FITNESS_PATH
from data.scripts.utils import read_text_csv, require_columns

KINDS=['exercise_plans','exercise_participation','followup_records']


def _select_grade(label: str) -> None:
    """같은 카드를 다시 클릭하면 전체 조회로 돌아갑니다."""
    st.session_state['followup_selected_grade'] = (
        None if st.session_state.get('followup_selected_grade') == label else label
    )


def _clear_fitness_types() -> None:
    """운동유형 필터를 해제합니다."""
    st.session_state['followup_fitness_types']=[]


def render() -> None:
    """확률 등급별 대상과 기존 체력 관리 기록을 조회합니다."""
    st.caption('장병 체력관리 / 07')
    st.title('체력 지도·후속조치 관리')
    st.write('예측 확률에 따라 안전·경계1등급·경계2등급·경계3등급으로 나누어 체력 지도·후속조치를 관리합니다.')
    st.caption('첨부 파일은 부상 확률이 아닌 다음 체력검정 미달 확률입니다. 안전은 30% 미만이며, 30%·50%·70% 경계값은 각각 경계1·2·3등급에 포함합니다. 등급 계산 결과는 CSV로 저장하지 않습니다.')
    if notice:=st.session_state.pop('management_notice',None):
        st.success(notice)
    try:
        people=read_text_csv(SYNTHETIC_PERSONNEL_PATH)
        require_columns(people,['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME'])
        if people.SOLDIER_ID.duplicated().any():
            raise ValueError('장병 명단 식별자 중복')
        probabilities=load_probabilities()
        missing=int((~people.SOLDIER_ID.isin(probabilities.SOLDIER_ID)).sum())
        unmatched=int((~probabilities.SOLDIER_ID.isin(people.SOLDIER_ID)).sum())
        population=people.merge(probabilities,on='SOLDIER_ID',how='inner',validate='one_to_one')
        current_ids=population.SOLDIER_ID
        records={kind:load_records(kind) for kind in KINDS}
    except (OSError,ValueError,KeyError) as error:
        st.error(f'관리 자료를 읽을 수 없습니다: {error}')
        st.caption('장병 명단과 SOLDIER_FAILURE_PROBABILITY.csv를 확인하세요.')
        st.stop()
    active_grade=st.session_state.get('followup_selected_grade')
    chosen=[active_grade] if active_grade in RISK_LEVELS else []
    eligible=set(current_ids)
    st.subheader('등급별 대상 인원')
    st.markdown('''<style>
        div[class*="st-key-followup-grade-"] button {
            min-height: 142px;
            width: 100%;
            border-radius: 12px;
            border: 1px solid #cbd5e1;
        }
        div[class*="st-key-followup-grade-"] button p {
            font-size: 18px;
            line-height: 1.8;
        }
        div[class*="st-key-followup-grade-selected-"] button {
            background-color: #173b70;
            border: 2px solid #2563eb;
            border-radius: 12px;
        }
        div[class*="st-key-followup-grade-selected-"] button * {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
    </style>''',unsafe_allow_html=True)
    for column,(label,interval) in zip(st.columns(4),zip(RISK_LEVELS,RISK_RANGES)):
        selected=label in chosen
        count=population.loc[population.RISK_LEVEL.eq(label),'SOLDIER_ID'].nunique()
        with column:
            st.button(f'{"✓ " if selected else ""}**{label}**  \n**{count:,}명**  \n{interval}',
                key=f'followup-grade-{"selected" if selected else "idle"}-{RISK_LEVELS.index(label)}',
                width='stretch',on_click=_select_grade,args=(label,))
    st.caption('상단 카드를 클릭하면 아래 현황·명단·장병 선택이 해당 등급으로 바뀝니다. 선택한 카드를 다시 누르면 전체 등급을 표시합니다.')
    if missing or unmatched:
        st.warning(f'예측 누락 장병 {missing:,}명 · 명단에 없는 예측 {unmatched:,}명은 제외했습니다. 예측 누락을 안전으로 분류하지 않습니다.')
    if chosen:
        eligible &= set(population.loc[population.RISK_LEVEL.isin(chosen),'SOLDIER_ID'])
    st.caption(f'현재 조회: {" / ".join(chosen) if chosen else "전체 등급"} · {len(eligible):,}명')
    people=population.loc[population.SOLDIER_ID.isin(eligible)].sort_values('FAILURE_PROBABILITY',ascending=False).copy()
    # 측정값은 참고 정보일 뿐이며, 기존 미달·악화 대상 분석 파일은 사용하지 않습니다.
    measurement_columns=['SOLDIER_ID','MESURE_ID','MESURE_DE','AGE','BMI',*EVENTS]
    try:
        measurements=pd.read_csv(PROCESSED_FITNESS_PATH,dtype={'SOLDIER_ID':str},usecols=measurement_columns)
        measurements['MESURE_DE']=pd.to_datetime(measurements.MESURE_DE.astype(str).str.removesuffix('.0'),format='%Y%m%d',errors='coerce')
        latest=measurements.sort_values(['MESURE_DE','MESURE_ID'],kind='stable',na_position='first').drop_duplicates('SOLDIER_ID',keep='last')
        people=people.merge(latest,on='SOLDIER_ID',how='left',validate='one_to_one')
    except (OSError,ValueError,KeyError):
        st.warning('참고용 측정 정보를 읽지 못했습니다. 확률 등급에 따른 대상 조회와 관리 기록은 이용할 수 있습니다.')
        for field in ['MESURE_ID','MESURE_DE','AGE','BMI',*EVENTS]:
            people[field]=pd.NA
    st.subheader('운동유형 (16)')
    st.caption('장병별 최신 측정의 백분위 4등급 × 군집 4개입니다. 선택창에서 여러 유형을 함께 고를 수 있습니다. 인원은 위에서 선택한 확률 등급 기준입니다.')
    try:
        people,type_catalog=load_fitness_types(people)
    except (OSError,ValueError,KeyError) as error:
        st.error(f'운동유형 자료를 연결할 수 없습니다: {error}')
        st.stop()
    counts=people.groupby('FITNESS_TYPE_KEY').SOLDIER_ID.nunique()
    type_labels={item.FITNESS_TYPE_KEY:
                 f'백분위 {int(item.AVERAGE_PERCENTILE_GRADE)}등급 · {item.TYPE_NAME} · {int(counts.get(item.FITNESS_TYPE_KEY,0)):,}명'
                 for _,item in type_catalog.iterrows()}
    selected_types=st.multiselect('운동유형 선택 (복수 선택 가능)',
        options=type_catalog.FITNESS_TYPE_KEY.tolist(),format_func=type_labels.get,
        key='followup_fitness_types',placeholder='운동유형을 선택하세요 · 미선택 시 전체',
        help='여러 유형을 선택하면 선택한 유형 중 하나에 해당하는 장병을 모두 조회합니다.')
    st.button('운동유형 전체 보기',key='followup-types-clear',on_click=_clear_fitness_types)
    unclassified=int(people.FITNESS_TYPE_KEY.isna().sum())
    st.caption(f'선택 유형 {len(selected_types)}개 · 미선택 시 전체 유형 조회 · 최신 측정 분류 없음 {unclassified:,}명. 분류 없는 장병은 전체 조회에만 포함됩니다.')
    if selected_types:
        people=people.loc[people.FITNESS_TYPE_KEY.isin(selected_types)].copy()
    eligible=set(people.SOLDIER_ID)
    st.caption(f'최종 대상 {len(eligible):,}명 · 확률 등급과 운동유형 조건을 모두 적용합니다.')
    st.subheader('후속조치 진행 현황')
    col1,col2=st.columns(2)
    owner=col1.selectbox('집계 담당자',['전체',*sorted(records['followup_records'].loc[records['followup_records'].SOLDIER_ID.isin(eligible),'ASSIGNEE'].unique())])
    period=col2.selectbox('집계 기간',['전체','이번 달','올해'],help='상담일 기준으로 조회합니다. 대상 인원은 선택한 등급의 전체 장병 수입니다.')
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
    st.caption('완료율 = 완료 인원 ÷ 선택 등급 대상 인원. 상태는 담당자·기간 조건에 맞는 장병별 최신 상담 기록 기준입니다. 해당 기록이 없거나 최신 상태가 점검 대기·취소이면 점검 대기에 포함합니다. 안전만 선택한 경우에도 선택 인원을 기준으로 집계합니다.')
    if not scope.empty:
        counts=scope.STATUS.value_counts().rename_axis('상태').reset_index(name='건수')
        st.plotly_chart(px.bar(counts,x='상태',y='건수',text='건수'),width='stretch')
    else:
        st.info('장병 정보는 연결되어 있습니다. 현재 범위의 후속조치 입력 기록이 아직 0건입니다.')
    with st.expander('후속조치 전체 명단·점검 예정'):
        view=scope.copy()
        view['점검기한경과']=(view.NEXT_CHECK_DATE.lt(today.isoformat())&~view.STATUS.isin(['완료','취소']))
        st.dataframe(view.rename(columns=LABELS),hide_index=True,width='stretch')
    mode=st.radio('후속조치 등록 방식',['장병별','그룹별'],horizontal=True,key='followup-assignment-mode')
    if mode=='그룹별':
        render_group_followup(people)
        st.stop()
    st.subheader('관리할 장병')
    search=st.text_input('이름·장병번호 검색')
    shown=people.loc[people.SOLDIER_NAME.str.contains(search,regex=False)|people.SOLDIER_ID.str.contains(search,regex=False)] if search else people
    st.caption(f'검색 결과 {shown.SOLDIER_ID.nunique():,}명')
    if shown.empty:
        st.info('조회 대상 또는 검색 조건에 맞는 장병이 없습니다. 기존 기록은 보존되어 있습니다.');st.stop()
    lookup=shown.set_index('SOLDIER_ID')
    soldier=st.selectbox('장병 선택',shown.SOLDIER_ID.tolist(),format_func=lambda sid:f'{lookup.loc[sid,"SOLDIER_NAME"]} · {sid}')
    person=lookup.loc[soldier]
    with st.container(border=True):
        st.subheader('선택 장병 정보')
        st.write(f'**{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}**')
        st.caption(f'장병번호: {soldier} · 신상은 합성 자료입니다.')
        probability_col,level_col=st.columns(2)
        probability_col.metric('다음 체력검정 미달 확률',f'{person.FAILURE_PROBABILITY:.2%}')
        level_col.metric('대상자 등급',person.RISK_LEVEL)
        st.write('운동유형: '+(f'백분위 {int(person.AVERAGE_PERCENTILE_GRADE)}등급 · {person.TYPE_NAME}'
                            if pd.notna(person.FITNESS_TYPE_KEY) else '최신 측정 분류 없음'))
        if pd.notna(person.MESURE_DE):
            st.caption(f'참고용 최신 측정 · 측정일 {person.MESURE_DE:%Y-%m-%d}')
            age=f'{int(person.AGE)}세' if pd.notna(person.AGE) else '정보 없음'
            bmi=f'{person.BMI:.2f}' if pd.notna(person.BMI) else '정보 없음'
            for col,label,value in zip(st.columns(2),['측정 당시 나이','BMI'],[age,bmi]):
                col.metric(label,value)
            measurements=[]
            for event,(label,unit) in EVENTS.items():
                measurements.append({'종목':label,'측정값':person[event],'단위':unit,
                    '3등급 하한':grade_cut(event,3)})
            st.dataframe(pd.DataFrame(measurements),hide_index=True,width='stretch')
        else:
            st.info('참고용 측정 정보가 없습니다. 확률 등급에 따른 관리 기록은 이용할 수 있습니다.')
    st.caption('상단 완료율은 선택한 등급에 담당자·기간 필터를 적용한 집계입니다. 아래 기록은 선택 장병 기준입니다.')
    labels=['운동 지도 계획','운동 참여 기록','상담·후속조치']
    for tab,kind in zip(st.tabs(labels),KINDS):
        with tab:
            editor(kind,soldier,records,pd.DataFrame(columns=['SOLDIER_ID']))
    with st.expander('입력 자료 보관 안내'):
        st.write(f'저장 위치: {MANAGEMENT_DIR}')
        st.write('입력 기록은 별도 CSV에 저장하며 분석 재실행으로 초기화하지 않습니다. 실제 확인한 체력 지도·상담 내용만 입력합니다. 부상 회복·운동 제한은 8번에서 관리합니다.')
        st.caption('여러 화면에서 동시에 수정하면 충돌을 안내합니다. 최신 기록을 다시 읽고 수정하세요. 원본 신상·부상은 합성 자료입니다.')

    st.subheader('선택 조건에 해당하는 장병 명단')
    st.write('대상자 등급: '+(' / '.join(chosen) if chosen else '전체 · 안전 포함'))
    st.caption(f'총 {shown.SOLDIER_ID.nunique():,}명 · 아래 명단에 있는 장병만 장병 선택에 표시됩니다.')
    roster_columns=['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME','FAILURE_PROBABILITY','RISK_LEVEL','AVERAGE_PERCENTILE_GRADE','CLUSTER','TYPE_NAME']
    roster=shown[roster_columns].copy()
    roster['FAILURE_PROBABILITY']=roster.FAILURE_PROBABILITY.mul(100)
    roster=roster.rename(columns={
        'SOLDIER_ID':'장병번호','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속',
        'FAILURE_PROBABILITY':'미달 확률(%)','RISK_LEVEL':'대상자 등급',
        'AVERAGE_PERCENTILE_GRADE':'백분위 등급','CLUSTER':'군집','TYPE_NAME':'운동유형'})
    st.dataframe(roster,hide_index=True,width='stretch')
