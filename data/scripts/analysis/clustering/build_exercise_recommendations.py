"""처방 상세정보와 군집 상대 편차로 유형별 운동 8개를 생성합니다.

체력 요소·동작 난이도·사용 부위는 명시적 수동 분류입니다. 편차는 상대적
보완 우선순위이며 절대 미달 또는 개인별 운동 적합성을 의미하지 않습니다.
실행: python -m data.scripts.analysis.clustering.build_exercise_recommendations
"""

import logging
from pathlib import Path

import pandas as pd

from data.scripts.paths import PROCESSED_FITNESS_TYPE_PATH, PROCESSED_PRESCRIPTION_DETAIL_PATH
from data.scripts.synthesis.generate_synthetic_injuries import LOCATION_NAMES
from data.scripts.logging_setup import caller_name, setup_logging
from data.scripts.utils import require_columns

OUTPUT_PATH = PROCESSED_FITNESS_TYPE_PATH.parent / 'FITNESS_TYPE_EXERCISE_RECOMMENDATIONS3.csv'
FOCUSES = {'근력': 'STRENGTH_RELATIVE', '근지구력': 'ENDURANCE_RELATIVE',
           '심폐지구력': 'CARDIO_RELATIVE', '유연성': 'FLEXIBILITY_RELATIVE'}
