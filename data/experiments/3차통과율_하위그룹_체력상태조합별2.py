"""하위그룹의 인원 가중 기여도로 상위그룹 3차 통과율을 계산한다.

실행: python data/experiments/3차통과율_하위그룹_체력상태조합별2.py
기여도=a_i/E=(n_i/E)*(a_i/n_i), 상위 통과율=기여도 합계.
"""
import importlib
from pathlib import Path

import numpy as np
import pandas as pd

# 숫자로 시작하는 모듈명은 importlib로 불러온다.
calculate_parent = importlib.import_module('3차통과율_체력상태조합별').calculate
OUTPUT_DIR = Path(__file__).resolve().parent / 'results' / Path(__file__).stem


def calculate():
    parent, people, excluded = calculate_parent()
    totals = parent.set_index('그룹')
    rows = []
    for first in range(5):
        for second in range(5):
            code = f'{int(first >= 2)}{int(second >= 2)}'
            members = people.loc[people['그룹'].eq(code).fillna(False)
                                 & people['1차미달종목수'].eq(first).fillna(False)
                                 & people['2차미달종목수'].eq(second).fillna(False)]
            a = int(members['3차상태코드'].eq(0).sum())
            b = int(members['3차상태코드'].eq(1).sum())
            n = a+b
            e = int(totals.loc[code, '평가인원_A+B'])
            r = a/n if n else np.nan
            # 빈 하위그룹은 자체율이 정의되지 않지만, E>0이면 기여 인원은 0이다.
            contribution = a/e if e else np.nan
            rows.append({'상위그룹': code, '세부그룹': f'{first},{second}',
                         '1차미달종목수': first, '2차미달종목수': second,
                         '하위그룹전체인원': len(members), '하위판정불가인원': len(members)-n,
                         '하위평가인원_n': n, '하위통과인원_a': a, '하위미통과인원': b,
                         '상위전체인원': int(totals.loc[code, '그룹전체인원']),
                         '상위평가인원_E': e, '하위자체통과율': r,
                         '하위자체통과율(%)': r*100,
                         '상위내인원비중': n/e if e else np.nan,
                         '상위통과율기여도': contribution,
                         '상위통과율기여도(%p)': contribution*100})
    details = pd.DataFrame(rows).sort_values(['상위그룹', '1차미달종목수', '2차미달종목수']).reset_index(drop=True)
    parent = parent.copy()
    contributions = details.groupby('상위그룹')['상위통과율기여도'].sum(min_count=1)
    parent['기여도합산_3차통과율'] = parent['그룹'].map(contributions)
    parent['기여도합산_3차통과율(%)'] = parent['기여도합산_3차통과율']*100
    parent['직접계산과차이'] = parent['기여도합산_3차통과율'] - parent['통과확률_A/(A+B)']
    people = people.copy()
    people['세부그룹'] = people['1차미달종목수'].astype('string') + ',' + people['2차미달종목수'].astype('string')
    columns = ['상위그룹', '세부그룹', '하위자체통과율(%)', '상위통과율기여도(%p)']
    people = people.merge(details[columns].rename(columns={'상위그룹': '그룹'}),
                          on=['그룹', '세부그룹'], how='left', validate='many_to_one')
    people['소속상위그룹_3차통과율(%)'] = people['그룹'].map(parent.set_index('그룹')['기여도합산_3차통과율(%)'])
    return parent, details, people, excluded


def main():
    parent, details, people, excluded = calculate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in [('상위그룹_기여도합산_3차통과율', parent), ('하위그룹_통과기여도', details), ('장병별_소속그룹비율', people)]:
        frame.to_csv(OUTPUT_DIR/f'{name}.csv', index=False, encoding='utf-8-sig')
    (OUTPUT_DIR/'계산설명.txt').write_text(
        'n_i=하위그룹 3차 평가인원, a_i=하위그룹 3차 통과인원, E=상위그룹 3차 평가인원\n'
        '자체 통과율 r_i=a_i/n_i\n'
        '상위 통과율에 대한 하위 기여도 c_i=(n_i/E)*r_i=a_i/E\n'
        '기여도(%p)=100*c_i, 상위 3차 통과율(%)=기여도(%p)의 합\n'
        '예: E=100, n=20, a=5이면 자체율=25%, 인원비중=20%, 기여도=5%p.\n'
        '기여도는 개인의 통과확률이나 하위그룹 자체 통과율이 아닙니다.\n'
        '판정불가는 평가 분모에서 제외합니다. n=0이면 자체율 공란, E>0이면 기여도 0입니다.\n'
        'E=0이면 해당 상위그룹의 기여도와 합산 통과율은 공란입니다.\n'
        '통과자 0명이면 자체율과 기여도 모두 0이며 보정하지 않습니다.\n'
        '3차 미달 종목 0~1개는 통과, 2~4개는 미통과입니다.\n'
        '장병별 CSV의 기여도는 소속 하위그룹 전체의 값입니다. 장병별로 다시 합산하면 안 됩니다.\n'
        '합산 통과율은 상위 통과인원/E와 일치하며 새로운 예측모형이 아닙니다.\n', encoding='utf-8')
    print(parent.to_string(index=False))
    print(f'그룹 배정 제외: {excluded}명 / 결과: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
