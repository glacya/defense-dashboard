"""실행: python data/experiments/시각화이미지/시각화이미지_생성.py"""
from pathlib import Path
import os,sys,importlib
ROOT=Path(__file__).resolve().parents[3]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from scipy.stats import t
EXP=ROOT/'data/experiments'; OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(EXP))
font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':12,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','axes.titlesize':17,'figure.facecolor':'white','savefig.facecolor':'white'})
BLUE='#2563eb';ORANGE='#e87935';GREEN='#169b83';GRAY='#94a3b8'
files=[]
def mod(name):return importlib.import_module(name)
def finish(fig,name,title,note):
 fig.suptitle(title,fontsize=20,fontweight='bold',x=.06,ha='left',y=.97)
 fig.text(.06,.035,note,fontsize=10,color='#475569',va='bottom')
 fig.subplots_adjust(left=.09,right=.96,top=.82,bottom=.20,wspace=.3,hspace=.5)
 fig.savefig(OUT/name,dpi=180)
 plt.close(fig);files.append((name,title,note))
def bars_labels(ax,bars,fmt='{:.1f}',offset=0):
 ax.bar_label(bars,fmt=fmt,padding=4,fontsize=11)
# 4: actual mean and CI, using shared fixed BMI groups.
ar,tables,bounds,data,_=mod('아노바_bmi').calculate()
fig,axs=plt.subplots(1,2,figsize=(13.33,7.5))
for ax,key,label in zip(axs,['STRENGTH','CARDIO'],['상대악력(%)','심폐지구력(mL/kg/min)']):
 tab=tables[key];n=tab['유효 인원'];ci=t.ppf(.975,n-1)*tab['표준편차']/np.sqrt(n)
 ax.errorbar(range(3),tab['평균'],yerr=ci,fmt='o',color=BLUE,capsize=7,markersize=9)
 ax.set_xticks(range(3),[f'{g}\n(n={int(v):,})' for g,v in zip(tab.index,n)])
 ax.set_ylabel(label);ax.grid(axis='y',alpha=.15)
 for i,y in enumerate(tab['평균']):ax.annotate(f'{y:.2f}',(i,y),xytext=(12,0),textcoords='offset points')
 ax.margins(x=.3,y=.25)
finish(fig,'04_BMI별_체력평균.png','BMI 그룹별 근력·심폐 평균 차이','점: 평균 / 오차막대: 평균의 95% 신뢰구간. BMI 낮음 <18.5, 보통 18.5–25 미만, 높음 ≥25. 인과효과 아님.')
# 6: chi rates.
cr,ct,*_=mod('카이제곱_bmi별미달여부').calculate()
fig,ax=plt.subplots(figsize=(13.33,7.5));x=np.arange(4)
for i,g in enumerate(['낮음','보통','높음']):
 vals=[ct[k].loc[g,'미달률(%)'] for k in ct]
 bars=ax.bar(x+(i-1)*.24,vals,.24,label=g,color=[GRAY,BLUE,ORANGE][i]);bars_labels(ax,bars)
ax.set_xticks(x,list(ct));ax.set_ylim(0,70);ax.set_ylabel('미달률(%)');ax.legend(ncol=3);ax.grid(axis='y',alpha=.15)
finish(fig,'06_BMI별_종목미달률.png','BMI 그룹별 체력 미달률','4종목 모두 전체 검정 Holm 보정 p<0.05. 그룹 쌍별 유의성을 뜻하지 않음. 낮음 75명·보통 2,073명·높음 1,272명.')
# 7 correlation
corr=pd.read_csv(EXP/'results/round_correlations/correlation_results.csv');pivot=corr.pivot(index='체력종목',columns='회차비교',values='Pearson_r')
fig,ax=plt.subplots(figsize=(13.33,7.5));im=ax.imshow(pivot, vmin=0,vmax=1,cmap='Blues',aspect='auto')
ax.set_xticks(range(len(pivot.columns)),pivot.columns);ax.set_yticks(range(len(pivot)),['근지구력','근력','심폐지구력','유연성'] if False else pivot.index)
for i in range(len(pivot)):
 for j in range(len(pivot.columns)):ax.text(j,i,f'{pivot.iloc[i,j]:.3f}',ha='center',va='center',color='white' if pivot.iloc[i,j]>.65 else '#172554',fontsize=16)
