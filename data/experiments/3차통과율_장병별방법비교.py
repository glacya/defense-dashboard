"""실행: python data/experiments/3차통과율_장병별방법비교.py"""
import importlib
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parent / 'results' / Path(__file__).stem


def main():
    grouped = importlib.import_module('3차통과율_하위그룹_체력상태조합별2')
    regression = importlib.import_module('3차통과율_로지스틱회귀예측')
    _, _, people, _ = grouped.calculate()
    _, fitted, metrics, _ = regression.calculate()
    if set(people.M_CODE) != set(fitted.M_CODE):
        raise ValueError('두 방법의 대상 장병이 다릅니다.')
    keys = ['M_CODE', '1차미달종목수', '2차미달종목수', '3차상태코드']
    comparison = people.merge(fitted[keys + ['모델통과확률', '교차검증통과확률']],
                              on=keys, how='left', validate='one_to_one', indicator=True)
    if not comparison['_merge'].eq('both').all():
        raise ValueError('두 방법의 개인별 입력 또는 3차 판정이 다릅니다.')
    comparison = comparison.drop(columns='_merge')
    comparison['회귀통과율(%)'] = comparison['모델통과확률']*100
    comparison['회귀교차검증통과율(%)'] = comparison['교차검증통과확률']*100
    comparison['차이_회귀-그룹(%p)'] = comparison['회귀통과율(%)'] - comparison['하위자체통과율(%)']
    summary = comparison.groupby(['그룹', '세부그룹'], sort=True).agg(
        장병수=('M_CODE', 'size'), 관측통과율=('하위자체통과율(%)', 'first'),
        회귀통과율=('회귀통과율(%)', 'first'),
        회귀교차검증평균=('회귀교차검증통과율(%)', 'mean'),
        차이=('차이_회귀-그룹(%p)', 'first')).reset_index()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(OUTPUT_DIR/'장병별_통과비율비교.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(OUTPUT_DIR/'하위그룹별_통과비율비교.csv', index=False, encoding='utf-8-sig')
    metrics.to_csv(OUTPUT_DIR/'회귀_교차검증성능.csv', index=False, encoding='utf-8-sig')
    (OUTPUT_DIR/'비교설명.txt').write_text(
        '두 방법 모두 현재 원자료로 다시 계산하고 M_CODE와 입력·결과를 대조했습니다.\n'
        '개인에게 적용하는 관측 통과율은 하위자체통과율(%)입니다. 기여도(%p)는 개인 확률이 아닙니다.\n'
        '회귀통과율은 전체 자료 적합값, 회귀교차검증통과율은 본인을 학습에서 제외한 예측값입니다.\n'
        '차이=회귀통과율-하위자체통과율이며 단위는 %p입니다.\n'
        '관측 통과율은 본인의 3차 결과도 포함하므로 이 비교만으로 예측 성능 우열을 판단하지 않습니다.\n', encoding='utf-8')
    print(summary.to_string(index=False))
    print(metrics.to_string(index=False))
    print(f'대조 장병: {len(comparison)}명 / 평균 절대 차이: {comparison["차이_회귀-그룹(%p)"].abs().mean():.3f}%p')


if __name__ == '__main__':
    main()
