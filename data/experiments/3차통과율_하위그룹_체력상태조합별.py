"""python data/experiments/하위그룹_체력상태조합별_3차통과율.py

상위 00/01/10/11 그룹을 실제 1·2차 미달 종목 수(0~4개)로 세분화.
3차 충족 A(0~1개 미달), 미달 B(2~4개 미달)의 통과율 A/(A+B)를 계산.
장병별 예측비율 CSV는 소속 세부그룹의 관측 통과비율을 각 장병에게 적용한다.
"""
from pathlib import Path

import pandas as pd

from 체력상태조합별_3차통과율 import calculate as calculate_parent

OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'data/experiments/results/성능평가방향성2'


def calculate():
    # 기존 코드와 동일한 원본·3등급 기준·측정일순 첫 3회 판정을 재사용한다.
    # 부모 main은 실행하지 않으므로 기존 결과 파일에 쓰지 않는다.
    parent, people, excluded = calculate_parent()
    rows = []
    for code, first_values, second_values in [
        ('00', [0, 1], [0, 1]), ('01', [0, 1], [2, 3, 4]),
        ('10', [2, 3, 4], [0, 1]), ('11', [2, 3, 4], [2, 3, 4])
    ]:
        for first in first_values:
            for second in second_values:
                members = people.loc[people['그룹'].eq(code).fillna(False)
                                     & people['1차미달종목수'].eq(first).fillna(False)
                                     & people['2차미달종목수'].eq(second).fillna(False)]
                a = int(members['3차상태코드'].eq(0).sum())
                b = int(members['3차상태코드'].eq(1).sum())
                rows.append({
                    '상위그룹': code,
                    '1차상태': '충족' if first < 2 else '미달',
                    '2차상태': '충족' if second < 2 else '미달',
                    '세부그룹': f'{first},{second}',
                    '1차미달종목수': first, '2차미달종목수': second,
                    '그룹전체인원': len(members),
                    '3차판정불가인원': int(members['3차상태코드'].isna().sum()),
                    'A_3차충족인원': a, 'B_3차미달인원': b, '평가인원_A+B': a + b,
                    '통과확률_A/(A+B)': a / (a + b) if a + b else float('nan'),
                    '통과율(%)': a / (a + b) * 100 if a + b else float('nan'),
                })
    details = pd.DataFrame(rows)
    people['세부그룹'] = (people['1차미달종목수'].astype('string') + ','
                         + people['2차미달종목수'].astype('string'))
    return parent, details, people, excluded


def build_person_predictions(details, people):
    """동일 세부그룹의 관측 통과비율을 개인별 적용 비율로 연결한다."""
    rates = details[[
        '상위그룹', '세부그룹', '그룹전체인원', '평가인원_A+B',
        'A_3차충족인원', 'B_3차미달인원', '통과확률_A/(A+B)',
    ]].rename(columns={
        '상위그룹': '그룹',
        '그룹전체인원': '세부그룹전체인원',
        '평가인원_A+B': '세부그룹평가인원',
        'A_3차충족인원': '세부그룹3차통과인원',
        'B_3차미달인원': '세부그룹3차미통과인원',
        '통과확률_A/(A+B)': '예측통과비율',
    })
    predictions = people.merge(rates, on=['그룹', '세부그룹'], how='left',
                               validate='many_to_one', sort=False)
    predictions['예측통과비율(%)'] = predictions['예측통과비율'] * 100
    predictions['예측미통과비율'] = 1 - predictions['예측통과비율']
    predictions['예측미통과비율(%)'] = predictions['예측미통과비율'] * 100
    predictions['비율적용상태'] = '세부그룹 관측 통과비율 적용'
    predictions.loc[predictions['예측통과비율'].isna(), '비율적용상태'] = '세부그룹 평가인원 0명: 비율 계산 불가'
    predictions.loc[predictions['그룹'].isna(), '비율적용상태'] = '1·2차 판정불가: 그룹 배정 제외'
    return predictions


def main():
    parent, details, people, excluded = calculate()
    predictions = build_person_predictions(details, people)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in [('상위4그룹_3차통과율', parent), ('세부25그룹_3차통과율', details),
                         ('장병별판정', people), ('장병별예측비율', predictions)]:
        frame.to_csv(OUTPUT_DIR / f'성능평가방향성2_{name}.csv', index=False, encoding='utf-8-sig')
    print(details.to_string(index=False))
    print(f'1·2차 판정불가로 그룹 배정 제외: {excluded}명')
    print('통과확률은 실제 3차 결과의 관측 비율입니다. 평가 인원 0명인 조합은 비율을 빈칸으로 저장합니다.')
    print('장병별 예측비율은 소속 세부그룹의 관측 비율을 적용한 값입니다. 본인의 3차 결과도 집계에 포함되므로 독립 검증된 예측확률은 아닙니다.')
    print(f'저장 위치: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
