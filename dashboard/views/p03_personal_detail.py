"""3번 화면: 개인 장병의 기본·신체·체력 변화 및 부상 이력입니다."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from config import DASHBOARD_DIR
from dashboard.py.personal_detail_data import load_personal
from dashboard.py.followup_fitness_types import load_fitness_types
from dashboard.py.followup_probability import load_probabilities
from dashboard.py.personal_fitness_profile import load_personal_profile
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
        data,injuries,metadata,injury_present=load_personal()
    except FileNotFoundError:
        st.warning('개인 상세용 분석 파일 또는 원본이 없습니다. 분석을 먼저 실행하세요.')
        st.code('python -m data.scripts.main analysis',language='powershell');st.stop()
    except (ValueError,KeyError,pd.errors.EmptyDataError) as error:
        st.error(f'자료 확인이 필요합니다: {error}');st.stop()
    st.subheader('장병 찾기')
    region_filter,unit_filter,search_filter=st.columns(3)
    people=data[['SOLDIER_ID','SOLDIER_NAME','REGION_NAME','RANK_NAME','UNIT_NAME']].drop_duplicates('SOLDIER_ID')
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
    history=data.loc[data.SOLDIER_ID.eq(soldier)].sort_values('ROUND')
    rounds=history.ROUND.astype(int).tolist()
    number=st.radio('상세 측정 회차',rounds,index=len(rounds)-1,horizontal=True,format_func=lambda value:f'{value}차')
    row=history.loc[history.ROUND.eq(number)].iloc[0]
    person_injuries=injuries.loc[injuries.SOLDIER_ID.eq(soldier)]
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
         '해당' if row.MANAGED else '확인된 조건 없음',f'{len(person_injuries)}건' if injury_present else '자료 없음']):
        column.metric(label,value,border=True)
    st.caption('부상 기록은 전체 보유 이력입니다. 발생일이 없어 선택 측정 회차의 부상으로 해석하지 않습니다.')
    with st.container(border=True):
        st.markdown('**다음 차수 미통과 예측**')
        try:
            probabilities=load_probabilities()
            prediction=probabilities.loc[probabilities.SOLDIER_ID.eq(soldier)]
        except (OSError,ValueError,KeyError,pd.errors.EmptyDataError,SQLAlchemyError) as error:
            st.info(f'미통과 확률 자료를 확인할 수 없습니다: {error}')
        else:
            if prediction.empty:
                st.info('이 장병의 다음 차수 미통과 확률 자료가 없습니다.')
            else:
                predicted=prediction.iloc[0]
                probability_panel,risk_panel=st.columns(2)
                probability_panel.metric('다음 차수 미통과 확률',f'{predicted.FAILURE_PROBABILITY:.2%}')
                risk_panel.metric('위험 등급',predicted.RISK_LEVEL)
                st.progress(float(predicted.FAILURE_PROBABILITY))
                st.caption('2·3차 측정 자료로 예측한 4차 미통과 확률입니다. 선택 회차를 바꿔도 예측값은 동일합니다.')
    st.subheader('회차별 신체 변화')
    body_dates=pd.to_datetime(history.MESURE_DE.astype(str).str.removesuffix('.0'),
                              format='%Y%m%d',errors='coerce').dt.strftime('%Y-%m-%d').fillna('날짜 정보 없음')
    body_options=[('키','HEIGHT','cm','#2563eb'),('체중','WEIGHT','kg','#0f766e'),
                  ('BMI','BMI','kg/m²','#7c3aed'),('체지방률','BODY_FAT_PERCENTAGE','%','#ea580c')]
    for column,(body_label,body_event,body_unit,color) in zip(st.columns(4),body_options):
        with column,st.container(border=True):
            values=pd.to_numeric(history[body_event],errors='coerce').replace([float('inf'),float('-inf')],float('nan'))
            selected_value=values.loc[history.ROUND.eq(number)].iloc[0]
            baseline=values.loc[history.ROUND.eq(1)]
            change=selected_value-baseline.iloc[0] if not baseline.empty else float('nan')
            change_unit='%p' if body_event=='BODY_FAT_PERCENTAGE' else body_unit
            st.metric(f'{body_label} · {number}차',f'{formatted(selected_value)} {body_unit}',
                      delta=f'{change:+.2f} {change_unit} · 1차 대비' if pd.notna(change) else None,
                      delta_color='off',border=False)
            if values.notna().any():
                trend=go.Figure(go.Scatter(
                    x=history.ROUND,y=values,mode='lines+markers+text',connectgaps=False,
                    text=[f'{value:.2f}'.rstrip('0').rstrip('.') if pd.notna(value) else '' for value in values],
                    textposition='top center',cliponaxis=False,
                    customdata=list(zip(body_dates,history.AGE.map(lambda value:formatted(value,0)))),
                    line={'color':color,'width':3},
                    marker={'size':[12 if value==number else 7 for value in history.ROUND],
                            'color':color,'line':{'color':'white','width':2}},
                    hovertemplate=f'%{{x}}차 · %{{customdata[0]}}<br>나이 %{{customdata[1]}}세<br>{body_label} %{{y:.2f}} {body_unit}<extra></extra>',
                ))
                trend.add_vline(x=number,line_color='#94a3b8',line_dash='dot')
                if body_event=='BMI':
                    trend.add_hrect(y0=18.5,y1=25,fillcolor='#0f766e',opacity=.06,line_width=0,
                                    layer='below')
                    trend.add_hline(y=25,line_color='#ca8a04',line_dash='dot')
                minimum,maximum=float(values.min()),float(values.max())
                padding=max((maximum-minimum)*.35, .5 if body_event in ('HEIGHT','BMI') else 1)
                trend.update_layout(height=205,showlegend=False,
                                    margin={'t':30,'b':35,'l':40,'r':25},
                                    xaxis={'tickmode':'array','tickvals':rounds,'showgrid':False,
                                           'ticktext':[f'{value}차' for value in rounds]},
                                    yaxis={'range':[minimum-padding,maximum+padding],
                                           'tickformat':'.1f','nticks':4,'zeroline':False},
                                    paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(trend,width='stretch',key=f'personal_body_trend_{body_event}',
                                config={'displayModeBar':False})
                if body_event=='BMI':
                    st.caption('옅은 초록: 18.5 이상 25 미만 · 점선: 25')
            else:
                st.info('측정 기록이 없습니다.')
    st.caption('점선은 선택 회차입니다. 점에 마우스를 올리면 측정일과 나이를 확인할 수 있습니다. 항목별 세로축 척도는 다릅니다.')
    with st.container(border=True,key='personal-type-recommendation'):
        type_panel,recommendation_panel=st.columns([1,1.5],gap='medium')
        try:
            classified,_=load_fitness_types(history[['SOLDIER_ID','MESURE_ID','ROUND']])
        except (OSError,ValueError,KeyError,pd.errors.EmptyDataError) as error:
            st.warning(f'체력유형 자료를 확인할 수 없습니다: {error}')
        else:
            classification=classified.loc[classified.ROUND.eq(number)].iloc[0]
            if pd.isna(classification.TYPE_NAME):
                st.info('선택 회차의 체력유형 분류 정보가 없습니다.')
            else:
                with type_panel,st.container(border=True):
                    st.subheader(f'{number}차 체력유형')
                    with st.container():
                        st.markdown(f'**{classification.TYPE_NAME}**')
                        st.caption(
                            f'평균 백분위 {int(classification.AVERAGE_PERCENTILE_GRADE)}등급 · '
                            f'군집 {int(classification.CLUSTER)} · {number}차 측정 기준'
                        )
                        try:
                            personal_profile,cluster_profile,member_count=load_personal_profile(row.MESURE_ID)
                        except (OSError,ValueError,KeyError,pd.errors.EmptyDataError) as error:
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
                with recommendation_panel,st.container(border=True):
                    render_recommendation(int(classification.AVERAGE_PERCENTILE_GRADE),int(classification.CLUSTER),
                                          person_injuries, injury_present)
    fitness,changes,injury=st.tabs(['체력측정·등급','회차별 변화','부상 이력'])
    with fitness:
        comparison_title,standards_panel=st.columns([1.4,1],vertical_alignment='top')
        with comparison_title:
            st.subheader(f'{number}차 종목별 기준 비교')
        with standards_panel:
            standard_rows=''.join(
                f'<tr><td style="text-align:left;padding:3px 8px">{label} ({unit})</td>'
                + ''.join(f'<td style="padding:3px 8px">{grade_cut(event,grade):g}</td>' for grade in (1,2,3))
                + '</tr>' for event,(label,unit) in EVENTS.items())
            st.markdown(
                '<div style="font-size:0.72rem;color:#68798b;text-align:right;margin-bottom:12px">'
                '<div style="font-weight:600;margin-bottom:4px">체력 등급 기준 · 남성 19~24세</div>'
                '<table style="font-size:inherit;width:100%;text-align:right;border-collapse:collapse">'
                '<thead><tr style="border-bottom:1px solid #dfe6ed"><th style="text-align:left;padding:3px 8px">종목</th>'
                '<th>1등급</th><th>2등급</th><th>3등급</th></tr></thead>'
                f'<tbody>{standard_rows}</tbody></table>'
                '<div style="margin-top:4px">각 기준값 이상 · 3등급 하한 미만은 미달</div></div>',
                unsafe_allow_html=True,
            )
        for column,(event,(label,unit)) in zip(st.columns(4),EVENTS.items()):
            with column,st.container(border=True):
                grade=row[f'{event}_GRADE']
                value=pd.to_numeric(row[event],errors='coerce')
                cut=grade_cut(event,3)
                judgment='판정 불가' if pd.isna(grade) else '미달' if grade==0 else '충족'
                color='#64748b' if pd.isna(grade) else '#dc2626' if grade==0 else '#0f766e'
                st.metric(label,f'{formatted(value)} {unit}')
                st.markdown(f'**{grade_label(grade)} · {judgment}**')
                if pd.notna(value) and float('-inf') < value < float('inf'):
                    comparison=go.Figure(go.Bar(
                        x=[value],y=[label],orientation='h',marker_color=color,
                        hovertemplate=f'{label} %{{x:.2f}} {unit}<extra></extra>',
                    ))
                    comparison.add_vline(x=cut,line_dash='dash',line_color='#ea580c',
                                         annotation_text='3등급 하한',annotation_position='top')
                    comparison.update_layout(height=155,showlegend=False,
                        margin={'t':35,'b':30,'l':5,'r':15},
                        xaxis={'title':unit,'range':[min(0,value*1.2),max(cut,value)*1.25]},
                        yaxis={'visible':False},paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(comparison,width='stretch',key=f'personal_grade_comparison_{event}',
                                    config={'displayModeBar':False})
                else:
                    st.info('측정 기록이 없습니다.')
                st.caption(f'3등급 하한: {cut:g} {unit}')
        st.caption('주황 점선은 남성 19~24세의 3등급 하한입니다. 종목별 단위와 축 범위가 다르며, 판정 불가 자료는 충족 여부를 표시하지 않습니다.')
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
        for offset in (0,2):
            for container,(event,(label,unit)) in zip(st.columns(2),list(EVENTS.items())[offset:offset+2]):
                with container,st.container(border=True):
                    reference=data[['ROUND',event]].copy()
                    reference[event]=pd.to_numeric(reference[event],errors='coerce').replace([float('inf'),float('-inf')],float('nan'))
                    reference=reference.groupby('ROUND')[event].agg(['mean','count']).sort_index()
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
        if not injury_present:
            st.warning('부상 원본 파일이 없습니다. 부상 없음으로 판단하지 않습니다.')
        elif person_injuries.empty:
            st.info('보유 부상 자료에서 이 장병의 기록이 없습니다.')
        else:
            shown=person_injuries.rename(columns={'INJURY_ID':'부상 식별자','SOLDIER_ID':'장병 식별자','INJURY_CATEGORY':'부상 대분류','INJURY_LOCATION':'부위','PREVENTABILITY':'예방 가능 여부','SEVERITY':'심각도'})
            shown['예방 가능 여부']=shown['예방 가능 여부'].map({'Y':'가능','N':'불가능'}).fillna('정보 없음')
            st.dataframe(shown,hide_index=True,width='stretch')
            st.download_button('부상 이력 CSV',shown.to_csv(index=False).encode('utf-8-sig'),f'{soldier}_부상이력.csv','text/csv')
    with st.expander('개인 측정 자료 다운로드·기준'):
        st.download_button('개인 전체 측정·판정·변화 CSV',history.to_csv(index=False).encode('utf-8-sig'),f'{soldier}_체력상세.csv','text/csv')
        st.write(metadata['비교']);st.write(metadata['주의'])
        st.caption('측정 당시 남성 19~24세 기준 · 종목별 등급이며 종합 인증등급이 아닙니다. 생성일: '+metadata['생성일시'])
