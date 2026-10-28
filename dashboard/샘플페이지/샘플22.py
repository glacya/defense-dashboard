"""샘플22: DB 조회 결과를 필터링하는 위험 장병 명단."""

import streamlit as st

from dashboard.py.main_sample import render_header, show_table
from dashboard.py.sample_db import filtered_db_data

render_header('샘플22 · 미달·위험 장병', 'DB에서 읽은 가상 장병 명단입니다. 실제 예측 결과가 아닙니다.')
data = filtered_db_data()
mode = st.radio('조회 대상', ['2종목 이상 미달','미통과 확률 70% 이상','전체'], horizontal=True)
if mode == '2종목 이상 미달':
    data = data.loc[data['미달 종목 수'].ge(2)]
elif mode == '미통과 확률 70% 이상':
    data = data.loc[data['미통과 확률(%)'].ge(70)]
search = st.text_input('이름·장병번호 검색')
if search:
    data = data.loc[data['이름'].str.contains(search, regex=False) | data['장병번호'].str.contains(search, regex=False)]
st.metric('조회 인원 · DB 샘플', f'{len(data)}명')
show_table(data[['장병번호','이름','계급','부대','미달 종목 수','미통과 확률(%)']])
