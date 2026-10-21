import argparse
import random
from pathlib import Path
import numpy as np
import pandas as pd
from tabulate import tabulate

# ==========================================
# 1. 전역 상수 (Global Constants)
# ==========================================
# 논문 표(Table 4)의 부위별 부상 데이터 및 가중치 반영[cite: 1]
INJURY_LOCATION_DATA = [
    # (상위 부위, 세부 부위, Total Frequency, Preventable Frequency)
    ('Upper', 'Head', 1, 0),
    ('Upper', 'Shoulder', 68, 25),
    ('Upper', 'Arm', 11, 0),
    ('Upper', 'Elbow', 6, 2),
    ('Upper', 'Forearm', 3, 1),
    ('Upper', 'Wrist', 24, 6),
    ('Upper', 'Hand/finger', 73, 8),
    ('Upper', 'Ribs', 1, 0),
    ('Upper', 'Back lower', 19, 13),
    ('Lower', 'Pelvic region', 9, 2),
    ('Lower', 'Hip', 3, 2),
    ('Lower', 'Leg upper', 12, 4),
    ('Lower', 'Knee', 183, 121),
    ('Lower', 'Leg lower', 22, 7),
    ('Lower', 'Ankle', 157, 108),
    ('Lower', 'Foot/toe', 23, 4),
    ('Lower', 'Not specified', 1, 0),
]

# 한글 매핑 디렉터리
LOCATION_KOR = {
    'Upper': '상지(상체)',
    'Lower': '하지(하체)',
}

SUB_LOCATION_KOR = {
    'Head': '머리',
    'Shoulder': '어깨',
    'Arm': '팔',
    'Elbow': '팔꿈치',
    'Forearm': '전완',
    'Wrist': '손목',
    'Hand/finger': '손/손가락',
    'Ribs': '갈비뼈',
    'Back lower': '요통/요추',
    'Pelvic region': '골반',
    'Hip': '고관절',
    'Leg upper': '허벅지',
    'Knee': '무릎',
    'Leg lower': '종아리',
    'Ankle': '발목',
    'Foot/toe': '발/발가락',
    'Not specified': '미지정',
}

# 심각도 구분
SEVERITY_LEVELS = ['경증', '중등증', '중증']
SEVERITY_WEIGHTS = [0.6, 0.3, 0.1]


def print_table(data: pd.DataFrame) -> None:
    print(tabulate(
        data,
        headers='keys',
        tablefmt='grid',
        showindex=False,
        stralign='center',
        numalign='right',
    ))


# ==========================================
# 2. 전역 변수 (Global Variables)
# ==========================================
# 확률 분포 계산[cite: 1]
TOTAL_FREQUENCIES = np.array([row[2] for row in INJURY_LOCATION_DATA], dtype=float)
LOCATION_PROBABILITIES = TOTAL_FREQUENCIES / TOTAL_FREQUENCIES.sum()

# 부위별 예방 가능 부상 비율 계산 (Preventable / Total)[cite: 1]
PREVENTABLE_RATIOS = {
    (row[0], row[1]): (row[3] / row[2]) if row[2] > 0 else 0.0
    for row in INJURY_LOCATION_DATA
}

