"""실행: streamlit run data/experiments/위험장병식별with변동률.py

종목별체력미달자_회차별변화율의 원본 데이터 로딩과 3등급 판정을 재사용한다.
"""
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
import altair as alt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 종목별체력미달자_회차별변화율 import analyze, AREAS, MEASURES


def aggregate_risk(detail, complete_only=True):
    detail = detail.copy()
    risk_cols = [f'{col}_미달' for col in AREAS.values()]
    detail['판정가능종목수'] = detail[risk_cols].notna().sum(axis=1)
    # 결측 종목은 0개 미달로 확정하지 않는다.
    detail['미달종목수'] = detail[risk_cols].sum(axis=1).astype('Int64').mask(
        detail['판정가능종목수'].ne(4))
    detail['미달종목'] = detail.apply(
        lambda row: ', '.join(label for label, col in AREAS.items()
                              if pd.notna(row[f'{col}_미달']) and row[f'{col}_미달']), axis=1)
    complete = detail.groupby('SOLDIER_ID')['판정가능종목수'].agg(lambda v: v.eq(4).all())
    target = detail.loc[detail.SOLDIER_ID.isin(complete[complete].index)] if complete_only else detail
    rows = []
    for round_no in (1, 2, 3):
        values = target.loc[target['회차'].eq(round_no), '미달종목수']
        row = {'회차': f'{round_no}차', '대상자수': len(values),
               '판정가능수': int(values.notna().sum()), '판정불가수': int(values.isna().sum())}
        for count in range(5):
            row[f'{count}개 미달'] = int(values.eq(count).sum())
        row['2개 이상 미달'] = int(values.ge(2).sum())
        rows.append(row)
    return pd.DataFrame(rows), target, int((~complete).sum())


