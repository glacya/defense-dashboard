"""실행: python -m streamlit run data/experiments/bmi_체력항목_zcore_그래프.py
저장: python data/experiments/bmi_체력항목_zcore_그래프.py --export
"""
import argparse
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from 분석_연령별 import analyze_age, METRICS

FITNESS = ['STRENGTH', 'ENDURANCE', 'CARDIO', 'FLEXIBILITY']
OUTPUT = Path(__file__).resolve().parent / 'results' / 'bmi_체력항목_zcore_그래프'


def calculate(bin_width=1.0, min_count=20):
    if bin_width <= 0 or min_count < 1:
        raise ValueError('구간 폭은 양수, 표시 최소 인원은 1 이상이어야 합니다.')
    first = analyze_age(return_first=True)
    clean = first[['BMI'] + FITNESS].replace([np.inf, -np.inf], np.nan)
    eligible = clean.BMI.gt(0) & clean[FITNESS].notna().all(axis=1)
    data = clean.loc[eligible].copy()
    if len(data) < 2:
        raise ValueError('BMI가 유효하고 체력 4종목이 모두 있는 대상이 2명 이상 필요합니다.')
    # All four scores use the same complete-case reference population.
    means, stds = data[FITNESS].mean(), data[FITNESS].std(ddof=1)
    if stds.isna().any() or stds.le(0).any():
        raise ValueError('표준편차가 0이거나 계산 불가한 종목은 표준화할 수 없습니다.')
    z = (data[FITNESS] - means) / stds
    data['체력종합점수'] = z.mean(axis=1, skipna=False)
    parameters = pd.DataFrame({'항목': [METRICS[x] for x in FITNESS], '컬럼': FITNESS,
                               '기준평균': means.to_numpy(), '기준표준편차': stds.to_numpy(),
                               '표준화기준인원': len(data), '가중치': 0.25})
    bucket = np.floor(data.BMI / bin_width).astype(int)
    table = data.assign(구간번호=bucket).groupby('구간번호').agg(
        인원=('체력종합점수', 'size'), 평균=('체력종합점수', 'mean'),
        표준편차=('체력종합점수', 'std'))
    table = table.reindex(range(int(bucket.min()), int(bucket.max()) + 1))
    table['인원'] = table['인원'].fillna(0).astype(int)
    table['구간시작'] = table.index.to_numpy() * bin_width
    table['구간끝'] = table['구간시작'] + bin_width
    table['구간중앙'] = (table['구간시작'] + table['구간끝']) / 2
    table['선표시'] = table['인원'].ge(min_count)
    summary = pd.DataFrame([{'첫측정인원':len(first), '분석인원':len(data),
                             '제외인원':int((~eligible).sum()), 'BMI구간폭':bin_width,
                             '표시최소인원':min_count, '종합점수평균':data['체력종합점수'].mean()}])
    return summary, parameters, table.reset_index(drop=True)


def make_figure(table):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.76,0.24], vertical_spacing=0.07)
    fig.add_trace(go.Scatter(x=table['구간중앙'], y=table['평균'].where(table['선표시']),
                            mode='lines+markers', connectgaps=False, name='평균 체력종합점수',
                            line={'color':'#2563eb','width':3},
                            customdata=table[['구간시작','구간끝','인원']],
                            hovertemplate='BMI [%{customdata[0]}, %{customdata[1]})<br>평균점수 %{y:.3f}<br>인원 %{customdata[2]}명<extra></extra>'), row=1,col=1)
    fig.add_hline(y=0,line_dash='dash',line_color='#777',row=1,col=1)
    for value in [18.5,25]:
        fig.add_vline(x=value,line_dash='dot',line_color='#999',row=1,col=1,annotation_text=f'BMI {value}')
    fig.add_trace(go.Bar(x=table['구간중앙'], y=table['인원'],name='구간별 인원',marker_color='#94a3b8'),row=2,col=1)
    fig.update_yaxes(title_text='4종목 Z-score 평균',row=1,col=1)
    fig.update_yaxes(title_text='인원(명)',row=2,col=1)
    fig.update_xaxes(title_text='BMI 구간 중앙값 (kg/m²)',row=2,col=1)
    fig.update_layout(title='BMI와 표준화 체력종합점수의 관계',height=620,legend={'orientation':'h'})
    return fig