# ==========================================
# 3. 데이터 생성 함수 (Data Generation)
# ==========================================
def generate_injury_data(
    df_personal: pd.DataFrame,
    injury_rate: float = 0.3,
    seed: int = 42,
    injury_count: int | None = None,
) -> pd.DataFrame:
    """
    기존 장병 데이터(df_personal)를 바탕으로 부상 기록 데이터프레임 생성
    - injury_rate: 전체 인원 중 부상을 입은 장병의 비율
    """
    np.random.seed(seed)
    random.seed(seed)

    # 1. 부상 대상 장병 추출
    n_total = len(df_personal)
    n_injured = (
        injury_count if injury_count is not None else int(n_total * injury_rate)
    )
    if n_injured < 0:
        raise ValueError('부상 건수는 0 이상이어야 합니다.')
    if n_injured and n_total == 0:
        raise ValueError('장병 데이터가 비어 있으면 부상 기록을 생성할 수 없습니다.')

    locations_per_soldier = len(INJURY_LOCATION_DATA)
    if n_injured > n_total * locations_per_soldier:
        raise ValueError(
            f'부상 건수는 장병 수와 부상 위치 수의 곱({n_total * locations_per_soldier})을 '
            '초과할 수 없습니다.'
        )

    soldier_indices = []
    location_indices = []
    used_locations = {}
    injury_counts = np.zeros(n_total, dtype=int)
    for _ in range(n_injured):
        eligible_soldiers = np.flatnonzero(injury_counts < locations_per_soldier)
        soldier_index = int(np.random.choice(eligible_soldiers))
        used_for_soldier = used_locations.setdefault(soldier_index, set())
        available_locations = np.array([
            index for index in range(locations_per_soldier)
            if index not in used_for_soldier
        ])
        location_probabilities = LOCATION_PROBABILITIES[available_locations]
        location_probabilities /= location_probabilities.sum()
        location_index = int(np.random.choice(
            available_locations, p=location_probabilities
        ))

        soldier_indices.append(soldier_index)
        location_indices.append(location_index)
        used_for_soldier.add(location_index)
        injury_counts[soldier_index] += 1

    injured_soldiers = df_personal.iloc[soldier_indices].copy()
    
    # 2. 논문 통계 기반 부상 위치 무작위 추출[cite: 1]
    main_locations = [INJURY_LOCATION_DATA[i][0] for i in location_indices]
    sub_locations = [INJURY_LOCATION_DATA[i][1] for i in location_indices]

    # 3. 부위별 예방 가능 여부(Preventable) 판별[cite: 1]
    is_preventable = [
        random.random() < PREVENTABLE_RATIOS[(main_loc, sub_loc)]
        for main_loc, sub_loc in zip(main_locations, sub_locations)
    ]
        
    # 4. 심각도 할당
    severities = np.random.choice(SEVERITY_LEVELS, size=n_injured, p=SEVERITY_WEIGHTS)
    
    # 5. DataFrame 구축
    df_injury = pd.DataFrame({
        '군번': injured_soldiers['군번'].values,
        '이름': injured_soldiers['이름'].values,
        '부대': injured_soldiers['부대'].values,
        '계급': injured_soldiers['계급'].values,
        '부상대분류': main_locations,
        '부상세부부위': sub_locations,
        '부상대분류_한글': [LOCATION_KOR[loc] for loc in main_locations],
        '부상세부부위_한글': [SUB_LOCATION_KOR[sub] for sub in sub_locations],
        '예방가능여부': ['예방가능' if p else '예방불가' for p in is_preventable],
        '부상심각도': severities,
    })

    if '전후방구분' in injured_soldiers.columns:
        df_injury['전후방구분'] = injured_soldiers['전후방구분'].values
    if '지역' in injured_soldiers.columns:
        df_injury['지역'] = injured_soldiers['지역'].values
    
    return df_injury


# ======================================
# 4. 요약 및 부대별 집계 함수
# ======================================
def get_injury_location_summary(df_injury: pd.DataFrame) -> pd.DataFrame:
    """전체 부위별 부상 건수 및 비율 요약"""
    summary = df_injury.groupby(['부상대분류_한글', '부상세부부위_한글']).size().reset_index(name='부상건수')
    summary['비율(%)'] = (summary['부상건수'] / len(df_injury) * 100).round(1)
    return summary.sort_values(by='부상건수', ascending=False)


def get_unit_injury_summary(df_personal: pd.DataFrame, df_injury: pd.DataFrame) -> pd.DataFrame:
    """부대별 전체 인원, 부상 인원, 부상률 및 부상 관련 지표 요약"""
    unit_summary = df_personal.groupby('부대').size().to_frame(name='전체인원')
    injury_summary = df_injury.groupby('부대').agg(
        총_부상건수=('군번', 'count'),
        예방가능_건수=('예방가능여부', lambda x: (x == '예방가능').sum()),
        중증_부상건수=('부상심각도', lambda x: (x == '중증').sum()),
    ).reindex(unit_summary.index, fill_value=0)
    unit_summary = unit_summary.join(injury_summary)

    unit_summary['예방가능_비율(%)'] = (
        unit_summary['예방가능_건수'] / unit_summary['총_부상건수'].replace(0, 1) * 100
    ).round(1)
    unit_summary['부상률(%)'] = (
        unit_summary['총_부상건수'] / unit_summary['전체인원'] * 100
    ).round(1)

    return unit_summary.reset_index().sort_values(by='총_부상건수', ascending=False)


def get_region_injury_summary(df_personal: pd.DataFrame, df_injury: pd.DataFrame) -> pd.DataFrame:
    """지역별 전체 인원, 부상 인원, 부상률 및 전체 부상자 중 비율 요약"""
    summary = df_personal.groupby('지역').size().to_frame(name='전체인원')
    summary['부상건수'] = df_injury.groupby('지역').size().reindex(summary.index, fill_value=0)
    summary['부상인원'] = (
        df_injury.groupby('지역')['군번'].nunique().reindex(summary.index, fill_value=0)
    )
    summary['지역내_부상률(%)'] = (summary['부상인원'] / summary['전체인원'] * 100).round(1)
    total_injuries = df_injury['군번'].nunique()
    summary['전체부상중_비율(%)'] = (
        (summary['부상인원'] / total_injuries * 100).round(1) if total_injuries else 0.0
    )
    return summary.sort_values(by='부상인원', ascending=False).reset_index()


