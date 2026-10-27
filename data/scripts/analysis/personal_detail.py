"""개인 상세용으로 1차 대비 측정값·등급·미달 종목 변화를 저장합니다."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from data.scripts.analysis.fitness_overview import EVENTS
from data.scripts.paths import PROCESSED_FITNESS_PATH, PROCESSED_MANAGEMENT_TARGETS_DIR, PROCESSED_PERSONAL_DETAIL_DIR
from data.scripts.utils import read_text_csv, require_columns, write_csv


def build_changes(source: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """원본과 판정 CSV를 연결해 각 회차의 1차 대비 변화를 계산합니다."""
    require_columns(source,['MESURE_ID','SOLDIER_ID',*EVENTS])
    require_columns(targets,['MESURE_ID','SOLDIER_ID','ROUND',*[f'{e}_GRADE' for e in EVENTS]])
    if targets.duplicated(['SOLDIER_ID','ROUND']).any():
        raise ValueError('장병·회차 중복')
    joined=targets.merge(source[['MESURE_ID','SOLDIER_ID',*EVENTS]],on=['MESURE_ID','SOLDIER_ID'],how='left',validate='one_to_one',indicator=True)
    if joined['_merge'].ne('both').any():
        raise ValueError('원본과 판정 연결 불일치')
    first=joined.loc[pd.to_numeric(joined.ROUND).eq(1)].set_index('SOLDIER_ID')
    if not joined.SOLDIER_ID.isin(first.index).all():
        raise ValueError('1차 측정 누락')
    output=joined[['MESURE_ID','SOLDIER_ID','ROUND']].copy()
    output['FIRST_MESURE_ID']=joined.SOLDIER_ID.map(first.MESURE_ID)
    improved={}
    for event in EVENTS:
        value=pd.to_numeric(joined[event],errors='coerce').replace([np.inf,-np.inf],np.nan)
        first_value=pd.to_numeric(joined.SOLDIER_ID.map(first[event]),errors='coerce').replace([np.inf,-np.inf],np.nan)
        output[f'{event}_CHANGE']=value-first_value
        grade=pd.to_numeric(joined[f'{event}_GRADE'],errors='coerce').astype(float)
        prior=pd.to_numeric(joined.SOLDIER_ID.map(first[f'{event}_GRADE']),errors='coerce').astype(float)
        def status(g):
            return np.select([g.eq(1),g.eq(2),g.eq(3),g.eq(0)],[4,3,2,1],default=np.nan)
        change=status(grade)-status(prior)
        output[f'{event}_GRADE_CHANGE']=np.select([change>0,change<0,change==0],['개선','하락','유지'],default='판정 불가')
        improved[event]=(prior.eq(0)&grade.gt(0))
    output['IMPROVED_EVENTS']=[' · '.join(EVENTS[e][0] for e in EVENTS if improved[e].iloc[i]) for i in range(len(joined))]
    return output


def run(input_path: Path, targets_path: Path, output_dir: Path) -> None:
    """추가 변화 정보만 저장하고 원본 신체·측정·부상 자료는 복제하지 않습니다."""
    result=build_changes(read_text_csv(input_path),read_text_csv(targets_path))
    write_csv(result,output_dir/'personal_changes.csv')
    metadata={'생성일시':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        '비교':'1차 대비 각 회차. 측정값 변화는 현재−1차. 등급 변화는 1등급이 가장 높음.',
        '주의':'측정값 변화와 미달·등급 변화는 별개. 판정 불가는 개선·유지로 처리하지 않음.'}
    (output_dir/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')


def main() -> None:
    """기본 자료를 사용해 개인 변화 CSV를 생성합니다."""
    run(PROCESSED_FITNESS_PATH,PROCESSED_MANAGEMENT_TARGETS_DIR/'management_targets.csv',PROCESSED_PERSONAL_DETAIL_DIR)
    print(f'개인 상세 분석 저장: {PROCESSED_PERSONAL_DETAIL_DIR}')


if __name__=='__main__':
    main()
