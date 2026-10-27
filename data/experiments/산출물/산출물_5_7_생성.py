"""기존 실험의 계산을 사용해 5~7번 산출물을 생성합니다.

실행: python data/experiments/산출물/산출물_5_7_생성.py
기존 분석 파일·results는 변경하지 않습니다.
"""

import ast
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go

EXPERIMENTS = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENTS.parents[1]))
sys.path.insert(0, str(EXPERIMENTS))


def save(frame, folder, name):
    """정밀도를 유지한 UTF-8 BOM CSV를 저장합니다."""
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f'{name}.csv', index=False, encoding='utf-8-sig')


def export_chi(module_name, folder):
    """기존 calculate 함수의 검정 결과·교차표·기대빈도를 저장합니다."""
    module = importlib.import_module(module_name)
    calculated = module.calculate()
    results, tables = calculated[:2]
    save(results, folder, '카이제곱_검정결과')
    rows = []
    for event, table in tables.items():
        part = table.copy()
        observed = table[['미달 인원', '충족 인원']]
        total = observed.to_numpy().sum()
        if total > 0:
            expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
            part['기대 미달 인원'] = expected[:, 0]
            part['기대 충족 인원'] = expected[:, 1]
        else:
            part['기대 미달 인원'] = np.nan
            part['기대 충족 인원'] = np.nan
        part = part.reset_index()
        part.insert(0, '종목', event)
        rows.append(part)
    save(pd.concat(rows, ignore_index=True), folder, '종목별_관측기대빈도_미달률')
    interpretation = results.copy()
    interpretation['결론'] = interpretation['Holm 보정 p값'].map(
        lambda p: '검정 불가' if pd.isna(p) else '관련성 근거 있음' if p < .05 else '관련성 근거 충분하지 않음')
    save(interpretation, folder, '검정결과_해석')
    if len(calculated) > 2:
        save(calculated[2], folder, 'BMI_구간별인원')
    assert len(results) == 4
    valid = results['p값'].notna()
    assert results.loc[valid, 'Holm 보정 p값'].ge(results.loc[valid, 'p값'] - 1e-14).all()
    return int(results['Holm 보정 p값'].lt(.05).sum())


def export_correlations(folder):
    """최상위 실행형 기존 상관분석의 출력 경로만 바꿔 원 계산을 실행합니다."""
    source_path = EXPERIMENTS / '체력측정회차별상관분석.py'
    tree = ast.parse(source_path.read_text(encoding='utf-8-sig'), filename=str(source_path))
    changed = 0
    # 기존 파일을 수정하지 않고 OUT 대입문만 메모리에서 교체합니다.
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'OUT' for target in node.targets):
            node.value = ast.parse(f'Path({str(folder)!r})', mode='eval').body
            changed += 1
    assert changed == 1
    ast.fix_missing_locations(tree)
    scope = {'__file__': str(source_path), '__name__': 'exported_round_correlations'}
    exec(compile(tree, str(source_path), 'exec'), scope)
    result = scope['result']
    assert len(result) == 12
    assert not result.duplicated(['변수', '회차비교']).any()
    for column in ['Pearson_r', 'Spearman_rho']:
        assert result[column].dropna().between(-1, 1).all()
        matrix = result.pivot(index='체력종목', columns='회차비교', values=column)
        matrix = matrix.reindex(columns=['1차↔2차', '2차↔3차', '1차↔3차'])
        save(matrix.reset_index(), folder, f'{column}_히트맵데이터')
        fig = go.Figure(go.Heatmap(z=matrix.values, x=matrix.columns.tolist(), y=matrix.index.tolist(),
            zmin=-1, zmax=1, zmid=0, colorscale='RdBu', reversescale=True,
            text=np.round(matrix.values, 3), texttemplate='%{text}',
            hovertemplate='%{y}<br>%{x}<br>상관계수=%{z:.3f}<extra></extra>'))
        fig.update_layout(title=f'회차별 체력 상관계수 · {column}', height=500)
        # 외부 인터넷 없이 열리는 독립 HTML입니다.
        fig.write_html(folder / f'{column}_히트맵.html', include_plotlyjs=True)
    # 원 스크립트의 종합 HTML도 오프라인에서 열리도록 저장합니다.
    html = scope['html'].replace('https://cdn.plot.ly/', 'https://cdn.plot.ly/')
    from plotly.offline import get_plotlyjs
    import re
    html = re.sub(r'<script src="https://cdn\.plot\.ly/[^\"]+"[^>]*></script>',
                  lambda match: '<script>' + get_plotlyjs() + '</script>', html, count=1)
    (folder / 'correlation_dashboard.html').write_text(html, encoding='utf-8')
    return {'입력파일': str(scope['INPUT']), '장병수': len(scope['ids']), '입력행수': len(scope['df']),
            '첫측정연령분포': scope['df'].loc[scope['df']['round'].eq(1), 'AGE'].value_counts().sort_index().to_dict()}


