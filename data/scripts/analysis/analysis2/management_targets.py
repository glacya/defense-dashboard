"""2번 화면의 장병·회차별 집중관리 선정 사유와 요약 CSV를 생성합니다."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from data.scripts.analysis.analysis2.fitness_overview import EVENTS, judge_measurements
from data.scripts.paths import PROCESSED_FITNESS_PATH, PROCESSED_MANAGEMENT_TARGETS_DIR
from data.scripts.utils import read_text_csv, require_columns, write_csv

REASONS = {'HIGH_BMI_FAIL': 'BMI≥25·근력 또는 심폐 미달', 'MULTIPLE_FAIL': '2개 이상 종목 미달',
           'WORSENED': '1차 대비 미달 종목 수 증가', 'PERSISTENT_FAIL': '동일 종목 최근 3회 지속 미달'}


def build_targets(source: pd.DataFrame) -> pd.DataFrame:
    """대상·비대상을 모두 보존해 필터 분모와 개인별 선정 근거를 제공합니다."""
    require_columns(source, ['BMI'])
    data = judge_measurements(source)
    bmi = pd.to_numeric(data.BMI, errors='coerce').replace([np.inf,-np.inf], np.nan)
    data['BMI_GROUP'] = pd.cut(bmi.where(bmi.gt(0)), [0,18.5,25,np.inf], labels=['낮음','보통','높음'], right=False).astype('string').fillna('판정 불가')
    first = data.loc[data.ROUND.eq(1)].set_index('SOLDIER_ID')
    data['FIRST_MESURE_ID'] = data.SOLDIER_ID.map(first.MESURE_ID)
    data['FIRST_FAIL_COUNT'] = data.SOLDIER_ID.map(first.FAIL_COUNT)
    data['FAIL_COUNT_CHANGE'] = data.FAIL_COUNT-data.FIRST_FAIL_COUNT
    failed, new_failed, persistent = {}, {}, {}
    for event in EVENTS:
        failed[event] = data[f'{event}_FAIL'].fillna(False)
        prior = data.SOLDIER_ID.map(first[f'{event}_FAIL']).astype('boolean')
        new_failed[event] = (data[f'{event}_FAIL'] & ~prior).fillna(False)
        sequence = data.groupby('SOLDIER_ID')[f'{event}_FAIL'].transform(
            lambda s: s.astype('Float64').rolling(3,min_periods=3).sum())
        persistent[event] = sequence.eq(3).fillna(False)
    for column, conditions in [('FAILED_EVENTS',failed),('NEW_FAILED_EVENTS',new_failed),('PERSISTENT_EVENTS',persistent)]:
        data[column] = [' · '.join(EVENTS[event][0] for event in EVENTS if conditions[event].iloc[i]) for i in range(len(data))]
    data['SELECTION_REASONS'] = [' · '.join(label for flag,label in REASONS.items() if row[flag]) for _,row in data.iterrows()]
    columns = ['MESURE_ID','SOLDIER_ID','ROUND','BMI_GROUP','EVALUATED_COUNT','FAIL_COUNT',
        'FIRST_MESURE_ID','FIRST_FAIL_COUNT','FAIL_COUNT_CHANGE','FAILED_EVENTS','NEW_FAILED_EVENTS','PERSISTENT_EVENTS',
        *REASONS,'MANAGED','SELECTION_REASONS', *[f'{event}_GRADE' for event in EVENTS]]
    return data[columns]


def run(input_path: Path, output_dir: Path) -> None:
    """원본을 읽고 관리 판정 CSV·회차별 사유 집계·메타데이터를 저장합니다."""
    source = read_text_csv(input_path)
    targets = build_targets(source)
    rows = []
    for number,group in targets.groupby('ROUND'):
        for flag,label in {**REASONS,'MANAGED':'통합 관리 대상 (중복 제거)'}.items():
            rows.append({'회차':int(number),'선정사유':label,'측정인원':len(group),'대상인원':int(group[flag].sum())})
    write_csv(targets, output_dir/'management_targets.csv')
    write_csv(pd.DataFrame(rows), output_dir/'target_summary.csv')
    metadata={'생성일시':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'입력측정':str(input_path),
        '기준':'측정 당시 남성 19~24세 기준. 연령 범위 밖·누락은 종목 판정 불가.',
        '대상':'네 조건의 합집합. 회차별 장병 한 번만 집계. 소속별 비교 없음.',
        '시간':'악화는 1차 대비 선택 회차. 지속 미달은 선택 회차까지 최근 세 회차. 미래 측정 미사용.',
        '누락':'False는 선정 조건이 확인되지 않음이며 건강·통과 보장이 아님. 미달 개수는 네 종목 모두 판정 가능할 때만 확정.',
        'BMI':'낮음 <18.5, 보통 18.5 이상 25 미만, 높음 25 이상. 보통은 정상·비만전단계 포함.',
        '상세':'이 파일은 대상 여부를 보존하기 위해 비대상 측정도 포함. 측정값·신상은 원본과 식별자로 연결.'}
    (output_dir/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')


def main() -> None:
    """기본 입력 경로로 2번 화면 분석을 실행합니다."""
    run(PROCESSED_FITNESS_PATH, PROCESSED_MANAGEMENT_TARGETS_DIR)
    print(f'집중관리 분석 저장: {PROCESSED_MANAGEMENT_TARGETS_DIR}')


if __name__=='__main__':
    main()
