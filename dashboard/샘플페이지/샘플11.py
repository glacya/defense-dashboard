"""샘플11: DB 조회 결과를 사용하는 전체 체력 현황."""

import plotly.express as px
import streamlit as st

from dashboard.py.main_sample import COLORS, render_header, show_chart
from dashboard.py.sample_db import filtered_db_data

render_header('샘플11 · 전체 현황', 'SQL로 읽은 더미데이터를 카드와 그래프로 표시합니다.')
data = filtered_db_data()
with st.container(horizontal=True):
    st.metric('샘플 장병', f'{len(data)}명')
    st.metric('2종목 이상 미달', f'{data["미달 종목 수"].ge(2).sum()}명')
    st.metric('예측 위험 · 70% 이상', f'{data["미통과 확률(%)"].ge(70).sum()}명')
left, right = st.columns(2)
with left, st.container(border=True):
    st.subheader('종목별 미달 인원 · DB 샘플')
    counts = data[['근력','근지구력','심폐지구력','유연성']].eq(0).sum().rename_axis('종목').reset_index(name='인원')
    show_chart(px.bar(counts, x='종목', y='인원', text='인원', color_discrete_sequence=['#FFD044']))
with right, st.container(border=True):
    st.subheader('체력 유형 분포 · DB 샘플')
    groups = data['체력 유형'].value_counts().rename_axis('유형').reset_index(name='인원')
    show_chart(px.pie(groups, names='유형', values='인원', hole=.65, color_discrete_sequence=COLORS))