fig.colorbar(im,ax=ax,label='Pearson r');fig.subplots_adjust(left=.30)
# Custom shorter labels to avoid clipping.
ax.set_yticklabels([str(v).split('(')[0] for v in pivot.index])
finish(fig,'07_회차별_상관히트맵.png','회차가 달라도 상대적 체력 수준은 유지되는 경향','장병별 1·2·3차 측정값의 상관. 높은 상관이 체력 향상이나 운동 효과를 뜻하지 않음.')
# 8 and 9 from actual current source
sport,changes,detail,_=mod('종목별체력미달자_회차별변화율').analyze()
fig,ax=plt.subplots(figsize=(13.33,7.5))
for (label,g),color in zip(sport.groupby('종목',sort=False),[BLUE,ORANGE,GREEN,'#865cce']):
 ax.plot([1,2,3],g['미달률(%)'],marker='o',linewidth=2.5,label=label,color=color)
 for xx,yy in zip([1,2,3],g['미달률(%)']):
  dy = (14 if label=='심폐지구력' else -8 if label=='근지구력' else -14 if label=='유연성' else 6) if xx==3 else 6
  ax.annotate(f'{yy:.1f}%',(xx,yy),xytext=(6,dy),textcoords='offset points',fontsize=10)
ax.set_xticks([1,2,3],['1차','2차','3차']);ax.set_ylim(0,48);ax.set_ylabel('미달률(%)');ax.legend(ncol=4);ax.grid(alpha=.15)
finish(fig,'08_회차별_미달률추이.png','미달률은 전반적으로 감소했지만 심폐의 감소 폭은 작음','동일 완전측정 대상 3,420명. 1차 대비 3차 변화이며 훈련의 인과효과를 입증하지 않음.')
risk,_,_=mod('위험장병식별').aggregate_risk(detail)
fig,ax=plt.subplots(figsize=(13.33,7.5));bars=ax.bar(risk['회차'],risk['2개 이상 미달'],color=[GRAY,BLUE,ORANGE],width=.55);bars_labels(ax,bars,'{:,.0f}');ax.set_ylim(0,1450);ax.set_ylabel('2개 이상 미달 인원(명)');ax.grid(axis='y',alpha=.15)
finish(fig,'09_여러종목_미달장병.png','2개 이상 미달 인원은 줄었지만 3차에도 826명','동일 대상 3,420명. 위험 기준은 2개 이상 미달이며 기존 취약 기준(1개 이상)과 구분.')
summary=pd.read_csv(EXP/'results/fitness_risk_summary.csv');valid=summary[['weak_1','weak_3']].dropna();counts=[(valid.weak_3<valid.weak_1).sum(),(valid.weak_3==valid.weak_1).sum(),(valid.weak_3>valid.weak_1).sum()]
fig,ax=plt.subplots(figsize=(13.33,7.5));bars=ax.bar(['개선','유지','악화'],counts,color=[GREEN,GRAY,ORANGE],width=.55);bars_labels(ax,bars,'{:,.0f}');ax.set_ylabel('인원(명)');ax.set_ylim(0,max(counts)*1.25)
finish(fig,'10_개인별_상태변화.png','개선자가 더 많지만 529명은 미달 종목 수 증가','1차 대비 3차 미달 종목 수 기준. 유지는 모든 측정값이 같거나 미달 종목이 같다는 뜻이 아님.')
persistent=pd.read_csv(EXP/'results/fitness_persistent_by_area.csv');areas=['근력','근지구력','심폐지구력','유연성'];pc=[persistent[k].astype(str).str.lower().eq('true').sum() for k in areas]
fig,ax=plt.subplots(figsize=(13.33,7.5));bars=ax.bar(areas,pc,color=[BLUE,ORANGE,GREEN,'#865cce']);bars_labels(ax,bars,'{:,.0f}');ax.set_ylabel('인원(명)');ax.set_ylim(0,max(pc)*1.3)
finish(fig,'11_동일종목_지속미달.png','같은 종목에서 세 회차 모두 미달한 장병 1,063명','분모 3,420명, 고유 인원 비율 31.08%. 종목별 인원은 서로 중복되므로 합산하지 않음.')
# 13 mean versus reference.
result,values=mod('t검정_단일표본_심폐기준비교').calculate();r=result.iloc[0]
fig,ax=plt.subplots(figsize=(13.33,7.5));ax.hist(values,bins=30,color=BLUE,alpha=.75);ax.axvline(42,color=ORANGE,linestyle='--',linewidth=2,label='기준값 42');ax.axvline(values.mean(),color=GREEN,linewidth=2,label=f'평균 {values.mean():.2f}');ax.set_xlabel('심폐지구력(mL/kg/min)');ax.set_ylabel('인원(명)');ax.legend()
finish(fig,'12_심폐평균_기준비교.png','심폐 평균은 기준 42보다 높지만 개인별 미달은 존재','평균 44.48, 평균 95% CI [44.32, 44.64]. 기준 42는 비교값이며 알려진 모집단 평균이라는 의미는 아님.')
# 17 five separate scales
nonlinear=mod('BMI_체력항목_비선형성분석');ns,pairs,bins,curves=nonlinear.calculate();fig,axs=plt.subplots(2,3,figsize=(13.33,7.5))
for ax,key in zip(axs.flat,nonlinear.TARGETS):
 pair=pairs[key];tab=bins[key];curve=curves[key];ax.scatter(pair.BMI,pair[key],s=2,alpha=.08,color=GRAY,rasterized=True);ax.plot(tab.BMI평균,tab['평균'].where(tab['평균선표시']),marker='o',markersize=3,color=BLUE,label='구간 평균');ax.plot(curve.BMI,curve.LOWESS,color=ORANGE,label='LOWESS');ax.set_title(nonlinear.METRICS[key],fontsize=11);ax.set_xlabel('BMI');ax.grid(alpha=.12)