def get_repeat_injury_soldiers(df_injury: pd.DataFrame) -> pd.DataFrame:
    """두 건 이상 부상 기록이 있는 장병과 기록 건수 반환"""
    injury_counts = (
        df_injury.groupby(['군번', '이름']).size().reset_index(name='부상건수')
    )
    return injury_counts[injury_counts['부상건수'] > 1].sort_values(
        by='부상건수', ascending=False
    )
    
    
def get_unit_location_crosstab(df_injury: pd.DataFrame) -> pd.DataFrame:
    """부대별 x 세부 부상 부위 교차표(Crosstab)"""
    return pd.crosstab(
        df_injury['부대'],
        df_injury['부상세부부위_한글'],
        margins=True,
        margins_name='합계',
    )


def get_specific_unit_report(df_injury: pd.DataFrame, unit_name: str) -> pd.DataFrame:
    """특정 부대의 부위별/심각도별 상세 부상 현황 조회"""
    df_unit = df_injury[df_injury['부대'] == unit_name]
    if df_unit.empty:
        print(f"[{unit_name}] 부대의 부상 기록이 없습니다.")
        return pd.DataFrame()
    
    report = df_unit.groupby(['부상대분류_한글', '부상세부부위_한글', '부상심각도', '예방가능여부']).size().reset_index(name='건수')
    return report.sort_values(by='건수', ascending=False)


def print_injury_report(df_personal: pd.DataFrame, df_injury: pd.DataFrame):
    """전체 및 부대별 부상 리포트 출력"""
    print("=== 1. 부상 데이터 샘플 (Head) ===")
    print_table(df_injury[['군번', '이름', '부대', '부상대분류_한글', '부상세부부위_한글', '예방가능여부', '부상심각도']].head())
    
    print("\n=== 2. 부대별 부상 및 예방 가능 비율 요약 ===")
    unit_summary = get_unit_injury_summary(df_personal, df_injury)
    print_table(unit_summary)
# %%
# ==========================================
# 5. run: 메인 실행
# ==========================================
def prepare_injury_csv_data(df_injury: pd.DataFrame) -> pd.DataFrame:
    output_columns = {
        '군번': 'SOLDIER_ID',
        '이름': 'NAME',
        '부상대분류_한글': 'INJURY_CATEGORY',
        '부상세부부위_한글': 'INJURY_LOCATION',
        '예방가능여부': 'PREVENTABLE_YN',
        '부상심각도': 'SEVERITY',
    }
    csv_data = df_injury[list(output_columns)].rename(columns=output_columns)
    csv_data.insert(0, 'INJURY_ID', range(1, len(csv_data) + 1))
    return csv_data


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('1 이상의 정수를 입력하세요.')
    return parsed


