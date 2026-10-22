"""개인 장병의 1·2차 미달 종목 수로 3차 통과확률을 예측한다.

실행: python data/experiments/로지스틱회귀예측.py
추가 개인 예측: python data/experiments/로지스틱회귀예측.py --first 1 --second 2
"""
import argparse
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

calculate_people = importlib.import_module('3차통과율_체력상태조합별').calculate

OUTPUT_DIR = Path(__file__).resolve().parent / 'results' / '로지스틱회귀예측'
FEATURES = ['1차미달종목수', '2차미달종목수']
THRESHOLD = 0.5


def new_model():
    return LogisticRegression(C=1.0, solver='lbfgs', max_iter=2000, tol=1e-8)


def predict_person(model, first, second):
    """학습된 모델로 개인의 3차 통과확률을 반환한다."""
    if any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or not 0 <= v <= 4
           for v in (first, second)):
        raise ValueError('미달 종목 수는 각각 0~4의 정수여야 합니다.')
    return float(model.predict_proba(np.array([[first, second]], dtype=float))[0, 1])


def calculate():
    _, people, excluded = calculate_people()
    people = people.copy()
    eligible = people[FEATURES].notna().all(axis=1)
    train = eligible & people['3차상태코드'].notna()
    x = people.loc[train, FEATURES].to_numpy(dtype=float)
    # 원본 0=충족, 1=미달을 학습용 1=통과, 0=미통과로 변환한다.
    y = people.loc[train, '3차상태코드'].eq(0).to_numpy(dtype=int)
    if len(y) == 0 or np.unique(y).size < 2:
        raise ValueError('로지스틱 회귀에는 3차 통과자와 미통과자 자료가 모두 필요합니다.')

    people['실제3차통과여부'] = people['3차상태코드'].map({0: 1, 1: 0}).astype('Int64')
    people['교차검증통과확률'] = np.nan
    folds = min(5, int(np.bincount(y, minlength=2).min()))
    metrics = {'학습인원': len(y), '통과인원': int(y.sum()), '미통과인원': int((1-y).sum()),
               '예측제외인원': excluded, '교차검증분할수': folds if folds >= 2 else 0,
               '검증상태': '클래스별 최소 2명 미충족: 검증 생략',
               'ROC_AUC': np.nan, 'Brier': np.nan, 'LogLoss': np.nan}
    if folds >= 2:
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
        oof = cross_val_predict(new_model(), x, y, cv=cv, method='predict_proba')[:, 1]
        people.loc[train, '교차검증통과확률'] = oof
        metrics.update({'검증상태': '개인별 학습 제외 예측으로 평가',
                        'ROC_AUC': roc_auc_score(y, oof), 'Brier': brier_score_loss(y, oof),
                        'LogLoss': log_loss(y, oof, labels=[0, 1])})

    model = new_model().fit(x, y)
    if model.n_iter_.max() >= model.max_iter:
        raise RuntimeError('모델 미수렴: 입력 자료와 학습 설정을 확인하세요.')
    people['모델통과확률'] = np.nan
    if eligible.any():
        people.loc[eligible, '모델통과확률'] = model.predict_proba(
            people.loc[eligible, FEATURES].to_numpy(dtype=float))[:, 1]
    people['모델통과확률(%)'] = people['모델통과확률'] * 100
    people['예측3차상태'] = '예측불가'
    people.loc[eligible, '예측3차상태'] = np.where(
        people.loc[eligible, '모델통과확률'] >= THRESHOLD, '통과', '미통과')
    values = np.r_[model.intercept_, model.coef_[0]]
    coefficients = pd.DataFrame({'항목': ['절편'] + FEATURES,
                                 '계수': values, '오즈비': np.exp(values)})
    return model, people, pd.DataFrame([metrics]), coefficients


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=int, choices=range(5), help='개인 1차 미달 종목 수')
    parser.add_argument('--second', type=int, choices=range(5), help='개인 2차 미달 종목 수')
    args = parser.parse_args()
    if (args.first is None) != (args.second is None):
        parser.error('--first와 --second를 함께 입력하세요.')
    model, people, metrics, coefficients = calculate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in [('개인별통과확률', people), ('교차검증성능', metrics), ('회귀계수', coefficients)]:
        frame.to_csv(OUTPUT_DIR / f'{name}.csv', index=False, encoding='utf-8-sig')
    (OUTPUT_DIR / '모델계수.json').write_text(json.dumps({
        'features': FEATURES, 'intercept': float(model.intercept_[0]),
        'coefficients': model.coef_[0].tolist(), 'pass_label': 1,
        'classification_threshold': THRESHOLD,
        'failure_item_threshold': 2,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUTPUT_DIR / '계산설명.txt').write_text(
        '체력상태조합별_3차통과율.calculate()의 원자료 처리와 판정을 그대로 재사용합니다.\n'
        '남성 19~24세 기준, 날짜순 첫 3회 측정 대상자 조건도 동일합니다.\n'
        '4개 영역의 미달 종목 수 0~1개=충족(통과), 2~4개=미달(미통과).\n'
        '입력 x1=1차 미달 종목 수, x2=2차 미달 종목 수.\n'
        '1·2차 충족/미달 상황은 종목 수에서 결정되므로 중복 입력하지 않습니다.\n'
        '목표 y=1은 3차 통과, y=0은 3차 미통과입니다.\n'
        'p=1/(1+exp(-(b0+b1*x1+b2*x2))), 개인별 예측 통과확률입니다.\n'
        'L2 로지스틱 회귀 C=1, 클래스 가중치 미적용, 분류 기준 p>=0.5.\n'
        '3차 자료는 정답에만 사용하며 예측 입력에는 사용하지 않습니다.\n'
        '1·2차 판정불가는 예측 제외, 3차 판정불가는 학습 제외 후 예측만 합니다.\n'
        '모델통과확률: 전체 유효 자료로 학습한 모델의 적합/새 대상 예측값.\n'
        '교차검증통과확률: 해당 개인을 학습에서 제외한 모델의 예측값.\n'
        '최대 5분할 층화 교차검증으로 ROC_AUC, Brier, LogLoss를 평가합니다.\n'
        '소수 클래스가 2명 미만이면 검증 생략, 단일 클래스이면 학습 오류를 알립니다.\n'
        '같은 1·2차 미달 수를 가진 개인은 같은 모델통과확률을 받습니다.\n'
        '개인의 실제 통과 비율이 아닌 추정 확률이며 미래 자료 검증은 별도입니다.\n', encoding='utf-8')
    print(metrics.to_string(index=False))
    if args.first is not None:
        p = predict_person(model, args.first, args.second)
        print(f'1차 {args.first}개 / 2차 {args.second}개 미달: 3차 통과확률 {p:.2%}')
    print(f'결과 저장: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
