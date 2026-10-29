"""원본 측정을 보존하고 전체 체력 현황용 판정·집계 CSV를 생성합니다."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from data.scripts.fitness_standards import AGE_MIN, AGE_MAX, FITNESS_EXERCISES, grade_cut
from data.scripts.paths import PROCESSED_FITNESS_PATH, PROCESSED_FITNESS_OVERVIEW_DIR, SYNTHETIC_PERSONNEL_PATH
from data.scripts.utils import read_text_csv, require_columns, write_csv

EVENTS = {'STRENGTH': ('근력', '%'), 'ENDURANCE': ('근지구력', '회'),
          'CARDIO': ('심폐지구력', 'mL/kg/min'), 'FLEXIBILITY': ('유연성', 'cm')}


def judge_measurements(source: pd.DataFrame) -> pd.DataFrame:
    """모든 측정에 날짜순 회차를 부여하고 적용 연령 내 종목 판정을 추가합니다."""
    require_columns(source, ['MESURE_ID', 'SOLDIER_ID', 'MESURE_DE', 'AGE', *FITNESS_EXERCISES])
    data = source.copy()
    for column in ('MESURE_ID', 'SOLDIER_ID'):
        data[column] = data[column].astype('string').str.strip()
        if data[column].isna().any() or data[column].eq('').any():
            raise ValueError(f'{column}: 빈 식별자')
    if data.MESURE_ID.duplicated().any():
        raise ValueError('중복 측정 식별자')
    data['_date'] = pd.to_datetime(data.MESURE_DE.astype('string').str.replace(r'\.0$', '', regex=True), format='%Y%m%d', errors='coerce')
    if data['_date'].isna().any():
        raise ValueError('측정일 형식 오류')
    data = data.sort_values(['SOLDIER_ID', '_date'], kind='stable').reset_index(drop=True)
    data['ROUND'] = data.groupby('SOLDIER_ID').cumcount() + 1
    eligible = pd.to_numeric(data.AGE, errors='coerce').between(AGE_MIN, AGE_MAX)
    for event in FITNESS_EXERCISES:
        values = pd.to_numeric(data[event], errors='coerce').replace([np.inf, -np.inf], np.nan)
        data[event] = values
        grade = pd.Series(pd.NA, index=data.index, dtype='Int64')
        valid = eligible & values.notna()
        grade.loc[valid] = 0
        for level in (3, 2, 1):
            grade.loc[valid & values.ge(grade_cut(event, level))] = level
        data[f'{event}_GRADE'] = grade
        data[f'{event}_FAIL'] = grade.eq(0)
    risks = [f'{event}_FAIL' for event in FITNESS_EXERCISES]
    data['EVALUATED_COUNT'] = data[risks].notna().sum(axis=1)
    data['FAIL_COUNT'] = data[risks].sum(axis=1).astype('Int64').where(data.EVALUATED_COUNT.eq(4))
    first = data.loc[data.ROUND.eq(1)].set_index('SOLDIER_ID').FAIL_COUNT
    data['MULTIPLE_FAIL'] = data.FAIL_COUNT.ge(2).fillna(False)
    data['WORSENED'] = data.FAIL_COUNT.gt(data.SOLDIER_ID.map(first)).fillna(False)
    data['PERSISTENT_FAIL'] = False
    for event in FITNESS_EXERCISES:
        # 해당 회차까지 최근 세 회차가 모두 판정 가능하고 미달인 경우만 인정합니다.
        sequence = data.groupby('SOLDIER_ID')[f'{event}_FAIL'].transform(
            lambda series: series.astype('Float64').rolling(3, min_periods=3).sum())
        data['PERSISTENT_FAIL'] |= sequence.eq(3).fillna(False)
    bmi = pd.to_numeric(data.get('BMI', pd.Series(np.nan, index=data.index)), errors='coerce')
    data['HIGH_BMI_FAIL'] = (bmi.ge(25) & (data.STRENGTH_FAIL | data.CARDIO_FAIL)).fillna(False)
    data['MANAGED'] = data[['HIGH_BMI_FAIL', 'MULTIPLE_FAIL', 'WORSENED', 'PERSISTENT_FAIL']].any(axis=1)
    data['MESURE_DE'] = data['_date'].dt.strftime('%Y-%m-%d')
    return data.drop(columns='_date')


def summarize(data: pd.DataFrame, personnel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """소속 구분 없이 전체 장병의 회차·종목·등급 통계를 생성합니다."""
    require_columns(personnel, ['SOLDIER_ID'])
    ids = personnel.SOLDIER_ID.astype('string').str.strip()
    if ids.isna().any() or ids.eq('').any() or ids.duplicated().any():
        raise ValueError('장병 명단 식별자 중복 또는 누락')
    if not data.SOLDIER_ID.isin(ids).all():
        raise ValueError('측정 장병을 명단에서 찾을 수 없습니다.')
    if data.empty:
        raise ValueError('집계할 측정 자료가 없습니다.')
    totals, events = [], []
    for number, current in data.groupby('ROUND', sort=True):
        valid = current.loc[current.EVALUATED_COUNT.eq(4)]
        failed = int(valid.FAIL_COUNT.ge(2).sum())
        totals.append({'회차': int(number), '전체장병수': ids.nunique(),
            '측정인원': len(current), '판정가능인원': len(valid),
            '판정불완전인원': len(current)-len(valid), '미달인원': failed,
            '미달률': failed/len(valid)*100 if len(valid) else np.nan,
            '관리대상인원': int(current.MANAGED.sum())})
        for event, (label, unit) in EVENTS.items():
            grades = current[f'{event}_GRADE']
            n = grades.count()
            values = current[event].dropna()
            under = int(grades.eq(0).sum())
            events.append({'회차': int(number), '종목': label, '단위': unit,
                '유효측정인원': len(values), '평균': values.mean(), '표준편차': values.std(ddof=1),
                '판정가능인원': n, '판정불가인원': len(current)-n, '미달인원': under,
                '미달률': under/n*100 if n else np.nan,
                **{f'{level}등급인원': int(grades.eq(level).sum()) for level in (1,2,3)}})
    return pd.DataFrame(totals), pd.DataFrame(events)


def run(input_path: Path, personnel_path: Path, output_dir: Path) -> None:
    """측정 원본과 장병 명단에서 판정·집계·메타데이터를 저장합니다."""
    data = judge_measurements(read_text_csv(input_path))
    people = read_text_csv(personnel_path)
    rounds, events = summarize(data, people)
    derived = ['MESURE_ID','SOLDIER_ID','ROUND','EVALUATED_COUNT','FAIL_COUNT',
               'HIGH_BMI_FAIL','MULTIPLE_FAIL','WORSENED','PERSISTENT_FAIL','MANAGED']
    derived += [f'{event}_{suffix}' for event in FITNESS_EXERCISES for suffix in ('GRADE','FAIL')]
    write_csv(data[derived], output_dir/'measurement_judgments.csv')
    write_csv(rounds, output_dir/'round_summary.csv')
    write_csv(events, output_dir/'event_summary.csv')
    metadata = {'生成日時': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        '입력측정': str(input_path), '입력명단': str(personnel_path),
        '측정시작': data.MESURE_DE.min(), '측정종료': data.MESURE_DE.max(),
        '기준': '측정 당시 남성 19~24세 기준 적용; 연령 범위 밖·누락은 판정 불가',
        '표본': '원본 측정 전체 보존; 첫 측정 19~24세로 제한하는 실험 보고서와 구분',
        '관리대상': 'BMI≥25이면서 근력 또는 심폐 미달 OR 선택 회차 2개 이상 미달 OR 1차 대비 미달 수 증가 OR 동일 종목 최근 3회 지속 미달; 중복 제거',
        '집계범위': '전체 장병 기준; 소속·비교집단 구분 없음. 각 회차 측정 인원을 함께 표시',
        '등급기준': {event: {str(level): grade_cut(event,level) for level in (1,2,3)} for event in EVENTS}}
    metadata['생성일시'] = metadata.pop('生成日時')
    (output_dir/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    """전체 현황 분석을 단독 실행합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=PROCESSED_FITNESS_PATH)
    parser.add_argument('--personnel', type=Path, default=SYNTHETIC_PERSONNEL_PATH)
    parser.add_argument('--output-dir', type=Path, default=PROCESSED_FITNESS_OVERVIEW_DIR)
    args = parser.parse_args()
    run(args.input, args.personnel, args.output_dir)
    print(f'분석 결과 저장: {args.output_dir}')


if __name__ == '__main__':
    main()
