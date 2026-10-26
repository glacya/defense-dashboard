"""화면: python -m streamlit run data/experiments/BMI_체력항목_비선형성분석.py
결과 저장: python data/experiments/BMI_체력항목_비선형성분석.py --export
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from statsmodels.nonparametric.smoothers_lowess import lowess

from 분석_연령별 import analyze_age, METRICS

TARGETS = ['STRENGTH', 'ENDURANCE', 'CARDIO', 'FLEXIBILITY', 'BODY_FAT_PERCENTAGE']
OUTPUT = Path(__file__).resolve().parent / 'results' / 'BMI비선형성분석'


def calculate(bin_width=1.0, frac=0.4, min_bin_count=20):
    if bin_width <= 0 or not 0 < frac <= 1 or min_bin_count < 1:
        raise ValueError('구간 폭은 양수, LOWESS 비율은 0 초과~1 이하, 최소 인원은 1 이상이어야 합니다.')
    first = analyze_age(return_first=True)
    valid_bmi = first.BMI.notna() & first.BMI.gt(0)
    data = first.loc[valid_bmi, ['BMI'] + TARGETS].copy()
    summaries, bins, curves, pairs = [], {}, {}, {}
    for metric in TARGETS:
        pair = data[['BMI', metric]].replace([np.inf, -np.inf], np.nan).dropna()
        pairs[metric] = pair
        grouped = pair.assign(구간시작=np.floor(pair.BMI / bin_width) * bin_width).groupby('구간시작')
        table = grouped.agg(인원=(metric, 'size'), BMI평균=('BMI', 'mean'), 평균=(metric, 'mean'), 표준편차=(metric, 'std')).reset_index()
        table['구간끝'] = table['구간시작'] + bin_width
        table['평균선표시'] = table['인원'].ge(min_bin_count)
        bins[metric] = table
        if len(pair) >= 3 and pair.BMI.nunique() >= 3:
            fitted = lowess(pair[metric], pair.BMI, frac=frac, it=3, return_sorted=True)
            curves[metric] = pd.DataFrame(fitted, columns=['BMI', 'LOWESS']).groupby('BMI', as_index=False).mean()
        else:
            curves[metric] = pd.DataFrame(columns=['BMI', 'LOWESS'])
        summaries.append({'항목': METRICS[metric], '컬럼': metric, '첫측정인원': len(first),
                          'BMI결측·비양수제외': int((~valid_bmi).sum()), '짝자료인원': len(pair),
                          '항목결측제외': len(data)-len(pair), '구간폭': bin_width,
                          'LOWESS비율': frac, '평균선최소인원': min_bin_count})
    return pd.DataFrame(summaries), pairs, bins, curves


def make_figure(metric, pair, table, curve):
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=pair.BMI, y=pair[metric], mode='markers', name='개인 측정값',
                              marker={'size': 4, 'opacity': 0.18, 'color': '#718096'}))
    # Keep sparse bins as gaps rather than connecting across them.
    fig.add_trace(go.Scatter(x=table.BMI평균, y=table['평균'].where(table['평균선표시']),
                            customdata=table[['인원','구간시작','구간끝']], mode='lines+markers',
                            name='구간별 평균', connectgaps=False,
                            hovertemplate='BMI 평균 %{x:.2f}<br>구간 [%{customdata[1]}, %{customdata[2]})<br>평균 %{y:.2f}<br>인원 %{customdata[0]}<extra></extra>'))
    fig.add_trace(go.Scatter(x=curve.BMI, y=curve.LOWESS, mode='lines', name='LOWESS', line={'color':'#e56b2f','width':3}))
    for boundary in [18.5, 25]:
        fig.add_vline(x=boundary, line_dash='dot', line_color='#777', annotation_text=f'BMI {boundary}')
    fig.update_layout(title=f'BMI와 {METRICS[metric]}', xaxis_title='BMI (kg/m²)',
                      yaxis_title=METRICS[metric], height=470, legend={'orientation':'h'})
    return fig


def export_results(result):
    summary, pairs, bins, curves = result
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT/'분석대상_설정.csv', index=False, encoding='utf-8-sig')
    html = ['<html><head><meta charset="utf-8"></head><body><h1>BMI 비선형성 탐색</h1>',
            '<p>개인별 첫 측정. 평균선은 최소 인원 기준 적용. LOWESS는 탐색 곡선이며 비선형성의 검정 결과가 아닙니다.</p>']
    for i, metric in enumerate(TARGETS):
        bins[metric].to_csv(OUTPUT/f'{metric}_BMI구간통계.csv', index=False, encoding='utf-8-sig')
        curves[metric].to_csv(OUTPUT/f'{metric}_LOWESS.csv', index=False, encoding='utf-8-sig')
        html.append(make_figure(metric,pairs[metric],bins[metric],curves[metric]).to_html(full_html=False,include_plotlyjs=True if i==0 else False))
    (OUTPUT/'BMI_체력항목_관계.html').write_text(''.join(html)+'</body></html>',encoding='utf-8')


def main():
    st.set_page_config(page_title='BMI 비선형성 탐색', layout='wide')
    st.title('BMI와 체력·신체 측정항목의 비선형성 탐색')
    st.caption('첫 측정 당시 19~24세 · 장병별 첫 측정 1건 · BMI 자체를 제외한 5개 항목 비교')
    width = st.selectbox('BMI 구간 폭', [0.5, 1.0, 2.0], index=1)
    frac = st.slider('LOWESS 평활 비율', 0.2, 0.8, 0.4, 0.1)
    minimum = st.number_input('평균선 표시 최소 구간 인원', min_value=1, value=20, step=1)
    try:
        result = calculate(width, frac, int(minimum))
    except (OSError, ValueError, KeyError) as exc:
        st.error(str(exc)); st.stop()
    summary, pairs, bins, curves = result
    st.dataframe(summary, hide_index=True)
    st.info('산점도와 LOWESS의 형태를 보고 직선·굴곡을 탐색합니다. 곡선만으로 비선형성을 확정하거나 제곱항을 자동 채택하지 않습니다. 표본이 적은 양끝 구간은 신중히 해석하세요.')
    for metric in TARGETS:
        st.plotly_chart(make_figure(metric,pairs[metric],bins[metric],curves[metric]), width='stretch')
        with st.expander(f'{METRICS[metric]} 구간별 인원·통계'):
            st.dataframe(bins[metric], hide_index=True)
            st.download_button('구간통계 CSV', bins[metric].to_csv(index=False).encode('utf-8-sig'),file_name=f'{metric}_BMI구간통계.csv',key=metric)
    st.caption('BMI 18.5·25는 분석용 3그룹 경계입니다. 상대악력·체중당 VO₂max는 BMI와 체중이 공통으로 관여합니다. 인과효과나 운동 효과로 해석하지 않습니다. 예측용 파생변수는 학습자료 안에서 선택하고 검증자료로 성능을 비교해야 합니다.')
    if st.button('현재 설정으로 전체 결과 저장'):
        export_results(result)
        st.success(f'저장 완료: {OUTPUT}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args()
    if args.export:
        export_results(calculate())
        print(f'저장 완료: {OUTPUT}')
    else:
        main()
