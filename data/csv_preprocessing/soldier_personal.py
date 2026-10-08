# %%
import random
import numpy as np
import pandas as pd


# 장병 생성 수
N_SAMPLES = 1000

# 지역별 가중치 설정
REGION_WEIGHTS = {
    '경기도': 9,
    '강원특별자치도': 9,
    '서울특별시': 9,
    '인천광역시': 9,
    '충청북도': 1,
    '충청남도': 1,
    '전북특별자치도': 1,
    '전남광주통합특별시': 1,
    '경상북도': 1,
    '경상남도': 1,
    '대전광역시': 1,
    '대구광역시': 1,
    '울산광역시': 1,
    '부산광역시': 1,
    '세종특별자치시': 1,
    '제주특별자치도': 1,
}

REGIONS = list(REGION_WEIGHTS)
REGION_PROBABILITIES = np.array(list(REGION_WEIGHTS.values()), dtype=float)
REGION_PROBABILITIES /= REGION_PROBABILITIES.sum()

UNITS_BY_REGION = {
    '경기도': ['경기_1사단', '경기_5사단', '경기_9사단'],
    '강원특별자치도': ['강원_2사단', '강원_7사단', '강원_12사단'],
    '서울특별시': ['수방사_1부대', '수방사_2부대'],
    '인천광역시': ['인천_17사단'],
    '충청북도': ['충북_37사단'],
    '충청남도': ['충남_32사단'],
    '전북특별자치도': ['전북_35사단'],
    '전남광주통합특별시': ['전남_31사단'],
    '경상북도': ['경북_45사단'],
    '경상남도': ['경남_39사단'],
    '대전광역시': ['대전_군수사'],
    '대구광역시': ['대구_50사단'],
    '울산광역시': ['울산_55사단'],
    '부산광역시': ['부산_53사단'],
    '세종특별자치시': ['세종_자운대'],
    '제주특별자치도': ['제주_9여단'],
}

RANKS = ['이병', '일병', '상병', '병장']
RANK_WEIGHTS = [2.5, 6.0, 6.0, 3.5]
RANK_PROBABILITIES = np.array(RANK_WEIGHTS) / sum(RANK_WEIGHTS)
RANK_ORDER = ['이병', '일병', '상병', '병장']
FRONT_REGIONS = ['경기도', '강원특별자치도', '서울특별시', '인천광역시']


# 헬퍼 함수들
# 이름 생성 함수
def get_rand_name():
    last_names = [
        '김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
        '한', '오', '서', '신', '권', '황', '안', '송', '류', '전',
        '홍', '고', '문', '양', '손', '배', '조', '백', '허', '유',
        '남', '심', '노', '정', '하', '곽', '성', '차', '주', '우',
        '남궁', '황보', '제갈', '사공', '선우', '서문', '독고',
    ]
    first_names = [
        '강', '건', '경', '고', '관', '나', '남', '노', '누', '다',
        '단', '담', '대', '덕', '도', '동', '라', '래', '로', '루',
        '마', '만', '명', '무', '문', '미', '민', '백', '범', '별',
        '병', '보', '빛', '사', '산', '상', '새', '서', '석', '선',
        '아', '안', '애', '우', '영', '예', '오', '옥', '완', '은',
        '진', '장', '재', '전', '정', '조', '종', '주', '준', '지',
        '찬', '창', '채', '천', '철', '초', '춘', '복', '치', '탐',
        '태', '택', '하', '한', '해', '혁', '현', '환', '혜', '호',
    ]

    last_name = random.choice(last_names)
    first_name = ''.join(random.sample(first_names, 2))
    return last_name + first_name

# 군번 생성 함수
def generate_unique_service_numbers(year_prefix: str, count: int):
    generated = set()
    while len(generated) < count:
        rand_num = f'{random.randint(0, 999999999):09d}'
        generated.add(f'{year_prefix}-{rand_num}')
    return list(generated)

# 월 그룹 할당 함수
def assign_month_group(rank):
    if rank == '이병':
        return random.randint(1, 3)
    if rank == '일병':
        return random.randint(4, 9)
    if rank == '상병':
        return random.randint(10, 15)
    return random.randint(16, 18)


# main: 메인 함수
def main():
    assigned_regions = list(
        np.random.choice(REGIONS, size=N_SAMPLES, p=REGION_PROBABILITIES)
    )
    assigned_units = [
        random.choice(UNITS_BY_REGION[region]) for region in assigned_regions
    ]
    assigned_ranks = list(
        np.random.choice(RANKS, size=N_SAMPLES, p=RANK_PROBABILITIES)
    )

    service_numbers = generate_unique_service_numbers('24', N_SAMPLES)
    df_personal = pd.DataFrame({
        '군번': service_numbers,
        '이름': [get_rand_name() for _ in range(N_SAMPLES)],
        '지역': assigned_regions,
        '부대': assigned_units,
        '계급': assigned_ranks,
    })
    df_personal['전후방구분'] = df_personal['지역'].apply(
        lambda region: '전방' if region in FRONT_REGIONS else '후방'
    )

    print(df_personal.head())

    print('[전후방 비율]')
    print(
        (df_personal['전후방구분'].value_counts(normalize=True) * 100)
        .round(1)
        .astype(str)
        + '%'
    )

    region_summary = pd.DataFrame({
        '인원수(명)': df_personal['지역'].value_counts(),
        '비율(%)': (df_personal['지역'].value_counts(normalize=True) * 100).round(1),
    }).sort_values(by='인원수(명)', ascending=False)
    print(region_summary[['인원수(명)', '비율(%)']])

    rank_summary = pd.DataFrame({
        '인원수(명)': df_personal['계급'].value_counts(),
        '비율(%)': (df_personal['계급'].value_counts(normalize=True) * 100).round(1),
    }).reindex(RANK_ORDER)
    print('[계급별 인원수 및 비율 집계]')
    print(rank_summary)

    print('중복 군번 개수:', df_personal['군번'].duplicated().sum())
    print('동명이인 수:', df_personal['이름'].duplicated().sum())

    df_personal.to_csv('soldier_personal.csv', index=False, encoding='utf-8-sig')
    print('장병 가상 데이터 저장 완')

if __name__ == '__main__':
    main()
# %%
