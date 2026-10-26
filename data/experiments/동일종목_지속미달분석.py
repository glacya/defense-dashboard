"""Visualize outputs from 장병별_회차별미달정보생성.py.
Run from project root: python data/experiments/동일종목_지속미달분석.py
화면 실행: python -m streamlit run data/experiments/동일종목_지속미달분석.py
Requires: pip install pandas plotly
"""
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / 'data/experiments/results'
DETAIL_PATH = RESULT_DIR / 'fitness_risk_by_round.csv'
SUMMARY_PATH = RESULT_DIR / 'fitness_risk_summary.csv'
HTML_PATH = RESULT_DIR / 'fitness_risk_dashboard.html'
PERSISTENT_PATH = RESULT_DIR / 'fitness_persistent_by_area.csv'

PERSON_COL = 'SOLDIER_ID'
AREAS = {
    'strength_risk': '근력',
    'endurance_risk': '근지구력',
    'cardio_risk': '심폐지구력',
    'flexibility_risk': '유연성',
}
ROUNDS = [1, 2, 3]


def parse_risk(s):
    """Read CSV risk booleans safely (True/False/blank)."""
    values = s.astype('string').str.strip().str.lower()
    invalid = values.notna() & ~values.isin(['true', 'false', '1', '0'])
    if invalid.any():
        raise ValueError(f'{s.name}: 알 수 없는 미달 값: {values[invalid].unique().tolist()}')
    return values.map({'true': True, 'false': False, '1': True, '0': False}).astype('boolean')


