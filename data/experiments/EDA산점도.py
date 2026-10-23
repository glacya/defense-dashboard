"""실행: python data/experiments/EDA산점도.py"""
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / 'processed/KS_NFA_PROCESSED.csv'


data = pd.read_csv(DATA_PATH, dtype={'M_CODE': 'string'})
data = data.loc[data['M_CODE'].notna() & data['M_CODE'].str.strip().ne('')]
data = data.sort_values('MESURE_DE', kind='stable').drop_duplicates('M_CODE')  # 첫 측정
data = data.loc[data['AGE'].between(19, 24)]
items = {'STRENGTH': '근력(%)', 'ENDURANCE': '근지구력(회)',
         'CARDIO': '심폐지구력', 'FLEXIBILITY': '유연성(cm)',
         'BODY_FAT_PERCENTAGE': '체지방률(%)'}
plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False})
fig, axes = plt.subplots(2, 3, figsize=(13, 7))
for ax, (column, label) in zip(axes.flat, items.items()):
    ax.scatter(data['BMI'], data[column], s=8, alpha=0.2)
    ax.set(xlabel='BMI', ylabel=label, title=f'BMI와 {label}')
axes.flat[-1].axis('off')
fig.suptitle('장병별 첫 측정: BMI와 체력·체지방률의 관계')
plt.tight_layout()
plt.show()

