"""실행: python data/experiments/성능평가방향성4.py

1·2차 미달 종목 수로 3차 통과확률을 추정하는 L2 로지스틱 회귀.
2번의 원자료 판정과 25개 하위그룹을 그대로 사용한다.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from 성능평가방향성2 import calculate as calculate_details

OUTPUT_DIR = Path(__file__).resolve().parent / 'results' / '성능평가방향성4'
FEATURES = ['1차미달종목수', '2차미달종목수']


def fit_probabilities(x, y, query):
    """빈 자료는 NaN, 단일 클래스는 라플라스 보정 비율로 대체한다."""
    if len(y) == 0:
        return np.full(len(query), np.nan), None, '학습 가능한 자료 없음'
    if np.unique(y).size == 1:
        return np.full(len(query), (y.sum() + 1) / (len(y) + 2)), None, '단일 클래스: (통과인원+1)/(평가인원+2) 적용'
    model = LogisticRegression(C=1.0, solver='lbfgs', max_iter=2000, tol=1e-8)
    model.fit(x, y)
    if model.n_iter_.max() >= model.max_iter:
        raise RuntimeError('로지스틱 회귀가 수렴하지 않았습니다. 입력 자료를 확인하세요.')
    return model.predict_proba(query)[:, 1], model, 'L2 로지스틱 회귀(C=1)'


def calculate():
    parent, details, people, excluded = calculate_details()
    people = people.copy()
    details = details.rename(columns={
        '통과확률_A/(A+B)': '실제통과비율', '통과율(%)': '실제통과율(%)',
    }).copy()
    eligible = people['그룹'].notna() & people[FEATURES].notna().all(axis=1)
    train = eligible & people['3차상태코드'].notna()
    x = people.loc[train, FEATURES].astype(float).to_numpy()
    # 통과를 1로 정의: 원래 상태코드의 0(충족)과 방향이 반대다.
    y = people.loc[train, '3차상태코드'].eq(0).astype(int).to_numpy()
    probability, model, status = fit_probabilities(x, y, details[FEATURES].to_numpy(dtype=float))
    details['추정통과확률'] = probability
    details['추정통과율(%)'] = probability * 100
    details['예상통과인원'] = details['평가인원_A+B'] * probability
    details['예상미달인원'] = details['평가인원_A+B'] * (1 - probability)
    details['추정방식'] = status
    people['추정통과확률'] = np.nan
    lookup = details.set_index('세부그룹')['추정통과확률']
    people.loc[eligible, '추정통과확률'] = people.loc[eligible, '세부그룹'].map(lookup)

    # 같은 사람을 학습과 검증에 동시에 넣지 않는 층화 교차검증.
    people['교차검증통과확률'] = np.nan
    counts = np.bincount(y, minlength=2)
    folds = min(5, int(counts.min()))
    metrics = {'학습인원': len(y), '통과인원': int(y.sum()),
               '미달인원': int(len(y) - y.sum()), '모델상태': status,
               '교차검증분할수': folds if folds >= 2 else 0,
               '검증상태': '각 클래스 최소 2명 필요: 교차검증 생략',
               'Brier': np.nan, 'LogLoss': np.nan, 'ROC_AUC': np.nan}
    if model is not None and folds >= 2:
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
        oof = cross_val_predict(model, x, y, cv=cv, method='predict_proba')[:, 1]
        people.loc[train, '교차검증통과확률'] = oof
        metrics.update({'검증상태': '층화 교차검증', 'Brier': brier_score_loss(y, oof),
                        'LogLoss': log_loss(y, oof, labels=[0, 1]),
                        'ROC_AUC': roc_auc_score(y, oof)})
    oof_means = people.loc[train].groupby('세부그룹')['교차검증통과확률'].mean()
    details['교차검증평균통과확률'] = details['세부그룹'].map(oof_means)
    totals = details.groupby('상위그룹')['예상통과인원'].sum(min_count=1)
    parent = parent.copy()
    parent['예상통과인원'] = parent['그룹'].map(totals)
    parent['추정통과확률'] = parent['예상통과인원'] / parent['평가인원_A+B'].replace(0, np.nan)
    coefficients = pd.DataFrame(columns=['항목', '계수', '오즈비'])
    if model is not None:
        values = np.r_[model.intercept_, model.coef_[0]]
        coefficients = pd.DataFrame({'항목': ['절편'] + FEATURES, '계수': values, '오즈비': np.exp(values)})
    return parent, details, people, pd.DataFrame([metrics]), coefficients, excluded


def main():
    parent, details, people, metrics, coefficients, excluded = calculate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in [('상위4그룹', parent), ('하위25그룹_통과비율', details),
                         ('장병별예측', people), ('교차검증성능', metrics), ('회귀계수', coefficients)]:
        frame.to_csv(OUTPUT_DIR / f'성능평가방향성4_{name}.csv', index=False, encoding='utf-8-sig')
    (OUTPUT_DIR / '계산설명.txt').write_text(
        '원본·대상자·측정순서·통과 판정은 성능평가방향성2와 동일합니다.\n'
        '전체 유효 표본을 함께 학습해 희소한 하위그룹에도 확률을 추정합니다.\n'
        'y=1: 3차 충족(미달 종목 0~1개), y=0: 3차 미달(2~4개).\n'
        'p=1/(1+exp(-(절편+b1*1차미달종목수+b2*2차미달종목수))).\n'
        'L2 규제 C=1, 클래스 가중치 미적용. 입력은 1·2차 미달 수만 사용합니다.\n'
        '실제통과비율=A/(A+B), 추정통과확률은 전체 자료에 적합한 모델 확률입니다.\n'
        '예상통과인원=3차 평가인원*추정통과확률(소수 가능).\n'
        '상위 확률은 하위 예상통과인원 합/상위 평가인원입니다.\n'
        '0명 하위그룹도 모델 확률은 표시하며 실제 비율은 공란입니다.\n'
        '1·2차 판정불가는 예측 제외, 3차 판정불가는 학습·검증 제외 후 예측만 합니다.\n'
        '단일 클래스이면 (통과인원+1)/(학습인원+2)로 대체, 학습 0명이면 확률 공란입니다.\n'
        '교차검증은 소수 클래스 수에 맞춘 최대 5분할입니다(각 클래스 2명 미만이면 생략).\n'
        '교차검증평균통과확률은 해당 하위그룹의 학습 제외 예측 평균입니다.\n'
        'Brier·LogLoss는 작을수록, ROC_AUC는 클수록 좋습니다.\n'
        '전체 자료 적합 확률과 교차검증 성능을 구분하세요. 외부·미래 자료 검증은 별도입니다.\n'
        '기존 전처리의 남성 19~24세 기준 및 3회 측정 대상자 조건을 상속합니다.\n', encoding='utf-8')
    print(details.to_string(index=False))
    print(metrics.to_string(index=False))
    print(f'1·2차 판정불가 제외: {excluded}명 / 저장 위치: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
