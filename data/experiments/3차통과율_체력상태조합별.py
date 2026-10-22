"""python data/experiments/체력상태조합별_3차통과율.py

원본 processed 자료의 첫 3회 측정으로 1·2차 방향별 실제 3차 통과율 집계.
0=충족(미달 종목 0~1개), 1=미달(2개 이상). 통과율은 관측 비율이다.
"""
from pathlib import Path
import pandas as pd
from 종목별체력미달자_회차별변화율 import analyze, AREAS

OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'data/experiments/results/성능평가방향성'


def calculate():
    # 최종 CSV와 3등급 기준표를 읽는다. 심폐는 통합 CARDIO(VO₂max)를 사용한다.
    _, _, detail, _ = analyze()
    cols = [f'{col}_미달' for col in AREAS.values()]
    detail['미달종목수'] = detail[cols].sum(axis=1).astype('Int64').mask(detail[cols].isna().any(axis=1))
    people = detail.pivot(index='M_CODE', columns='회차', values='미달종목수').reindex(columns=[1, 2, 3])
    people.columns = ['1차미달종목수', '2차미달종목수', '3차미달종목수']
    for r in (1, 2, 3):
        count = people[f'{r}차미달종목수']
        people[f'{r}차상태코드'] = count.ge(2).astype('Int64').mask(count.isna())
        people[f'{r}차상태'] = people[f'{r}차상태코드'].map({0: '충족', 1: '미달'}).fillna('판정불가')
    valid = people[['1차상태코드', '2차상태코드']].notna().all(axis=1)
    people['그룹'] = pd.Series(pd.NA, index=people.index, dtype='string')
    people.loc[valid, '그룹'] = (people.loc[valid, '1차상태코드'].astype(str)
                                  + people.loc[valid, '2차상태코드'].astype(str))
    rows = []
    for code, first, second in [('00', '충족', '충족'), ('01', '충족', '미달'),
                                 ('10', '미달', '충족'), ('11', '미달', '미달')]:
        group = people.loc[people['그룹'].eq(code).fillna(False)]
        a = int(group['3차상태코드'].eq(0).sum())
        b = int(group['3차상태코드'].eq(1).sum())
        rows.append({'그룹': code, '1차': first, '2차': second, '그룹전체인원': len(group),
                     '3차판정불가인원': int(group['3차상태코드'].isna().sum()),
                     'A_3차충족인원': a, 'B_3차미달인원': b, '평가인원_A+B': a+b,
                     '통과확률_A/(A+B)': a/(a+b) if a+b else float('nan'),
                     '통과율(%)': a/(a+b)*100 if a+b else float('nan')})
    return pd.DataFrame(rows), people.reset_index(), int((~valid).sum())


def main():
    groups, people, excluded = calculate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    groups.to_csv(OUTPUT_DIR / '성능평가방향성_4그룹_3차통과율.csv', index=False, encoding='utf-8-sig')
    people.to_csv(OUTPUT_DIR / '성능평가방향성_장병별판정.csv', index=False, encoding='utf-8-sig')
    print(groups.to_string(index=False))
    print(f'1·2차 판정불가로 그룹 배정 제외: {excluded}명')
    print('통과율은 실제 3차 결과의 관측 비율이며 별도 검증된 예측확률이 아닙니다.')
    print(f'저장 위치: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