def interpretation(table):
    visible = table.loc[table['선표시'] & table['평균'].notna()]
    notes = [
        '점수 0은 이번 분석 대상의 평균 수준입니다. 양수는 평균보다 높은 종합점수, 음수는 평균보다 낮은 종합점수를 뜻합니다. 음수라고 체력 미달인 것은 아닙니다.',
        '각 점은 해당 BMI 구간에 속한 사람들의 평균입니다. 같은 사람의 BMI가 변했을 때 체력이 어떻게 바뀌는지를 보여주는 그래프는 아닙니다.'
    ]
    if visible.empty:
        notes.append('현재 최소 인원 조건을 충족하는 구간이 없습니다. 표시 최소 인원을 조정하거나 구간 폭을 넓혀주세요.')
        return notes
    peak = visible.loc[visible['평균'].idxmax()]
    def describe(row):
        return f"BMI {row['구간시작']:g} 이상 {row['구간끝']:g} 미만: 평균 {row['평균']:+.3f}점, {int(row['인원']):,}명"
    notes.append('현재 표시 구간 중 평균이 가장 높은 구간은 ' + describe(peak) + '입니다. 이 구간이 개인의 최적 BMI라는 의미는 아닙니다.')
    tail = visible.loc[visible['구간시작'] >= peak['구간끝']]
    if not tail.empty:
        last = tail.iloc[-1]
        notes.append('높은 BMI 쪽의 마지막 표시 구간은 ' + describe(last) + '입니다. 최고 평균 구간과 비교해 점수가 ' + ('낮습니다.' if last['평균'] < peak['평균'] else '같거나 높습니다.'))
    notes.append('기본 구간 폭 1의 현재 결과에서는 BMI 20대 초반에서 평균점수가 상대적으로 높고, 그 이후 대체로 감소합니다. 낮은 BMI 구간의 상승은 높은 BMI 구간의 하락보다 완만하므로 대칭적인 역U자라고 단정하지 않습니다. 구간 폭을 바꾸면 요약 형태와 최고 구간이 달라질 수 있습니다.')
    notes.append('종합점수는 근력·근지구력·심폐·유연성을 같은 가중치로 평균한 값입니다. 항목별 서로 다른 관계가 합쳐지므로 개별 항목 그래프도 함께 확인해야 합니다.')
    notes.append('BMI의 비선형 항을 탐색할 참고 근거가 되지만, 이 점수와의 관계가 3차 통과확률의 관계를 직접 입증하지는 않습니다. 파생변수 채택은 별도 교차검증으로 판단합니다.')
    return notes


def export_results(result):
    summary,parameters,table=result
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for name,frame in [('분석대상_설정',summary),('종목별_표준화기준',parameters),('BMI구간별_체력종합점수',table)]:
        frame.to_csv(OUTPUT/f'{name}.csv',index=False,encoding='utf-8-sig')
    html='<html><head><meta charset="utf-8"></head><body><h1>BMI와 체력종합점수</h1><p>근력·근지구력·심폐·유연성의 Z-score를 동일 가중치로 평균. BMI·체지방률 제외. 장병별 첫 측정, 완전자료 기준, 표본 표준편차(ddof=1). 0은 기준 표본의 평균이며 공식 통과 기준이 아닙니다.</p>'
    html+=make_figure(table).to_html(full_html=False,include_plotlyjs=True)
    html += '<h2>그래프 해석</h2><ul>' + ''.join('<li>'+escape(note)+'</li>' for note in interpretation(table)) + '</ul>'
    (OUTPUT/'BMI_체력종합점수_선그래프.html').write_text(html+'</body></html>',encoding='utf-8')


def main():
    st.set_page_config(page_title='BMI와 표준화 체력점수',layout='wide')
    st.title('BMI와 체력 4종목 Z-score 평균의 관계')
    st.caption('첫 측정 당시 19~24세 · 장병별 첫 측정 · BMI·체지방률은 점수에서 제외')
    width=st.selectbox('BMI 구간 폭',[0.5,1.0,2.0],index=1)
    minimum=st.number_input('선 표시 최소 구간 인원',min_value=1,value=20,step=1)
    try:
        result=calculate(width,int(minimum))
    except (ValueError,OSError,KeyError) as exc:
        st.error(str(exc));st.stop()
    summary,parameters,table=result
    st.dataframe(summary,hide_index=True)
    st.latex(r'Z_j=\frac{X_j-\bar{X}_j}{s_j},\qquad S=\frac{Z_{근력}+Z_{근지구력}+Z_{심폐}+Z_{유연성}}{4}')
    st.info('점수가 높으면 네 종목을 종합한 상대적 체력 수준이 높습니다. 0은 분석 대상의 평균이며, 평균한 종합점수 자체의 표준편차가 1이라는 뜻은 아닙니다.')
    st.plotly_chart(make_figure(table),width='stretch')
    st.caption('구간은 시작값 이상·끝값 미만이며 X축 점은 구간 중앙값입니다. 평균점수를 연결한 선이므로 시간에 따른 개인 변화가 아닙니다. 인원이 적거나 비어 있는 구간에서는 선이 끊깁니다.')
    with st.expander('종목별 표준화 기준'):
        st.dataframe(parameters,hide_index=True)
    with st.expander('BMI 구간별 종합점수·인원'):
        st.dataframe(table,hide_index=True)
        st.download_button('구간통계 CSV',table.to_csv(index=False).encode('utf-8-sig'),file_name='BMI구간별_체력종합점수.csv')
    st.warning('동일 가중치의 분석용 상대점수이며 공식 체력등급·통과 기준이 아닙니다. 한 종목의 미달이 다른 종목의 높은 점수에 가려질 수 있습니다. BMI와 체중을 공유하는 지표가 포함돼 있으므로 인과효과로 해석하지 않습니다. 예측모형에서 사용할 때는 표준화 기준을 각 학습자료에서만 계산해야 합니다.')
    st.subheader('그래프 해석')
    for note in interpretation(table):
        st.write('• ' + note)
    st.caption('Z-score 평균 +0.3은 종합점수 자체의 표준편차 기준 0.3배를 뜻하지 않습니다. 체중이 공통으로 관여하는 지표의 특성 및 소수 구간의 불확실성을 고려하세요.')
    if st.button('현재 설정 결과 저장'):
        export_results(result);st.success(f'저장 완료: {OUTPUT}')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--export',action='store_true')
    args=parser.parse_args()
    if args.export:
        export_results(calculate());print(f'저장 완료: {OUTPUT}')
    else:
        main()
