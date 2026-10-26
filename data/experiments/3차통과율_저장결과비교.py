"""저장된 장병별 그룹 통과율과 로지스틱 예측을 비교한다."""
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parent / 'results'
OUTPUT = RESULTS / '3차통과율_저장된장병정보비교' / '장병별_저장결과비교.csv'


def main():
    dtype = {'SOLDIER_ID': 'string', '그룹': 'string'}
    group = pd.read_csv(RESULTS/'3차통과율_하위그룹_체력상태조합별2/장병별_소속그룹비율.csv', dtype=dtype)
    regression = pd.read_csv(RESULTS/'로지스틱회귀예측/개인별통과확률.csv', dtype=dtype)
    if set(group.SOLDIER_ID) != set(regression.SOLDIER_ID):
        raise ValueError('두 파일의 장병 목록이 다릅니다.')
    common = [c for c in group.columns if c in regression.columns and c != 'SOLDIER_ID']
    g, r = group.set_index('SOLDIER_ID'), regression.set_index('SOLDIER_ID')
    for col in common:
        left, right = g[col], r[col].reindex(g.index)
        if not (left.eq(right).fillna(False) | (left.isna() & right.isna())).all():
            raise ValueError(f'두 파일의 장병 정보가 다릅니다: {col}')
    extra = ['SOLDIER_ID', '실제3차통과여부', '모델통과확률(%)', '교차검증통과확률', '예측3차상태']
    result = group.merge(regression[extra], on='SOLDIER_ID', validate='one_to_one')
    result['로지스틱_교차검증통과확률(%)'] = result.pop('교차검증통과확률')*100
    result = result.rename(columns={
        'SOLDIER_ID': '장병식별자', '그룹': '상위그룹_1차2차상태코드',
        '세부그룹': '하위그룹_1차2차미달종목수',
        '하위자체통과율(%)': '하위그룹_실제통과율(%)',
        '상위통과율기여도(%p)': '하위그룹의_상위통과율기여도(%p)',
        '소속상위그룹_3차통과율(%)': '상위그룹_실제통과율(%)',
        '모델통과확률(%)': '로지스틱_예측통과확률(%)',
        '예측3차상태': '로지스틱_3차예측판정',
        '실제3차통과여부': '실제3차통과여부_1통과_0미통과',
    })
    result['통과율차이_로지스틱-하위그룹(%p)'] = result['로지스틱_예측통과확률(%)']-result['하위그룹_실제통과율(%)']
    first = ['장병식별자', '상위그룹_1차2차상태코드', '하위그룹_1차2차미달종목수',
             '하위그룹_실제통과율(%)', '로지스틱_예측통과확률(%)',
             '통과율차이_로지스틱-하위그룹(%p)', '로지스틱_교차검증통과확률(%)',
             '3차상태', '로지스틱_3차예측판정']
    result = result[first+[c for c in result.columns if c not in first]]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False, encoding='utf-8-sig')
    print(f'비교 CSV 저장 완료: {len(result)}명')


if __name__ == '__main__':
    main()
