"""기존 실험 계산 함수를 사용해 12~15번 산출물을 저장합니다."""

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUTPUT = Path(__file__).resolve().parent
EXPERIMENTS = OUTPUT.parent
sys.path.insert(0, str(EXPERIMENTS.parents[1]))
sys.path.insert(0, str(EXPERIMENTS))


def save(frame, folder, name):
    """계산 정밀도를 유지한 CSV를 저장합니다."""
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f'{name}.csv', index=False, encoding='utf-8-sig')


def main():
    """기존 네 분석을 호출하고 결과표·분포 그래프·LOWESS를 생성합니다."""
    single = importlib.import_module('t검정_단일표본_심폐기준비교')
    independent = importlib.import_module('t검정_독립표본_BMI별근력비교')
    distribution = importlib.import_module('체력측정항목_전체분포분석')
    nonlinear = importlib.import_module('BMI_체력항목_비선형성분석')
    folder12 = OUTPUT / '12_심폐_단일표본t검정'
    folder13 = OUTPUT / '13_BMI별근력_독립표본t검정'
    folder14 = OUTPUT / '14_6개항목_전체분포'
    folder15 = OUTPUT / '15_BMI_비선형성탐색'
    result12, values = single.calculate()
    reference42, _ = single.calculate(42.0)
    save(result12, folder12, '심폐_단일표본t검정_기준44.8')
    save(reference42, folder12, '심폐_단일표본t검정_기준42.0_참고')
    fig = go.Figure(go.Histogram(x=values, nbinsx=30, name='첫 측정 심폐'))
    fig.add_vline(x=single.DEFAULT_REFERENCE, line_color='#c66b39', annotation_text='기본 비교 기준 44.8')
    fig.add_vline(x=42, line_color='#718096', line_dash='dot', annotation_text='참고 기준 42')
    fig.update_layout(title='심폐 측정값 분포와 비교 기준', xaxis_title='VO₂max (mL/kg/min)', yaxis_title='인원')
    fig.write_html(folder12 / '심폐_분포와기준.html', include_plotlyjs=True)
    result13, boundaries, bmi_data, excluded = independent.calculate()
    save(result13, folder13, 'BMI낮음높음_근력_t검정')
    save(boundaries, folder13, 'BMI_구간별인원')
    two = bmi_data.loc[bmi_data['BMI그룹'].isin(['낮음', '높음'])]
    stats13 = two.groupby('BMI그룹', observed=True).STRENGTH.agg(['count', 'mean', 'std']).reset_index()
    save(stats13.rename(columns={'count': '유효인원', 'mean': '평균', 'std': '표준편차'}), folder13, '비교집단_기술통계')
    fig = go.Figure()
    for label in ['낮음', '높음']:
        fig.add_trace(go.Box(y=two.loc[two['BMI그룹'].eq(label), 'STRENGTH'].dropna(), name=f'BMI {label}'))
    fig.update_layout(title='BMI 낮음·높음 집단의 상대악력', yaxis_title='상대악력 (%)')
    fig.write_html(folder13 / 'BMI낮음높음_근력분포.html', include_plotlyjs=True)
    summary, data = distribution.calculate()
    save(summary, folder14, '6개항목_기술통계')
    hist = make_subplots(rows=3, cols=2, subplot_titles=list(distribution.METRICS.values()))
    boxes = make_subplots(rows=3, cols=2, subplot_titles=list(distribution.METRICS.values()))
    histogram_rows, box_rows = [], []
    for index, (column, label) in enumerate(distribution.METRICS.items()):
        valid = data[column].replace([np.inf, -np.inf], np.nan).dropna()
        counts, edges = np.histogram(valid, bins=30)
        for j, count in enumerate(counts):
            histogram_rows.append({'컬럼': column, '항목': label, '구간시작': edges[j], '구간끝': edges[j+1], '인원': int(count), '마지막구간_상한포함': j == len(counts)-1})
        q1, median, q3 = valid.quantile([.25, .5, .75])
        iqr = q3-q1
        inside = valid.loc[valid.between(q1-1.5*iqr, q3+1.5*iqr)]
        box_rows.append({'컬럼': column, '항목': label, 'Q1': q1, '중앙값': median, 'Q3': q3,
                         '아래수염': inside.min(), '위수염': inside.max(),
                         '하한펜스': q1-1.5*iqr, '상한펜스': q3+1.5*iqr, '범위밖인원': len(valid)-len(inside)})
        row, col = index//2+1, index%2+1
        hist.add_trace(go.Bar(x=(edges[:-1]+edges[1:])/2, y=counts, width=np.diff(edges), name=label), row=row, col=col)
        boxes.add_trace(go.Box(x=valid, name=label, quartilemethod='linear', boxpoints='outliers'), row=row, col=col)
        assert int(counts.sum()) == len(valid)
    save(pd.DataFrame(histogram_rows), folder14, '6개항목_히스토그램빈도')
    save(pd.DataFrame(box_rows), folder14, '6개항목_박스플롯통계')
    for fig, name, title in [(hist, '6개항목_히스토그램', '전체 측정값 분포 · 항목별 30구간'), (boxes, '6개항목_박스플롯', '전체 측정값 분포 · 1.5 IQR')]:
        fig.update_layout(title=title, height=1050, showlegend=False)
        fig.write_html(folder14 / f'{name}.html', include_plotlyjs=True)
    from 산출물_15_이미지생성 import generate
    generate()
    calculated = nonlinear.calculate()
    assert len(summary) == 6
    assert int(result12.iloc[0]['유효인원']) == len(values)
    assert result13.iloc[0]['평균차95%CI하한'] <= result13.iloc[0]['평균차_낮음-높음(%p)'] <= result13.iloc[0]['평균차95%CI상한']
    for column in nonlinear.TARGETS:
        assert calculated[2][column]['인원'].sum() == len(calculated[1][column])
    metadata = {'생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), '第一測定標本': len(data),
        '표본': '장병별 날짜순 첫 측정 당시 19~24세, 기존 analyze_age 공통 표본',
        '12': {'주기준': single.DEFAULT_REFERENCE, '참고기준': 42, '검정': '양측 단일표본 t검정, 평균의 95% CI',
               '주의': '44.8은 2등급 하한으로 개인 백분위 50%나 알려진 모집단 평균이 아님. 42.0은 3등급 하한. 참고 분석을 별도 보고'},
        '13': {'검정': result13.iloc[0]['적용검정'], 'BMI구간': '<18.5 낮음, ≥25 높음; 보통 제외', 'BMI제외': excluded,
               '주의': 'Levene 기반 Student/Welch 선택; 낮음−높음 평균차와 95% CI; 탐색적 비교'},
        '14': '체력 4종목+BMI+체지방률; 표본표준편차 ddof=1; 항목별 결측 제외; 30구간 히스토그램; linear 사분위; IQR 밖 값 자동 삭제 안 함',
        '15': {'BMI구간폭': 1.0, 'LOWESS_frac': .4, 'LOWESS_it': 3, '평균선최소인원': 20,
               '주의': 'BMI와 4종목·체지방률 5항목 관계; 곡선만으로 비선형성·예측력 개선·인과성 확정 불가'}}
    metadata['첫측정표본'] = metadata.pop('第一測定標本')
    (OUTPUT / '생성기준_12_15.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2, default=int), encoding='utf-8')
    lines = ['# 12~15번 산출물', '', '| 번호 | 결과 | 기존 실험 |', '|---|---|---|',
        '| 12 | [심폐 단일표본 t검정](12_심폐_단일표본t검정/심폐_단일표본t검정_기준44.8.csv) | t검정_단일표본_심폐기준비교.py |',
        '| 13 | [BMI별 근력 t검정](13_BMI별근력_독립표본t검정/BMI낮음높음_근력_t검정.csv) | t검정_독립표본_BMI별근력비교.py |',
        '| 14 | [6개 항목 기술통계](14_6개항목_전체분포/6개항목_기술통계.csv) | 체력측정항목_전체분포분석.py |',
        '| 15 | [BMI 관계·LOWESS 그래프](15_BMI_비선형성탐색/BMI_체력항목_통합그래프.png) | BMI_체력항목_비선형성분석.py |', '',
        f'첫 측정 19~24세 표본 {len(data):,}명. 기존 계산 함수를 사용하며 기존 파일·results는 변경하지 않습니다.', '',
        '12번은 기존 기본값 44.8(2등급 하한)을 주 결과로 저장하고 이미지에 적힌 42.0은 참고 파일로 별도 저장합니다. 2등급 하한을 현재 표본의 50백분위로 해석하지 않습니다.',
        '14번은 기술통계·히스토그램 빈도·박스플롯 통계 CSV와 독립 HTML 그래프를 저장합니다. 극단값을 자동 삭제하지 않습니다.',
        '15번은 분석대상_설정.csv와 5항목의 산점도·평균선·LOWESS를 한 장에 담은 PNG만 저장합니다.', '',
        '```powershell', 'python data/experiments/산출물/산출물_12_15_생성.py', '```', '']
    (OUTPUT / 'README_12_15.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'first measurement sample: {len(data)}')
    for folder in [folder12, folder13, folder14, folder15]:
        print(folder.name, len(list(folder.glob('*.csv'))), 'CSV;', len(list(folder.glob('*.html'))), 'HTML')


if __name__ == '__main__':
    main()

