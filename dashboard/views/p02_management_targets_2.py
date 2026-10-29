"""2번 화면: 네 조건의 통합 체력 집중관리 대상자를 조회합니다."""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.py.management_targets_data_2 import load_targets
from sqlalchemy.exc import SQLAlchemyError
from data.scripts.analysis.analysis2.management_targets import REASONS
from data.scripts.analysis.analysis2.fitness_overview import EVENTS
from data.scripts.fitness_standards import grade_cut

LABELS={'SOLDIER_ID':'장병 식별자','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속',
        'ROUND':'회차','BMI':'BMI','BMI_GROUP':'BMI 구간','FAIL_COUNT':'미달 개수',
        'EVALUATED_COUNT':'판정 가능 종목 수','FAILED_EVENTS':'미달 종목',
        'FAIL_COUNT_CHANGE':'1차 대비 미달 수 변화','NEW_FAILED_EVENTS':'1차 대비 신규 미달 종목',
        'PERSISTENT_EVENTS':'지속 미달 종목','SELECTION_REASONS':'선정 사유'}

REASON_LABELS={**REASONS,'MULTIPLE_FAIL':'복수 종목 미달',
               'PERSISTENT_FAIL':'동일 종목 지속 미달 (최근 3회)'}


def render() -> None:
    """상단 회차 선택과 관리 사유 필터로 개인별 선정 근거를 표시합니다."""
    st.caption('장병 체력관리 / 02')
    st.title('체력 미달·악화 대상자 조회_2')
    st.caption('DB 조회 기반 · 기존 CSV 화면과 동일한 판정 기준')
    st.write('BMI와 실제 미달, 복수 종목 미달, 악화, 지속 미달을 함께 확인합니다.')
    try:
        data,source,metadata=load_targets()
    except (SQLAlchemyError, ModuleNotFoundError):
        st.error('DB 조회에 실패했습니다. DB 접속 설정·드라이버·네트워크를 확인하세요.');st.stop()
    except (ValueError,KeyError,pd.errors.EmptyDataError,json.JSONDecodeError) as error:
        st.error(f'자료 확인이 필요합니다: {error}');st.stop()
    if data.empty:
        st.info('조회할 측정 자료가 없습니다.');st.stop()
    rounds=sorted(int(n) for n in data.ROUND.unique())
    number=st.radio('측정 회차',rounds,index=len(rounds)-1,horizontal=True,
                    format_func=lambda n:f'{n}차',key='management_round_2')
    available=REASON_LABELS
    if number==1:
        st.caption('1차 기준 · BMI 관련·복수 종목 미달을 확인합니다. 악화·지속 미달은 후속 회차에서 확인할 수 있습니다.')
    elif number==2:
        st.caption('2차 기준 · 악화는 1차와 비교합니다. 3회 지속 미달은 아직 판정하지 않습니다.')
    else:
        st.caption(f'{number}차 기준 · 악화는 1차와 비교하고, 지속 미달은 최근 세 회차를 확인합니다.')
    st.sidebar.header('조회 조건')
    if 'management_reasons_2' in st.session_state:
        st.session_state['management_reasons_2']=[v for v in st.session_state['management_reasons_2'] if v in available.values()]
    chosen=st.sidebar.multiselect('관리 사유',list(available.values()),key='management_reasons_2',
                                  help='선택하지 않으면 전체 사유, 여러 개 선택하면 하나 이상 해당하는 장병을 표시합니다.')
    if available['PERSISTENT_FAIL'] in chosen and number<3:
        st.sidebar.info('동일 종목 지속 미달은 세 회차 기록이 필요합니다. 상단에서 3차 이상을 선택하세요.')
    if available['WORSENED'] in chosen and number==1:
        st.sidebar.info('미달 종목 수 증가는 1차와 비교하므로 2차 이상을 선택하세요.')
    fail_count='전체'
    if '복수 종목 미달' in chosen:
        fail_count=st.sidebar.selectbox(f'{number}차 미달 종목 수',['전체','2개','3개','4개'],key='management_count_2')
    events=st.sidebar.multiselect('미달 종목',[v[0] for v in EVENTS.values()],help='여러 개 선택하면 하나 이상 미달한 장병을 표시합니다.')
    search=st.sidebar.text_input('이름·장병번호 검색')
    current=data.loc[data.ROUND.eq(number)]
    targets=current.loc[current.MANAGED]
    shown=targets.copy()
    if chosen:
        flags=[key for key,value in available.items() if value in chosen]
        shown=shown.loc[shown[flags].any(axis=1)]
    if fail_count=='판정 불완전':
        shown=shown.loc[shown.EVALUATED_COUNT.lt(4)]
    elif fail_count!='전체':
        n=int(fail_count[0])
        shown=shown.loc[shown.FAIL_COUNT.eq(n)]
    if events:
        shown=shown.loc[shown.FAILED_EVENTS.map(lambda s:any(event in s.split(' · ') for event in events))]
    if search:
        shown=shown.loc[shown.SOLDIER_ID.str.contains(search,regex=False)|shown.SOLDIER_NAME.str.contains(search,regex=False)]
    for column,title,value in zip(st.columns(4),[f'{number}차 측정 인원','집중관리 대상','관리 대상 비율','조회 결과'],
        [f'{len(current):,}명',f'{len(targets):,}명',f'{len(targets)/len(current)*100:.1f}%' if len(current) else '해당 없음',f'{len(shown):,}명']):
        column.metric(title,value,border=True)
    st.caption('관리 대상은 선정 조건의 합집합이며, 같은 장병은 한 번만 집계합니다. 비율 분모는 선택 회차 측정 인원입니다.')
    reasons=pd.DataFrame([{'선정 사유':label,'인원':int(targets[flag].sum())} for flag,label in available.items()])
    chart=px.bar(reasons,x='인원',y='선정 사유',orientation='h',text='인원',color_discrete_sequence=['#2563eb'])
    chart.update_layout(yaxis_title=None,height=330)
    st.plotly_chart(chart,width='stretch')
    st.caption('사유별 인원은 필터 적용 전 전체 관리 대상 기준이며 중복됩니다. 합산하지 마세요.')
    st.subheader('통합 대상자 명단')
    conditions=[f'{number}차 기준', ' / '.join(chosen) if chosen else '전체 관리 사유']
    if fail_count!='전체':
        conditions.append('판정 불완전' if fail_count=='판정 불완전' else f'{fail_count} 미달')
    if events:
        conditions.append(' / '.join(events)+' 미달')
    if search:
        conditions.append(f'검색: {search}')
    st.info(' · '.join(conditions))
    display=shown[list(LABELS)].rename(columns=LABELS)
    display=display.rename(columns={'미달 개수':f'{number}차 미달 종목 수'})
    st.dataframe(display,hide_index=True,width='stretch')
    st.download_button('조회 명단 CSV 다운로드',display.to_csv(index=False).encode('utf-8-sig'),f'집중관리대상_{number}차.csv','text/csv')
    if shown.empty:
        st.info('조회 조건에 해당하는 관리 대상자가 없습니다.')
    else:
        st.subheader('개인별 선정 근거')
        selected=st.selectbox('장병 선택',shown.SOLDIER_ID.tolist(),format_func=lambda value:f'{shown.loc[shown.SOLDIER_ID.eq(value),"SOLDIER_NAME"].iloc[0]} · {value}')
        row=shown.loc[shown.SOLDIER_ID.eq(selected)].iloc[0]
        st.write(f'**{row.SOLDIER_NAME} · {row.RANK_NAME} · {row.UNIT_NAME}**')
        st.write('선정 사유: '+row.SELECTION_REASONS)
        st.caption(f'BMI {row.BMI:.2f} · 구간 {row.BMI_GROUP}' if pd.notna(row.BMI) else 'BMI 판정 불가')
        detail=[]
        first=source.loc[source.MESURE_ID.eq(row.FIRST_MESURE_ID)].iloc[0]
        for event,(label,unit) in EVENTS.items():
            grade=row[f'{event}_GRADE']
            detail.append({'종목':label,'단위':unit,'1차 측정값':first[event],'선택 회차 측정값':row[event],
                '3등급 하한':grade_cut(event,3),
                '등급':'판정 불가' if pd.isna(grade) else '3등급 미만' if grade==0 else f'{int(grade)}등급',
                '판정':'판정 불가' if pd.isna(grade) else '미달' if grade==0 else '충족'})
        st.dataframe(pd.DataFrame(detail),hide_index=True,width='stretch')
        history=data.loc[data.SOLDIER_ID.eq(selected)&data.ROUND.le(number)].sort_values('ROUND')
        history_cols=['ROUND','MESURE_DE','FAIL_COUNT','FAILED_EVENTS','PERSISTENT_EVENTS','SELECTION_REASONS']
        st.dataframe(history[history_cols].rename(columns={**LABELS,'MESURE_DE':'측정일'}),hide_index=True,width='stretch')
    with st.expander('선정 기준·자료 안내'):
        for key in ['기준','대상','시간','누락','BMI','상세']:
            st.write(metadata[key])
        st.caption('신상은 합성 자료이며 실제 부상 위험 판정이 아닙니다. 조회·판정일: '+metadata['생성일시'])