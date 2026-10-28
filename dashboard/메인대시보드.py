"""체력 현황과 예측·운동 처방 예시를 연결하는 장병 체력관리 메인 화면."""

import hashlib

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.py.management_targets_data import load_targets
from data.scripts.analysis.analysis2.management_targets import REASONS

COLORS = ['#438DFF', '#25C6D8', '#F2A93B', '#F15B70']
STYLE = '''<style>
:root {color-scheme:dark; --st-background-color:#071321;
 --st-secondary-background-color:#10243A; --st-text-color:#EFF5FB;
 --st-primary-color:#2589FF; --st-border-color:#244666;}
.stApp,[data-testid="stAppViewContainer"] {
 background:radial-gradient(ellipse at 76% -18%,rgba(24,91,154,.34),transparent 46%),
 linear-gradient(145deg,#09192B 0%,#071321 58%,#050D18 100%); color:#EFF5FB;}
[data-testid="stHeader"] {background:rgba(7,19,33,.92);}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#0A1D33,#09192B 58%,#06101C);
 border-right:1px solid #244666;}
h1,h2,h3,p,label,[data-testid="stMetricValue"] {color:#EFF5FB;}
[data-testid="stCaptionContainer"] p {color:#AFC4D9;}
[data-testid="stMainBlockContainer"] {padding-top:5rem!important;}
[data-testid="stVerticalBlockBorderWrapper"]>div {border-color:#244666;}
[data-testid="stMetric"] {background:linear-gradient(145deg,#142F4B,#0D2035);
 border:1px solid #285073;border-radius:12px;padding:18px;
 box-shadow:inset 0 3px 0 #25C6D8,0 8px 22px rgba(0,0,0,.14);}
[data-testid="stMetricValue"] {color:#A9DFFF;font-weight:700;}
.eyebrow {color:#25C6D8;font-size:12px;letter-spacing:3px;font-weight:700;}
.demo {display:inline-block;background:#302A20;color:#FFD58B;border:1px solid #806239;
 border-radius:20px;padding:5px 12px;font-size:12px;margin-bottom:12px;}
div[class*="st-key-demo_"] {
 background:rgba(242,193,59,.08);border:1px solid #B58B2B!important;border-radius:12px;}
div[class*="st-key-demo_"] h3,
div[class*="st-key-demo_"] [data-testid="stCaptionContainer"] p {
 color:#FFD85A!important;}
</style>'''


def load_home_data() -> pd.DataFrame:
    """분석 자료를 읽고 자료 부재를 화면에 안내합니다."""
    try:
        data, _, _ = load_targets()
        return data
    except (OSError, ValueError, KeyError) as error:
        st.error(f'분석 자료를 읽을 수 없습니다: {error}')
        st.code('python -m data.scripts.analysis.pipeline', language='powershell')
        st.stop()