def main():
    """연령·BMI 미달 관련성과 회차별 상관분석 산출물을 생성합니다."""
    folder5 = OUTPUT / '05_연령별_카이제곱'
    folder6 = OUTPUT / '06_BMI그룹별_카이제곱'
    folder7 = OUTPUT / '07_회차별_상관분석'
    significant_age = export_chi('카이제곱_연령별미달여부', folder5)
    significant_bmi = export_chi('카이제곱_bmi별미달여부', folder6)
    correlation = export_correlations(folder7)
    metadata = {'생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        '5번': '장병별 첫 측정 당시 19~24세, 연령×종목별 미달 여부; 기존 calculate 함수 사용',
        '6번': '기존 실험과 동일한 고정 BMI 3구간: 0<BMI<18.5 낮음, 18.5≤BMI<25 보통, BMI≥25 높음. 이미지의 삼분위와 다름',
        '카이제곱': '미달은 3등급 하한 미만; 결측 판정 제외; 종목 4개에 Holm 보정; Cramer V 및 기대빈도 진단 포함',
        '연령유의종목수': significant_age, 'BMI유의종목수': significant_bmi,
        '7번': correlation,
        '상관기준': '기존 fitness_risk_by_round.csv를 그대로 사용; 3회 기록 보유자; 쌍별 결측·무한값 제외; Pearson와 Spearman; p값 다중비교 보정 없음',
        '유의사항': '7번 기존 입력의 표본은 5·6번 첫측정 표본과 다를 수 있음. 상관은 개선 또는 인과효과가 아님. 기존 results의 갱신 시점을 확인해야 함'}
    (OUTPUT / '생성기준_5_7.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2, default=int), encoding='utf-8')
    text = ['# 5~7번 분석 산출물', '',
        '| 번호 | 산출물 | 기존 분석 코드 |', '|---|---|---|',
        '| 5 | [연령별 카이제곱 결과](05_연령별_카이제곱/카이제곱_검정결과.csv) | 카이제곱_연령별미달여부.py |',
        '| 6 | [BMI 그룹별 카이제곱 결과](06_BMI그룹별_카이제곱/카이제곱_검정결과.csv) | 카이제곱_bmi별미달여부.py |',
        '| 7 | [회차별 상관계수](07_회차별_상관분석/correlation_results.csv) | 체력측정회차별상관분석.py |', '',
        '## 기준 확인', '',
        '- 5·6번은 기존 계산 함수를 사용하며, Holm 보정 p값과 Cramér’s V, 기대빈도 진단을 포함합니다.',
        '- 이미지의 BMI 삼분위 대신 현재 실험의 고정 구간(<18.5 / 18.5~25 미만 / ≥25)을 사용했습니다. 삼분위 결과로 표기하지 마세요.',
        f'- 7번은 기존 results/fitness_risk_by_round.csv의 세 회차 보유자 {correlation["장병수"]:,}명을 사용했습니다. 첫 측정 연령 분포는 생성기준_5_7.json에 기록했습니다.',
        '- 7번은 앞선 첫 측정 19~24세 표본과 동일하다고 가정하지 않습니다. 원본 실험의 표본과 계산을 보존했습니다.',
        '- 상관 히트맵은 Pearson와 Spearman 각각 CSV·HTML로 제공합니다. HTML은 인터넷 없이 열 수 있습니다.',
        '- 기존 분석 코드와 기존 results 파일은 수정하지 않습니다. 출력 폴더만 변경해 실행했습니다.', '',
        '## 재생성', '', '```powershell', 'python data/experiments/산출물/산출물_5_7_생성.py', '```', '']
    (OUTPUT / 'README_5_7.md').write_text('\n'.join(text), encoding='utf-8')
    print(json.dumps({'연령유의종목': significant_age, 'BMI유의종목': significant_bmi,
                      '상관표본': correlation['장병수']}, ensure_ascii=True))


if __name__ == '__main__':
    main()

