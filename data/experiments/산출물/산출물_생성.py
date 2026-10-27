"""기존 실험 함수로 이미지의 기술통계·ANOVA 산출물 4종을 생성합니다.

실행: python data/experiments/산출물/산출물_생성.py
기존 실험 파일과 기존 results 폴더는 변경하지 않습니다.
"""

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

EXPERIMENTS = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent
# 기존 실험들은 같은 폴더의 한글 모듈을 직접 import합니다.
sys.path.insert(0, str(EXPERIMENTS))


def save(frame, directory, name):
    """기존 결과의 숫자 정밀도를 유지해 Excel 호환 CSV로 저장합니다."""
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / f'{name}.csv', index=False, encoding='utf-8-sig')


def export_anova(module, results, tables, directory, data=None):
    """기존 ANOVA 결과와 유의한 종목의 기존 사후검정 결과를 저장합니다."""
    save(results, directory, 'ANOVA_결과표')
    summaries = []
    for metric, table in tables.items():
        part = table.rename_axis('집단').reset_index()
        part.insert(0, '컬럼', metric)
        summaries.append(part)
    save(pd.concat(summaries, ignore_index=True), directory, '종목별_집단통계')
    pairs = []
    for _, row in results.loc[results['적용 p값'].lt(.05)].iterrows():
        metric = next(key for key in module.EXERCISES if module.METRICS[key] == row['항목'])
        method = row['사후검정 방법']
        table = module.posthoc(metric, method) if data is None else module.posthoc(data, metric, method)
        table.insert(0, '항목', row['항목'])
        pairs.append(table)
    # 유의 종목이 없어도 상태를 알 수 있는 파일을 생성합니다.
    followup = pd.concat(pairs, ignore_index=True) if pairs else pd.DataFrame(columns=['항목', '사후검정', '보정 p값', '판정'])
    save(followup, directory, '유의종목_사후검정')
    if hasattr(module, 'interpret_results'):
        save(module.interpret_results(results), directory, '검정결과_해석')
    return len(followup)


def main():
    """기존 네 분석을 실행하고 결과와 생성 기준을 기록합니다."""
    age = importlib.import_module('분석_연령별')
    bmi = importlib.import_module('분석_bmi별')
    age_anova = importlib.import_module('아노바_연령')
    bmi_anova = importlib.import_module('아노바_bmi')
    age_people, age_stats, source_rows = age.analyze_age()
    bmi_people, bmi_stats, bmi_data, bmi_excluded = bmi.analyze_bmi()
    age_results, age_tables = age_anova.calculate()
    bmi_results, bmi_tables, boundaries, bmi_test_data, excluded = bmi_anova.calculate()
    folders = ['01_연령별_기술통계', '02_BMI그룹별_기술통계', '03_연령별_ANOVA', '04_BMI그룹별_ANOVA']
    save(age_people, OUTPUT / folders[0], '연령별_인원구성비')
    save(age_stats, OUTPUT / folders[0], '연령별_기술통계')
    save(bmi_people, OUTPUT / folders[1], 'BMI그룹별_인원구성비')
    save(bmi_stats, OUTPUT / folders[1], 'BMI그룹별_기술통계')
    age_pairs = export_anova(age_anova, age_results, age_tables, OUTPUT / folders[2])
    bmi_pairs = export_anova(bmi_anova, bmi_results, bmi_tables, OUTPUT / folders[3], bmi_test_data)
    save(boundaries, OUTPUT / folders[3], 'BMI_구간별인원')
    assert age_people['장병 수'].sum() == age_stats.groupby('연령')['장병 수'].first().sum()
    assert bmi_people['장병 수'].sum() == len(bmi_data)
    assert len(age_results) == len(bmi_results) == 4
    assert bmi_excluded == excluded
    metadata = {
        '생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        '입력파일': str(age.DATA_PATH), '원본측정건수': source_rows,
        '연령분석인원': int(age_people['장병 수'].sum()), 'BMI분석인원': len(bmi_data),
        'BMI제외인원': bmi_excluded, '연령사후비교건수': age_pairs, 'BMI사후비교건수': bmi_pairs,
        '표본': '전체 기록 중 장병별 날짜순 첫 측정을 선택하고 당시 19~24세만 포함; 같은 날짜는 원본 행 순서',
        'BMI구간': '0<BMI<18.5 낮음; 18.5≤BMI<25 보통; BMI≥25 높음. 보통은 정상·비만전단계 포함',
        '기술통계항목': list(age.METRICS), 'ANOVA종목': age_anova.EXERCISES,
        '표준편차': '표본 표준편차 ddof=1, 항목별 결측 제외',
        '검정': '기존 calculate 함수 사용: Levene(중앙값) p<0.05이면 Welch, 그 외 일반 ANOVA',
        '사후검정': '적용 p<0.05 종목만: Welch→Games–Howell, 일반→Tukey HSD; 종목 내 쌍 비교 보정',
        '다중검정': '기존 분석과 동일하게 ANOVA 종목 간 Holm 보정 미적용',
        '효과크기': 'η²는 일반 ANOVA 제곱합 기반 참고값; Welch 적용 여부와 구분',
        '사용모듈': ['분석_연령별', '분석_bmi별', '아노바_연령', '아노바_bmi', 'statistics_compat'],
    }
    (OUTPUT / '생성기준.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    text = ['# 분석 산출물', '', '기존 실험 계산 함수를 사용해 생성한 결과입니다. 기존 파일과 results는 수정하지 않습니다.', '',
            f'첫 측정 19~24세 {metadata["연령분석인원"]:,}명; BMI 분석 {len(bmi_data):,}명; BMI 제외 {bmi_excluded}명.', '',
            '| 번호 | 산출물 | 사용한 기존 분석 |', '|---|---|---|',
            '| 1 | [연령별 기술통계](01_연령별_기술통계/연령별_기술통계.csv) | 분석_연령별.py |',
            '| 2 | [BMI 그룹별 기술통계](02_BMI그룹별_기술통계/BMI그룹별_기술통계.csv) | 분석_bmi별.py |',
            '| 3 | [연령별 ANOVA](03_연령별_ANOVA/ANOVA_결과표.csv) | 아노바_연령.py |',
            '| 4 | [BMI 그룹별 ANOVA](04_BMI그룹별_ANOVA/ANOVA_결과표.csv) | 아노바_bmi.py |', '',
            '각 폴더에 인원·집단통계와, 해당되는 경우 유의 종목의 사후검정을 함께 저장합니다.', '',
            '## 재생성', '', '프로젝트 루트에서:', '', '```powershell',
            'python data/experiments/산출물/산출물_생성.py', '```', '',
            '이 명령은 이 폴더의 동명 산출물을 갱신합니다. 표본·구간·검정 선택과 효과크기 기준은 생성기준.json을 확인하세요.', '',
            '기술통계는 체력 4종목과 BMI·체지방률, ANOVA는 체력 4종목을 비교합니다. 차이는 관찰된 집단 간 관계이며 인과성을 뜻하지 않습니다.',
            'CSV 숫자는 반올림하지 않고 저장하며, 표에서 표시할 때만 필요한 자릿수로 반올림하세요.', '']
    (OUTPUT / 'README.md').write_text('\n'.join(text), encoding='utf-8')
    print(json.dumps({'연령표본': metadata['연령분석인원'], 'BMI표본': len(bmi_data), '연령사후비교': age_pairs, 'BMI사후비교': bmi_pairs}, ensure_ascii=True))
    for folder in folders:
        print(folder, len(list((OUTPUT / folder).glob('*.csv'))))


if __name__ == '__main__':
    main()
