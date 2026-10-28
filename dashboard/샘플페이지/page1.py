"""샘플 페이지 1: 전체 체력 현황."""
from dashboard.py.main_sample import render_header, render_overview

render_header('페이지 1 · 전체 현황', '종목별 미달 인원과 체력 유형을 확인합니다. 모든 데이터는 예시입니다.')
render_overview()
