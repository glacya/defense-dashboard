"""기존 산출물을 변경하지 않고 별도 시각화와 탐색 목록을 추가합니다."""

import hashlib
import html
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
DEST = ROOT / '추가시각화'


def read(folder, name):
    return pd.read_csv(folder / name)


def page(name, title, figures, note):
    """인터넷 없이 열 수 있는 설명 포함 HTML을 저장합니다."""
    text = ['<!doctype html><html lang="ko"><meta charset="utf-8">',
            '<style>body{font-family:Arial,"Malgun Gothic",sans-serif;max-width:1250px;margin:30px auto;padding:16px;background:#f5f7fb;color:#203047}section{background:white;padding:14px;margin:20px 0;border-radius:10px}</style>',
            f'<h1>{html.escape(title)}</h1><p>{html.escape(note)}</p>']
    for i, fig in enumerate(figures):
        text.append('<section>' + pio.to_html(fig, full_html=False, include_plotlyjs=True if i == 0 else False) + '</section>')
    text.append('</html>')
    (DEST / name).write_text('\n'.join(text), encoding='utf-8')


def main():
    """현존 표를 시각화하고 원본 파일 해시가 유지되는지 확인합니다."""
    original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*')
                if p.is_file() and DEST not in p.parents}
    DEST.mkdir(exist_ok=True)
    links = []
    for number, stem, group in [(1, '01_연령별_기술통계', '연령'), (2, '02_BMI그룹별_기술통계', 'BMI그룹')]:
        folder = ROOT / stem
        table = read(folder, '연령별_기술통계.csv' if number == 1 else 'BMI그룹별_기술통계.csv')
        people = read(folder, '연령별_인원구성비.csv' if number == 1 else 'BMI그룹별_인원구성비.csv')
        figs = [go.Figure(go.Bar(x=people[group].astype(str), y=people['장병 수'], text=people['장병 수'], textposition='auto'))]
        figs[0].update_layout(title='집단별 인원', xaxis_title=group, yaxis_title='인원 (명)')
        combined = make_subplots(rows=3, cols=2, subplot_titles=table['항목'].unique().tolist())
        for i, (metric, values) in enumerate(table.groupby('항목', sort=False)):
            combined.add_trace(go.Scatter(x=values[group].astype(str), y=values['평균'], mode='lines+markers',
                error_y={'type': 'data', 'array': values['표준편차']}, name=metric,
                customdata=values[['유효 측정 인원', '표준편차']],
                hovertemplate='%{x}<br>평균 %{y:.3f}<br>유효 인원 %{customdata[0]}<br>SD %{customdata[1]:.3f}<extra></extra>'), row=i//2+1, col=i%2+1)
            combined.update_yaxes(title_text=metric, row=i//2+1, col=i%2+1)
        combined.update_layout(title='집단별 평균 ± 표본 표준편차', height=1050, showlegend=False)
        figs.append(combined)
        name = f'{number:02d}_기술통계_시각화.html'
        page(name, f'{group}별 체력 기술통계', figs, '오차막대는 개인 측정값의 산포를 나타내는 ±1 SD이며 평균의 95% 신뢰구간이 아닙니다. 평균선은 집단 요약이며 개인의 시간 변화를 뜻하지 않습니다.')
        links.append((number, f'{group}별 인원·평균·표준편차', name))
    for number, stem in [(3, '03_연령별_ANOVA'), (4, '04_BMI그룹별_ANOVA')]:
        table = read(ROOT / stem, 'ANOVA_결과표.csv')
        fig = go.Figure(go.Bar(x=table['항목'], y=table['η²'], customdata=table[['적용 검정', '적용 p값']],
                              hovertemplate='%{x}<br>η²=%{y:.4f}<br>%{customdata[0]}<br>p=%{customdata[1]:.3e}<extra></extra>'))
        fig.update_layout(title='종목별 효과크기 η²', yaxis_title='η² (일반 ANOVA 제곱합 기반)')
        figs = [fig]
        pairs = read(ROOT / stem, '유의종목_사후검정.csv')
        if not pairs.empty:
            low = next(c for c in pairs if '하한' in c)
            high = next(c for c in pairs if '상한' in c)
            a, b = ('연령 A', '연령 B') if number == 3 else ('그룹 A', '그룹 B')
            for event, rows in pairs.groupby('항목', sort=False):
                diff = rows['평균차(A−B)']
                plot = go.Figure(go.Scatter(x=diff, y=rows[a].astype(str)+' − '+rows[b].astype(str), mode='markers',
                    error_x={'type': 'data', 'symmetric': False, 'array': rows[high]-diff, 'arrayminus': diff-rows[low]}))
                plot.add_vline(x=0, line_dash='dot')
                plot.update_layout(title=f'{event} · 사후검정 평균차와 95% 동시 신뢰구간', xaxis_title='平均差 A−B')
                figs.append(plot)
        name = f'{number:02d}_ANOVA_시각화.html'
        page(name, f'{stem[3:]} 결과 시각화', figs, 'η²는 일반 ANOVA 기반 참고 효과크기입니다. Welch 검정 통계량과 구분하세요. ANOVA 종목 간 다중검정 보정은 미적용입니다. 사후검정 그래프는 원 결과에 유의 종목이 있을 때만 표시합니다.')
        links.append((number, 'ANOVA 효과크기·사후검정 신뢰구간', name))
    for number, stem, group in [(5, '05_연령별_카이제곱', '연령'), (6, '06_BMI그룹별_카이제곱', 'BMI그룹')]:
        table = read(ROOT / stem, '카이제곱_검정결과.csv')
        counts = read(ROOT / stem, '종목별_관측기대빈도_미달률.csv')
        rates = go.Figure()
        for event, values in counts.groupby('종목', sort=False):
            rates.add_trace(go.Bar(x=values[group].astype(str), y=values['미달률(%)'], name=event,
                customdata=values[['미달 인원', '평가가능수']],
                hovertemplate='%{x}<br>미달률 %{y:.2f}%<br>미달 %{customdata[0]} / 평가가능 %{customdata[1]}<extra></extra>'))
        rates.update_layout(title='집단별 종목 미달률', barmode='group', yaxis_title='미달률 (%)')
        effect = go.Figure(go.Bar(x=table['종목'], y=table["Cramér's V"], customdata=table[['Holm 보정 p값', '상태']],
            hovertemplate='%{x}<br>V=%{y:.4f}<br>Holm p=%{customdata[0]:.3e}<br>%{customdata[1]}<extra></extra>'))
        effect.update_layout(title='미달 여부와의 관련성 크기', yaxis_title='Cramér’s V', yaxis_range=[0,1])
        name=f'{number:02d}_카이제곱_시각화.html'
        page(name, f'{group}와 미달 여부', [rates,effect], '미달률의 분모는 해당 집단·종목 평가 가능 인원입니다. 유의성은 Holm 보정 p값으로 판단하며 관련성은 인과성을 뜻하지 않습니다. BMI는 고정 구간을 사용합니다.')
        links.append((number, '집단별 미달률·Cramér’s V', name))
    for number, folder, filename in [(12, '12_심폐_단일표본t검정', '심폐_단일표본t검정_기준44.8.csv'),
                                     (13, '13_BMI별근력_독립표본t검정', 'BMI낮음높음_근력_t검정.csv')]:
        row = read(ROOT / folder, filename).iloc[0]
        if number == 12:
            center, low, high = row['표본평균'], row['평균95%CI하한'], row['평균95%CI상한']
            reference = row['기준평균']
            title = '심폐 평균의 95% 신뢰구간과 기준 44.8'
            unit = 'VO₂max (mL/kg/min)'
        else:
            center, low, high = row['평균차_낮음-높음(%p)'], row['평균차95%CI하한'], row['평균차95%CI상한']
            reference = 0
            title = 'BMI 낮음−높음의 상대악력 평균차 · 95% 신뢰구간'
            unit = '평균차 (%p)'
        fig = go.Figure(go.Scatter(x=[center], y=['추정값'], mode='markers',
            error_x={'type':'data','symmetric':False,'array':[high-center],'arrayminus':[center-low]}))
        fig.add_vline(x=reference, line_dash='dot', line_color='#c66b39')
        fig.update_layout(title=title, xaxis_title=unit, height=400)
        name=f'{number:02d}_평균추정_신뢰구간.html'
        page(name,title,[fig],'구간은 모집단 평균 또는 평균차의 추정 불확실성입니다. 개인 측정값의 분포 범위가 아닙니다. 대표성과 독립성 등 검정 가정의 한계는 원 분석 설명을 따릅니다.')
        links.append((number,title,name))
    rows=[]
    for number,title,name in links:
        rows.append(f'<li>{number}. <a href="{html.escape(name)}">{html.escape(title)}</a></li>')
    for number,folder,file,title in [(7,'07_회차별_상관분석','Pearson_r_히트맵.html','Pearson 상관 히트맵'),
        (7,'07_회차별_상관분석','Spearman_rho_히트맵.html','Spearman 상관 히트맵'),
        (12,'12_심폐_단일표본t검정','심폐_분포와기준.html','심폐 분포와 기준'),
        (13,'13_BMI별근력_독립표본t검정','BMI낮음높음_근력분포.html','BMI 집단별 근력 분포'),
        (14,'14_6개항목_전체분포','6개항목_히스토그램.html','6개 항목 히스토그램'),
        (14,'14_6개항목_전체분포','6개항목_박스플롯.html','6개 항목 박스플롯'),
        (15,'15_BMI_비선형성탐색','BMI_체력항목_관계.html','BMI 산점도·LOWESS'),
        (15,'15_BMI_비선형성탐색','BMI_체력항목_꺾은선.html','BMI 구간별 평균 꺾은선')]:
        assert (ROOT/folder/file).exists()
        rows.append(f'<li>{number}. <a href="../{folder}/{file}">{title} (기존 그래프)</a></li>')
    index='<!doctype html><html lang="ko"><meta charset="utf-8"><title>분석 시각화 목록</title><body style="font-family:Arial,Malgun Gothic;max-width:1000px;margin:40px auto"><h1>분석 산출물 시각화</h1><p>기존 데이터·그래프를 보존하고 추가한 시각화입니다. 8~11번 산출물은 현재 폴더에 없어 이번 목록에서 제외했습니다.</p><ol>'+''.join(rows)+'</ol></body></html>'
    (DEST/'시각화_목록.html').write_text(index,encoding='utf-8')
    for path,digest in original.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest, f'기존 파일 변경: {path}'
    print(f'Added HTML: {len(links)+1}; original files verified: {len(original)}')


if __name__=='__main__':
    main()
