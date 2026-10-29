"""DB에서 측정·장병 명단을 조회하고 기존 분석 기준으로 관리 대상을 판정합니다."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.db import run_query
from data.scripts.analysis.analysis2.management_targets import build_targets

# 판정에는 이전 회차도 필요하므로 전체 측정 이력을 가져옵니다.
TARGET_SOURCE_SQL = '''
SELECT m.mesure_id, m.soldier_id, m.mesure_de, m.age,
       m.strength, m.endurance, m.cardio, m.flexibility,
       m.height, m.weight, m.bmi, m.body_fat_percentage,
       s.soldier_name, s.rank_name, s.unit_name
FROM fitness_measurements AS m
LEFT JOIN soldiers AS s ON s.soldier_id = m.soldier_id
ORDER BY m.soldier_id, m.mesure_de, m.mesure_id
'''


@st.cache_data(ttl=600, show_spinner=False)
def load_targets() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """DB 조회·판정 결과를 10분간 캐시하며 CSV 파일은 사용하지 않습니다."""
    joined = run_query(TARGET_SOURCE_SQL, ttl=0)
    if joined.SOLDIER_NAME.isna().any():
        raise ValueError('측정 기록과 연결되지 않는 장병 정보가 있습니다.')
    people_columns = ['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME']
    people = joined[people_columns].drop_duplicates()
    source = joined.drop(columns=people_columns[1:]).copy()
    # DB 날짜 형식이 DATE 또는 문자열이어도 기존 분석 함수의 YYYYMMDD 입력에 맞춥니다.
    source['MESURE_DE'] = pd.to_datetime(source.MESURE_DE.astype('string'), errors='raise').dt.strftime('%Y%m%d')
    targets = build_targets(source)
    linked = targets.merge(source, on=['MESURE_ID','SOLDIER_ID'], validate='one_to_one')
    linked = linked.merge(people, on='SOLDIER_ID', validate='many_to_one')
    metadata = {
        '생성일시': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        '기준': '측정 당시 남성 19~24세 기준. 연령 범위 밖·누락은 종목 판정 불가.',
        '대상': '네 조건 중 하나 이상 해당하는 장병. 회차별 중복 집계하지 않습니다.',
        '시간': '악화는 1차 대비 선택 회차, 지속 미달은 선택 회차까지 최근 세 회차 기준입니다.',
        '누락': '판정 불가는 통과로 보지 않습니다. 미달 개수는 네 종목 모두 판정 가능할 때 확정합니다.',
        'BMI': '낮음 <18.5, 보통 18.5 이상 25 미만, 높음 25 이상.',
        '상세': 'DB fitness_measurements와 soldiers를 조회하고 기존 build_targets()로 판정합니다. CSV를 읽거나 저장하지 않습니다. 조회·판정 결과는 10분 캐시됩니다.',
    }
    return linked, source, metadata
