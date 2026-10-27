"""15번 시각화 목록의 두 HTML을 생성합니다. 기존 PNG·CSV는 유지합니다."""

import hashlib
import importlib
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parents[1]))
sys.path.insert(0, str(ROOT.parent))


def main():
    """기존 계산·그림 함수를 활용해 관계 및 평균 꺾은선 HTML을 저장합니다."""
    module = importlib.import_module('BMI_체력항목_비선형성분석')
    output = ROOT / '15_BMI_비선형성탐색'
    output.mkdir(exist_ok=True)
    keep = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.suffix in ('.png', '.csv')}
    summary, pairs, bins, curves = module.calculate()
    pieces = ['<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>BMI 산점도·LOWESS</title></head><body style="font-family:Arial,Malgun Gothic;max-width:1400px;margin:30px auto">',
              '<h1>BMI와 체력항목의 관계</h1><p>개인별 첫 측정 · 구간 폭 1.0 · 구간 인원 20명 이상 평균선 · LOWESS frac=0.4, it=3. 곡선은 탐색 결과이며 인과성·예측력 개선을 의미하지 않습니다.</p>']
    lines = make_subplots(rows=3, cols=2, subplot_titles=[module.METRICS[m] for m in module.TARGETS])
    for index, metric in enumerate(module.TARGETS):
        table = bins[metric]
        # 빈 구간도 복원해 희소 구간을 가로질러 평균선을 잇지 않습니다.
        if not table.empty:
            starts = np.arange(table['구간시작'].min(), table['구간시작'].max()+.5, 1.0)
            table = table.set_index('구간시작').reindex(starts).rename_axis('구간시작').reset_index()
            table['구간끝'] = table['구간시작']+1
            table['평균선표시'] = table['인원'].ge(20)
            table['BMI평균'] = table['BMI평균'].fillna(table['구간시작']+.5)
        fig = module.make_figure(metric, pairs[metric], table, curves[metric])
        pieces.append(fig.to_html(full_html=False, include_plotlyjs=True if index==0 else False))
        r,c=index//2+1,index%2+1
        lines.add_trace(go.Scatter(x=table['구간시작']+.5, y=table['평균'].where(table['평균선표시']),
            mode='lines+markers',connectgaps=False,name=module.METRICS[metric],
            customdata=table[['구간시작','구간끝','인원','표준편차']],
            hovertemplate='BMI [%{customdata[0]:.1f}, %{customdata[1]:.1f})<br>평균 %{y:.3f}<br>인원 %{customdata[2]:.0f}<br>SD %{customdata[3]:.3f}<extra></extra>'),row=r,col=c)
        lines.update_xaxes(title_text='BMI 구간 중앙값',row=r,col=c)
        lines.update_yaxes(title_text=module.METRICS[metric],row=r,col=c)
    pieces.append('</body></html>')
    (output/'BMI_체력항목_관계.html').write_text('\n'.join(pieces),encoding='utf-8')
    lines.update_layout(title='BMI 구간별 평균 꺾은선 · 구간 폭 1.0 · 최소 20명',height=1350,showlegend=False)
    lines.add_annotation(text='20명 미만·빈 구간은 연결하지 않음. 집단 평균이며 개인의 시간 변화가 아님.',
                         xref='paper',yref='paper',x=0,y=-.07,showarrow=False)
    lines.write_html(output/'BMI_체력항목_꺾은선.html',include_plotlyjs=True)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in keep.items())
    print('Created 2 standalone HTML files. Existing PNG/CSV unchanged.')


if __name__=='__main__':
    main()