# 처방번호, 체력 요소, 동작 난이도(1=기초/2=일반/3=도전), 장비, 사용 부위.
# 분류가 확정된 후보만 추천합니다. 원본의 전체 운동을 자동 분류하지 않습니다.
RULES = [
    (179, '근력', 1, '벽', 'Shoulder|Arm|Elbow|Wrist'),
    (470, '근력', 1, '없음', 'Shoulder|Arm|Elbow|Wrist'),
    (9, '근력', 1, '없음', 'Hip|Leg upper|Knee|Ankle'),
    (14, '근력', 1, '없음', 'Back lower|Pelvic region|Hip|Leg upper'),
    (24, '근력', 1, '없음', 'Leg lower|Ankle|Foot/toe'),
    (15, '근력', 2, '없음', 'Shoulder|Arm|Elbow|Wrist|Hand/finger'),
    (10, '근력', 2, '없음', 'Hip|Leg upper|Knee|Ankle'),
    (117, '근력', 2, '덤벨 또는 저항 도구', 'Arm|Elbow|Forearm'),
    (180, '근력', 3, '덤벨', 'Hip|Leg upper|Knee|Ankle'),
    (5, '근력', 3, '철봉', 'Shoulder|Arm|Elbow|Forearm|Hand/finger'),
    (12, '근지구력', 2, '없음', 'Shoulder|Elbow|Back lower|Pelvic region'),
    (20, '근지구력', 2, '없음', 'Shoulder|Elbow|Back lower|Hip'),
    (22, '근지구력', 1, '없음', 'Shoulder|Wrist|Back lower|Hip|Knee'),
    (124, '근지구력', 1, '없음', 'Back lower|Pelvic region'),
    (79, '근지구력', 1, '없음', 'Back lower|Pelvic region'),
    (21, '근지구력', 2, '없음', 'Back lower|Pelvic region|Hip'),
    (140, '근지구력', 2, '없음', 'Back lower|Pelvic region|Hip'),
    (131, '근지구력', 3, '없음', 'Back lower|Pelvic region|Hip'),
    (156, '근지구력', 3, '없음', 'Back lower|Pelvic region|Hip'),
    (135, '근지구력', 3, '없음', 'Shoulder|Wrist|Hip|Knee'),
    (192, '심폐지구력', 1, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (262, '심폐지구력', 1, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (38, '심폐지구력', 1, '실내 자전거', 'Hip|Leg upper|Knee|Leg lower|Ankle'),
    (43, '심폐지구력', 1, '트레드밀', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (101, '심폐지구력', 2, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (39, '심폐지구력', 2, '계단', 'Hip|Leg upper|Knee|Leg lower|Ankle'),
    (17, '심폐지구력', 2, '없음', 'Shoulder|Hip|Leg upper|Knee|Leg lower|Ankle'),
    (37, '심폐지구력', 3, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (44, '심폐지구력', 3, '줄넘기', 'Shoulder|Wrist|Knee|Leg lower|Ankle|Foot/toe'),
    (325, '심폐지구력', 3, '없음', 'Hip|Leg upper|Knee|Leg lower|Ankle|Foot/toe'),
    (68, '유연성', 1, '없음', 'Hip|Leg upper|Knee'),
    (70, '유연성', 1, '없음', 'Hip|Leg upper|Knee'),
    (181, '유연성', 1, '없음', 'Leg lower|Ankle'),
    (347, '유연성', 1, '없음', 'Shoulder|Arm'),
    (69, '유연성', 1, '없음', 'Pelvic region|Hip'),
    (100, '유연성', 1, '없음', 'Elbow|Forearm|Wrist'),
    (53, '유연성', 2, '없음', 'Hip|Leg upper'),
    (81, '유연성', 2, '없음', 'Back lower|Pelvic region'),
    (98, '유연성', 2, '없음', 'Shoulder|Back lower'),
    (99, '유연성', 2, '없음', 'Shoulder|Arm'),
]


def build_recommendations(types: pd.DataFrame, details: pd.DataFrame,
                          profiles: pd.DataFrame) -> pd.DataFrame:
    keys = ['AVERAGE_PERCENTILE_GRADE', 'CLUSTER']
    require_columns(types, [*keys, 'TYPE_NAME'])
    require_columns(details, ['PRESCRIPTION_TYPE_ID', 'PRESCRIPTION'])
    require_columns(profiles, [*keys, *FOCUSES.values()])
    if types.duplicated(keys).any() or profiles.duplicated(keys).any():
        raise ValueError('등급·군집 키가 중복됩니다.')
    details = details.copy()
    details['PRESCRIPTION_TYPE_ID'] = pd.to_numeric(details.PRESCRIPTION_TYPE_ID, errors='raise')
    if details.PRESCRIPTION_TYPE_ID.duplicated().any():
        raise ValueError('처방번호가 중복됩니다.')
    candidates = []
    source = details.set_index('PRESCRIPTION_TYPE_ID')
    for prescription_id, focus, difficulty, equipment, parts in RULES:
        if prescription_id not in source.index:
            raise ValueError(f'원본 처방 상세정보에 없는 처방번호: {prescription_id}')
        locations = parts.split('|')
        if not set(locations).issubset(LOCATION_NAMES):
            raise ValueError('사용 부위 매핑 오류')
        candidates.append({'PRESCRIPTION_TYPE_ID': prescription_id,
            'RECOMMENDED_EXERCISE': source.loc[prescription_id, 'PRESCRIPTION'],
            'IMPROVEMENT_FOCUS': focus, 'EXERCISE_DIFFICULTY': difficulty,
            'REQUIRED_EQUIPMENT': equipment,
            'BODY_PARTS': ' | '.join(LOCATION_NAMES[part] for part in locations)})
    candidates = pd.DataFrame(candidates)
    merged = types.merge(profiles[[*keys, *FOCUSES.values()]], on=keys, how='left', validate='one_to_one')
    if merged[list(FOCUSES.values())].isna().any().any():
        raise ValueError('체력 유형에 대응하는 편차 정보가 없습니다.')
    rows = []
    for item in merged.to_dict('records'):
        grade = int(item['AVERAGE_PERCENTILE_GRADE'])
        if grade not in (1, 2, 3, 4):
            raise ValueError('등급은 1~4여야 합니다.')
        ordered = sorted(FOCUSES, key=lambda focus: item[FOCUSES[focus]])
        name = item['TYPE_NAME']
        matches = [focus for focus in FOCUSES
                   if name.endswith(f'{focus} 약점형') or name.endswith(f'{focus} 강점형')]
        if len(matches) != 1:
            raise ValueError(f'해석할 수 없는 체력 유형: {name}')
        if name.endswith('약점형'):
            ordered = matches
            quotas = {matches[0]: 8}
            allocation = '유형에 명시된 약점 요소 운동 8개'
        else:
            ordered = [focus for focus in ordered if focus != matches[0]]
            quotas = dict(zip(ordered, [4, 2, 2]))
            allocation = '강점 요소 제외 후 상대 편차가 낮은 순 4/2/2개 배분'
        target_difficulty = {1: 3, 2: 2, 3: 1, 4: 1}[grade]
        rank = 0
        for focus in ordered:
            pool = candidates.loc[candidates.IMPROVEMENT_FOCUS.eq(focus)].copy()
            pool['DISTANCE'] = (pool.EXERCISE_DIFFICULTY - target_difficulty).abs()
            selected = pool.sort_values(['DISTANCE', 'PRESCRIPTION_TYPE_ID']).drop_duplicates('RECOMMENDED_EXERCISE').head(quotas[focus])
            if len(selected) != quotas[focus]:
                raise ValueError(f'{focus} 추천 후보가 부족합니다.')
            for exercise in selected.drop(columns='DISTANCE').to_dict('records'):
                rank += 1
                gap = float(item[FOCUSES[focus]])
                rows.append({**{key: item[key] for key in [*keys, 'TYPE_NAME']},
                    'SOURCE_TYPE_NAME': item['TYPE_NAME'], 'RECOMMENDATION_RANK': rank,
                    **exercise, 'RELATIVE_GAP': gap,
                    'TRAINING_GUIDANCE': f'{grade}등급 기준 동작 난이도 {target_difficulty}에 가까운 운동 우선. 개인별 수행 수준에 맞춰 강도와 반복량을 조절합니다.',
                    'RECOMMENDATION_BASIS': f'{grade}등급 군집 {item["CLUSTER"]}: {focus} 상대 편차 {gap:+.2f}%p; {allocation}. 등급별 난이도는 수동 규칙입니다.',
                    'SOURCE_URL': 'https://nfa.kspo.or.kr/',
                    'SOURCE_FILE': 'KS_NFA_PRESCRIPTION_DETAIL.csv'})
    result = pd.DataFrame(rows)
    columns = list(result.columns)
    columns.remove('BODY_PARTS')
    columns.insert(columns.index('RECOMMENDED_EXERCISE') + 1, 'BODY_PARTS')
    return result[columns]


def run(fitness_type_path: Path, prescription_detail_path: Path,
        profile_dir: Path, output_path: Path) -> None:
    profiles = pd.concat([pd.read_csv(profile_dir / f'grade_{grade}_relative_profile.csv')
                          for grade in (1, 2, 3, 4)], ignore_index=True)
    result = build_recommendations(pd.read_csv(fitness_type_path),
                                  pd.read_csv(prescription_detail_path), profiles)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding='utf-8-sig')
    logging.getLogger(__name__).info('체력 유형별 추천 운동 %d건 저장: %s', len(result), output_path)


if __name__ == '__main__':
    setup_logging(caller_name(__file__))
    run(PROCESSED_FITNESS_TYPE_PATH, PROCESSED_PRESCRIPTION_DETAIL_PATH,
        PROCESSED_FITNESS_TYPE_PATH.parent / 'clustering', OUTPUT_PATH)
