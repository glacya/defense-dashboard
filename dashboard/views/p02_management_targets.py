"""2번 화면: 네 조건의 통합 체력 집중관리 대상자를 조회합니다."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from dashboard.common.charts import (
    ALERT_COLOR,
    LIGHT_TEXT,
    NAVY_BACKGROUND,
    OK_COLOR,
    WARN_COLOR,
    apply_chart_layout,
    style_bar_chart,
)
from dashboard.common.table_widgets import render_dataframe
from dashboard.py import queries
from dashboard.common.formatting import format_timestamp
from dashboard.py.management_targets_data import prepare_round_targets, targets_metadata
from dashboard.py.personal_detail_data import load_soldier_history
from dashboard.py.fitness_judgment import EVENTS, REASONS
from fitness_standards import grade_cut

LABELS={'SOLDIER_ID':'군번','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속',
        'ROUND':'회차','BMI':'BMI','BMI_GROUP':'BMI 구간','FAIL_COUNT':'미달 개수',
        'FAILED_EVENTS':'미달 종목',
        'FAIL_COUNT_CHANGE':'1차 대비 미달 종목 수 변화','NEW_FAILED_EVENTS':'1차 대비 신규 미달 종목',
        'PERSISTENT_EVENTS':'지속 미달 종목','SELECTION_REASONS':'선정 사유'}

REASON_LABELS={**REASONS,'HIGH_BMI_FAIL':'BMI가 25 이상이면서, 근력 또는 심폐지구력 미달','MULTIPLE_FAIL':'복수 종목 미달',
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
        rounds=queries.load_round_numbers()
    except (ValueError,SQLAlchemyError) as error:
        st.error(f'자료 확인이 필요합니다: {error}');st.stop()
    if not rounds:
        st.info('조회할 측정 자료가 없습니다.');st.stop()
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
    # 선택 회차 요약과 대상 명단을 판정 CTE 한 번으로 가져온다.
    summary,raw_targets=queries.load_round_details(number)
    targets=prepare_round_targets(raw_targets)
    measured=int(summary.MEASURED)
    reason_filter,event_filter=st.columns(2,gap='medium')
    if 'management_reasons' in st.session_state:
        st.session_state['management_reasons']=[v for v in st.session_state['management_reasons'] if v in available.values()]
    chosen=st.session_state.get('management_reasons', [])
    with reason_filter,st.container(border=True,key='management-reason-conditions'):
        st.markdown('**관리 사유**')
        buttons=st.columns(2)
        for index,(flag,label) in enumerate(available.items()):
            selected=label in chosen
            buttons[index%2].button(f'{"✓ " if selected else ""}{label} · {int(summary[flag]):,}명',
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
    search=st.text_input('이름 또는 군번으로 검색')
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
        [f'{measured:,}명',f'{len(targets):,}명',f'{len(targets)/measured*100:.1f}%' if measured else '해당 없음',f'{len(shown):,}명']):
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
    render_dataframe(display, hide_index=True, width='stretch')
    st.download_button('조회 명단 CSV 다운로드',display.to_csv(index=False).encode('utf-8-sig'),f'집중관리대상_{number}차.csv','text/csv')
    if shown.empty:
        st.info('조회 조건에 해당하는 관리 대상자가 없습니다.')
    else:
        st.subheader('개인별 선정 근거')
        names=dict(zip(shown.SOLDIER_ID,shown.SOLDIER_NAME))  # 선택지마다 표 전체를 찾지 않도록 한 번만 만든다
        selected=st.selectbox('장병 선택',shown.SOLDIER_ID.tolist(),format_func=lambda value:f'{names[value]} · {value}')
        row=shown.loc[shown.SOLDIER_ID.eq(selected)].iloc[0]
        st.write(f'**{row.SOLDIER_NAME} · {row.RANK_NAME} · {row.UNIT_NAME}**')
        st.write('선정 사유: '+row.SELECTION_REASONS)
        st.caption(f'BMI {row.BMI:.2f} · 구간 {row.BMI_GROUP}' if pd.notna(row.BMI) else 'BMI 판정 불가')
        # 선택한 장병 한 명의 모든 회차 판정(1차 측정값·이력)을 따로 조회한다.
        soldier_history=load_soldier_history(selected)
        first=soldier_history.loc[soldier_history.ROUND.eq(1)].iloc[0]
        for column,(event,(label,unit)) in zip(st.columns(4),EVENTS.items()):
            with column,st.container(border=True):
                grade=row[f'{event}_GRADE']
                grade_text='판정 불가' if pd.isna(grade) else '3등급 미만' if grade==0 else f'{int(grade)}등급'
                judgment='판정 불가' if pd.isna(grade) else '미달' if grade==0 else '충족'
                color='#64748b' if pd.isna(grade) else ALERT_COLOR if grade==0 else OK_COLOR
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
                    comparison=style_bar_chart(comparison)
                    cut=grade_cut(event,3)
                    comparison.add_hline(y=cut,line_color=WARN_COLOR,line_dash='dash')
                    apply_chart_layout(comparison,height=240,showlegend=False,
                        margin={'t':25,'b':25,'l':35,'r':10},
                        yaxis={'range':[min(0,float(values.min())*1.2),max(cut,float(values.max()))*1.2],
                               'zeroline':False},xaxis={'showgrid':False})
                    st.plotly_chart(comparison,width='stretch',key=f'management_comparison_{event}',
                                    config={'displayModeBar':False})
                else:
                    st.info('측정 기록이 없습니다.')
                st.caption(f'3등급 하한: {grade_cut(event,3):g} {unit}')
        st.caption('회색은 1차, 색상 막대는 선택 회차입니다. 주황 점선은 남성 19~24세의 3등급 하한이며 종목별 축 척도는 다릅니다.')
        history=soldier_history.loc[soldier_history.ROUND.le(number)]
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
            apply_chart_layout(heatmap,height=300,margin={'t':55,'b':15,'l':85,'r':15},
                xaxis={'side':'top','type':'category','fixedrange':True},
                yaxis={'autorange':'reversed','fixedrange':True},
                font={'color':LIGHT_TEXT},paper_bgcolor=NAVY_BACKGROUND,plot_bgcolor=NAVY_BACKGROUND)
            st.plotly_chart(heatmap,width='stretch',key='management_history_heatmap',
                            config={'displayModeBar':False})
            st.caption('연한 초록: 충족 · 주황: 미달 · 빨강: 같은 종목 최근 3회 지속 미달 · 회색: 판정 불가')
            st.info(f'{number}차 선정 사유: '+(row.SELECTION_REASONS or '해당 없음'))
    with st.expander('선정 기준·자료 안내'):
        metadata=targets_metadata()
        st.write('국민체력100의 19 ~ 24세 남성 등급 기준표를 바탕으로 판정합니다.')
        st.write('각 회차별로 각 장병은 한 번만 집계되며, 집계되는 장병은 관리 사유 4가지 중 하나라도 만족하는 장병들입니다.')
        st.write("'악화'는 1회차 측정 대비 선택한 회차(2, 3)의 측정이 더 나빠졌음을 의미합니다.")
        st.write("'지속 미달'은 최근 3개 회차의 측정이 계속해서 미달(3등급 미만)임을 의미합니다.")
        st.write('''BMI 그룹은 다음 세 가지로 나눕니다.
- 낮음: BMI가 18.5 미만
- 보통: BMI가 18.5 이상 25 미만
- 높음: BMI가 25 이상''')
        st.caption('생성일: '+format_timestamp(metadata['생성일시']))
