"""3번 화면: 개인 장병의 기본·신체·체력 변화 및 부상 이력입니다."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from config import DASHBOARD_DIR
from dashboard.py import queries
from dashboard.py.personal_detail_data import load_soldier_history, personal_metadata
from dashboard.py.personal_exercise_recommendations import render_recommendation
from dashboard.py.fitness_judgment import EVENTS
from data.scripts.fitness_standards import grade_cut


def _reset_personal_unit_filter(unit_key: str) -> None:
    """지역 변경 시 부대 선택을 초기화해 이전 지역의 조건이 남지 않게 합니다."""
    st.session_state[unit_key] = []


def formatted(value, digits=2) -> str:
    """누락된 숫자는 미측정으로 표시합니다."""
    number=pd.to_numeric(value,errors='coerce')
    return '정보 없음' if pd.isna(number) else f'{number:.{digits}f}'


def grade_label(value) -> str:
    """종목 등급 0과 판정 불가를 구분해 표시합니다."""
    return '판정 불가' if pd.isna(value) else '3등급 미만' if value==0 else f'{int(value)}등급'


def render() -> None:
    """장병 선택 후 측정 시점별 상세와 개인 이력을 표시합니다."""
    st.caption('장병 체력관리 / 03')
    st.title('개인 장병 상세')
    st.write('한 장병의 신체·체력 변화와 부상 기록을 함께 확인합니다.')
    try:
        people=queries.load_roster()[['SOLDIER_ID','SOLDIER_NAME','REGION_NAME','RANK_NAME','UNIT_NAME']]
    except (ValueError,SQLAlchemyError) as error:
        st.error(f'자료 확인이 필요합니다: {error}');st.stop()
    st.subheader('장병 찾기')
    region_filter,unit_filter,search_filter=st.columns(3)
    region_key='personal_region_filter'
    unit_key='personal_unit_filter'
    units_by_region=people.groupby('REGION_NAME')['UNIT_NAME'].unique().map(list).to_dict()
    regions=region_filter.multiselect(
        '지역',
        options=sorted(people.REGION_NAME.dropna().unique().tolist()),
        key=region_key,
        on_change=_reset_personal_unit_filter,
        args=(unit_key,),
        placeholder='전체 지역',
    )
    available_units=(
        sorted({unit for region in regions for unit in units_by_region.get(region, [])})
        if regions else sorted(people.UNIT_NAME.dropna().unique().tolist())
    )
    units=unit_filter.multiselect(
        '부대',
        options=available_units,
        key=unit_key,
        placeholder='전체 부대',
    )
    search=search_filter.text_input('이름·장병번호 검색')
    if regions:
        people=people.loc[people.REGION_NAME.isin(regions)]
    if units:
        people=people.loc[people.UNIT_NAME.isin(units)]
    if search:
        people=people.loc[people.SOLDIER_NAME.str.contains(search,regex=False)|people.SOLDIER_ID.str.contains(search,regex=False)]
    if people.empty:
        st.info('선택한 지역·부대·검색 조건에 해당하는 장병이 없습니다.');st.stop()
    st.caption(f'조건에 해당하는 장병 {people.SOLDIER_ID.nunique():,}명')
    people=people.sort_values(['SOLDIER_NAME','SOLDIER_ID'])
    labels=people.set_index('SOLDIER_ID')
    soldier=st.selectbox('장병 선택',people.SOLDIER_ID.tolist(),
        format_func=lambda value:f'{labels.loc[value,"SOLDIER_NAME"]} · {labels.loc[value,"RANK_NAME"]} · {value}')
    # 선택한 장병 한 명의 판정·변화·부상만 따로 조회한다.
    history=load_soldier_history(soldier)
    rounds=history.ROUND.astype(int).tolist()
    number=st.radio('상세 측정 회차',rounds,index=len(rounds)-1,horizontal=True,format_func=lambda value:f'{value}차')
    row=history.loc[history.ROUND.eq(number)].iloc[0]
    person_injuries=queries.load_soldier_injuries(soldier)
    date=pd.to_datetime(str(row.MESURE_DE).removesuffix('.0'),format='%Y%m%d',errors='coerce')
    date_label=date.strftime('%Y-%m-%d') if pd.notna(date) else '날짜 확인 필요'
    identity,body_summary=st.columns([1,3],vertical_alignment='center')
    with identity,st.container(border=True):
        st.image(str(DASHBOARD_DIR / 'img' / 'soldier_profile.svg'),width=90)
        st.subheader(f'{row.SOLDIER_NAME} · {row.RANK_NAME}')
        st.caption(f'장병번호 {soldier} · {row.UNIT_NAME}')
        st.caption(f'선택 측정일 {date_label} · {formatted(row.AGE,0)}세')
    with body_summary:
        st.subheader(f'{number}차 신체 정보')
        entries=[('키','HEIGHT','cm'),('체중','WEIGHT','kg'),('BMI','BMI','kg/m²'),('체지방률','BODY_FAT_PERCENTAGE','%')]
        for col,(label,key,unit) in zip(st.columns(4),entries):
            col.metric(label,f'{formatted(row.get(key))} {unit}',border=True)
        st.write('BMI 구간: **'+row.BMI_GROUP+'**')
        st.caption('낮음 <18.5 · 보통 18.5 이상 25 미만 · 높음 25 이상. 보통에는 정상·비만전단계가 포함됩니다.')
    st.caption('신상·부상은 합성 자료입니다. 이미지는 공통 장병 프로필입니다.')
    for column,label,value in zip(st.columns(4),['선택 회차','미달 종목 수','집중관리 조건','전체 부상 기록'],
        [f'{number}차',f'{int(row.FAIL_COUNT)}개' if pd.notna(row.FAIL_COUNT) else '판정 불완전',
         '해당' if row.MANAGED else '확인된 조건 없음',f'{len(person_injuries)}건']):
        column.metric(label,value,border=True)
    st.caption('부상 기록은 전체 보유 이력입니다. 발생일이 없어 선택 측정 회차의 부상으로 해석하지 않습니다.')
    cols=['ROUND','MESURE_DE','AGE','HEIGHT','WEIGHT','BMI','BODY_FAT_PERCENTAGE']
    body_table,body_chart=st.columns([2,1],vertical_alignment='top')
    with body_table:
        st.dataframe(history[[c for c in cols if c in history]].rename(columns={'ROUND':'회차','MESURE_DE':'측정일','AGE':'나이','HEIGHT':'키 (cm)','WEIGHT':'체중 (kg)','BODY_FAT_PERCENTAGE':'체지방률 (%)'}),hide_index=True,width='stretch')
    with body_chart,st.container(border=True):
        body_options={'체중':('WEIGHT','kg'),'키':('HEIGHT','cm'),
                      'BMI':('BMI','kg/m²'),'체지방률':('BODY_FAT_PERCENTAGE','%')}
        body_label=st.selectbox('신체 변화',list(body_options),key='personal_body_chart_event')
        body_event,body_unit=body_options[body_label]
        values=pd.to_numeric(history[body_event],errors='coerce').replace([float('inf'),float('-inf')],float('nan'))
        if values.notna().any():
            trend=go.Figure(go.Scatter(
                x=history.ROUND,y=values,mode='lines+markers',connectgaps=False,
                line={'color':'#0f766e','width':2},marker={'size':7},
                hovertemplate=f'%{{x}}차<br>{body_label} %{{y:.2f}} {body_unit}<extra></extra>',
            ))
            trend.add_vline(x=number,line_color='#94a3b8',line_dash='dot')
            trend.update_layout(height=210,showlegend=False,
                                margin={'t':10,'b':30,'l':45,'r':15},
                                xaxis={'title':'측정 회차','dtick':1},
                                yaxis={'title':body_unit})
            st.plotly_chart(trend,width='stretch',key='personal_body_trend',
                            config={'displayModeBar':False})
            st.caption('점선은 선택 회차입니다.')
        else:
            st.info('해당 항목의 신체 측정 기록이 없습니다.')
    type_panel,recommendation_panel=st.columns([1,1.4],gap='large')
    classification=row  # 이력 행에 체력유형(등급·군집·유형명)이 들어 있다.
    if pd.isna(classification.TYPE_NAME):
        st.info('선택 회차의 체력유형 분류 정보가 없습니다.')
    else:
        with type_panel:
            st.subheader(f'{number}차 체력유형')
            with st.container(border=True):
                st.markdown(f'**{classification.TYPE_NAME}**')
                st.caption(
                    f'평균 백분위 {int(classification.AVERAGE_PERCENTILE_GRADE)}등급 · '
                    f'군집 {int(classification.CLUSTER)} · {number}차 측정 기준'
                )
                try:
                    personal_profile,cluster_profile,member_count=queries.load_measurement_profile(row.MESURE_ID)
                except (ValueError,KeyError,SQLAlchemyError) as error:
                    st.info(f'클러스터 비교 차트를 표시할 수 없습니다: {error}')
                else:
                    axes=[EVENTS[event][0] for event in personal_profile.index]
                    radar=go.Figure()
                    for name,values,color in [
                        ('선택 장병',personal_profile,'#2563eb'),
                        ('같은 체력유형 평균',cluster_profile,'#ea580c'),
                    ]:
                        scores=[float(value) if pd.notna(value) else None for value in values]
                        radar.add_trace(go.Scatterpolar(
                            r=scores+scores[:1],theta=axes+axes[:1],
                            mode='lines+markers',name=name,
                            line={'color':color,'width':3},
                            hovertemplate='%{theta}<br>백분위 %{r:.1f}<extra>%{fullData.name}</extra>',
                        ))
                    radar.update_layout(
                        polar={'radialaxis':{'visible':True,'range':[0,100],'dtick':20},
                               'angularaxis':{'direction':'clockwise'},'gridshape':'linear'},
                        height=380,margin={'t':35,'b':45,'l':65,'r':65},
                        legend={'orientation':'h','y':-0.12,'x':0.5,'xanchor':'center'},
                    )
                    st.plotly_chart(radar,width='stretch',key='personal_cluster_radar')
                    st.caption(f'바깥쪽일수록 종목 백분위가 높습니다. 같은 등급·클러스터의 전체 회차 측정 {member_count:,}건 평균이며 선택 측정도 포함합니다. 백분위는 전체 측정 기준으로 계산합니다.')
        with recommendation_panel:
            render_recommendation(int(classification.AVERAGE_PERCENTILE_GRADE),int(classification.CLUSTER))
    fitness,changes,injury=st.tabs(['체력측정·등급','회차별 변화','부상 이력'])
    with fitness:
        rows=[]
        for event,(label,unit) in EVENTS.items():
            grade=row[f'{event}_GRADE']
            rows.append({'종목':label,'단위':unit,'측정값':row[event],'등급':grade_label(grade),
                '판정':'판정 불가' if pd.isna(grade) else '미달' if grade==0 else '충족',
                '3등급 하한':grade_cut(event,3)})
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
        st.write('미달 종목: '+(row.FAILED_EVENTS or '확인된 미달 없음'))
        st.write('집중관리 사유: '+(row.SELECTION_REASONS or '현재 자료에서 확인된 선정 조건 없음'))
    with changes:
        st.subheader('1차 대비 선택 회차 변화')
        rows=[]
        for event,(label,unit) in EVENTS.items():
            rows.append({'종목':label,'단위':unit,'측정값 변화':row[f'{event}_CHANGE'],'등급 변화':row[f'{event}_GRADE_CHANGE']})
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
        delta=row.FAIL_COUNT_CHANGE
        st.write('미달 종목 수 변화: '+(f'{int(delta):+d}개' if pd.notna(delta) else '판정 불가'))
        st.write('1차 대비 신규 미달: '+(row.NEW_FAILED_EVENTS or '없음'))
        st.write('1차 대비 미달 해소: '+(row.IMPROVED_EVENTS or '없음'))
        st.write('선택 회차까지 최근 3회 지속 미달: '+(row.PERSISTENT_EVENTS or '확인된 종목 없음'))
        st.caption('미측정·연령 범위 밖은 판정 불가입니다. 개선·신규 미달은 두 시점 모두 판정 가능한 종목에서만 확인합니다.')
        st.subheader('종목별 개인 변화와 전체 평균')
        st.caption('파랑: 개인 측정값 · 회색: 같은 회차 전체 평균 · 주황 점선: 3등급 하한. 평균에는 선택 장병도 포함합니다.')
        round_means=queries.load_round_means().set_index('ROUND')
        for offset in (0,2):
            for container,(event,(label,unit)) in zip(st.columns(2),list(EVENTS.items())[offset:offset+2]):
                with container,st.container(border=True):
                    reference=pd.DataFrame({'mean':round_means[event],'count':round_means['MEASURED']})
                    average=reference.loc[number,'mean'] if number in reference.index else float('nan')
                    value=pd.to_numeric(row[event],errors='coerce')
                    if pd.notna(value) and pd.notna(average):
                        difference=value-average
                        comparison=f'평균보다 {abs(difference):.2f} {unit} '+('높음' if difference>0 else '낮음' if difference<0 else '차이 없음')
                    else:
                        comparison='측정값 또는 평균이 없어 비교할 수 없음'
                    st.metric(f'{label} · {number}차',f'{formatted(value)} {unit}',border=False)
                    st.caption(f'전체 평균 {formatted(average)} {unit} · {comparison}')
                    plot=go.Figure()
                    plot.add_trace(go.Scatter(x=reference.index,y=reference['mean'],mode='lines+markers',
                        name='전체 평균',line={'color':'#94a3b8','width':2},
                        customdata=reference['count'],hovertemplate='%{x}차<br>전체 평균 %{y:.2f}<br>유효 인원 %{customdata:,.0f}명<extra></extra>'))
                    plot.add_trace(go.Scatter(x=history.ROUND,y=history[event],mode='lines+markers',
                        name='개인 측정값',line={'color':'#2563eb','width':3},
                        hovertemplate='%{x}차<br>개인 측정값 %{y:.2f}<extra></extra>'))
                    plot.add_trace(go.Scatter(x=reference.index,y=[grade_cut(event,3)]*len(reference),mode='lines',
                        name='3등급 하한',line={'color':'#ea580c','dash':'dot'},
                        hovertemplate='3등급 하한 %{y:.2f}<extra></extra>'))
                    plot.add_vline(x=number,line_color='#cbd5e1',line_dash='dash')
                    plot.update_layout(xaxis_title='측정 회차',xaxis_dtick=1,yaxis_title=f'{label} ({unit})',height=340,
                                       legend={'orientation':'h','y':1.15,'x':0},margin={'t':65,'l':25,'r':15,'b':30})
                    st.plotly_chart(plot,width='stretch',key=f'personal_mean_{event}')
        st.caption('전체 평균은 각 회차의 유효 측정값으로 계산하며 회차별 인원이 달라질 수 있습니다. 평균보다 낮다는 것과 기준 미달은 다릅니다. 그래프는 전체 보유 회차를 표시하고, 세로 점선은 선택 회차입니다. 등급 기준은 남성 19~24세에서만 유효합니다.')
        table=history[['ROUND','FAIL_COUNT','FAILED_EVENTS','NEW_FAILED_EVENTS','IMPROVED_EVENTS','PERSISTENT_EVENTS']].rename(columns={'ROUND':'회차','FAIL_COUNT':'미달 개수','FAILED_EVENTS':'미달 종목','NEW_FAILED_EVENTS':'1차 대비 신규 미달','IMPROVED_EVENTS':'1차 대비 미달 해소','PERSISTENT_EVENTS':'최근 3회 지속 미달'})
        st.dataframe(table,hide_index=True,width='stretch')
    with injury:
        st.subheader('개인 부상 이력')
        st.caption('발생일·회복 상태·운동 제한 자료는 현재 원본에 없습니다. 회차별 부상이나 현재 회복 여부를 추정하지 않습니다.')
        if person_injuries.empty:
            st.info('보유 부상 자료에서 이 장병의 기록이 없습니다.')
        else:
            shown=person_injuries.rename(columns={'INJURY_ID':'부상 식별자','SOLDIER_ID':'장병 식별자','INJURY_CATEGORY':'부상 대분류','INJURY_LOCATION':'부위','PREVENTABILITY':'예방 가능 여부','SEVERITY':'심각도'})
            shown['예방 가능 여부']=shown['예방 가능 여부'].map({'Y':'가능','N':'불가능'}).fillna('정보 없음')
            st.dataframe(shown,hide_index=True,width='stretch')
            st.download_button('부상 이력 CSV',shown.to_csv(index=False).encode('utf-8-sig'),f'{soldier}_부상이력.csv','text/csv')
    with st.expander('개인 측정 자료 다운로드·기준'):
        st.download_button('개인 전체 측정·판정·변화 CSV',history.to_csv(index=False).encode('utf-8-sig'),f'{soldier}_체력상세.csv','text/csv')
        metadata=personal_metadata()
        st.write(metadata['비교']);st.write(metadata['주의'])
        st.caption('측정 당시 남성 19~24세 기준 · 종목별 등급이며 종합 인증등급이 아닙니다. 생성일: '+metadata['생성일시'])
