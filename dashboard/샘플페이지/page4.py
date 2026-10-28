"""샘플 페이지 4: 체력 유형별 운동 처방."""
import streamlit as st
from dashboard.py.main_sample import filtered_data, render_header, show_table

render_header('페이지 4 · 운동 처방', '유형별 운동 추천 화면 예시입니다. 실제 개인 맞춤 처방이 아닙니다.')
data = filtered_data()
kind = st.selectbox('체력 유형', ['전체',*sorted(data['체력 유형'].unique())])
if kind != '전체':
    data = data.loc[data['체력 유형'].eq(kind)]
show_table(data[['장병번호','이름','부대','체력 유형','추천 운동']])