def demo_predictions(current: pd.DataFrame) -> pd.DataFrame:
    """장병 식별자로 재현 가능한 가상 예측·처방을 만들며 저장하지 않습니다."""
    result = current[['SOLDIER_ID', 'SOLDIER_NAME', 'RANK_NAME', 'UNIT_NAME']].copy()
    result.columns = ['장병번호', '이름', '계급', '소속']
    seeds = result['장병번호'].map(lambda value: int(hashlib.sha256(str(value).encode()).hexdigest()[:8], 16))
    result['미통과 확률(%)'] = seeds.map(lambda value: 10 + value % 86)
    result['위험 구간'] = result['미통과 확률(%)'].map(lambda value: '높음' if value >= 70 else '보통' if value >= 40 else '낮음')
    types = ['심폐 보완형', '근력 보완형', '근지구력 보완형', '유연성 보완형']
    prescriptions = ['걷기·가벼운 달리기 예시', '기초 저항 운동 예시', '맨몸 순환 운동 예시', '전신 스트레칭 예시']
    result['체력 유형'] = seeds.map(lambda value: types[(value // 100) % 4])
    result['추천 운동'] = seeds.map(lambda value: prescriptions[(value // 100) % 4])
    return result.sort_values('미통과 확률(%)', ascending=False)


def chart(figure) -> None:
    """샘플 대시보드와 동일한 남색 차트 스타일을 적용합니다."""
    figure.update_layout(height=290, margin=dict(l=10, r=20, t=15, b=10),
                         paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                         font=dict(color='#C6D3E0'), legend_title_text='',
                         xaxis=dict(gridcolor='#244666'), yaxis=dict(gridcolor='#244666'))
    st.plotly_chart(figure, width='stretch', config={'displayModeBar': False})


def scoped_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """예측 예시 화면에서 사용할 부대 범위를 선택합니다."""
    data = load_home_data()
    latest = data.sort_values('ROUND').drop_duplicates('SOLDIER_ID', keep='last')
    unit = st.sidebar.selectbox('부대', ['전체', *sorted(latest.UNIT_NAME.unique())])
    if unit != '전체':
        latest = latest.loc[latest.UNIT_NAME.eq(unit)]
    return latest, demo_predictions(latest)


def prediction_page() -> None:
    """가상 미통과 확률과 위험 장병을 조회합니다."""
    st.title('다음 회차 미통과 예측')
    st.warning('더미데이터입니다. 표시 확률은 실제 예측 모델의 결과가 아닙니다.')
    _, demo = scoped_data()
    threshold = st.slider('예시 위험 기준 (%)', 10, 95, 70)
    shown = demo.loc[demo['미통과 확률(%)'].ge(threshold)]
    st.metric('예시 위험 장병', f'{len(shown):,}명')
    st.dataframe(shown.iloc[:, :6].style.set_properties(**{'color':'#FFD85A','background-color':'#302A20'}), hide_index=True, width='stretch')


def prescription_page() -> None:
    """가상 체력 유형별 추천 운동을 조회합니다."""
    st.title('체력유형·운동추천')
    st.warning('더미데이터입니다. 유형과 추천 운동은 화면 구성 예시이며 개인 맞춤 처방이 아닙니다.')
    _, demo = scoped_data()
    selected = st.selectbox('체력 유형', ['전체', *sorted(demo['체력 유형'].unique())])
    if selected != '전체':
        demo = demo.loc[demo['체력 유형'].eq(selected)]
    st.dataframe(demo[['장병번호', '이름', '소속', '체력 유형', '추천 운동']].style.set_properties(**{'color':'#FFD85A','background-color':'#302A20'}), hide_index=True, width='stretch')


def home() -> None:
    """실제 체력 요약과 가상 예측·처방을 메인에 표시합니다."""
    st.markdown('<div class="eyebrow">MILITARY FITNESS · OVERVIEW</div>', unsafe_allow_html=True)
    st.title('장병 체력관리 메인대시보드')
    st.caption('전체 현황부터 우선 관리 대상과 운동 지도까지, 한눈에 확인하세요.')
    data = load_home_data()
    st.sidebar.divider()
    st.sidebar.subheader('조회 조건')
    rounds = sorted(data.ROUND.unique())
    number = st.sidebar.selectbox('측정 회차', rounds, index=len(rounds)-1, format_func=lambda value: f'{int(value)}차')
    unit = st.sidebar.selectbox('부대', ['전체', *sorted(data.UNIT_NAME.unique())])
    scoped = (data if unit == '전체' else data.loc[data.UNIT_NAME.eq(unit)]).copy()
    scoped['MAIN_MANAGED'] = scoped['PERSISTENT_FAIL']
    current = scoped.loc[scoped.ROUND.eq(number)]
    st.caption(f'{int(number)}차 측정 기준 · {unit} · 체력 현황은 분석 데이터, 예측·운동 처방은 더미데이터')
    with st.container(horizontal=True):
        st.metric('측정 장병', f'{len(current):,}명', border=True)
        st.metric('체력 미달 (2종목 이상)', f'{int(current.FAIL_COUNT.ge(2).sum()):,}명', border=True)
        st.metric('동일종목 연속미달자', f'{int(current.MAIN_MANAGED.sum()):,}명', border=True)
        st.metric('1차 대비 악화', f'{int(current.WORSENED.sum()):,}명', border=True)
    st.caption('체력 미달: 2종목 이상 미달한 장병. 동일종목 연속미달자: 같은 종목이 최근 3회 연속 미달인 장병이며, 여러 종목에 해당해도 한 번만 집계합니다. 1·2차는 3회 연속 여부를 판정할 수 없습니다.')
    left, right = st.columns([1.1, 1])
    with left, st.container(border=True):
        st.subheader('회차별 미달·동일종목 연속미달자 추이')
        history = scoped.loc[scoped.ROUND.le(number)].copy()
        trend = history.groupby('ROUND').agg(미달=('FAIL_COUNT', lambda values: int(values.ge(2).sum())), 관리대상=('MAIN_MANAGED', 'sum')).reset_index()
        trend['측정 회차'] = trend.ROUND.map(lambda value: f'{int(value)}차')
        trend = trend.rename(columns={'관리대상':'동일종목 연속미달자'})
        chart(px.line(trend, x='측정 회차', y=['미달', '동일종목 연속미달자'], markers=True, color_discrete_sequence=COLORS, labels={'value': '인원(명)', 'variable': ''}))
    with right, st.container(border=True):
        st.subheader('관리 사유별 대상 인원')
        reasons = pd.DataFrame({'관리 사유': list(REASONS.values()), '인원': [int(current[flag].sum()) for flag in REASONS]})
        chart(px.bar(reasons, x='인원', y='관리 사유', orientation='h', color_discrete_sequence=['#25C6D8'], text='인원'))
        st.caption('사유별 인원은 중복될 수 있습니다.')
    st.markdown('<span class="demo">DEMO · 미통과 예측 / 운동 처방</span>', unsafe_allow_html=True)
    demo = demo_predictions(current)
    risk = demo.loc[demo['위험 구간'].eq('높음')]
    left, right = st.columns([1.35, 1])
    with left, st.container(border=True,key='demo_prediction'):
        st.subheader('미통과 예측 위험 장병')
        st.caption(f'가상 확률 70% 이상 {len(risk):,}명 · 상위 8명 · 실제 예측 결과 아님')
        st.dataframe(risk[['이름', '계급', '소속', '미통과 확률(%)']].head(8).style.set_properties(**{'color':'#FFD85A','background-color':'#302A20'}), hide_index=True, width='stretch',
                     column_config={'미통과 확률(%)': st.column_config.ProgressColumn(min_value=0, max_value=100, format='%d%%')})
        st.page_link(PREDICTION, label='미통과 예측 예시 전체 보기 →')
    with right, st.container(border=True,key='demo_prescription'):
        st.subheader('운동 처방 예시')
        st.caption('가상 유형별 배정 현황 · 실제 처방 아님')
        groups = demo['체력 유형'].value_counts().rename_axis('체력 유형').reset_index(name='인원')
        chart(px.pie(groups, names='체력 유형', values='인원', hole=.7, color_discrete_sequence=['#FFE680','#FFD044','#DBA922','#AA7B12']))
        st.page_link(PRESCRIPTION, label='유형별 추천 운동 예시 보기 →')
    st.subheader('빠른 이동')
    for column, pages in zip(st.columns(3), [REAL_PAGES[:2], REAL_PAGES[2:4], REAL_PAGES[4:]]):
        with column, st.container(border=True):
            for page in pages:
                st.page_link(page, label=page.title)
    st.caption('예측 확률·체력 유형·추천 운동은 화면 시연용 가상 값이며 저장되지 않습니다.')


def main() -> None:
    """메인과 기존 6개 화면, 예측·추천 예시 화면을 연결합니다."""
    st.set_page_config(page_title='장병 체력관리 메인대시보드', page_icon='🪖', layout='wide')
    st.markdown(STYLE, unsafe_allow_html=True)
    st.sidebar.title('🪖 장병 체력관리')
    st.sidebar.caption('FITNESS MANAGEMENT')
    selected = st.navigation({
        '메인': [st.Page(home, title='메인대시보드', icon=':material/home:', default=True)],
        '체력 조회·분석': REAL_PAGES[:3],
        '예측·운동추천': [PREDICTION, PRESCRIPTION],
        '부상 관리': [REAL_PAGES[3], REAL_PAGES[5]],
        '체력 지도': [REAL_PAGES[4]],
    })
    selected.run()


if __name__ == '__main__':
    REAL_PAGES = [st.Page(filename, title=title) for filename, title in [
        ('장병체력_전체현황.py', '① 전체 체력 현황'),
        ('장병체력_미달_악화대상자조회.py', '② 미달·악화 대상자'),
        ('장병체력_개인상세.py', '③ 개인 장병 상세'),
        ('장병체력_부상현황.py', '⑥ 부상 현황'),
        ('장병체력_지도후속조치.py', '⑦ 체력 지도·후속조치'),
        ('장병체력_부상후속조치.py', '⑧ 부상 후속조치'),
    ]]
    PREDICTION = st.Page(prediction_page, title='④ 미통과 예측 · 예시')
    PRESCRIPTION = st.Page(prescription_page, title='⑤ 운동추천 · 예시')
    main()
