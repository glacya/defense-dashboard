"""python data/experiments/예측성능평가3.py

성능평가2와 동일하게 회차별 2개 이상 미달을 위험으로 정의한다.
1·2차 상태와 1차 BMI 구간별 학습 미달률로 3차 위험을 예측한다.
BMI는 학습 표본의 삼분위 구간이며 의학적 정상/비정상 분류가 아니다.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, roc_auc_score, brier_score_loss

from 종목별체력미달자변화률2 import analyze, AREAS

OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'data/experiments/results/성능평가3'
SEED = 42
THRESHOLD = .5
PRIOR_WEIGHT = 10  # 소수 인원 그룹의 추정치를 전체 학습 미달률 쪽으로 보정하는 가중치


def build_people():
    _, _, detail, _ = analyze()
    cols = [f'{v}_미달' for v in AREAS.values()]
    detail['미달개수'] = detail[cols].sum(axis=1).astype('Int64').mask(detail[cols].isna().any(axis=1))
    counts = detail.pivot(index='M_CODE', columns='회차', values='미달개수').reindex(columns=[1, 2, 3])
    counts.columns = ['weak_1', 'weak_2', 'weak_3']
    if 'BMI' not in detail:
        raise ValueError('원본에 BMI 컬럼이 없습니다.')
    bmi = detail.loc[detail['회차'].eq(1)].set_index('M_CODE')['BMI']
    counts['BMI_1'] = pd.to_numeric(bmi, errors='coerce').replace([np.inf, -np.inf], np.nan)
    counts.loc[counts.BMI_1.le(0), 'BMI_1'] = np.nan
    valid = counts.dropna(subset=['weak_1', 'weak_2', 'weak_3']).copy()
    excluded = len(counts) - len(valid)
    valid['상태조합'] = np.where(valid.weak_1.ge(2), '미달', '충족') + '→' + np.where(valid.weak_2.ge(2), '미달', '충족')
    valid['기존규칙점수(%)'] = (valid.weak_1.ge(2).astype(int) + valid.weak_2.ge(2).astype(int)) * 50
    valid['actual_3rd_risk'] = valid.weak_3.ge(2).astype(int)
    return valid, excluded


def evaluate(frame, probability, name):
    y = frame.actual_3rd_risk.to_numpy(dtype=int)
    predicted = np.asarray(probability) >= THRESHOLD
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    ratio = lambda a, b: a / b if b else np.nan
    return {'모형': name, '평가인원': len(y), 'TN': tn, 'FP': fp, 'FN': fn, 'TP': tp,
            '정확도(%)': ratio(tp + tn, len(y)) * 100, '정밀도(%)': ratio(tp, tp + fp) * 100,
            '재현율(%)': ratio(tp, tp + fn) * 100,
            'F1': ratio(2 * tp, 2 * tp + fp + fn),
            'ROC_AUC': roc_auc_score(y, probability) if len(np.unique(y)) == 2 else np.nan,
            'Brier점수': brier_score_loss(y, probability)}


def main():
    people, excluded = build_people()
    if people.actual_3rd_risk.value_counts().min() < 2:
        raise ValueError('위험·비위험 장병별 최소 2명이 필요합니다.')
    train, test = train_test_split(people, test_size=.3, random_state=SEED,
                                   stratify=people.actual_3rd_risk)
    train, test = train.copy(), test.copy()
    quantiles = train.BMI_1.dropna().quantile([1 / 3, 2 / 3]).to_numpy()
    if len(quantiles) != 2 or not np.isfinite(quantiles).all() or quantiles[0] >= quantiles[1]:
        raise ValueError('BMI 삼분위 구간을 만들 수 없습니다.')
    low, high = map(float, quantiles)
    for frame in [train, test]:
        frame['BMI구간'] = pd.cut(frame.BMI_1, [-np.inf, low, high, np.inf],
                                   labels=['낮음', '중간', '높음']).astype('string').fillna('결측')
    prior = float(train.actual_3rd_risk.mean())

    def fit_group(keys):
        rules = train.groupby(keys, observed=True).actual_3rd_risk.agg(['size', 'sum']).reset_index()
        rules = rules.rename(columns={'size': '학습인원', 'sum': '학습3차미달인원'})
        rules['학습미달률'] = rules['학습3차미달인원'] / rules['학습인원']
        rules['예측확률'] = (rules['학습3차미달인원'] + PRIOR_WEIGHT * prior) / (rules['학습인원'] + PRIOR_WEIGHT)
        return rules

    state_rules = fit_group(['상태조합'])
    rules = fit_group(['상태조합', 'BMI구간'])
    # 학습에 없던 BMI 조합은 상태조합 추정치, 상태조합도 없으면 전체 학습 미달률 사용.
    predictions = test.reset_index().merge(rules, on=['상태조합', 'BMI구간'], how='left', validate='many_to_one')
    state_probability = predictions['상태조합'].map(state_rules.set_index('상태조합')['예측확률']).fillna(prior)
    predictions['예측출처'] = np.where(predictions['예측확률'].notna(), '상태+BMI 학습그룹', '상태그룹/전체 학습률 대체')
    predictions['예측확률'] = predictions['예측확률'].fillna(state_probability)
    predictions['예측3차미달'] = predictions['예측확률'].ge(THRESHOLD)
    predictions['적중'] = predictions['예측3차미달'].eq(predictions.actual_3rd_risk)
    predictions['예측확률(%)'] = predictions['예측확률'] * 100
    metrics = pd.DataFrame([
        evaluate(predictions, predictions['예측확률'], '상태조합+BMI'),
        evaluate(predictions, state_probability, '상태조합만(학습률)'),
        evaluate(predictions, predictions['기존규칙점수(%)'].ge(50).astype(float), '성능평가2 규칙'),
    ])
    groups = predictions.groupby(['상태조합', 'BMI구간'], observed=True).agg(
        평가인원=('적중', 'size'), 실제3차미달인원=('actual_3rd_risk', 'sum'),
        적중인원=('적중', 'sum'), 예측확률=('예측확률', 'mean')).reset_index()
    groups['실제3차미달률(%)'] = groups['실제3차미달인원'] / groups['평가인원'] * 100
    groups['그룹내적중률(%)'] = groups['적중인원'] / groups['평가인원'] * 100
    membership = pd.concat([train.assign(데이터구분='학습'), test.assign(데이터구분='평가')]).reset_index()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in [('train_rules', rules), ('test_predictions', predictions),
                         ('test_group_stats', groups), ('metrics', metrics), ('split_membership', membership)]:
        frame.to_csv(OUTPUT_DIR / f'performance3_{name}.csv', index=False, encoding='utf-8-sig')
    config = {'학습인원': len(train), '평가인원': len(test), '판정불가제외인원': excluded,
              'BMI기준차수': 1, 'BMI구간': {'낮음': f'BMI ≤ {low}', '중간': f'{low} < BMI ≤ {high}', '높음': f'BMI > {high}', '결측': '별도 그룹'},
              'BMI삼분위경계': [low, high], '미달기준': '4종목 중 2개 이상',
              '학습전체미달률': prior, '축소가중인원': PRIOR_WEIGHT, '예측임계값': THRESHOLD, 'random_seed': SEED,
              '주의': '단일 부대 내부 평가. 다른 부대·미래 자료에서 별도 검증 필요. BMI 구간은 의학적 분류가 아님.'}
    (OUTPUT_DIR / 'performance3_settings.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'BMI 경계: {low:.4f}, {high:.4f} / 학습 {len(train)}명 / 평가 {len(test)}명')
    print(metrics.to_string(index=False))
    print(f'결과: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
