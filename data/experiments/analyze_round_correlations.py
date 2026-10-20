"""장병 1·2·3차 체력측정값 상관분석.
실행: python data/experiments/analyze_round_correlations.py
입력: data/experiments/results/fitness_risk_by_round.csv
출력: data/experiments/results/round_correlations/
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'data/experiments/results/fitness_risk_by_round.csv'
OUT = ROOT / 'data/experiments/results/round_correlations'
OUT.mkdir(parents=True, exist_ok=True)

ID, ROUND = 'M_CODE', 'round'
MEASURES = {'REL_GRIP':'근력(상대악력)', 'CROSS_UP':'근지구력(교차윗몸일으키기)', 'SIT_REACH':'유연성(앉아윗몸앞으로굽히기)'}
CARDIO = {'TRAD':'심폐-트레드밀', 'STEP':'심폐-스텝', '20M_RUN':'심폐-왕복오래달리기'}
PAIRS = [(1,2),(2,3),(1,3)]

if not INPUT.exists():
    raise FileNotFoundError(f'입력 파일이 없습니다: {INPUT}\n먼저 identify_fitness_risk_4_rounds3.py를 실행하세요.')
df = pd.read_csv(INPUT, dtype={ID:'string'})
required = {ID,ROUND,*MEASURES,*CARDIO}
missing = required - set(df.columns)
if missing:
    raise ValueError(f'입력 CSV에 필요한 컬럼이 없습니다: {sorted(missing)}')
df[ROUND] = pd.to_numeric(df[ROUND], errors='coerce')
df = df[df[ROUND].isin([1,2,3]) & df[ID].notna()].copy()
if df.duplicated([ID,ROUND]).any():
    raise ValueError('동일 장병·회차가 중복되었습니다. 데이터 생성 과정을 확인하세요.')
# 3회 모두 측정 기록이 있는 장병만 선택 (종목별 결측은 비교 쌍마다 제외)
ids = df.groupby(ID)[ROUND].nunique()
ids = ids[ids == 3].index
df = df[df[ID].isin(ids)].copy()
if df.empty:
    raise ValueError('1·2·3차 측정 기록이 모두 있는 장병이 없습니다.')

records = []
paired_data = {}
for col, label in {**MEASURES, **CARDIO}.items():
    w = df.pivot(index=ID, columns=ROUND, values=col).apply(pd.to_numeric, errors='coerce')
    for a,b in PAIRS:
        pair = w[[a,b]].replace([np.inf,-np.inf],np.nan).dropna().copy()
        # 심폐 측정방법은 두 회차 모두 해당 방식이 단독으로 선택된 경우만 사용
        if col in CARDIO:
            methods = df[[ID,ROUND,'cardio_method']] if 'cardio_method' in df else None
            if methods is not None:
                mw = methods.pivot(index=ID,columns=ROUND,values='cardio_method')
                eligible = mw.index[(mw[a] == col) & (mw[b] == col)]
                pair = pair.loc[pair.index.intersection(eligible)]
            else:
                # cardio_method 컬럼이 없으면 해당 회차의 다른 심폐 측정값이 없는지 확인
                all_w = {c:df.pivot(index=ID,columns=ROUND,values=c) for c in CARDIO}
                for other in CARDIO:
                    if other != col:
                        pair = pair.loc[pair.index[all_w[other].loc[pair.index,[a,b]].isna().all(axis=1)]]
        n = len(pair)
        pr=pp=sr=sp=np.nan
        if n >= 3 and pair[a].nunique() > 1 and pair[b].nunique() > 1:
            pr,pp = pearsonr(pair[a],pair[b])
            sr,sp = spearmanr(pair[a],pair[b])
        records.append({'체력종목':label,'변수':col,'회차비교':f'{a}차↔{b}차',
                        '표본수':n,'Pearson_r':pr,'Pearson_p':pp,
                        'Spearman_rho':sr,'Spearman_p':sp,
                        '해석':('계산불가(표본 부족 또는 상수값)' if pd.isna(pr) else
                              '양의 상관' if pr >= 0.3 else
                              '음의 상관' if pr <= -0.3 else '약한 선형 상관')})
        paired_data[(label,a,b)] = pair

result = pd.DataFrame(records)
result.to_csv(OUT/'correlation_results.csv',index=False,encoding='utf-8-sig')

# Pearson 상관계수 히트맵: 측정 방법을 분리하여 표시
pivot = result.pivot(index='체력종목',columns='회차비교',values='Pearson_r')
pivot = pivot.reindex(columns=['1차↔2차','2차↔3차','1차↔3차'])
fig1 = go.Figure(go.Heatmap(z=pivot.values,x=list(pivot.columns),y=list(pivot.index),
                            zmin=-1,zmax=1,zmid=0,colorscale='RdBu',reversescale=True,
                            text=np.where(np.isnan(pivot.values),'표본 부족',np.round(pivot.values,3).astype(str)),
                            texttemplate='%{text}',hovertemplate='%{y}<br>%{x}<br>r=%{z:.3f}<extra></extra>'))
fig1.update_layout(title='체력종목별 회차 간 Pearson 상관계수',height=480)

# 비교별 막대그래프
fig2 = px.bar(result,x='체력종목',y='Pearson_r',color='회차비교',barmode='group',
              hover_data=['표본수','Pearson_p'],title='체력종목별 회차 간 상관계수 비교',
              labels={'Pearson_r':'Pearson r'})
fig2.update_layout(yaxis_range=[-1,1],height=480)

# 표본수 비교 (측정 방식에 따라 표본수가 달라짐)
fig3 = px.bar(result,x='체력종목',y='표본수',color='회차비교',barmode='group',
              title='체력종목별 상관분석에 사용된 장병 수')
fig3.update_layout(height=430)

# 개별 회차 쌍의 산점도는 저장하지 않고 요약 히트맵과 막대그래프에 집중
from plotly.io import to_html
html = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>장병 체력 회차별 상관분석</title>
<style>body{font-family:Arial,'Malgun Gothic',sans-serif;max-width:1250px;margin:32px auto;padding:0 18px;background:#f5f7f9;color:#17212b}h1{margin-bottom:8px}.note{color:#52606d}.panel{background:white;border-radius:12px;padding:14px;margin:20px 0;box-shadow:0 1px 8px #ddd}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}th{background:#edf1f4}</style></head><body>
<h1>장병 체력측정 1·2·3차 상관분석</h1><p class="note">동일 장병의 회차 간 체력측정 원점수 비교. Pearson·Spearman, p값 및 분석 표본 수 확인.</p>
'''
for fig in (fig1,fig2,fig3):
    html += '<div class="panel">'+to_html(fig,full_html=False,include_plotlyjs='cdn')+'</div>'
html += '<div class="panel"><h2>상관분석 결과표</h2>'+result.round(4).fillna('—').to_html(index=False,escape=True)+'</div>'
html += '<p class="note">주의: 상관관계는 체력 개선 또는 운동처방의 인과적 효과를 의미하지 않습니다. 측정 회차가 실제 시간순인지 확인하세요. 심폐지구력은 동일 측정 방식끼리 비교했습니다.</p></body></html>'
(OUT/'correlation_dashboard.html').write_text(html,encoding='utf-8')
print(f'분석 대상: 3회 기록 보유 장병 {len(ids):,}명')
print(result[['체력종목','회차비교','표본수','Pearson_r','Pearson_p','Spearman_rho','Spearman_p']].to_string(index=False))
print(f'\n결과 저장: {OUT}')