def main():
    st.set_page_config(page_title='위험장병식별 · 변동률', layout='wide')
    st.title('위험장병식별 · 회차별 변동률')
    st.caption('근력·근지구력·심폐지구력·유연성 중 정확히 2개·3개·4개 미달한 장병 집계')
    st.info('남성 19~24세 3등급 기준을 적용합니다. 성별 컬럼이 없어 남성 표본을 전제로 합니다. 측정일순 첫 3회를 비교합니다.')
    complete_only = st.checkbox('1·2·3차 모두 네 종목 판정 가능한 동일 장병만 비교', value=True)
    try:
        _, _, detail, standards = analyze()
        summary, target, excluded = aggregate_risk(detail, complete_only)
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    st.metric('3회 이상 측정 장병', f'{detail.SOLDIER_ID.nunique():,}명')
    if complete_only:
        st.caption(f'비교 대상 {target.SOLDIER_ID.nunique():,}명 · 판정불가 회차가 있어 제외한 장병 {excluded:,}명')
    else:
        st.warning('회차별 판정가능 인원이 다를 수 있습니다. 판정불가는 미달 개수 집계에서 제외합니다.')
    st.caption('심폐는 통합 CARDIO(VO₂max) 값이 42 미만이면 미달로 판정합니다. 기준값과 같으면 충족입니다.')
    with st.expander('적용 3등급 기준표'):
        st.dataframe(standards.loc[standards.exercise.isin(MEASURES)], hide_index=True)

    counts = summary.set_index('회차')[[f'{n}개 미달' for n in (2, 3, 4)]]
    st.subheader('미달 종목 개수별 장병 수')
    st.caption('2개·3개·4개는 서로 중복되지 않는 정확한 미달 종목 개수입니다.')
    chart_data = counts.reset_index().melt(id_vars='회차', var_name='미달 종목 개수', value_name='장병 수')
    selection = alt.selection_point(name='risk_bar', fields=['회차', '미달 종목 개수'],
                                    on='click', toggle=False, clear='dblclick')
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X('미달 종목 개수:N', sort=['2개 미달', '3개 미달', '4개 미달']),
        xOffset=alt.XOffset('회차:N', sort=['1차', '2차', '3차']),
        y=alt.Y('장병 수:Q', title='장병 수(명)'),
        color=alt.Color('회차:N', sort=['1차', '2차', '3차']),
        opacity=alt.condition(selection, alt.value(1), alt.value(0.35)),
        tooltip=['회차:N', '미달 종목 개수:N', '장병 수:Q']
    ).add_params(selection)
    st.caption('막대를 클릭하면 아래에 해당 차수·미달 개수의 장병 정보가 표시됩니다.')
    chart_event = st.altair_chart(chart, key='risk_bar_chart', on_select='rerun',
                                 selection_mode='risk_bar')
    st.line_chart(counts, y_label='장병 수(명)')
    st.dataframe(counts, width='stretch')
    st.subheader('회차별 위험 장병 합계: 2개 이상 미달')
    for container, row in zip(st.columns(3), summary.to_dict('records')):
        container.metric(row['회차'], f"{row['2개 이상 미달']:,}명")
    with st.expander('전체 분포 및 판정가능 인원'):
        st.dataframe(summary, hide_index=True)

    st.subheader('미달 종목 개수별 장병 수 변동률')
    st.caption('(비교 차수 인원 − 기준 차수 인원) / 기준 차수 인원 × 100. 음수는 감소, 양수는 증가이며 기준 인원이 0명이면 계산하지 않습니다.')
    change_rows = []
    indexed = summary.set_index('회차')
    for group in ['2개 미달', '3개 미달', '4개 미달', '2개 이상 미달']:
        for before, after in [(1, 2), (2, 3), (1, 3)]:
            a = int(indexed.loc[f'{before}차', group])
            b = int(indexed.loc[f'{after}차', group])
            change_rows.append({'구분': group, '비교': f'{before}차→{after}차',
                                '기준인원': a, '비교인원': b, '증감인원': b - a,
                                '변동률(%)': (b - a) / a * 100 if a else float('nan')})
    changes = pd.DataFrame(change_rows)
    change_chart = changes.pivot(index='구분', columns='비교', values='변동률(%)').reindex(
        index=['2개 미달', '3개 미달', '4개 미달', '2개 이상 미달'],
        columns=['1차→2차', '2차→3차', '1차→3차'])
    st.bar_chart(change_chart, stack=False, y_label='인원 변동률(%)')
    change_table = change_chart.rename(columns={
        '1차→2차': '1→2차', '2차→3차': '2→3차', '1차→3차': '1→3차'})
    change_table.columns.name = None
    st.dataframe(change_table, column_config={
        column: st.column_config.NumberColumn(column, format='%.2f%%')
        for column in change_table.columns})
    st.caption('각 그룹의 인원수 변동률입니다. 개인별 개선·악화 비율을 의미하지 않습니다.')
    st.download_button('변동률 CSV 다운로드', change_table.to_csv().encode('utf-8-sig'),
                       file_name='위험장병_회차별변동률.csv', mime='text/csv')

    st.subheader('위험 장병 정보 조회')
    selected = chart_event.selection.get('risk_bar', [])
    if selected:
        round_no = int(selected[0]['회차'][0])
        fail_count = int(selected[0]['미달 종목 개수'].split('개')[0])
        soldiers = target.loc[target['회차'].eq(round_no) & target['미달종목수'].eq(fail_count)].copy()
        soldiers = soldiers.drop(columns=['MVM_PRSCRPTN_CN'], errors='ignore')
        first = ['SOLDIER_ID', 'AGE', 'MESURE_DE', '회차', '미달종목수', '미달종목']
        soldiers = soldiers[first + [c for c in soldiers.columns if c not in first]]
        st.write(f'{round_no}차 · 정확히 {fail_count}개 미달 장병 {len(soldiers):,}명')
        st.dataframe(soldiers, hide_index=True)
        st.download_button('조회 장병 CSV 다운로드', soldiers.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'위험장병_{round_no}차_{fail_count}개미달.csv', mime='text/csv')
    else:
        st.info('위 막대그래프에서 조회할 막대를 클릭하세요. 그래프를 두 번 클릭하면 선택이 해제됩니다.')
    st.download_button('전체 집계 CSV 다운로드', summary.to_csv(index=False).encode('utf-8-sig'),
                       file_name='위험장병_회차별집계.csv', mime='text/csv')


if __name__ == '__main__':
    main()