axs.flat[-1].axis('off');axs.flat[-1].legend(*axs.flat[0].get_legend_handles_labels(),loc='center',frameon=False)
finish(fig,'15_BMI_항목별_관계.png','BMI와의 관계는 체력·신체 항목마다 다름','첫 측정 3,420명. 구간 폭 1, 평균선 최소 20명, LOWESS 비율 0.4. 곡선은 비선형성의 검정 결과가 아님.')
z=mod('bmi_체력항목_zcore_그래프');zs,params,zt=z.calculate();fig,ax=plt.subplots(figsize=(13.33,7.5));ax.plot(zt['구간중앙'],zt['평균'].where(zt['선표시']),marker='o',color=BLUE,linewidth=2.5);ax.axhline(0,color=GRAY,linestyle='--');ax.axvline(25,color=ORANGE,linestyle=':',label='BMI 25');ax.set_xlabel('BMI 구간 중앙값');ax.set_ylabel('체력 4종목 Z-score 평균');ax.legend();ax.grid(alpha=.12)
finish(fig,'추가_BMI_체력종합점수.png','BMI가 높아질수록 체력종합점수가 낮아지는 추세','동일 가중치 4종목 Z-score 평균. 0은 표본 평균이며 공식 통과 기준이 아님. 개인별 상관 유의성은 별도 검정 필요.')
# Representative images for the remaining descriptive and weak-effect analyses.
people,age_stats,_=mod('분석_연령별').analyze_age()
bp,bst,_,_=mod('분석_bmi별').analyze_bmi()
FITNESS_KEYS=['STRENGTH','ENDURANCE','CARDIO','FLEXIBILITY']
BODY_KEYS=['HEIGHT','WEIGHT','BMI','BODY_FAT_PERCENTAGE']
LABELS={'STRENGTH':'상대악력(%)','ENDURANCE':'근지구력(회)','CARDIO':'심폐지구력(mL/kg/min)','FLEXIBILITY':'유연성(cm)','HEIGHT':'키(cm)','WEIGHT':'체중(kg)','BMI':'BMI(kg/m²)','BODY_FAT_PERCENTAGE':'체지방률(%)'}
def descriptive_images(stats,group,order,number,prefix):
 for keys,kind in [(FITNESS_KEYS,'체력'),(BODY_KEYS,'신체')]:
  fig,axs=plt.subplots(2,2,figsize=(13.33,7.5))
  for ax,key in zip(axs.flat,keys):
   v=stats.loc[stats['컬럼'].eq(key)].set_index(group).reindex(order)
   x=np.arange(len(order));ax.errorbar(x,v['평균'],yerr=v['표준편차'],fmt='o-',capsize=4,color=BLUE,markersize=5,linewidth=1.6)
   ax.set_xticks(x,[str(g) for g in order]);ax.set_title(LABELS[key],fontsize=12)
   ax.set_ylabel('평균 ± 표준편차');ax.grid(axis='y',alpha=.15);ax.margins(x=.12)
  finish(fig,f'{number}_{prefix}_{kind}측정값.png',f'{prefix} {kind} 측정항목의 평균과 산포','장병별 첫 측정. 점은 평균, 오차막대는 표본 표준편차(95% 신뢰구간 아님). 항목별 세로축·단위가 다름.')
  table_rows=[]
  for g in order:
   v=stats.loc[stats[group].eq(g)].set_index('컬럼')
   n=int(v.iloc[0]['장병 수'])
   table_rows.append([str(g),f'{n:,}']+[f"{v.loc[k,'평균']:.2f} ± {v.loc[k,'표준편차']:.2f}" for k in keys])
  fig,ax=plt.subplots(figsize=(13.33,7.5));ax.axis('off')
  tab=ax.table(cellText=table_rows,colLabels=[group,'인원(명)']+[LABELS[k] for k in keys],cellLoc='center',colLoc='center',bbox=[0,.13,1,.72],colWidths=[.10,.10,.20,.20,.20,.20])
  tab.auto_set_font_size(False);tab.set_fontsize(12)
  for (r,c),cell in tab.get_celld().items():
   cell.set_edgecolor('#d9e2ef')
   if r==0:cell.set_facecolor('#1e3a5f');cell.set_text_props(color='white',weight='bold',fontsize=11)
   else:cell.set_facecolor('#f0f5fc' if r%2 else 'white')
  finish(fig,f'{number}_{prefix}_{kind}기술통계표.png',f'{prefix} {kind} 측정항목 기술통계','값은 평균 ± 표본 표준편차. 인원은 그룹 전체이며 유효 인원·결측 수는 원본 집계 CSV에서 확인. 통계적 차이 검정과 구분.')
 descriptive=stats.copy()
 descriptive.to_csv(OUT/f'{number}_{prefix}_기술통계.csv',index=False,encoding='utf-8-sig')
