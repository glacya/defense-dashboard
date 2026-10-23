"""실행: python data/experiments/운동_체력미달정보생성.py"""
from pathlib import Path

import numpy as np
import pandas as pd

from 분석_연령별 import analyze_age

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT/'data/experiments/results/운동_체력미달별처방관련성'
DEFICIT_PATH = OUTPUT_DIR/'장병별_첫측정_체력미달정보.csv'
AREAS = {'근력': 'STRENGTH', '근지구력': 'ENDURANCE', '심폐지구력': 'CARDIO', '유연성': 'FLEXIBILITY'}


def generate():
    first = analyze_age(return_first=True).copy()
    first['MESURE_ID'] = pd.to_numeric(first['MESURE_ID'], errors='raise').astype('Int64')
    if first.MESURE_ID.isna().any() or first.MESURE_ID.duplicated().any() or first.SOLDIER_ID.duplicated().any():
        raise ValueError('장병별 첫 측정 식별자가 결측 또는 중복입니다.')
    standards = pd.read_csv(ROOT/'data/definitions/grade3_male_19_24.csv')
    standards = standards.loc[standards.sex.eq('M') & standards.age_min.eq(19) & standards.age_max.eq(24)]
    if standards.exercise.duplicated().any():
        raise ValueError('기준표 종목 중복입니다.')
    standards = standards.set_index('exercise')
    first = first[['SOLDIER_ID', 'MESURE_ID', 'AGE', 'MESURE_DE']+list(AREAS.values())].copy()
    for label, col in AREAS.items():
        if col not in standards.index or standards.loc[col, 'rule'] != 'min_inclusive':
            raise ValueError(f'{col}: 기준표 확인 필요')
        cut = float(standards.loc[col, 'min_value'])
        if not np.isfinite(cut):
            raise ValueError(f'{col}: 기준값 오류')
        first[f'{label}_미달기준값'] = cut
        first[f'{label}_미달여부'] = first[col].lt(cut).astype('boolean').mask(first[col].isna())
        first[f'{label}_판정'] = first[f'{label}_미달여부'].map({True: '미달', False: '충족'}).fillna('판정불가')
    records = pd.read_csv(ROOT/'data/processed/KS_NFA_PRESCRIPTION.csv', usecols=['MESURE_ID'])
    ids = pd.to_numeric(records.MESURE_ID, errors='raise')
    first['운동처방기록있음'] = first.MESURE_ID.isin(ids)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    first.to_csv(DEFICIT_PATH, index=False, encoding='utf-8-sig')
    return first


if __name__ == '__main__':
    frame = generate()
    print(f'첫 측정 미달정보 {len(frame):,}명 저장: {DEFICIT_PATH}')
