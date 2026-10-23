"""실행: python data/experiments/카이제곱검정_bmi_심페.py"""
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm
from statsmodels.stats.multitest import multipletests
from 분석_bmi별 import analyze_bmi

# 1. 첫 측정 자료와 BMI 그룹 불러오기
_, _, data, _ = analyze_bmi()
data = data.dropna(subset=['CARDIO']).copy()


print(data['BMI그룹'])

# 2. 심폐 42 미만은 미달, 42 이상은 충족
data['판정'] = np.where(data['CARDIO'] < 42, '미달', '충족')
table = pd.crosstab(data['BMI그룹'], data['판정']).reindex(columns=['미달', '충족'], fill_value=0)

# 3. 카이제곱 검정과 전체 효과크기
chi2, p, dof, expected = chi2_contingency(table, correction=False)
n = table.to_numpy().sum()
v = np.sqrt(chi2 / n)

# 4. 미달 칸의 조정표준화잔차: (관측−기대)/√[기대×(1−행 비율)×(1−열 비율)]
row_ratio = table.sum(axis=1).to_numpy() / n
fail_ratio = table['미달'].sum() / n
z = (table['미달'].to_numpy() - expected[:, 0]) / np.sqrt(
    expected[:, 0] * (1 - row_ratio) * (1 - fail_ratio))

# 5. 세 그룹의 잔차 p값에 Holm 보정(전체 카이제곱 검정과는 별개)
raw_p = 2 * norm.sf(np.abs(z))
holm_p = multipletests(raw_p, method='holm')[1]
result = pd.DataFrame({
    '미달률(%)': table['미달'] / table.sum(axis=1) * 100,
    '기대 미달 인원': expected[:, 0],
    '조정표준화잔차': z,
    '보정 전 p값': raw_p,
    'Holm 보정 p값': holm_p,
})

# 6. 터미널에 결과와 간단한 해석 출력
print('BMI 그룹별 심폐 미달·충족 인원')
print(table)
print(f'\nχ²={chi2:.3f}, 자유도={dof}, p값={p:.3e}, 전체 효과크기 V={v:.3f}')
print('BMI 그룹과 심폐 미달 여부가 관련 있다는 근거가 있습니다.' if p < .05
      else 'BMI 그룹과 심폐 미달 여부의 관련성을 확인할 근거가 충분하지 않습니다.')
print('\n그룹별 조정표준화잔차')
print(result.to_string(float_format=lambda x: f'{x:.4g}'))
print('\n잔차 양수: 기대보다 미달자가 많음 / 음수: 적음')
print('±1.96은 보정 전 참고 기준이며, 최종 판단은 Holm 보정 p값<0.05입니다.')
if expected.min() < 1 or (expected < 5).mean() > .2:
    print('기대빈도가 부족하므로 근사 p값 해석에 주의하세요.')
elif p < .05:
    for group, row in result.iterrows():
        if row['Holm 보정 p값'] < .05:
            direction = '많음' if row['조정표준화잔차'] > 0 else '적음'
            print(f'{group}: 미달 인원이 기대보다 유의하게 {direction}')
        else:
            print(f'{group}: 보정 후 유의한 차이 없음')
else:
    print('전체 검정이 유의하지 않아 잔차는 참고용으로만 확인합니다.')
print('기대는 BMI와 미달 여부가 독립일 때의 예상 인원이며, 특정 두 그룹의 직접 비교는 아닙니다.')
