"""
장병 1·2·3차 체력측정값 상관분석 (상세 주석 버전)

[분석 목적]
동일 장병이 1차, 2차, 3차에 받은 체력측정 결과를 연결하여,
'이전 회차에서 측정값이 높은 장병이 다음 회차에서도 높은 경향이 있는가?'를 확인한다.

[실행]
프로젝트 최상위 폴더(defense-dashboard)에서:
    pip install pandas numpy scipy plotly
    python data/experiments/analyze_round_correlations_commented.py

[입력]
    data/experiments/results/fitness_risk_by_round.csv
    - 기존 identify_fitness_risk_4_rounds3.py가 생성하는 회차별 상세 파일

[출력]
    data/experiments/results/round_correlations/correlation_results.csv
    data/experiments/results/round_correlations/correlation_dashboard.html

[통계 해석 주의]
- Pearson r: 두 회차의 '선형적' 연관성. -1~+1 사이의 값.
- Spearman rho: 두 회차의 '순위' 사이의 단조 관계. -1~+1 사이의 값.
- p값: 귀무가설(모집단 상관계수=0)하에서 관측된 정도 이상으로
  극단적인 결과가 나올 가능성을 나타내는 값.
- 상관관계가 높아도 체력이 개선되었다는 뜻은 아니다.
- CSV 원본 행 순서로 회차를 매겼다면 실제 측정 시간순인지 먼저 확인해야 한다.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
import plotly.express as px
import plotly.graph_objects as go
from plotly.io import to_html


# ============================================================
# 1. 입력·출력 경로 및 분석 변수 설정
# ============================================================

# __file__: 현재 실행 중인 Python 파일의 위치
# resolve(): 절대경로로 변환
# parents[2]: 파일이 data/experiments/에 있을 때 프로젝트 최상위 폴더
# 예) defense-dashboard/data/experiments/현재파일.py → defense-dashboard/
ROOT = Path(__file__).resolve().parents[2]

# 앞 단계의 체력 위험 분석 프로그램이 저장한 회차별 상세 데이터
INPUT = ROOT / 'data/experiments/results/fitness_risk_by_round.csv'

# 상관분석 결과 파일을 저장할 폴더
OUT = ROOT / 'data/experiments/results/round_correlations'
OUT.mkdir(parents=True, exist_ok=True)  # 이미 존재해도 오류 없이 진행

# 동일 장병을 연결할 식별자와 측정 회차 컬럼명
ID = 'M_CODE'
ROUND = 'round'

# 3회 측정에서 직접 비교할 수 있는 체력종목
# 키: 실제 CSV 컬럼명, 값: 결과표와 그래프에 표시할 이름
MEASURES = {
    'REL_GRIP': '근력(상대악력)',
    'CROSS_UP': '근지구력(교차윗몸일으키기)',
    'SIT_REACH': '유연성(앉아윗몸앞으로굽히기)',
}

# 심폐지구력은 측정 방법별 단위와 의미가 다를 수 있다.
# 따라서 TRAD와 STEP 등의 원점수를 하나로 합치지 않고 각각 분석한다.
CARDIO = {
    'TRAD': '심폐-트레드밀',
    'STEP': '심폐-스텝',
    '20M_RUN': '심폐-왕복오래달리기',
}

# 분석할 회차 쌍: (앞 회차, 뒤 회차)
# (1,2): 초기→중간, (2,3): 중간→최종, (1,3): 초기→최종
PAIRS = [(1, 2), (2, 3), (1, 3)]


# ============================================================
# 2. 입력 파일 읽기 및 데이터 유효성 확인
# ============================================================

# 원본 파일이 없으면 분석을 진행할 수 없으므로 명확한 오류 메시지 제공
if not INPUT.exists():
    raise FileNotFoundError(
        f'입력 파일이 없습니다: {INPUT}\n'
        '먼저 identify_fitness_risk_4_rounds3.py를 실행하세요.'
    )

# M_CODE는 숫자로 변환하지 않는다.
# 예) '000123'을 정수로 읽으면 앞의 0이 사라져 ID가 바뀔 수 있다.
df = pd.read_csv(INPUT, dtype={ID: 'string'})

# *MEASURES, *CARDIO는 딕셔너리의 '키(컬럼명)'를 펼쳐 넣는 문법이다.
# 분석에 꼭 필요한 컬럼들이 실제 CSV에 있는지 검사한다.
required = {ID, ROUND, *MEASURES, *CARDIO}
missing = required - set(df.columns)
if missing:
    raise ValueError(f'입력 CSV에 필요한 컬럼이 없습니다: {sorted(missing)}')

# 회차가 문자열로 읽혔을 수도 있으므로 숫자형으로 변환
# 변환할 수 없는 값은 NaN으로 바뀐다.
df[ROUND] = pd.to_numeric(df[ROUND], errors='coerce')

# 1·2·3차 데이터만 선택하고, 장병 ID가 없는 행은 제외한다.
df = df[df[ROUND].isin([1, 2, 3]) & df[ID].notna()].copy()

# 동일 장병의 동일 회차가 2행 이상이면 pivot()에서 오류가 발생한다.
# 임의로 한 행을 선택하지 않고 원본 전처리 과정부터 확인하도록 한다.
if df.duplicated([ID, ROUND]).any():
    raise ValueError('동일 장병·회차가 중복되었습니다. 데이터 생성 과정을 확인하세요.')

# 장병별로 서로 다른 측정 회차가 몇 개 있는지 센다.
# nunique()는 회차의 '서로 다른 값 개수'를 반환한다.
# 예) A001: 1,2,3 → 3개 / A002: 1,3 → 2개
ids = df.groupby(ID)[ROUND].nunique()

# 세 회차 기록이 모두 있는 장병만 전체 분석 모집단(분석 대상)으로 설정
ids = ids[ids == 3].index

# 해당 장병들의 행만 남긴다.
df = df[df[ID].isin(ids)].copy()
if df.empty:
    raise ValueError('1·2·3차 측정 기록이 모두 있는 장병이 없습니다.')


# ============================================================
# 3. 체력종목별 · 회차 쌍별 상관분석
# ============================================================

# 상관계수, p값, 표본 수 등을 한 줄씩 누적할 리스트
records = []

# 각 종목·회차 쌍의 원본 짝 데이터 저장 (추가 분석 시 재사용 가능)
paired_data = {}

# {**MEASURES, **CARDIO}: 두 딕셔너리를 하나로 합친다.
# 총 6개 측정변수에 대해 같은 분석을 반복한다.
for col, label in {**MEASURES, **CARDIO}.items():

    # [핵심 1] 세로형 데이터를 장병별 가로형 데이터로 변환
    # 변환 전: M_CODE | round | REL_GRIP
    #          A001   |   1   | 40
    #          A001   |   2   | 43
    #          A001   |   3   | 45
    # 변환 후: M_CODE |  1  |  2  |  3
    #          A001   | 40  | 43  | 45
    # index=ID: 장병별 한 행 / columns=ROUND: 회차별 한 열
    # values=col: 지금 분석하는 체력종목의 실제 측정값
    w = df.pivot(index=ID, columns=ROUND, values=col)
    w = w.apply(pd.to_numeric, errors='coerce')

    # 각 체력종목에 대해 세 종류의 회차 비교를 수행한다.
    for a, b in PAIRS:

        # [핵심 2] 비교할 두 회차만 선택
        # 예) a=1, b=2라면 장병별 1차·2차 측정값만 추출
        # inf/-inf는 유효한 체력측정값이 아니므로 NaN으로 바꾼다.
        # dropna(): 두 회차 중 하나라도 측정값이 없으면 그 장병만 제외
        # 원본 df 전체를 삭제하는 것은 아니며 비교 쌍마다 표본 수가 달라질 수 있다.
        pair = (
            w[[a, b]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .copy()
        )

        # [심폐지구력 처리] 동일 측정 방법으로 검사한 장병만 비교
        # TRAD(트레드밀), STEP(스텝), 20M_RUN(왕복오래달리기)는
        # 서로 다른 측정 방식이므로 원점수를 섞어서 상관분석하지 않는다.
        if col in CARDIO:

            # 전처리 결과에 cardio_method가 있으면 해당 컬럼을 활용
            # cardio_method는 각 회차에서 단독으로 선택된 측정 방법을 뜻한다.
            methods = (
                df[[ID, ROUND, 'cardio_method']]
                if 'cardio_method' in df.columns else None
            )

            if methods is not None:
                # 장병별 회차에 따라 어떤 심폐 측정 방법을 사용했는지 정렬
                mw = methods.pivot(index=ID, columns=ROUND, values='cardio_method')

                # 예) col='STEP'이면 1차와 2차 모두 STEP인 장병만 선택
                eligible = mw.index[(mw[a] == col) & (mw[b] == col)]
                pair = pair.loc[pair.index.intersection(eligible)]
            else:
                # cardio_method 컬럼이 없을 때의 대체 검증
                # 선택한 심폐 측정 방법 외에 다른 방법의 값이 동시에
                # 기록되어 있지 않은 장병만 남긴다.
                all_w = {
                    c: df.pivot(index=ID, columns=ROUND, values=c)
                    for c in CARDIO
                }
                for other in CARDIO:
                    if other != col:
                        other_empty = all_w[other].loc[pair.index, [a, b]].isna().all(axis=1)
                        pair = pair.loc[other_empty]

        # 실제 상관분석에 사용되는 장병 수
        # 예) 전체 5,708명이라도 두 회차 모두 STEP을 측정한 장병은 더 적을 수 있다.
        n = len(pair)

        # 계산할 수 없는 경우를 대비해 결과를 결측값(NaN)으로 초기화
        # pr: Pearson 상관계수 / pp: Pearson p값
        # sr: Spearman 상관계수 / sp: Spearman p값
        pr = pp = sr = sp = np.nan

        # [핵심 3] 상관계수 계산 전 조건 검사
        # n>=3: 최소한의 표본 수 확보
        # nunique()>1: 한 회차의 모든 값이 같으면 분산이 0이어서
        #               상관계수의 분모가 0이 되므로 계산 불가
        if n >= 3 and pair[a].nunique() > 1 and pair[b].nunique() > 1:

            # Pearson 상관분석: 실제 측정값의 선형적 관계 계산
            # pearsonr(x, y) → (상관계수 r, 양측 검정 p값)
            # r이 +1에 가까움: 높은 장병이 다른 회차에도 높은 경향
            # r이 -1에 가까움: 높은 장병이 다른 회차에는 낮은 경향
            # r이 0에 가까움: 선형 관계가 약함(비선형 관계 가능성은 남음)
            pr, pp = pearsonr(pair[a], pair[b])

            # Spearman 상관분석: 두 회차 값의 순위 관계 계산
            # spearmanr(x, y) → (순위상관계수 rho, 양측 검정 p값)
            # 원점수 대신 순위를 사용하므로 단조 관계를 확인할 수 있다.
            sr, sp = spearmanr(pair[a], pair[b])

        # 상관계수 크기에 따른 '편의상' 해석 문구
        # ±0.3은 절대적인 통계 기준이 아니라 이 코드에서 정한 분류 경계이다.
        # 유의성 판단은 아래 Pearson_p 등 p값과 함께 검토해야 한다.
        if pd.isna(pr):
            interpretation = '계산불가(표본 부족 또는 상수값)'
        elif pr >= 0.3:
            interpretation = '양의 상관'
        elif pr <= -0.3:
            interpretation = '음의 상관'
        else:
            interpretation = '약한 선형 상관'

        # 분석 결과를 딕셔너리 형태로 저장하고 리스트에 추가
        records.append({
            '체력종목': label,
            '변수': col,
            '회차비교': f'{a}차↔{b}차',
            '표본수': n,
            'Pearson_r': pr,
            'Pearson_p': pp,
            'Spearman_rho': sr,
            'Spearman_p': sp,
            '해석': interpretation,
        })

        # 나중에 대응표본 검정 등 추가 분석을 할 때 활용 가능
        paired_data[(label, a, b)] = pair


# ============================================================
# 4. 상관분석 결과 CSV 저장
# ============================================================

# 종목 6개 × 회차 비교 3쌍 = 최대 18행의 결과표
result = pd.DataFrame(records)

# utf-8-sig: Windows Excel에서 한글이 깨질 가능성을 줄임
result.to_csv(
    OUT / 'correlation_results.csv',
    index=False,       # DataFrame의 행 인덱스는 CSV에 쓰지 않음
    encoding='utf-8-sig',
)


# ============================================================
# 5. Pearson 상관계수 히트맵
# ============================================================

# 긴 결과표를 '행=체력종목, 열=회차비교, 값=Pearson r' 형태로 재구성
pivot = result.pivot(
    index='체력종목',
    columns='회차비교',
    values='Pearson_r',
)

# 그래프 열 순서를 분석 목적에 맞게 고정
pivot = pivot.reindex(columns=['1차↔2차', '2차↔3차', '1차↔3차'])

# 히트맵 칸에 표시할 문자열: 소수점 3자리, 결측이면 '표본 부족'
heatmap_text = [
    ['표본 부족' if pd.isna(v) else f'{v:.3f}' for v in row]
    for row in pivot.to_numpy()
]

fig1 = go.Figure(
    go.Heatmap(
        z=pivot.values,                 # 색상에 반영할 실제 상관계수
        x=list(pivot.columns),         # 가로축: 회차 비교
        y=list(pivot.index),           # 세로축: 체력종목
        zmin=-1,                       # 상관계수의 이론적 최솟값
        zmax=1,                        # 상관계수의 이론적 최댓값
        zmid=0,                        # 0을 색상 중심으로 설정
        colorscale='RdBu',             # 빨강-파랑 계열
        reversescale=True,
        text=heatmap_text,             # 각 칸 내부에 숫자 표시
        texttemplate='%{text}',
        hovertemplate='%{y}<br>%{x}<br>r=%{z:.3f}<extra></extra>',
    )
)
fig1.update_layout(title='체력종목별 회차 간 Pearson 상관계수', height=480)


# ============================================================
# 6. 회차 비교별 Pearson 상관계수 막대그래프
# ============================================================

fig2 = px.bar(
    result,
    x='체력종목',                      # 가로축: 체력종목
    y='Pearson_r',                     # 세로축: Pearson 상관계수
    color='회차비교',                   # 회차 쌍별로 막대 구분
    barmode='group',                   # 같은 종목의 3개 막대를 나란히 배치
    hover_data=['표본수', 'Pearson_p'], # 마우스를 올리면 n과 p값 표시
    title='체력종목별 회차 간 상관계수 비교',
    labels={'Pearson_r': 'Pearson r'},
)
fig2.update_layout(yaxis_range=[-1, 1], height=480)


# ============================================================
# 7. 분석 표본 수 막대그래프
# ============================================================

# 근력·근지구력·유연성은 세 회차 모두 측정한 장병이 많을 수 있지만,
# 심폐 측정은 방법별로 표본 수가 달라질 수 있다.
# 따라서 상관계수뿐 아니라 실제 분석 표본 수를 함께 보여준다.
fig3 = px.bar(
    result,
    x='체력종목',
    y='표본수',
    color='회차비교',
    barmode='group',
    title='체력종목별 상관분석에 사용된 장병 수',
)
fig3.update_layout(height=430)


# ============================================================
# 8. HTML 대시보드 생성
# ============================================================

# HTML/CSS로 제목, 설명, 그래프, 결과표를 한 페이지에 배치한다.
html = '''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>장병 체력 회차별 상관분석</title>
<style>
body {font-family:Arial,'Malgun Gothic',sans-serif;max-width:1250px;
      margin:32px auto;padding:0 18px;background:#f5f7f9;color:#17212b}
h1 {margin-bottom:8px}
.note {color:#52606d}
.panel {background:white;border-radius:12px;padding:14px;margin:20px 0;
        box-shadow:0 1px 8px #ddd}
table {border-collapse:collapse;width:100%;font-size:13px}
th,td {padding:8px;border-bottom:1px solid #ddd;text-align:left}
th {background:#edf1f4}
</style>
</head>
<body>
<h1>장병 체력측정 1·2·3차 상관분석</h1>
<p class="note">동일 장병의 회차 간 체력측정 원점수 비교.
Pearson·Spearman, p값 및 분석 표본 수 확인.</p>
'''

# Plotly 그래프 3개를 순서대로 HTML에 삽입
# include_plotlyjs='cdn': 인터넷 연결 시 Plotly 라이브러리를 불러온다.
# 오프라인에서도 열어야 한다면 'cdn'을 True로 변경한다(파일 크기 증가).
for fig in (fig1, fig2, fig3):
    html += (
        '<div class="panel">'
        + to_html(fig, full_html=False, include_plotlyjs='cdn')
        + '</div>'
    )

# 소수점 4자리로 표시한 결과표를 HTML 표로 추가
# fillna('—'): 상관계수를 계산할 수 없는 경우 빈 값 대신 — 표시
html += (
    '<div class="panel"><h2>상관분석 결과표</h2>'
    + result.round(4).fillna('—').to_html(index=False, escape=True)
    + '</div>'
)

# 분석 결과 해석 시 주의사항을 페이지 하단에 명시
html += '''
<p class="note">주의: 상관관계는 체력 개선 또는 운동처방의 인과적 효과를
의미하지 않습니다. 측정 회차가 실제 시간순인지 확인하세요.
심폐지구력은 동일 측정 방식끼리 비교했습니다.</p>
</body></html>
'''

# 완성된 HTML을 UTF-8 인코딩으로 저장
(OUT / 'correlation_dashboard.html').write_text(html, encoding='utf-8')


# ============================================================
# 9. 실행 결과 콘솔 출력
# ============================================================

print(f'분석 대상: 3회 기록 보유 장병 {len(ids):,}명')
print(result[[
    '체력종목', '회차비교', '표본수',
    'Pearson_r', 'Pearson_p', 'Spearman_rho', 'Spearman_p',
]].to_string(index=False))
print(f'\n결과 저장: {OUT}')
