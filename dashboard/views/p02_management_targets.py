"""2번 화면: 네 조건의 통합 체력 집중관리 대상자를 조회합니다."""

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.py.management_targets_data import load_targets
from dashboard.py.fitness_judgment import EVENTS, REASONS
from data.scripts.fitness_standards import grade_cut

LABELS={'SOLDIER_ID':'장병 식별자','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속',
        'ROUND':'회차','BMI':'BMI','BMI_GROUP':'BMI 구간','FAIL_COUNT':'미달 개수',
        'FAILED_EVENTS':'미달 종목',
        'FAIL_COUNT_CHANGE':'1차 대비 미달 수 변화','NEW_FAILED_EVENTS':'1차 대비 신규 미달 종목',
        'PERSISTENT_EVENTS':'지속 미달 종목','SELECTION_REASONS':'선정 사유'}

REASON_LABELS={**REASONS,'MULTIPLE_FAIL':'복수 종목 미달',
               'PERSISTENT_FAIL':'동일 종목 지속 미달 (최근 3회)'}


def _toggle_condition(key: str, value: str) -> None:
    selected=list(st.session_state.get(key, []))
    if value in selected:
        selected.remove(value)
    else:
        selected.append(value)
    st.session_state[key]=selected


def render() -> None:
    """상단 회차 선택과 관리 사유 필터로 개인별 선정 근거를 표시합니다."""
    st.caption('장병 체력관리 / 02')
    st.title('체력 미달·악화 대상자 조회')
    st.write('BMI와 실제 미달, 복수 종목 미달, 악화, 지속 미달을 함께 확인합니다.')
    try:
        data,source,metadata=load_targets()
    except FileNotFoundError:
        st.warning('분석 자료 또는 원본이 없습니다. 먼저 집중관리 분석을 실행하세요.')
        st.code('python -m data.scripts.analysis.analysis2.management_targets',language='powershell');st.stop()
    except (ValueError,KeyError,pd.errors.EmptyDataError,json.JSONDecodeError) as error:
        st.error(f'자료 확인이 필요합니다: {error}');st.stop()
    if data.empty:
        st.info('조회할 측정 자료가 없습니다.');st.stop()
    rounds=sorted(int(n) for n in data.ROUND.unique())
    number=st.radio('측정 회차',rounds,index=len(rounds)-1,horizontal=True,
                    format_func=lambda n:f'{n}차',key='management_round')
    available=REASON_LABELS
    if number==1:
        st.caption('1차 기준 · BMI 관련·복수 종목 미달을 확인합니다. 악화·지속 미달은 후속 회차에서 확인할 수 있습니다.')
    elif number==2:
        st.caption('2차 기준 · 악화는 1차와 비교합니다. 3회 지속 미달은 아직 판정하지 않습니다.')
    else:
        st.caption(f'{number}차 기준 · 악화는 1차와 비교하고, 지속 미달은 최근 세 회차를 확인합니다.')
    st.subheader('조회 조건')
    current=data.loc[data.ROUND.eq(number)]
    targets=current.loc[current.MANAGED]
    reason_filter,event_filter=st.columns(2,gap='medium')
    if 'management_reasons' in st.session_state:
        st.session_state['management_reasons']=[v for v in st.session_state['management_reasons'] if v in available.values()]
    chosen=st.session_state.get('management_reasons', [])
    with reason_filter,st.container(border=True,key='management-reason-conditions'):
        st.markdown('**관리 사유**')
        buttons=st.columns(2)
        for index,(flag,label) in enumerate(available.items()):
            selected=label in chosen
            buttons[index%2].button(f'{"✓ " if selected else ""}{label} · {int(targets[flag].sum()):,}명',
                key=f'management-reason-{flag}',width='stretch',
                type='primary' if selected else 'secondary',
                on_click=_toggle_condition,args=('management_reasons',label))
    if available['PERSISTENT_FAIL'] in chosen and number<3:
        reason_filter.info('동일 종목 지속 미달은 세 회차 기록이 필요합니다. 상단에서 3차 이상을 선택하세요.')
    if available['WORSENED'] in chosen and number==1:
        reason_filter.info('미달 종목 수 증가는 1차와 비교하므로 2차 이상을 선택하세요.')
    fail_count='전체'
    if '복수 종목 미달' in chosen:
        fail_count=reason_filter.selectbox(f'{number}차 미달 종목 수',['전체','2개','3개','4개'],key='management_count')
    events=st.session_state.get('management_events', [])
    with event_filter,st.container(border=True,key='management-event-conditions'):
        st.markdown('**미달 종목**')
        buttons=st.columns(2)
        for index,(event,(label,_)) in enumerate(EVENTS.items()):
            selected=label in events
            buttons[index%2].button(f'{"✓ " if selected else ""}{label}',
                key=f'management-event-{event}',width='stretch',
                type='primary' if selected else 'secondary',
                on_click=_toggle_condition,args=('management_events',label))
    st.caption('여러 항목을 선택할 수 있으며, 다시 누르면 해제합니다. 미선택 시 전체 조회합니다. 인원은 선택 회차의 전체 관리 대상 기준입니다.')
    search=st.text_input('이름·장병번호 검색')
    shown=targets.copy()
    if chosen:
        flags=[key for key,value in available.items() if value in chosen]
        shown=shown.loc[shown[flags].any(axis=1)]
    if fail_count!='전체':
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
    st.subheader('통합 대상자 명단')
    conditions=[f'{number}차 기준', ' / '.join(chosen) if chosen else '전체 관리 사유']
    if fail_count!='전체':
        conditions.append(f'{fail_count} 미달')
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
        first=source.loc[source.MESURE_ID.eq(row.FIRST_MESURE_ID)].iloc[0]
        for column,(event,(label,unit)) in zip(st.columns(4),EVENTS.items()):
            with column,st.container(border=True):
                grade=row[f'{event}_GRADE']
                grade_text='판정 불가' if pd.isna(grade) else '3등급 미만' if grade==0 else f'{int(grade)}등급'
                judgment='판정 불가' if pd.isna(grade) else '미달' if grade==0 else '충족'
                color='#64748b' if pd.isna(grade) else '#dc2626' if grade==0 else '#0f766e'
                st.markdown(f'**{label} ({unit})**')
                st.caption(f'{grade_text} · {judgment}')
                values=pd.to_numeric(pd.Series([first[event],row[event]]),errors='coerce').replace(
                    [float('inf'),float('-inf')],float('nan'))
                if values.notna().any():
                    comparison=go.Figure(go.Bar(
                        x=['1차',f'선택 {number}차'],y=values,
                        marker_color=['#94a3b8',color],
                        text=[f'{value:g}' if pd.notna(value) else '' for value in values],
                        textposition='outside',cliponaxis=False,
                        hovertemplate=f'%{{x}}<br>%{{y:.2f}} {unit}<extra></extra>',
                    ))
                    cut=grade_cut(event,3)
                    comparison.add_hline(y=cut,line_color='#ea580c',line_dash='dash')
                    comparison.update_layout(height=240,showlegend=False,
                        margin={'t':25,'b':25,'l':35,'r':10},
                        yaxis={'range':[min(0,float(values.min())*1.2),max(cut,float(values.max()))*1.2],
                               'zeroline':False},xaxis={'showgrid':False},
                        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(comparison,width='stretch',key=f'management_comparison_{event}',
                                    config={'displayModeBar':False})
                else:
                    st.info('측정 기록이 없습니다.')
                st.caption(f'3등급 하한: {grade_cut(event,3):g} {unit}')
        st.caption('회색은 1차, 색상 막대는 선택 회차입니다. 주황 점선은 남성 19~24세의 3등급 하한이며 종목별 축 척도는 다릅니다.')
        history=data.loc[data.SOLDIER_ID.eq(selected)&data.ROUND.le(number)].sort_values('ROUND')
        with st.container(border=True,key='management-history-panel'):
            st.subheader('회차별 미달 현황')
            state_values=[]
            state_labels=[]
            for event,(label,_) in EVENTS.items():
                event_values=[]
                event_labels=[]
                for record in history.to_dict('records'):
                    grade=record[f'{event}_GRADE']
                    persistent=str(record.get('PERSISTENT_EVENTS','')).split(' · ')
                    state=0 if pd.isna(grade) else 3 if grade==0 and label in persistent else 2 if grade==0 else 1
                    event_values.append(state)
                    event_labels.append(['판정 불가','충족','미달','지속 미달'][state])
                state_values.append(event_values)
                state_labels.append(event_labels)
            round_labels=[f'{int(record.ROUND)}차<br>미달 {int(record.FAIL_COUNT)}개'
                          if pd.notna(record.FAIL_COUNT) else f'{int(record.ROUND)}차<br>판정 불완전'
                          for record in history.itertuples()]
            heatmap=go.Figure(go.Heatmap(
                z=state_values,x=round_labels,y=[label for label,_ in EVENTS.values()],
                text=state_labels,texttemplate='%{text}',zmin=0,zmax=3,
                colorscale=[[0,'#e2e8f0'],[1/6,'#e2e8f0'],
                            [1/6,'#d1fae5'],[.5,'#d1fae5'],
                            [.5,'#fed7aa'],[5/6,'#fed7aa'],
                            [5/6,'#fca5a5'],[1,'#fca5a5']],
                showscale=False,xgap=6,ygap=6,
                hovertemplate='%{x}<br>%{y}: %{text}<extra></extra>',
            ))
            heatmap.update_layout(height=300,margin={'t':55,'b':15,'l':85,'r':15},
                xaxis={'side':'top','type':'category','fixedrange':True},
                yaxis={'autorange':'reversed','fixedrange':True},
                paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                font={'color':'#182b40'})
            st.plotly_chart(heatmap,width='stretch',key='management_history_heatmap',
                            config={'displayModeBar':False})
            st.caption('연한 초록: 충족 · 주황: 미달 · 빨강: 같은 종목 최근 3회 지속 미달 · 회색: 판정 불가')
            st.info(f'{number}차 선정 사유: '+(row.SELECTION_REASONS or '해당 없음'))
    with st.expander('선정 기준·자료 안내'):
        for key in ['기준','대상','시간','누락','BMI','상세']:
            st.write(metadata[key])
        st.caption('신상은 합성 자료이며 실제 부상 위험 판정이 아닙니다. 생성일: '+metadata['생성일시'])