def probability(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError('0과 1 사이의 값을 입력하세요.')
    return parsed


def main():
    default_dir = (
        Path(__file__).resolve().parents[2]
        / 'data'
        / 'csv_file'
        / 'csv_data'
    )

    parser = argparse.ArgumentParser(
        description='장병 인적사항 데이터를 바탕으로 부상 데이터를 생성합니다.'
    )
    parser.add_argument(
        '-n', '--count', type=positive_int,
        help='생성할 부상 기록 건수 (지정하지 않으면 전체 인원의 injury-rate 비율)',
    )
    parser.add_argument(
        '--injury-rate', type=probability, default=0.3,
        help='전체 인원 대비 부상 기록 건수 비율 (기본값: 0.3, --count 지정 시 무시)',
    )
    parser.add_argument('--seed', type=int, default=42, help='난수 시드 (기본값: 42)')
    parser.add_argument(
        '-p', '--personal-csv', type=Path,
        default=default_dir / 'soldier_personal_data.csv',
        help='인적사항 입력 CSV 경로',
    )
    parser.add_argument(
        '-o', '--output', type=Path, default=None,
        help='CSV 저장 경로 전체 (선택 사항)',
    )
    parser.add_argument(
        '-f', '--filename', type=str, default='soldier_injury_data.csv',
        help='기본 폴더에 저장할 CSV 파일 이름',
    )
    args = parser.parse_args()

    personal_csv_path = args.personal_csv
    injury_csv_path = args.output or (default_dir / args.filename)
    
    # 개인 인적사항 데이터 로드
    try:
        df_personal = pd.read_csv(personal_csv_path, encoding='utf-8-sig')
        df_personal = df_personal.rename(columns={
            'SOLDIER_ID': '군번',
            'SOLDIER_NAME': '이름',
            'REGION_NAME': '지역',
            'UNIT_NAME': '부대',
            'RANK_NAME': '계급',
            'FRONT_REAR_CLASSIFICATION': '전후방구분',
        })
    except FileNotFoundError:
        print(f"{personal_csv_path} 파일이 없어 임시 장병 데이터를 생성합니다.")
        df_personal = pd.DataFrame({
            '군번': [f'24-{i:09d}' for i in range(1000)],
            '이름': [f'장병_{i}' for i in range(1000)],
            '부대': [f'부대_{i % 10 + 1}' for i in range(1000)],
            '계급': ['일병'] * 1000,
        })

    df_injury = generate_injury_data(
        df_personal,
        injury_rate=args.injury_rate,
        seed=args.seed,
        injury_count=args.count,
    )

    repeat_injury_soldiers = get_repeat_injury_soldiers(df_injury)
    print(f'\n=== 중복 부상 인원: {len(repeat_injury_soldiers)}명 ===')
    if repeat_injury_soldiers.empty:
        print('중복 부상 인원이 없습니다.')
    else:
        print_table(repeat_injury_soldiers)

    if '전후방구분' in df_injury.columns:
        injury_counts = df_injury['전후방구분'].value_counts().reindex(['전방', '후방'], fill_value=0)
        injury_summary = injury_counts.rename_axis('구분').reset_index(name='부상인원')
        injury_summary['비율(%)'] = (injury_summary['부상인원'] / len(df_injury) * 100).round(1)
        print('\n=== 전방·후방 부상 인원 비율 (전체 부상자 기준) ===')
        print_table(injury_summary)

    if '지역' in df_personal.columns and '지역' in df_injury.columns:
        print('\n=== 지역별 부상 현황 ===')
        print_table(get_region_injury_summary(df_personal, df_injury))
    
    # 부대별 리포트 포함 출력
    print_injury_report(df_personal, df_injury)
    
    # CSV 저장
    injury_csv_path.parent.mkdir(parents=True, exist_ok=True)
    prepare_injury_csv_data(df_injury).to_csv(
        injury_csv_path, index=False, encoding='utf-8-sig'
    )
    print(f"\n장병 부상 가상 데이터 저장 완료: {injury_csv_path}")


# ==========================================
# 6. PyTest 용 테스트 함수
# ==========================================
def test_injury_data_and_unit_summary():
    df_dummy = pd.DataFrame({
        '군번': [f'24-{i:09d}' for i in range(100)],
        '이름': [f'테스트_{i}' for i in range(100)],
        '지역': ['서울'] * 40 + ['강원'] * 60,
        '부대': ['A부대'] * 50 + ['B부대'] * 50,
        '계급': ['이병'] * 100,
    })
    
    df_inj = generate_injury_data(df_dummy, injury_rate=0.5, seed=123)
    csv_data = prepare_injury_csv_data(df_inj)
    unit_summary = get_unit_injury_summary(df_dummy, df_inj)
    
    assert len(df_inj) == 50
    assert csv_data.columns[0] == 'INJURY_ID'
    assert csv_data['INJURY_ID'].tolist() == list(range(1, len(df_inj) + 1))
    assert '총_부상건수' in unit_summary.columns
    assert '전체인원' in unit_summary.columns
    assert '부상률(%)' in unit_summary.columns
    assert '예방가능_비율(%)' in unit_summary.columns
    region_summary = get_region_injury_summary(df_dummy, df_inj)
    assert region_summary['부상인원'].sum() == df_inj['군번'].nunique()
    assert region_summary['부상건수'].sum() == len(df_inj)
    assert {'지역내_부상률(%)', '전체부상중_비율(%)'}.issubset(region_summary.columns)

    repeated_injuries = generate_injury_data(df_dummy, seed=123, injury_count=150)
    assert len(repeated_injuries) == 150
    assert repeated_injuries['군번'].duplicated().any()
    assert not repeated_injuries.duplicated(['군번', '부상세부부위']).any()
    assert len(prepare_injury_csv_data(repeated_injuries)) == 150

    repeated_region_summary = get_region_injury_summary(df_dummy, repeated_injuries)
    assert repeated_region_summary['부상건수'].sum() == 150
    assert repeated_region_summary['부상인원'].sum() == repeated_injuries['군번'].nunique()
    
    repeat_injury_soldiers = get_repeat_injury_soldiers(repeated_injuries)
    assert not repeat_injury_soldiers.empty
    assert (repeat_injury_soldiers['부상건수'] > 1).all()

if __name__ == '__main__':
    main()
