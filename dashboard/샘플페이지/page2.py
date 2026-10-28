"""샘플 페이지 2: 미달·예측 위험 장병 조회."""
import streamlit as st
from dashboard.py.main_sample import filtered_data, render_header, show_table

render_header('페이지 2 · 미달·위험 장병', '조건에 해당하는 가상 장병 명단입니다.')
data = filtered_data()
mode = st.radio('조회 대상', ['2종목 이상 미달', '미통과 확률 70% 이상', '전체'], horizontal=True)
if mode == '2종목 이상 미달':
    data = data.loc[data['미달 종목 수'].ge(2)]
elif mode == '미통과 확률 70% 이상':
    data = data.loc[data['미통과 확률(%)'].ge(70)]
st.metric('조회 인원 · 샘플', f'{len(data)}명')
show_table(data[['장병번호','이름','계급','부대','미달 종목 수','미통과 확률(%)']])
