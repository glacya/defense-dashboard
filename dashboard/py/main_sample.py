"""메인 샘플에서 공유하는 더미데이터·스타일·차트 표시 함수."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from config import ROOT_DIR

ASSETS = ROOT_DIR / 'dashboard' / 'assets' / 'main_sample'
COLORS = ['#FFE680', '#FFD044', '#DBA922', '#AA7B12']



def apply_style() -> None:
    """분리된 CSS 파일을 읽어 공통 스타일을 적용합니다."""
    st.markdown('<style>' + (ASSETS / 'style.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


def render_header(title: str, description: str) -> None:
    """JS로 동작하는 시각·데이터 안내와 화면 제목을 표시합니다."""
    header = st.components.v2.component(
        'main_sample_header',
        html='<div class="sample-status"><span class="sample-badge">SAMPLE DATA</span><span id="sample-clock"></span><button id="sample-help" type="button" aria-expanded="false">데이터 안내</button></div><p id="sample-note" hidden>표시된 장병과 수치는 화면 시연용 가상 데이터입니다.</p>',
        css=(ASSETS / 'header.css').read_text(encoding='utf-8'),
        js=(ASSETS / 'main.js').read_text(encoding='utf-8'),
    )
    header(key='sample_header')
    st.title(title)
    st.caption(description)


@st.cache_data(show_spinner=False)
def _read_sample_csv(path: str, modified_ns: int) -> pd.DataFrame:
    """CSV 읽기 결과를 캐시하고 파일 변경 시 새로 읽습니다."""
    data = pd.read_csv(path, encoding='utf-8-sig', dtype={'장병번호': 'string'})
    required = ['장병번호','이름','계급','부대','미통과 확률(%)',
                '근력','근지구력','심폐지구력','유연성','미달 종목 수','체력 유형','추천 운동']
    missing = set(required) - set(data.columns)
    if missing:
        raise ValueError(f'샘플 CSV 필수 열 누락: {sorted(missing)}')
    if data.empty or data['장병번호'].isna().any() or data['장병번호'].duplicated().any():
        raise ValueError('샘플 CSV의 장병번호가 누락·중복되었거나 데이터가 없습니다.')
    return data


def sample_data() -> pd.DataFrame:
    """더미 CSV를 읽으며 파일 수정 시각을 캐시 갱신 기준으로 사용합니다."""
    path = ASSETS / 'sample_soldiers.csv'
    try:
        return _read_sample_csv(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError) as error:
        st.error(f'샘플 데이터를 읽을 수 없습니다: {error}')
        st.stop()


def filtered_data() -> pd.DataFrame:
    """페이지 전반에 동일한 부대 선택을 적용합니다."""
    data = sample_data()
    unit = st.sidebar.selectbox('조회 부대', ['전체','1중대','2중대','3중대'], key='sample_unit')
    return data if unit == '전체' else data.loc[data['부대'].eq(unit)]


def show_chart(figure) -> None:
    """남색 배경에 노란색 샘플 차트를 표시합니다."""
    figure.update_layout(height=310, margin=dict(l=10,r=10,t=20,b=10),
                         paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                         font=dict(color='#FFD85A'), xaxis=dict(gridcolor='#244666'), yaxis=dict(gridcolor='#244666'))
    st.plotly_chart(figure, width='stretch')


def show_table(data: pd.DataFrame) -> None:
    """가상 데이터를 노란색 표로 표시합니다."""
    st.dataframe(data.style.set_properties(**{'color':'#FFD85A','background-color':'#302A20'}), hide_index=True, width='stretch')


def render_overview() -> None:
    """실제 명단 없이 가상 데이터의 요약과 분포를 표시합니다."""
    data = filtered_data()
    with st.container(horizontal=True):
        st.metric('샘플 장병', f'{len(data)}명')
        st.metric('2종목 이상 미달', f'{data["미달 종목 수"].ge(2).sum()}명')
        st.metric('예측 위험 · 70% 이상', f'{data["미통과 확률(%)"].ge(70).sum()}명')
        st.metric('운동 처방 예시', f'{len(data)}명')
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.subheader('종목별 미달 인원 · 샘플')
        counts = data[['근력','근지구력','심폐지구력','유연성']].eq(0).sum().rename_axis('종목').reset_index(name='인원')
        show_chart(px.bar(counts, x='종목', y='인원', text='인원', color_discrete_sequence=['#FFD044']))
    with right, st.container(border=True):
        st.subheader('체력 유형 분포 · 샘플')
        types = data['체력 유형'].value_counts().rename_axis('유형').reset_index(name='인원')
        show_chart(px.pie(types, names='유형', values='인원', hole=.65, color_discrete_sequence=COLORS))
