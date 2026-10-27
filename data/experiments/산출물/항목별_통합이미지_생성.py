"""기존 CSV를 유지하고 각 분석 폴더에 통합 PNG를 추가합니다."""

import hashlib
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 10})
BLUE, ORANGE = '#2563eb', '#ea580c'


def read(folder, name):
    return pd.read_csv(folder / name)


def finish(fig, folder, title, note):
    """한 분석의 여러 패널을 한 이미지로 저장합니다."""
    fig.suptitle(title, fontsize=20, fontweight='bold')
    fig.supxlabel(note, fontsize=10)
    for ax in fig.axes:
        if ax.axison:
            ax.grid(axis='y', alpha=.15)
    path = folder / '분석결과_통합시각화.png'
    fig.savefig(path, dpi=170, facecolor='white')
    plt.close(fig)
    return path


def main():
    """기존 산출물의 해시를 확인하며 통합 이미지 10개를 생성합니다."""
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*')
              if p.is_file() and p.name != '분석결과_통합시각화.png'}
    created = []
    for number, stem, group, prefix in [(1,'01_연령별_기술통계','연령','연령별'), (2,'02_BMI그룹별_기술통계','BMI그룹','BMI그룹별')]:
        folder=ROOT/stem
        stats=read(folder,f'{prefix}_기술통계.csv')
        people=read(folder,f'{prefix}_인원구성비.csv')
        fig, axes=plt.subplots(4,2,figsize=(15,16),layout='constrained')
        ax=axes.flat[0]
        bars=ax.bar(people[group].astype(str),people['장병 수'],color=BLUE)
        ax.bar_label(bars,padding=3)
        ax.set(title='집단별 인원',ylabel='장병 수 (명)')
        axes.flat[1].axis('off')
        axes.flat[1].text(.05,.85,'오차막대: 평균 ± 표본 표준편차(SD)\n평균의 신뢰구간이 아닙니다.\n항목별 유효 인원으로 계산합니다.\n집단 간 비교이며 개인의 변화가 아닙니다.',va='top',linespacing=2,fontsize=12)
        for ax,(metric,rows) in zip(list(axes.flat)[2:],stats.groupby('항목',sort=False)):
            ax.errorbar(rows[group].astype(str),rows['평균'],yerr=rows['표준편차'],fmt='o-',capsize=4,color=BLUE)
            ax.set(title=metric,ylabel='평균 ± SD',xlabel=group)
        created.append(finish(fig,folder,f'{number}. {group}별 체력 기술통계','첫 측정 당시 19~24세 · 결측은 항목별 제외 · 서로 다른 단위는 패널별 확인'))
    for number,stem in [(3,'03_연령별_ANOVA'),(4,'04_BMI그룹별_ANOVA')]:
        folder=ROOT/stem
        results=read(folder,'ANOVA_결과표.csv')
        groups=read(folder,'종목별_집단통계.csv')
        pairs=read(folder,'유의종목_사후검정.csv')
        fig,axes=plt.subplots(3,2,figsize=(16,14),layout='constrained')
        labels={'STRENGTH':'상대악력 (%)','ENDURANCE':'근지구력 (회)','FLEXIBILITY':'유연성 (cm)','CARDIO':'심폐 (mL/kg/min)'}
        for ax,(metric,rows) in zip(axes.flat,groups.groupby('컬럼',sort=False)):
            n=rows['유효 인원']
            error=1.96*rows['표준편차']/np.sqrt(n.replace(0,np.nan))
            ax.errorbar(rows['집단'].astype(str),rows['평균'],yerr=error,fmt='o',capsize=5,color=BLUE)
            ax.set(title=labels.get(metric,metric),ylabel='평균 ± 1.96 SE (근사 95% CI)')
        ax=axes.flat[4]
        bars=ax.barh(results['항목'],results['η²'],color=ORANGE)
        ax.bar_label(bars,fmt='%.3f',padding=3)
        ax.set(title='참고 효과크기',xlabel='η² (일반 ANOVA 제곱합 기반)')
        ax=axes.flat[5]; ax.axis('off')
        lines=['종목별 적용 검정·p값']
        for _,row in results.iterrows():
            lines.append(f'{row["항목"]}\n  {row["적용 검정"]}, p={row["적용 p값"]:.3e}')
        lines += [f'사후검정 쌍 비교: {len(pairs)}건','종목 간 다중검정 보정 미적용','사후검정 상세 CI는 기존 CSV 확인']
        ax.text(.02,.98,'\n'.join(lines),va='top',fontsize=10,linespacing=1.7)
        created.append(finish(fig,folder,f'{number}. 집단별 평균 비교 · ANOVA','그림의 CI는 집단 평균의 근사 구간 · 평균차 검정과 사후검정의 판단은 기존 결과표 기준'))
    for number,stem,group in [(5,'05_연령별_카이제곱','연령'),(6,'06_BMI그룹별_카이제곱','BMI그룹')]:
        folder=ROOT/stem
        result=read(folder,'카이제곱_검정결과.csv')
        counts=read(folder,'종목별_관측기대빈도_미달률.csv')
        fig,axes=plt.subplots(3,2,figsize=(15,13),layout='constrained')
        for ax,(event,rows) in zip(axes.flat,counts.groupby('종목',sort=False)):
            bars=ax.bar(rows[group].astype(str),rows['미달률(%)'],color=BLUE)
            ax.bar_label(bars,fmt='%.1f',padding=3)
            total=rows['평가가능수'].sum()
            if total:
                ax.axhline(rows['미달 인원'].sum()/total*100,color=ORANGE,ls='--',label='종목 전체 미달률')
            ax.set(title=event,ylabel='미달률 (%)',ylim=(0,100)); ax.legend(fontsize=8)
        ax=axes.flat[4]
        ax.barh(result['종목'],result["Cramér's V"],color=ORANGE)
        ax.set(title='관련성 크기',xlabel='Cramér’s V',xlim=(0,1))
        ax=axes.flat[5]; ax.axis('off')
        lines=['Holm 보정 p값 (4종목)']
        for _,row in result.iterrows():
            lines += [f'{row["종목"]}: {row["Holm 보정 p값"]:.3e}',f'  {row["상태"]}']
        ax.text(.03,.95,'\n'.join(lines),va='top',linespacing=1.8,fontsize=11)
        created.append(finish(fig,folder,f'{number}. {group}와 체력 미달 여부','분모: 집단·종목별 판정 가능 인원 · 점선은 독립 가정의 기대 미달률 · 관련성은 인과성이 아님'))
    folder=ROOT/'07_회차별_상관분석'; result=read(folder,'correlation_results.csv')
    fig,axes=plt.subplots(1,2,figsize=(15,6),layout='constrained')
    for ax,column,title in zip(axes,['Pearson_r','Spearman_rho'],['Pearson (선형 관계)','Spearman (순위 관계)']):
        matrix=result.pivot(index='체력종목',columns='회차비교',values=column).reindex(columns=['1차↔2차','2차↔3차','1차↔3차'])
        image=ax.imshow(matrix.values,cmap='RdBu_r',vmin=-1,vmax=1,aspect='auto')
        ax.set_xticks(range(3),labels=matrix.columns)
        ax.set_yticks(range(len(matrix)),labels=['근력','근지구력','유연성','심폐'] if False else [str(x).split('(')[0] for x in matrix.index])
        ax.set_title(title)
        for i in range(len(matrix)):
            for j in range(3):
                value=matrix.iloc[i,j]
                ax.text(j,i,f'{value:.3f}',ha='center',va='center',color='white' if abs(value)>.55 else 'black')
        fig.colorbar(image,ax=ax,shrink=.8,label='상관계수')
    created.append(finish(fig,folder,'7. 회차별 체력 측정값 상관계수',f'쌍별 표본 수 {result["표본수"].min():,}~{result["표본수"].max():,}명 · 상관은 개선 정도 또는 인과효과를 의미하지 않음'))
    folder=ROOT/'12_심폐_단일표본t검정'
    files=['심폐_단일표본t검정_기준44.8.csv','심폐_단일표본t검정_기준42.0_참고.csv']
    fig,axes=plt.subplots(2,1,figsize=(12,8),layout='constrained')
    for ax,file in zip(axes,files):
        r=read(folder,file).iloc[0]; mean=r['표본평균']; lo=r['평균95%CI하한']; hi=r['평균95%CI상한']; ref=r['기준평균']
        ax.errorbar(mean,0,xerr=[[mean-lo],[hi-mean]],fmt='o',capsize=9,color=BLUE)
        ax.axvline(ref,color=ORANGE,ls='--',label=f'기준 {ref:g}')
        ax.set(title=f'{"주 분석" if ref==44.8 else "참고 분석"} · 기준 {ref:g} · 양측 p={r["양측p값"]:.3e}',yticks=[],xlabel='심폐 VO₂max (mL/kg/min)')
        ax.text(mean,.07,f'평균 {mean:.3f}\n95% CI [{lo:.3f}, {hi:.3f}]',ha='center')
        ax.set_ylim(-.25,.4); ax.legend()
    created.append(finish(fig,folder,'12. 심폐 평균과 기준값 비교','오차막대: 평균 95% CI · 44.8은 2등급 하한, 현재 표본의 50백분위라는 뜻은 아님 · 42는 별도 참고'))
    folder=ROOT/'13_BMI별근력_독립표본t검정'
    stats=read(folder,'비교집단_기술통계.csv'); r=read(folder,'BMI낮음높음_근력_t검정.csv').iloc[0]
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    axes[0].errorbar(stats['BMI그룹'],stats['평균'],yerr=stats['표준편차'],fmt='o',capsize=8,color=BLUE)
    axes[0].set(title='집단 평균 ± 표본 SD',ylabel='상대악력 (%)')
    diff=r['평균차_낮음-높음(%p)'];lo=r['평균차95%CI하한'];hi=r['평균차95%CI상한']
    axes[1].errorbar(diff,0,xerr=[[diff-lo],[hi-diff]],fmt='o',capsize=8,color=BLUE)
    axes[1].axvline(0,color=ORANGE,ls='--');axes[1].set(yticks=[],xlabel='평균차 (%p)',title=f'낮음-높음 평균차와 95% CI\n{r["적용검정"]} · p={r["양측p값"]:.3e}')
    axes[1].text(.05,.15,f'차이 {diff:.3f}\n95% CI [{lo:.3f}, {hi:.3f}]',transform=axes[1].transAxes)
    created.append(finish(fig,folder,'13. BMI 낮음·높음 집단의 근력 평균 차이','낮음: BMI<18.5 · 높음: BMI≥25 · 왼쪽 SD는 개인 산포, 오른쪽 CI는 평균차 추정 · 인과결론 아님'))
    folder=ROOT/'14_6개항목_전체분포'
    bins=read(folder,'6개항목_히스토그램빈도.csv');stats=read(folder,'6개항목_기술통계.csv')
    fig,axes=plt.subplots(3,2,figsize=(15,14),layout='constrained')
    for ax,(column,rows) in zip(axes.flat,bins.groupby('컬럼',sort=False)):
        r=stats.loc[stats['컬럼'].eq(column)].iloc[0]
        ax.bar((rows['구간시작']+rows['구간끝'])/2,rows['인원'],width=rows['구간끝']-rows['구간시작'],color=BLUE,alpha=.7)
        ax.axvline(r['평균'],color=ORANGE,label=f'평균 {r["평균"]:.2f}')
        ax.axvline(r['중앙값'],color='#059669',ls='--',label=f'중앙값 {r["중앙값"]:.2f}')
        ax.set(title=f'{r["항목"]} · n={r["유효인원"]:,.0f}',ylabel='인원 (명)',xlabel=r['항목']);ax.legend(fontsize=9)
    created.append(finish(fig,folder,'14. 체력·신체 6개 항목 전체 분포','항목별 30구간 · 항목마다 단위와 축이 다름 · 극단값은 자동 제거하지 않음'))
    for path,digest in before.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest, f'기존 산출물 변경: {path}'
    print(f'Created {len(created)} PNG images; preserved {len(before)} existing files.')
    for path in created:
        print(path.parent.name)


if __name__=='__main__':
    main()