def main(show_ui=False):
    for path in [DETAIL_PATH, SUMMARY_PATH]:
        if not path.exists():
            raise FileNotFoundError(f'분석 결과 파일이 없습니다: {path}\n먼저 장병별_회차별미달정보생성.py를 실행하세요.')

    detail = pd.read_csv(DETAIL_PATH, dtype={PERSON_COL: 'string'})
    summary = pd.read_csv(SUMMARY_PATH, dtype={PERSON_COL: 'string'})
    required_detail = {PERSON_COL, 'round', 'risk_status', 'weak_count', *AREAS}
    required_summary = {PERSON_COL, 'weak_1', 'weak_2', 'weak_3'}
    if required_detail - set(detail.columns) or required_summary - set(summary.columns):
        raise ValueError('결과 CSV의 필수 컬럼이 부족합니다. 원본 분석 코드를 다시 실행하세요.')
    for col in AREAS:
        detail[col] = parse_risk(detail[col])
    detail['round'] = pd.to_numeric(detail['round'], errors='raise').astype(int)
    detail = detail.loc[detail['round'].isin(ROUNDS)].copy()
    detail['weak_count'] = pd.to_numeric(detail['weak_count'], errors='coerce')
    if detail.duplicated([PERSON_COL, 'round']).any():
        raise ValueError('한 장병의 동일 회차가 중복되어 있습니다.')

    # 요약 CSV의 네 컬럼으로 변화 유형을 계산하되, 세 회차 모두 판정 가능한 경우만 비교한다.
    comparable = detail.assign(valid=detail['risk_status'].isin(['정상', '취약'])).groupby(PERSON_COL).agg(
        valid=('valid', 'all'), rounds=('round', 'nunique')
    )
    comparable_ids = comparable.index[comparable['valid'] & comparable['rounds'].eq(3)]
    for col in ['weak_1', 'weak_2', 'weak_3']:
        summary[col] = pd.to_numeric(summary[col], errors='coerce')
    comparable_rows = summary[PERSON_COL].isin(comparable_ids) & summary[['weak_1', 'weak_2', 'weak_3']].notna().all(axis=1)
    summary['change_type'] = '비교불가'
    summary.loc[comparable_rows, 'change_type'] = '유지'
    summary.loc[comparable_rows & summary['weak_3'].lt(summary['weak_1']), 'change_type'] = '개선'
    summary.loc[comparable_rows & summary['weak_3'].gt(summary['weak_1']), 'change_type'] = '악화'

    # Three complete evaluations are necessary for a valid persistence KPI.
    complete = detail.assign(
        complete=detail['risk_status'].isin(['정상', '취약']) & detail[list(AREAS)].notna().all(axis=1)
    )
    valid_ids = (
        complete.groupby(PERSON_COL)
        .agg(n_rounds=('round', 'nunique'), all_complete=('complete', 'all'))
        .query('n_rounds == 3 and all_complete')
        .index
    )
    valid = detail[detail[PERSON_COL].isin(valid_ids)].copy()
    if valid.empty:
        raise ValueError('1·2·3차 네 종목 모두 판정 가능한 장병이 없습니다.')
    persistent = pd.DataFrame(index=valid_ids)
    for col, name in AREAS.items():
        wide = valid.pivot(index=PERSON_COL, columns='round', values=col)
        persistent[name] = wide[ROUNDS].eq(True).all(axis=1).astype(bool)
    persistent['동일종목_지속미달'] = persistent[list(AREAS.values())].any(axis=1)
    persistent.index.name = PERSON_COL
    persistent.reset_index().to_csv(PERSISTENT_PATH, index=False, encoding='utf-8-sig')

    total = len(persistent)
    n_persistent = int(persistent['동일종목_지속미달'].sum())
    rate = n_persistent / total * 100 if total else 0

    # 1. Status by round (include not-evaluable counts)
    status_df = (detail.groupby(['round', 'risk_status']).size()
                 .reset_index(name='인원'))
    fig1 = px.bar(status_df, x='round', y='인원', color='risk_status',
                  barmode='stack', text='인원', title='회차별 정상·취약·판정불가 인원',
                  category_orders={'risk_status': ['정상', '취약', '판정불가']})
    fig1.update_xaxes(tickvals=ROUNDS, ticktext=['1차', '2차', '3차'])

    # 2. Weak count distribution (only complete evaluations)
    dist = detail[detail['risk_status'].isin(['정상', '취약'])].copy()
    dist['미달 종목 수'] = dist['weak_count'].astype(int).astype(str) + '개'
    dist['측정 회차'] = dist['round'].astype(str) + '차'
    fig2 = px.histogram(dist, x='미달 종목 수', color='측정 회차',
                        barmode='group', title='회차별 미달 종목 개수 분포',
                        category_orders={'미달 종목 수': [f'{n}개' for n in range(5)],
                                         '측정 회차': ['1차', '2차', '3차']})
    fig2.update_layout(yaxis_title='인원')

    # 3. Change distribution (already derived in summary)
    changes = (summary['change_type'].fillna('비교불가')
               .value_counts().rename_axis('변화 유형').reset_index(name='인원'))
    fig3 = px.bar(changes, x='변화 유형', y='인원', text='인원',
                  title='1차 대비 3차 취약 종목 수 변화',
                  category_orders={'변화 유형': ['개선', '유지', '악화', '비교불가']})

    # 4. Same-area three-round failures
    area_counts = persistent[list(AREAS.values())].sum().rename_axis('체력종목').reset_index(name='인원')
    fig4 = px.bar(area_counts, x='체력종목', y='인원', text='인원',
                  title='체력종목별 3회 연속 미달 인원')

    # 5. KPI proportion
    fig5 = go.Figure(go.Pie(
        labels=['동일종목 3회 연속 미달', '그 외'],
        values=[n_persistent, total - n_persistent], hole=0.62,
        textinfo='label+percent'
    )) if total else go.Figure()
    fig5.update_layout(title='동일 체력종목 지속 미달률')

    figures = [fig1, fig2, fig3, fig4, fig5]
    for fig in figures:
        fig.update_layout(template='plotly_white', font=dict(family='Malgun Gothic, Arial, sans-serif'))

    # One HTML dashboard containing every visualization; no Streamlit needed.
    import plotly.io as pio
    cards = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap">'
        f'<div class="card"><small>동일 체력종목 지속 미달률</small><h1>{rate:.2f}%</h1></div>'
        f'<div class="card"><small>동일종목 지속 미달 인원</small><h1>{n_persistent:,}명</h1></div>'
        f'<div class="card"><small>3회 모두 평가 가능 인원</small><h1>{total:,}명</h1></div>'
        '</div>'
    )
    sections = []
    for i, fig in enumerate(figures):
        sections.append('<section>' + pio.to_html(fig, full_html=False, include_plotlyjs=True if i == 0 else False) + '</section>')
    html = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<title>장병 체력 취약 현황</title><style>'
            'body{font-family:Malgun Gothic,Arial,sans-serif;max-width:1100px;margin:28px auto;padding:0 18px;background:#f5f7fa;color:#243044}'
            '.card,section{background:white;border-radius:12px;padding:16px 22px;box-shadow:0 2px 12px #0000000b}'
            '.card{flex:1;min-width:200px}.card small{color:#64748b}.card h1{margin:8px 0}'
            'section{margin-top:18px}</style></head><body><h1>장병 체력 취약 현황 대시보드</h1>'
            + cards + ''.join(sections)
            + '<p>동일 종목 지속 미달: 같은 체력종목이 1·2·3차 모두 3등급 기준 미달. 종목별 인원은 중복 집계될 수 있습니다.</p>'
            + '<p>회차는 장병별_회차별미달정보생성.py에서 측정일순으로 부여한 값을 사용합니다.</p>'
            + '</body></html>')
    HTML_PATH.write_text(html, encoding='utf-8')
    if show_ui:
        st.title('동일종목 지속 미달 분석')
        st.caption('같은 체력종목이 1·2·3차 모두 미달인 장병을 분석합니다. 최신 회차별 분석 CSV를 사용합니다.')
        left, middle, right = st.columns(3)
        left.metric('3회 모두 평가 가능', f'{total:,}명')
        middle.metric('동일종목 지속 미달', f'{n_persistent:,}명')
        right.metric('동일종목 지속 미달률', f'{rate:.2f}%')
        st.caption(f'분모는 세 회차 네 종목 모두 평가 가능한 고유 장병 수입니다. 전체 상세자료의 고유 장병 중 {detail[PERSON_COL].nunique()-total:,}명은 분모에서 제외했습니다.')
        st.info('매 회차 미달 종목이 달라도 포함되는 ‘지속 취약’과 달리, 이 분석은 같은 종목이 세 회차 모두 미달이어야 합니다. 여러 종목에 해당하는 장병은 종목별 막대에서 중복되지만 전체 지속 미달 인원에서는 한 번만 셉니다.')
        st.caption('왼쪽 종목별 막대를 클릭하면 아래 장병 목록이 바뀝니다. 그래프를 두 번 클릭해 선택을 해제하면 종목 선택 상자를 사용할 수 있습니다.')
        left, right = st.columns(2)
        with left:
            area_event = st.plotly_chart(fig4, width='stretch', key='persistent_areas',
                                         on_select='rerun', selection_mode='points')
        with right:
            st.plotly_chart(fig5, width='stretch', key='persistent_rate')
        area_counts['비율(%)'] = area_counts['인원']/total*100
        st.dataframe(area_counts, hide_index=True)
        st.subheader('동일종목 지속 미달 장병 조회')
        selected = st.selectbox('조회 종목', ['하나 이상 해당'] + list(AREAS.values()))
        points = area_event.selection.get('points', [])
        if points and points[-1].get('x') in AREAS.values():
            selected = points[-1]['x']
            st.info(f'그래프 선택: {selected} — 세 회차 모두 해당 종목이 미달인 장병입니다.')
        flag = '동일종목_지속미달' if selected == '하나 이상 해당' else selected
        soldiers = persistent.loc[persistent[flag]].reset_index()
        st.write(f'선택 조건에 해당하는 장병: **{len(soldiers):,}명**')
        soldier_event = st.dataframe(soldiers, hide_index=True, width='stretch',
                                     key=f'persistent_soldiers_{selected}', on_select='rerun',
                                     selection_mode='single-row')
        st.caption('장병 목록에서 행을 선택하면 해당 장병의 회차별 측정정보를 확인할 수 있습니다. 장병 식별자는 SOLDIER_ID입니다.')
        rows = soldier_event.selection.get('rows', [])
        if rows and rows[0] < len(soldiers):
            person_id = soldiers.iloc[rows[0]][PERSON_COL]
            st.subheader(f'장병 {person_id} · 1·2·3차 측정정보')
            person_detail = valid.loc[valid[PERSON_COL].eq(person_id)].sort_values('round')
            st.dataframe(person_detail, hide_index=True)
        with st.expander('조회된 장병 전체의 1·2·3차 상세 측정'):
            st.dataframe(valid.loc[valid[PERSON_COL].isin(soldiers[PERSON_COL])], hide_index=True)
        st.download_button('선택 장병 CSV 다운로드', soldiers.to_csv(index=False).encode('utf-8-sig'),
                           file_name='동일종목_지속미달_선택장병.csv', mime='text/csv')
        st.subheader('전체 체력 현황과 회차별 변화')
        st.caption('아래 현황은 전체 입력자료 기준입니다. 정상=미달 0개, 취약=1개 이상이며, 지속 미달 분석의 분모와 구분합니다.')
        for i, fig in enumerate([fig1, fig2, fig3]):
            st.plotly_chart(fig, width='stretch', key=f'overall_{i}')
        st.download_button('전체 지속 미달 판정 CSV', persistent.reset_index().to_csv(index=False).encode('utf-8-sig'),
                           file_name='동일종목_지속미달_전체판정.csv', mime='text/csv')
        st.download_button('시각화 HTML 다운로드', html.encode('utf-8'),
                           file_name='동일종목_지속미달분석.html', mime='text/html')
    print(f'3회 모두 평가 가능 인원: {total:,}명')
    print(f'동일 체력종목 지속 미달 인원: {n_persistent:,}명')
    print(f'동일 체력종목 지속 미달률: {rate:.2f}%')
    print(f'대시보드 저장: {HTML_PATH}')
    print(f'지속 미달 상세 CSV 저장: {PERSISTENT_PATH}')


if __name__ == '__main__':
    if get_script_run_ctx(suppress_warning=True) is not None:
        st.set_page_config(page_title='동일종목 지속 미달 분석', layout='wide')
        try:
            main(show_ui=True)
        except (ValueError, OSError, KeyError) as exc:
            st.error(str(exc))
    else:
        main()
