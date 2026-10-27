"""15번 산출물을 설정 CSV와 5항목 통합 이미지로 생성합니다."""

import importlib
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT.parent
sys.path.insert(0, str(EXPERIMENTS.parents[1]))
sys.path.insert(0, str(EXPERIMENTS))


def generate():
    """기존 실험 계산으로 산점도·구간 평균·LOWESS를 한 이미지에 그립니다."""
    module = importlib.import_module('BMI_체력항목_비선형성분석')
    summary, pairs, bins, curves = module.calculate()
    output = ROOT / '15_BMI_비선형성탐색'
    output.mkdir(exist_ok=True)
    settings = output / '분석대상_설정.csv'
    if not settings.exists():
        summary.to_csv(settings, index=False, encoding='utf-8-sig')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(3, 2, figsize=(16, 14), layout='constrained')
    for ax, metric in zip(axes.flat, module.TARGETS):
        pair, table, curve = pairs[metric], bins[metric], curves[metric]
        ax.scatter(pair.BMI, pair[metric], s=7, alpha=.12, color='#64748b', rasterized=True, label='개인 측정값')
        full = np.arange(table['구간시작'].min(), table['구간시작'].max()+.5, 1.0)
        table = table.set_index('구간시작').reindex(full)
        ax.plot(table.index+.5, table['평균'].where(table['인원'].ge(20)), 'o-',
                color='#2563eb', markersize=4, linewidth=1.8, label='BMI 구간별 평균')
        ax.plot(curve.BMI, curve.LOWESS, color='#ea580c', linewidth=2.3, label='LOWESS')
        for boundary in (18.5, 25):
            ax.axvline(boundary, color='#94a3b8', linestyle=':', linewidth=1)
        ax.set(title=module.METRICS[metric], xlabel='BMI (kg/m²)', ylabel=module.METRICS[metric])
        ax.grid(alpha=.15)
    axes.flat[-1].axis('off')
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles, labels, loc='upper left', frameon=False, fontsize=13)
    axes.flat[-1].text(.03,.55,'첫 측정 당시 19~24세 · 항목별 결측 제외\nBMI 구간 폭 1.0 · 평균선은 구간 인원 20명 이상\n희소·빈 구간의 평균선은 연결하지 않음\nLOWESS: frac=0.4, it=3\n점선: BMI 18.5 / 25\n\n곡선은 탐색 결과이며 인과성이나\n예측력 개선을 입증하지 않습니다.',
                        transform=axes.flat[-1].transAxes, va='top', linespacing=1.8)
    fig.suptitle('15. BMI와 체력항목의 비선형성 탐색', fontsize=21, fontweight='bold')
    path=output/'BMI_체력항목_통합그래프.png'
    fig.savefig(path, dpi=170, facecolor='white')
    plt.close(fig)
    generate_heatmap()
    return path


def generate_heatmap():
    """동일 첫 측정 표본의 BMI와 5항목 Pearson 상관을 한 이미지로 저장합니다."""
    module = importlib.import_module('BMI_체력항목_비선형성분석')
    _, pairs, _, _ = module.calculate()
    labels = ['근력\n상대악력', '근지구력', '심폐지구력', '유연성', '체지방률']
    values, sizes = [], []
    for metric in module.TARGETS:
        pair = pairs[metric]
        valid = len(pair) >= 3 and pair.BMI.nunique() > 1 and pair[metric].nunique() > 1
        values.append(float(pearsonr(pair.BMI, pair[metric]).statistic) if valid else np.nan)
        sizes.append(len(pair))
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False})
    fig, ax = plt.subplots(figsize=(12, 3.5), layout='constrained')
    matrix = np.array([values])
    assert np.all(np.abs(matrix[np.isfinite(matrix)]) <= 1)
    image = ax.imshow(np.ma.masked_invalid(matrix), cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
    ax.set_xticks(range(len(labels)), labels=labels)
    ax.set_yticks([0], labels=['BMI'])
    ax.tick_params(length=0, pad=12)
    for i, (value, n) in enumerate(zip(values, sizes)):
        label = f'r = {value:+.3f}\nn = {n:,}' if np.isfinite(value) else f'계산 불가\nn = {n:,}'
        ax.text(i, 0, label, ha='center', va='center', fontsize=13,
                color='white' if np.isfinite(value) and abs(value) > .55 else '#17212b')
    ax.set_title('BMI와 체력항목의 Pearson 상관계수', fontsize=18, pad=20)
    fig.colorbar(image, ax=ax, label='Pearson r', ticks=[-1, -.5, 0, .5, 1], shrink=.85)
    fig.supxlabel('첫 측정 당시 19~24세 · 항목별 유효 짝자료 사용\n선형 관계 요약이며, 곡선 관계와 인과성은 이 계수만으로 판단하지 않습니다.', fontsize=10)
    path = ROOT / '15_BMI_비선형성탐색' / 'BMI_체력항목_Pearson_히트맵.png'
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=180, facecolor='white')
    plt.close(fig)
    return path


if __name__=='__main__':
    print(generate())
