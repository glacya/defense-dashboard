"""샘플 페이지 3: 개인 장병 상세."""
import pandas as pd
import streamlit as st
from dashboard.py.main_sample import filtered_data, render_header, show_table

render_header('페이지 3 · 개인 상세', '장병을 선택해 체력 등급과 추천 운동 예시를 확인합니다.')
data = filtered_data().set_index('장병번호')
selected = st.selectbox('샘플 장병 선택', data.index, format_func=lambda sid:f'{data.loc[sid,"이름"]} · {sid}')
person = data.loc[selected]
st.subheader(f'{person["이름"]} · {person["계급"]} · {person["부대"]}')
show_table(pd.DataFrame([{'종목':event, '등급':'3등급 미만' if person[event]==0 else f'{person[event]}등급'} for event in ['근력','근지구력','심폐지구력','유연성']]))
st.info(f'추천 운동 예시: {person["추천 운동"]}')
