"""python data/experiments/성능평가방향성3.py

상위 그룹의 관측 통과확률을 소속 하위 그룹에 동일하게 적용한다.
예상 통과 인원 = 하위 평가 인원 × 상위 통과확률.
하위 그룹 자체의 통과율로 예상 인원을 계산하지 않는다.
판정불가는 분모에서 제외한다. 상위 확률 역시 실제 3차에서 구한 관측 비율이다.
"""
from pathlib import Path

from 성능평가방향성2 import calculate as calculate_details

OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'data/experiments/results/성능평가방향성3'


def calculate():
    parent, details, people, excluded = calculate_details()
    totals = parent.set_index('그룹')
    details = details.copy()
    details['상위그룹전체인원'] = details['상위그룹'].map(totals['그룹전체인원'])
    details['상위평가인원'] = details['상위그룹'].map(totals['평가인원_A+B'])
    details['상위통과확률'] = details['상위그룹'].map(totals['통과확률_A/(A+B)'])
    denominator = details['상위평가인원'].replace(0, float('nan'))
    details['하위인원비중'] = details['평가인원_A+B'] / denominator
    details = details.rename(columns={
        'A_3차충족인원': '실제3차통과인원', 'B_3차미달인원': '실제3차미달인원',
        '통과확률_A/(A+B)': '비교용_하위실제통과율', '통과율(%)': '비교용_하위실제통과율(%)'})
    details['적용통과확률'] = details['상위통과확률']
    details['적용통과율(%)'] = details['적용통과확률'] * 100
    details['예상통과인원'] = details['평가인원_A+B'] * details['적용통과확률']
    details['예상미달인원'] = details['평가인원_A+B'] * (1 - details['적용통과확률'])
    details['실제−예상통과인원'] = details['실제3차통과인원'] - details['예상통과인원']
    details['상위대비예상통과기여비율'] = details['예상통과인원'] / denominator
    parent = parent.copy()
    parent['하위예상통과인원합'] = parent['그룹'].map(
        details.groupby('상위그룹')['예상통과인원'].sum(min_count=1))
    return parent, details, excluded


def main():
    parent, details, excluded = calculate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in [('상위그룹_가중통과집계', parent), ('세부그룹_통과기여계산', details)]:
        frame.to_csv(OUTPUT_DIR / f'성능평가방향성3_{name}.csv', index=False, encoding='utf-8-sig')
    (OUTPUT_DIR / '계산설명.txt').write_text(
        '상위 통과확률 = 상위 실제3차충족인원 ÷ 상위 평가인원\n'
        '각 하위 그룹의 적용통과확률 = 소속 상위 그룹의 통과확률(동일 적용)\n'
        '예상 통과 인원 = 하위 평가인원 × 적용통과확률\n'
        '예상 미달 인원 = 하위 평가인원 × (1−적용통과확률)\n'
        '예상 인원은 소수일 수 있으며 실제 통과 인원과 구분합니다.\n'
        '비교용 하위 실제통과율은 결과 확인용이며 예상 인원 계산에는 사용하지 않습니다.\n'
        '하위 예상 통과 인원 합은 상위 실제 통과 인원과 일치합니다.\n'
        '동일 자료의 상위 관측 통과율을 배분한 계산이며 독립적인 예측 성능 평가는 아닙니다.\n', encoding='utf-8')
    print(parent.to_string(index=False))
    print(f'그룹 배정 제외: {excluded}명 / 저장 위치: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
