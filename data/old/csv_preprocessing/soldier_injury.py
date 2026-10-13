# %%
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
    ('Upper extremity', 'Head', 1, 0),
    ('Upper extremity', 'Shoulder', 68, 25),
    ('Upper extremity', 'Arm', 11, 0),
    ('Upper extremity', 'Elbow', 6, 2),
    ('Upper extremity', 'Forearm', 3, 1),
    ('Upper extremity', 'Wrist', 24, 6),
    ('Upper extremity', 'Hand/finger', 73, 8),
    ('Upper extremity', 'Ribs', 1, 0),
    ('Upper extremity', 'Back lower', 19, 13),
    ('Lower extremity', 'Pelvic region', 9, 2),
    ('Lower extremity', 'Hip', 3, 2),
    ('Lower extremity', 'Leg upper', 12, 4),
    ('Lower extremity', 'Knee', 183, 121),
    ('Lower extremity', 'Leg lower', 22, 7),
    ('Lower extremity', 'Ankle', 157, 108),
    ('Lower extremity', 'Foot/toe', 23, 4),
    ('Lower extremity', 'Not specified', 1, 0),
]

# 한글 매핑 디렉터리
LOCATION_KOR = {
    'Upper extremity': '상지(상체)',
    'Lower extremity': '하지(하체)',
}

SUB_LOCATION_KOR = {
    'Head': '머리',
    'Shoulder': '어깨',
    'Arm': '팔',
    'Elbow': '팔꿈치',
    'Forearm': '전두골/전복부',
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
        tablefmt='rounded_grid',
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

# %%
# ==========================================
# 3. 데이터 생성 함수 (Data Generation)
# ==========================================
def generate_injury_data(df_personal: pd.DataFrame, injury_rate: float = 0.3, seed: int = 42) -> pd.DataFrame:
    """
    기존 장병 데이터(df_personal)를 바탕으로 부상 기록 데이터프레임 생성
    - injury_rate: 전체 인원 중 부상을 입은 장병의 비율
    """
    np.random.seed(seed)
    random.seed(seed)

    # 1. 부상 대상 장병 추출
    n_total = len(df_personal)
    n_injured = int(n_total * injury_rate)
    
    injured_soldiers = df_personal.sample(n=n_injured, random_state=seed).copy()
    
    # 2. 논문 통계 기반 부상 위치 무작위 추출[cite: 1]
    location_indices = np.random.choice(
        len(INJURY_LOCATION_DATA),
        size=n_injured,
        p=LOCATION_PROBABILITIES
    )
    
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

# %%
# ==========================================
# 4. 요약 및 부대별 집계 함수 (Summaries & Unit Reports)
# ==========================================
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
    summary['부상인원'] = df_injury.groupby('지역').size().reindex(summary.index, fill_value=0)
    summary['지역내_부상률(%)'] = (summary['부상인원'] / summary['전체인원'] * 100).round(1)
    total_injuries = len(df_injury)
    summary['전체부상중_비율(%)'] = (
        (summary['부상인원'] / total_injuries * 100).round(1) if total_injuries else 0.0
    )
    return summary.sort_values(by='부상인원', ascending=False).reset_index()


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
def run():
    # 동적 경로 설정 (현재 파일 기준 최상위 프로젝트 루트 접근)
    # 현재 파일 위치: .../defense-dashboard/data/csv_preprocessing/soldier_injury.py (예시)
    # .parents[1] 또는 .parents[2]를 조절하여 프로젝트 루트(defense-dashboard) 경로 확보
    project_root = Path(__file__).resolve().parents[2]  # 환경에 맞춰 단계(index) 조절 가능

    # 입출력 경로 지정
    personal_csv_path = project_root / 'data' / 'csv_file' / 'csv_data' / 'soldier_personal_data.csv'
    injury_csv_path = project_root / 'data' / 'csv_file' / 'csv_data' / 'soldier_injury_data.csv'
    
    # 개인 인적사항 데이터 로드
    personal_csv = Path(__file__).resolve().parents[1] / 'csv_file' / 'csv_data' / 'soldier_personal_data.csv'
    try:
        df_personal = pd.read_csv(personal_csv, encoding='utf-8-sig')
    except FileNotFoundError:
        print(f"{personal_csv} 파일이 없어 임시 장병 데이터를 생성합니다.")
        df_personal = pd.DataFrame({
            '군번': [f'24-{i:09d}' for i in range(1000)],
            '이름': [f'장병_{i}' for i in range(1000)],
            '부대': [f'부대_{i % 10 + 1}' for i in range(1000)],
            '계급': ['일병'] * 1000,
        })

    # 부상 테이블 생성 (전체 인원의 30% 부상 발생)
    df_injury = generate_injury_data(df_personal, injury_rate=0.3, seed=42)

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
    df_injury.to_csv(injury_csv_path, index=False, encoding='utf-8-sig')
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
    unit_summary = get_unit_injury_summary(df_dummy, df_inj)
    
    assert len(df_inj) == 50
    assert '총_부상건수' in unit_summary.columns
    assert '전체인원' in unit_summary.columns
    assert '부상률(%)' in unit_summary.columns
    assert '예방가능_비율(%)' in unit_summary.columns
    region_summary = get_region_injury_summary(df_dummy, df_inj)
    assert region_summary['부상인원'].sum() == len(df_inj)
    assert {'지역내_부상률(%)', '전체부상중_비율(%)'}.issubset(region_summary.columns)


if __name__ == '__main__':
    run()
# %%
