"""6번 화면: 전체 부상·종목별 등급 비교·개인 부상 이력입니다."""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.py.injury_overview_data import load_injury_overview
from data.scripts.analysis.fitness_overview import EVENTS
from data.scripts.analysis.injury_overview import GRADE_LABELS

INJURY_LABELS={'INJURY_ID':'부상 식별자','SOLDIER_ID':'장병 식별자','INJURY_CATEGORY':'부상 대분류',
               'INJURY_LOCATION':'부상 부위','SEVERITY':'심각도','PREVENTABILITY':'예방 가능 여부'}


def main() -> None:
    """부상 기록 전체를 기준으로 현황과 개인 기록을 표시합니다."""
    st.set_page_config(page_title='부상 현황',page_icon='🩹',layout='wide')
    st.caption('장병 체력관리 / 06')
    st.title('부상 현황')
    st.write('부상 인원과 건수를 구분하고, 체력등급에 따른 분포와 개인별 기록을 확인합니다.')
    try:
        people,grades,summary,metadata,injuries=load_injury_overview()
    except FileNotFoundError:
        st.warning('분석 결과 또는 원본 파일이 없습니다. 아래 명령으로 생성하세요.')
        st.code('python -m data.scripts.analysis.injury_overview',language='powershell');st.stop()
    except (ValueError,KeyError,pd.errors.EmptyDataError) as error:
        st.error(f'자료를 확인해 주세요: {error}');st.stop()
    if summary.empty:
        st.info('표시할 집계 자료가 없습니다.');st.stop()
    st.info('합성 부상 자료 · 발생일이 없어 전체 보유 기록을 집계합니다. 최신 체력등급과의 비교이며 실제 부상 위험을 입증하는 결과가 아닙니다.')
    row=summary.iloc[0]
    values=[f'{int(row["전체장병수"]):,}명',f'{int(row["부상인원"]):,}명',f'{int(row["부상건수"]):,}건',
            f'{row["부상자비율"]:.1f}%' if pd.notna(row['부상자비율']) else '해당 없음',f'{int(row["반복부상인원"]):,}명']
    for col,label,value in zip(st.columns(5),['전체 장병 수','부상 기록 보유 인원','부상 건수','부상자 비율','2건 이상 부상 기록'],values):
        col.metric(label,value,border=True)
    st.caption('전체 장병 명단이 분모입니다. 한 장병에게 부상이 여러 건 있어도 부상 인원은 1명입니다.')
    overall,comparison,individual=st.tabs(['전체 부상 분포','체력등급별 비교','개인별 부상 이력'])
    with overall:
        if injuries.empty:
            st.info('부상 파일에 기록이 없습니다.')
        else:
            left,right=st.columns(2)
            for container,column,title in [(left,'INJURY_LOCATION','부위별 부상 건수'),(right,'SEVERITY','심각도별 부상 건수')]:
                counts=injuries.groupby(column,dropna=False).size().rename('건수').reset_index().rename(columns={column:'구분'})
                with container,st.container(border=True):
                    st.subheader(title)
                    st.plotly_chart(px.bar(counts,x='구분',y='건수',text='건수',color_discrete_sequence=['#d47746']),width='stretch')
            st.caption('분포 그래프는 부상 건수 기준입니다. 같은 장병이 여러 번 포함될 수 있습니다.')
    with comparison:
        event=st.selectbox('비교할 체력 종목',list(EVENTS),format_func=lambda key:EVENTS[key][0])
        grade_table=grades.loc[grades['종목'].eq(EVENTS[event][0])]
        left,right=st.columns(2)
        with left:
            chart=px.bar(grade_table,x='등급',y='부상자비율',text='부상자비율',
                category_orders={'등급':list(GRADE_LABELS.values())},hover_data=['전체인원','부상인원','부상건수'],color_discrete_sequence=['#2563eb'])
            chart.update_traces(texttemplate='%{text:.1f}%')
            chart.update_layout(yaxis_range=[0,100],yaxis_title='부상자 비율 (%)',title='최신 종목 등급별 부상자 비율')
            st.plotly_chart(chart,width='stretch')
        with right:
            st.dataframe(grade_table.drop(columns='종목'),hide_index=True,width='stretch',
                column_config={'부상자비율':st.column_config.NumberColumn(format='%.1f%%')})
        st.caption('분모: 각 등급의 전체 장병 수. 0명인 등급의 비율은 계산하지 않습니다. 종합등급이 아닌 종목별 등급이며 판정 불가 집단도 별도 표시합니다.')
        st.download_button('등급별 부상 집계 CSV',grade_table.to_csv(index=False).encode('utf-8-sig'),'체력등급별_부상현황.csv','text/csv')
    with individual:
        left,right=st.columns(2)
        search=left.text_input('이름·장병번호 검색')
        condition=right.selectbox('부상 기록',['전체','기록 있음','2건 이상','기록 없음'])
        shown=people.copy()
        if search:
            shown=shown.loc[shown.SOLDIER_NAME.str.contains(search,regex=False)|shown.SOLDIER_ID.str.contains(search,regex=False)]
        if condition=='기록 있음':
            shown=shown.loc[shown.INJURY_COUNT.gt(0)]
        elif condition=='2건 이상':
            shown=shown.loc[shown.INJURY_COUNT.ge(2)]
        elif condition=='기록 없음':
            shown=shown.loc[shown.INJURY_COUNT.eq(0)]
        cols=['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME','INJURY_COUNT']
        display=shown[cols].rename(columns={'SOLDIER_ID':'장병 식별자','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속','INJURY_COUNT':'부상 건수'})
        st.caption(f'조회 결과 {len(shown):,}명 · 신상 정보는 합성 자료입니다.')
        st.dataframe(display,hide_index=True,width='stretch')
        if shown.empty:
            st.info('검색 조건에 해당하는 장병이 없습니다.')
        else:
            lookup=shown.set_index('SOLDIER_ID')
            soldier=st.selectbox('장병 선택',shown.SOLDIER_ID.tolist(),format_func=lambda sid:f'{lookup.loc[sid,"SOLDIER_NAME"]} · {sid}')
            person=lookup.loc[soldier]
            st.write(f'**{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}**')
            records=injuries.loc[injuries.SOLDIER_ID.eq(soldier)].rename(columns=INJURY_LABELS)
            if records.empty:
                st.info('보유 부상 자료에서 해당 장병의 기록이 없습니다. 현재 건강 상태나 회복 여부를 뜻하지 않습니다.')
            else:
                records['예방 가능 여부']=records['예방 가능 여부'].map({'Y':'가능','N':'불가능'}).fillna('정보 없음')
                st.dataframe(records,hide_index=True,width='stretch')
                st.download_button('개인 부상 기록 CSV',records.to_csv(index=False).encode('utf-8-sig'),f'{soldier}_부상이력.csv','text/csv')
        st.caption('발생일·회복 상태·운동 제한 항목은 원본에 없어 표시하지 않습니다.')
    with st.expander('집계 기준·자료 출처'):
        for key in ['집계범위','등급','기간','합성','중복']:
            st.write(metadata[key])
        st.caption('분석 생성일: '+metadata['생성일시'])


if __name__=='__main__':
    main()
