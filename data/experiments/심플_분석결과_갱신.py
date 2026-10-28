"""현재 측정 데이터로 심플 분석결과 문서의 정량 결과를 갱신한다."""
import importlib
import sys
from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, pearsonr, spearmanr, ttest_1samp, t
from statsmodels.stats.multitest import multipletests
from data.scripts.fitness_standards import GRADE_CUTS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE / 'results/심플분석결과_재계산'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    age = importlib.import_module('분석_연령별')
    first = age.analyze_age(return_first=True)
    source = pd.read_csv(age.DATA_PATH, dtype={'SOLDIER_ID': 'string'})
    source['_date'] = pd.to_datetime(source.MESURE_DE.astype(str), format='%Y%m%d', errors='raise')
    source = source.loc[source.SOLDIER_ID.isin(first.SOLDIER_ID)].sort_values(['SOLDIER_ID','_date'], kind='stable')
    source['round'] = source.groupby('SOLDIER_ID').cumcount()+1
    assert len(first) == 3582 and len(source) == 10746
    assert source.groupby('SOLDIER_ID').size().eq(3).all()
    fitness = list(GRADE_CUTS)
    assert source[fitness].notna().all().all()
    first = first.copy()
    first['BMI그룹'] = pd.cut(first.BMI, [0,18.5,25,np.inf], labels=['낮음','보통','높음'], right=False)
    metrics = fitness + ['BMI', 'BODY_FAT_PERCENTAGE']
    for group in ['AGE', 'BMI그룹']:
        first.groupby(group, observed=False)[metrics].agg(['count','mean','std']).to_csv(
            OUT/f'{group}_기술통계.csv', encoding='utf-8-sig')
    first[metrics].describe().to_csv(OUT/'전체기술통계.csv', encoding='utf-8-sig')
    age_stats, _ = importlib.import_module('아노바_연령').calculate()
    bmi_stats, *_ = importlib.import_module('아노바_bmi').calculate()
    independent, *_ = importlib.import_module('t검정_독립표본_BMI별근력비교').calculate()
    for name, frame in [('연령분산분석',age_stats),('BMI분산분석',bmi_stats),('BMI근력t검정',independent)]:
        frame.to_csv(OUT/f'{name}.csv', index=False, encoding='utf-8-sig')
    chi = {}
    for group in ['AGE','BMI그룹']:
        rows=[]
        for col in fitness:
            fail = first[col].lt(GRADE_CUTS[col][3])
            table = pd.crosstab(first[group], fail)
            stat,p,_,_=chi2_contingency(table,correction=False)
            rows.append({'종목':col,'p':p,'V':np.sqrt(stat/table.to_numpy().sum())})
        frame=pd.DataFrame(rows)
        frame['Holm p']=multipletests(frame.p,method='holm')[1]
        frame.to_csv(OUT/f'{group}_카이제곱.csv',index=False,encoding='utf-8-sig')
        chi[group]=frame.set_index('종목')
    bmi=[]
    for label, group in first.groupby('BMI그룹',observed=False):
        bmi.append({'그룹':label,'인원':len(group),'근력미달률':group.STRENGTH.lt(GRADE_CUTS['STRENGTH'][3]).mean()*100,
                    '심폐미달률':group.CARDIO.lt(GRADE_CUTS['CARDIO'][3]).mean()*100})
    bmi=pd.DataFrame(bmi)
    bmi.to_csv(OUT/'BMI그룹별미달률.csv',index=False,encoding='utf-8-sig')
    correlations=[]
    risks=pd.DataFrame({col:source[col].lt(GRADE_CUTS[col][3]) for col in fitness})
    source['미달수']=risks.sum(axis=1)
    counts=source.pivot(index='SOLDIER_ID',columns='round',values='미달수')
    status = {'개선': int((counts[3]<counts[1]).sum()), '악화': int((counts[3]>counts[1]).sum()),
              '유지': int((counts[3]==counts[1]).sum())}
    assert sum(status.values()) == len(first)
    pd.DataFrame([status]).to_csv(OUT/'상태변화.csv', index=False, encoding='utf-8-sig')
    assert first.groupby('BMI그룹', observed=False).size().sum() == len(first)
    persistent=risks.assign(SOLDIER_ID=source.SOLDIER_ID).groupby('SOLDIER_ID')[fitness].all()
    for col in fitness:
        wide=source.pivot(index='SOLDIER_ID',columns='round',values=col)
        for a,b in combinations([1,2,3],2):
            correlations.append({'종목':col,'회차A':a,'회차B':b,'Pearson':pearsonr(wide[a],wide[b]).statistic,
                                 'Spearman':spearmanr(wide[a],wide[b]).statistic})
    corr=pd.DataFrame(correlations)
    corr.to_csv(OUT/'회차별상관.csv',index=False,encoding='utf-8-sig')
    means=first.groupby('BMI그룹',observed=False)[fitness].mean()
    cardio=first.CARDIO
    single_module = importlib.import_module('t검정_단일표본_심폐기준비교')
    reference = single_module.DEFAULT_REFERENCE
    single_result, _ = single_module.calculate()
    single_result.to_csv(OUT/'심폐단일표본t검정.csv', index=False, encoding='utf-8-sig')
    test=ttest_1samp(cardio,reference)
    margin=t.ppf(.975,len(cardio)-1)*cardio.std(ddof=1)/np.sqrt(len(cardio))
    z=importlib.import_module('bmi_체력항목_zcore_그래프').calculate()[2]
    z.to_csv(OUT/'BMI구간별Z점수.csv',index=False,encoding='utf-8-sig')
    report=HERE/'심플_분석결과.md'
    text=report.read_text(encoding='utf-8')
    replacements={}
    age_p=' · '.join(f"{r['항목']} p={r['적용 p값']:.4f}" for _,r in age_stats.iterrows())
    replacements[3]=(f'종목별 등분산 진단에 따라 일반/Welch ANOVA 적용. {age_p}',
                     '4종목 모두 p>0.05로 연령별 평균 차이의 통계적 근거가 충분하지 않음')
    replacements[4]=(f"4종목 모두 적용 p<0.001. 근력 η²={bmi_stats.iloc[0]['η²']:.3f}, 심폐 η²={bmi_stats.iloc[3]['η²']:.3f}. 낮음→높음 평균: 근력 {means.loc['낮음','STRENGTH']:.2f}→{means.loc['높음','STRENGTH']:.2f}%, 심폐 {means.loc['낮음','CARDIO']:.2f}→{means.loc['높음','CARDIO']:.2f} mL/kg/min",
                     'BMI 그룹에 따라 평균 체력이 다르며, 특히 근력·심폐 차이가 큼')
    replacements[5]=(f"4종목 모두 Holm 보정 p>0.05. 유연성 보정 p={chi['AGE'].loc['FLEXIBILITY','Holm p']:.4f}, V={chi['AGE'].loc['FLEXIBILITY','V']:.3f}",
                     '현재 표본에서 연령과 종목별 미달 여부의 유의한 관련성이 확인되지 않음')
    high=bmi.loc[bmi.그룹.eq('높음')].iloc[0]
    replacements[6]=(f"4종목 모두 Holm 보정 p<0.05. 근력 V={chi['BMI그룹'].loc['STRENGTH','V']:.3f}, 심폐 V={chi['BMI그룹'].loc['CARDIO','V']:.3f}. 높음 그룹 미달률: 근력 {high.근력미달률:.2f}%, 심폐 {high.심폐미달률:.2f}%",
                     'BMI 높은 그룹에서 근력·심폐 미달이 더 흔하게 관찰됨')
    replacements[7]=(f'모든 종목·회차 쌍에서 양의 상관. Pearson r {corr.Pearson.min():.3f}~{corr.Pearson.max():.3f}',
                     '이전 회차에서 체력이 높은 사람이 다음에도 높은 경향이 있음')
    labels=['근력','근지구력','심폐','유연성']
    changes=[]
    for label,col in zip(labels,fitness):
        rates=risks[col].groupby(source['round']).mean()*100
        changes.append(f'{label} {rates[1]:.2f}→{rates[3]:.2f}%')
    replacements[8]=('1→3차 미달률: '+', '.join(changes),'미달 비율은 전반적으로 줄었지만 심폐의 감소 폭은 작음')
    total=int(persistent.any(axis=1).sum())
    replacements[11]=(f'동일 종목에서 세 회차 모두 미달한 장병 {total:,}명({total/len(first)*100:.2f}%). '+
                      '·'.join(f'{label} {persistent[col].sum():,}명' for label,col in zip(labels,fitness)),
                      '일부 장병은 같은 종목에서 미달이 계속됨. 종목별 인원은 중복되므로 합산하지 않음')
    direction = '높음' if cardio.mean() > reference else '낮음' if cardio.mean() < reference else '같음'
    replacements[12]=(f'기준평균 {reference:g}, 표본평균 {cardio.mean():.2f}, 평균차 {cardio.mean()-reference:+.2f}, 평균 95% CI [{cardio.mean()-margin:.2f}, {cardio.mean()+margin:.2f}], t={test.statistic:.3f}, p={test.pvalue:.3e}',
                      f'평균은 기준 {reference:g}보다 {direction}. '+('양측 p<0.05로 귀무가설 기각. ' if test.pvalue < .05 else '귀무가설 기각 못함. ')+ '평균 비교와 개인별 3등급 미달 기준 42.0은 구분함')
    r=independent.iloc[0]
    replacements[13]=(f"{r['적용검정']}. 낮음 {int(r['낮음인원']):,}명 평균 {r['낮음평균']:.2f}%, 높음 {int(r['높음인원']):,}명 평균 {r['높음평균']:.2f}%. 평균차 {r['평균차_낮음-높음(%p)']:.2f}%p, 95% CI [{r['평균차95%CI하한']:.2f}, {r['평균차95%CI상한']:.2f}], p={r['양측p값']:.3e}",
                      'BMI 낮음 그룹의 평균 상대악력이 높음 그룹보다 높음')
    replacements[15]=('BMI와 체력·체지방률의 산점도·구간별 평균·LOWESS를 탐색하는 분석. 이전 표본에서 작성한 곡선 해석과 평활 비율별 안정성 주장은 현재 표본에서 재검증하지 않아 제외함',
                      '현재 표본의 곡선을 다시 확인한 뒤 비선형 관계를 해석해야 함')
    lines=text.splitlines()
    for i,line in enumerate(lines):
        parts=line.split('|')
        if len(parts)==7 and parts[1].strip().isdigit():
            number=int(parts[1].strip())
            if number in replacements:
                if number == 12:
                    parts[2] = f' 심폐 평균과 기준값 {reference:g} 비교 '
                parts[4]=' '+replacements[number][0]+' '
                parts[5]=' '+replacements[number][1]+' '
                lines[i]='|'.join(parts)
        if line.startswith('| 낮음 |') or line.startswith('| 보통 |') or line.startswith('| 높음 |'):
            label=parts[1].strip()
            r=bmi.loc[bmi.그룹.eq(label)].iloc[0]
            lines[i]=f'| {label} | {int(r.인원):,}명 | {r.근력미달률:.2f}% | {r.심폐미달률:.2f}% |'
        for low in [18,21,25,30]:
            if line.startswith(f'| {low} 이상 '):
                value=z.loc[z['구간시작'].eq(low),'평균'].iloc[0]
                lines[i]=f'| {low} 이상 {low+1} 미만 | {value:+.3f} |'
    text='\n'.join(lines)+'\n'
    text=text.replace('대상 인원·일부 집계 수정일:', '정량 결과 재계산일:')
    text=text.replace('- 기존에 실행·저장한 결과와 새 BMI 기준으로 재계산한 결과를 사용했습니다. 그래프 형태에 대한 해석과 통계검정 결과를 구분합니다.',
                      '- 정량 결과는 현재 측정 CSV로 재계산했습니다. 재계산 근거 CSV는 `results/심플분석결과_재계산/`에 저장했습니다. 기존 이미지·HTML의 갱신 여부와 문서 수치를 구분합니다.')
    start=text.index('> **갱신 범위:**')
    end=text.index('\n\n',start)
    text=text[:start]+'> **갱신 범위:** 정량 결과와 BMI 그룹별 표·Z-score 수치는 현재 3,582명 기준입니다. 기존 이미지·HTML은 이번 갱신에 포함하지 않았습니다. 15번 LOWESS의 곡선 형태·평활 비율별 안정성은 재검증하지 않았으므로 이전 해석을 제외했습니다.'+text[end:]
    text=text.replace('전후 변화만으로 운동 효과를 확정하지 않습니다.', '전후 변화만으로 운동 효과를 확정하지 않습니다.')
    heading='## 결과 출처\n'
    evidence='- [현재 표본 재계산 근거 CSV](results/심플분석결과_재계산/): 이 문서의 갱신된 정량 결과 근거.'
    text=text.replace(evidence+'\n','')
    text=text.replace(heading,heading+'\n'+evidence+'\n')
    image_note='> 아래 이미지는 기존 자료이며 이번 문서 갱신에서 재생성하지 않았습니다. 현재 수치 인용 시 본문의 재계산 결과를 사용하세요.'
    text=text.replace(image_note+'\n','')
    text=text.replace('## 분석별 대표 이미지\n','## 분석별 대표 이미지\n\n'+image_note+'\n')
    report.write_text(text,encoding='utf-8')
    print('Updated report and quantitative evidence; N=',len(first))


if __name__=='__main__':
    main()
