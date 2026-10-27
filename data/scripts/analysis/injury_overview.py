"""합성 부상 기록을 장병별·최신 종목 등급별로 집계합니다."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from data.scripts.analysis.fitness_overview import EVENTS, judge_measurements
from data.scripts.paths import PROCESSED_FITNESS_PATH, SYNTHETIC_PERSONNEL_PATH, SYNTHETIC_INJURY_PATH, PROCESSED_INJURY_OVERVIEW_DIR
from data.scripts.utils import read_text_csv, require_columns, write_csv

GRADE_LABELS={1:'1등급',2:'2등급',3:'3등급',0:'3등급 미만',-1:'판정 불가'}


def build_tables(source: pd.DataFrame, people: pd.DataFrame, injuries: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """명단 전체를 분모로 집계하고 반복 부상은 건수와 인원을 구분합니다."""
    require_columns(people,['SOLDIER_ID'])
    require_columns(injuries,['INJURY_ID','SOLDIER_ID','INJURY_CATEGORY','INJURY_LOCATION','SEVERITY','PREVENTABILITY'])
    for table,key in [(people,'SOLDIER_ID'),(injuries,'INJURY_ID')]:
        if table[key].isna().any() or table[key].astype(str).str.strip().eq('').any() or table[key].duplicated().any():
            raise ValueError(f'{key}: 중복 또는 빈 식별자')
    if not injuries.SOLDIER_ID.isin(people.SOLDIER_ID).all():
        raise ValueError('장병 명단에 없는 부상 기록')
    if not source.SOLDIER_ID.isin(people.SOLDIER_ID).all():
        raise ValueError('장병 명단에 없는 측정 기록')
    judged=judge_measurements(source)
    latest=judged.sort_values('ROUND',kind='stable').drop_duplicates('SOLDIER_ID',keep='last')
    cols=['SOLDIER_ID','MESURE_ID','ROUND',*[f'{e}_GRADE' for e in EVENTS]]
    personal=people[['SOLDIER_ID']].merge(latest[cols],on='SOLDIER_ID',how='left',validate='one_to_one')
    counts=injuries.groupby('SOLDIER_ID').size()
    personal['INJURY_COUNT']=personal.SOLDIER_ID.map(counts).fillna(0).astype(int)
    personal['HAS_INJURY']=personal.INJURY_COUNT.gt(0)
    rows=[]
    for event,(label,_) in EVENTS.items():
        grades=pd.to_numeric(personal[f'{event}_GRADE'],errors='coerce').fillna(-1)
        for grade,text in GRADE_LABELS.items():
            group=personal.loc[grades.eq(grade)]
            n=len(group); affected=int(group.HAS_INJURY.sum())
            rows.append({'종목':label,'등급':text,'전체인원':n,'부상인원':affected,
                '부상건수':int(group.INJURY_COUNT.sum()),'부상자비율':affected/n*100 if n else float('nan')})
    total=len(personal); affected=int(personal.HAS_INJURY.sum())
    overview=pd.DataFrame([{'전체장병수':total,'부상인원':affected,'부상건수':len(injuries),
        '부상자비율':affected/total*100 if total else float('nan'),
        '반복부상인원':int(personal.INJURY_COUNT.ge(2).sum()),'측정기록없음':int(personal.MESURE_ID.isna().sum())}])
    return personal,pd.DataFrame(rows),overview


def run(input_path: Path, personnel_path: Path, injury_path: Path, output_dir: Path) -> None:
    """원본을 변경하지 않고 부상 현황 CSV 3개와 기준 정보를 저장합니다."""
    tables=build_tables(read_text_csv(input_path),read_text_csv(personnel_path),read_text_csv(injury_path))
    for table,name in zip(tables,['personal_injury_summary.csv','grade_injury_summary.csv','injury_summary.csv']):
        write_csv(table,output_dir/name)
    metadata={'생성일시':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        '집계범위':'장병 명단 전체와 보유 부상 기록 전체. 부상자 비율은 부상 기록 1건 이상 장병 수 / 집단 전체 인원 ×100.',
        '등급':'장병별 최신 측정의 종목별 등급. 종합 인증등급이 아님. 남성 19~24세 범위 밖·누락·미측정은 판정 불가.',
        '기간':'부상 발생일이 없어 기간별 집계·발생률·측정 당시 부상 판정은 하지 않음.',
        '합성':'부상 기록은 BMI·심폐 수준을 기반으로 합성됨. 등급별 차이를 실제 부상 위험이나 인과관계로 해석하지 않음.',
        '중복':'같은 장병의 반복 부상은 부상인원 1명, 부상건수 여러 건으로 집계. 서로 다른 종목의 인원을 합산하지 않음.'}
    (output_dir/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')


def main() -> None:
    """기본 입력 파일로 부상 현황 분석을 실행합니다."""
    run(PROCESSED_FITNESS_PATH,SYNTHETIC_PERSONNEL_PATH,SYNTHETIC_INJURY_PATH,PROCESSED_INJURY_OVERVIEW_DIR)
    print(f'부상 현황 분석 저장: {PROCESSED_INJURY_OVERVIEW_DIR}')


if __name__=='__main__':
    main()