descriptive_images(age_stats,'연령',list(range(19,25)),'01','연령별')
descriptive_images(bst,'BMI그룹',['낮음','보통','높음'],'02','BMI그룹별')
ra,ta=mod('아노바_연령').calculate()
fig,ax=plt.subplots(figsize=(13.33,7.5));v=ta['FLEXIBILITY'];ci=t.ppf(.975,v['유효 인원']-1)*v['표준편차']/np.sqrt(v['유효 인원']);ax.errorbar(v.index,v['평균'],yerr=ci,fmt='o',color=BLUE,capsize=6);ax.set_xticks(v.index);ax.set_xlabel('연령(세)');ax.set_ylabel('유연성 평균(cm)');ax.grid(alpha=.15)
finish(fig,'03_연령별_유연성평균.png','유연성의 연령별 평균 차이는 작음','평균·95% 신뢰구간. 전체 ANOVA p=0.0293, η²=0.0036. Tukey 사후검정의 유의한 연령 쌍 없음.')
rc,tc=mod('카이제곱_연령별미달여부').calculate()
fig,ax=plt.subplots(figsize=(13.33,7.5));v=tc['유연성'];bars=ax.bar(v.index.astype(str),v['미달률(%)'],color=BLUE);bars_labels(ax,bars);ax.set_xlabel('연령(세)');ax.set_ylabel('유연성 미달률(%)');ax.set_ylim(0,45)
finish(fig,'05_연령별_유연성미달률.png','연령과 유연성 미달의 관련성은 유의하지만 작음','전체 검정 Holm 보정 p=0.0213, V=0.070. 다른 3종목은 유의하지 않음. 각 연령 쌍의 유의성은 미검정.')
rt,*_=mod('t검정_독립표본_BMI별근력비교').calculate();v=rt.iloc[0]
fig,ax=plt.subplots(figsize=(13.33,7.5));diff=v['평균차_낮음-높음(%p)'];ax.errorbar([diff],[0],xerr=[[diff-v['평균차95%CI하한']],[v['평균차95%CI상한']-diff]],fmt='o',capsize=8,color=BLUE,markersize=10);ax.axvline(0,color=GRAY,linestyle='--');ax.set_yticks([0],['낮음 - 높음']);ax.set_xlim(-2,22);ax.set_xlabel('평균 상대악력 차이(%p)');ax.text(diff,.12,f'{diff:.2f}%p',ha='center');ax.set_ylim(-.5,.5)
finish(fig,'13_BMI별_근력평균차.png','BMI 낮음 그룹의 평균 상대악력이 16.37%p 높음','평균차의 95% CI [14.15, 18.60]. 낮음 n=75, 높음 n=1,272. BMI ANOVA와 중복되는 보조 비교.')
fd=mod('체력측정항목_전체분포분석').calculate()[1]
metrics=['STRENGTH','ENDURANCE','CARDIO','FLEXIBILITY','BMI','BODY_FAT_PERCENTAGE'];labels=['상대악력(%)','근지구력(회)','심폐(mL/kg/min)','유연성(cm)','BMI','체지방률(%)'];fig,axs=plt.subplots(2,3,figsize=(13.33,7.5))
for ax,k,label in zip(axs.flat,metrics,labels):ax.hist(fd[k].dropna(),bins=25,color=BLUE,alpha=.8);ax.set_title(label,fontsize=12);ax.set_ylabel('인원')
finish(fig,'14_6개항목_전체분포.png','체력·신체 항목의 분포와 산포는 서로 다름','첫 측정 3,420명, 항목별 결측 0명. 항목마다 단위·가로축이 다르므로 산포 절댓값을 직접 비교하지 않음.')
files.sort(key=lambda x:x[0])
readme='# 분석결과 시각화 이미지\n\n운동처방 2항목을 제외한 심플_분석결과.md의 새 순번 1~15를 파일명에 사용했습니다. 현재 원자료를 활용하는 BMI·회차 분석은 재계산했고, 상관·지속 미달은 저장 결과를 사용했습니다. 1·2번은 인원 구성이 아닌 체력·신체 측정값의 기술통계에 초점을 맞췄습니다.\n\nPNG는 2400×1350(16:9), 한글 글꼴 적용. 통계적으로 유의한 차이뿐 아니라 관리 대상 규모와 탐색적 관계를 포함했습니다.\n\n| 이미지 | 내용 | 해석 범위 |\n|---|---|---|\n'
for name,title,note in files:readme+=f'| [{name}]({name}) | {title} | {note} |\n'
readme+='\n15개 분석을 다루며, 1·2번은 각각 체력·신체 비교 그래프와 기술통계표 4종을 제공합니다. 나머지는 분석별 대표 이미지와 추가 Z-score 종합점수입니다. 3·5번은 차이가 작다는 결과를 보여주기 위한 그림이며, 모든 그림이 개선안 선정 또는 통계적 유의성을 뜻하지 않습니다.\n\n재생성: `python data/experiments/시각화이미지/시각화이미지_생성.py`\n'
(OUT/'README.md').write_text(readme,encoding='utf-8-sig')
# Contact sheet for visual review.
from PIL import Image,ImageOps,ImageDraw
sheet=Image.new('RGB',(960,270*((len(files)+1)//2)), '#e2e8f0')
for i,(name,_,_) in enumerate(files):
 im=Image.open(OUT/name);im.thumbnail((480,270));sheet.paste(im,((i%2)*480,(i//2)*270))
sheet.save(ROOT/'tmp/시각화미리보기.jpg')
print(f'{len(files)}개 PNG 작성 완료')


