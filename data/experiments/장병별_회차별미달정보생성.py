"""장병별 첫 3회 측정의 종목 미달·취약 상태와 개선·악화·유지를 집계한다.

실행: python data/experiments/장병별_회차별미달정보생성.py
이 코드의 취약 기준은 미달 종목 1개 이상이다.
"""
from pathlib import Path
import pandas as pd
from data.scripts.fitness_standards import grade3_standards

# ============================================================
# 1. 파일 위치 설정
# ============================================================

# 프로젝트의 최상위 폴더(defense-dashboard) 찾기
ROOT = Path(__file__).resolve().parents[2]

# 체력측정 데이터 파일
DATA_PATH = ROOT / 'data/processed/KS_NFA_PROCESSED.csv'

# 남성 19~24세의 체력 3등급 기준표

# 분석 결과를 저장할 폴더
OUTPUT_DIR = ROOT / 'data/experiments/results'

# 결과 폴더가 없으면 자동 생성
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# 장병을 구분하는 고유번호
PERSON_COL = 'SOLDIER_ID'

# 나이 컬럼
AGE_COL = 'AGE'

# 심폐지구력은 전처리에서 통합한 CARDIO(VO₂max)를 사용
CARDIO_COLS = ['CARDIO']

# 반드시 측정해야 하는 3개 종목
REQUIRED_COLS = ['STRENGTH', 'ENDURANCE', 'FLEXIBILITY']

# 전체 측정 컬럼
ALL_MEASURE_COLS = REQUIRED_COLS + CARDIO_COLS

# 최종적으로 평가할 4개 체력종목
AREA_COLS = [
    'strength_risk',       # 근력 미달 여부
    'endurance_risk',      # 근지구력 미달 여부
    'cardio_risk',         # 심폐지구력 미달 여부
    'flexibility_risk'     # 유연성 미달 여부
]


# ============================================================
# 2. 데이터와 3등급 기준표 불러오기
# ============================================================

# 체력측정 데이터 읽기
# SOLDIER_ID는 숫자가 아닌 문자열로 읽어서 고유번호를 유지
df = pd.read_csv(DATA_PATH, dtype={PERSON_COL: 'string'})

# 체력 3등급 기준표 읽기
standards = grade3_standards()


# 분석에 필요한 컬럼이 모두 있는지 확인
missing = sorted(
    set([PERSON_COL, AGE_COL] + ALL_MEASURE_COLS)
    - set(df.columns)
)

# 필요한 컬럼이 없으면 오류 발생
if missing:
    raise ValueError(f'측정 데이터에 없는 컬럼: {missing}')


# 기준표에 필요한 컬럼 확인
needed_std = {
    'sex', 'age_min', 'age_max',
    'exercise', 'rule', 'min_value', 'max_value'
}

if not needed_std.issubset(standards.columns):
    raise ValueError(
        f'기준표에 없는 컬럼: {sorted(needed_std - set(standards.columns))}'
    )


# 남성(M), 19~24세 기준만 선택
standards = standards[
    (standards['sex'].astype(str).str.upper() == 'M') &
    (standards['age_min'] == 19) &
    (standards['age_max'] == 24)
].copy()


# 동일한 체력종목이 기준표에 중복되어 있는지 확인
if standards['exercise'].duplicated().any():
    raise ValueError('기준표에 동일한 종목이 중복되어 있습니다.')


# 체력종목 이름을 기준으로 기준값을 쉽게 조회하도록 설정
std = standards.set_index('exercise')


# 측정할 종목이 기준표에 모두 있는지 확인
if not set(ALL_MEASURE_COLS).issubset(std.index):
    raise ValueError(
        f'기준표에 없는 종목: {sorted(set(ALL_MEASURE_COLS) - set(std.index))}'
    )


# 측정값과 나이를 숫자형으로 변환
# 숫자로 바꿀 수 없는 값은 NaN으로 처리
for col in ALL_MEASURE_COLS + [AGE_COL]:
    df[col] = pd.to_numeric(df[col], errors='coerce')


# ============================================================
# 3. 체력측정을 3회 이상 받은 장병 추출
# ============================================================

# 원본 CSV에서 각 행이 몇 번째 위치에 있었는지 저장
# 같은 날짜의 측정은 원본 행 순서로 구분
df['_source_order'] = range(len(df))


# 19~24세이고 장병 고유번호가 있는 데이터만 선택
df = df[
    df[AGE_COL].between(19, 24) &
    df[PERSON_COL].notna()
].copy()


# 장병별 체력측정 횟수 계산
counts = df.groupby(PERSON_COL).size()


# 체력측정을 3회 이상 받은 장병만 선택
eligible_ids = counts[counts >= 3].index


# 해당 장병들의 모든 측정 데이터 추출
three = df[df[PERSON_COL].isin(eligible_ids)].copy()


# 장병 고유번호와 원본 행 순서대로 정렬
three['_measure_date'] = pd.to_datetime(three['MESURE_DE'].astype('string').str.replace(r'\.0$', '', regex=True), format='%Y%m%d', errors='coerce')
if three['_measure_date'].isna().any():
    raise ValueError('측정일이 잘못된 기록이 있습니다.')
three = three.sort_values([PERSON_COL, '_measure_date', '_source_order'])


# 장병별로 측정 회차 번호 부여
# 첫 번째 측정 = 1차, 두 번째 = 2차, 세 번째 = 3차
three['round'] = three.groupby(PERSON_COL).cumcount() + 1


# 4회 이상 측정한 장병도 처음 3회만 사용
three = three[three['round'] <= 3].copy()


# ============================================================
# 4. 체력종목별 3등급 미달 여부 계산
# ============================================================

# 측정값을 3등급 기준과 비교하는 함수
#
# True  : 3등급 기준 미달
# False : 3등급 기준 충족
# NA    : 측정값이 없어 비교할 수 없음

def judge(series, exercise):

    # 해당 체력종목의 3등급 기준 가져오기
    rule = std.loc[exercise]

    # 측정값을 숫자로 변환
    v = pd.to_numeric(series, errors='coerce')

    # 기준값의 비교 방식
    kind = rule['rule']

    # 최소 기준값
    lower = rule['min_value']

    # 최대 기준값
    upper = rule['max_value']

    # 미달 여부를 저장할 변수
    fail = pd.Series(False, index=v.index)

    # 최소 기준값 이상이면 충족
    # 예: 기준 42회 → 41회 미달, 42회 충족
    if kind == 'min_inclusive':

        if pd.isna(lower):
            raise ValueError(f'{exercise}: 최소 기준값이 없습니다.')

        fail = v < float(lower)

    # 최소값 이상, 최대값 미만이어야 충족
    elif kind == 'min_inclusive_max_exclusive':

        fail = (v < float(lower)) | (v >= float(upper))

    # 최소값 초과, 최대값 미만이어야 충족
    elif kind == 'min_exclusive_max_exclusive':

        fail = (v <= float(lower)) | (v >= float(upper))

    else:
        raise ValueError(f'{exercise}: 알 수 없는 rule={kind}')

    # 측정값이 없는 경우에는 NA로 처리
    return fail.where(v.notna(), pd.NA).astype('boolean')


# 중복 컬럼을 만들지 않고 최종 출력 이름으로 직접 판정한다.
for col in ALL_MEASURE_COLS:
    three[f'{col.lower()}_risk'] = judge(three[col], col)

# ============================================================
# 6. 회차별 3등급 미달 체력종목 개수 계산
# ============================================================




# 4개 체력종목 중 3등급 기준에 미달한 종목 개수
# True=1, False=0으로 변환하여 합계 계산
three['weak_count'] = (
    three[AREA_COLS]
    .fillna(False)
    .astype(int)
    .sum(axis=1)
)


# 기본 판정은 판정불가
three['risk_status'] = '판정불가'


# 4개 체력종목 모두 평가했는지 확인
complete = three[AREA_COLS].notna().all(axis=1)


# 4개 모두 평가했고 미달 종목이 0개라면 정상
three.loc[
    complete & (three['weak_count'] == 0),
    'risk_status'
] = '정상'


# 4개 모두 평가했고 미달 종목이 1개 이상이면 취약
three.loc[
    complete & (three['weak_count'] >= 1),
    'risk_status'
] = '취약'


# ============================================================
# 7. 장병별 1차·2차·3차 측정 결과 비교
# ============================================================

# 한 장병의 1차·2차·3차 미달 개수를 한 행으로 정리
#
# 예:
# SOLDIER_ID   weak_1   weak_2   weak_3
# A001        3        2        1

summary = three.pivot(
    index=PERSON_COL,
    columns='round',
    values='weak_count'
)

# 컬럼명을 알아보기 쉽게 변경
summary = summary.rename(columns={
    1: 'weak_1',
    2: 'weak_2',
    3: 'weak_3'
})


# 각 회차의 정상/취약/판정불가 결과 정리
status = three.pivot(
    index=PERSON_COL,
    columns='round',
    values='risk_status'
)

status = status.rename(columns={
    1: 'status_1',
    2: 'status_2',
    3: 'status_3'
})


# 미달 개수와 판정 결과를 하나의 데이터프레임으로 합치기
summary = summary.join(status).reset_index()


# 1차·2차·3차 모두 평가 가능한 장병인지 확인
complete_3 = summary[
    ['status_1', 'status_2', 'status_3']
].ne('판정불가').all(axis=1)


# 처음에는 비교불가로 설정
summary['change_type'] = '비교불가'


# 1차보다 3차의 미달 개수가 감소하면 개선
summary.loc[
    complete_3 & (summary['weak_3'] < summary['weak_1']),
    'change_type'
] = '개선'


# 1차보다 3차의 미달 개수가 증가하면 악화
summary.loc[
    complete_3 & (summary['weak_3'] > summary['weak_1']),
    'change_type'
] = '악화'


# 1차와 3차의 미달 개수가 같으면 유지
summary.loc[
    complete_3 & (summary['weak_3'] == summary['weak_1']),
    'change_type'
] = '유지'


# 가장 최근인 3차 측정에서 취약한 장병인지 확인
#
# True  : 3차에 미달 종목이 1개 이상
# False : 3차에 미달 종목이 0개
summary['current_risk'] = summary['status_3'].map({
    '취약': True,
    '정상': False
})


# 1차·2차·3차 모두 취약했는지 확인
summary['persistent_risk'] = pd.NA

summary.loc[complete_3, 'persistent_risk'] = summary.loc[
    complete_3,
    ['status_1', 'status_2', 'status_3']
].eq('취약').all(axis=1)


# ============================================================
# 8. 분석 결과 CSV 파일 저장
# ============================================================

# 회차별 상세 결과 파일
by_round_path = OUTPUT_DIR / 'fitness_risk_by_round.csv'

# 장병별 3회 측정 비교 결과 파일
summary_path = OUTPUT_DIR / 'fitness_risk_summary.csv'


# 회차별 상세 결과 저장: 내부 계산용·중복 판정 컬럼은 제외한다.
three.drop(columns=[
    '_source_order', '_measure_date',
]).to_csv(
    by_round_path,
    index=False,
    encoding='utf-8-sig'
)


# 장병별 요약 CSV에는 식별자와 회차별 미달 종목 수만 저장
summary[[PERSON_COL, 'weak_1', 'weak_2', 'weak_3']].to_csv(
    summary_path,
    index=False,
    encoding='utf-8-sig'
)


# ============================================================
# 9. 분석 결과 출력
# ============================================================

# 분석 대상 장병 수
print(f'3회 이상 측정한 사람: {len(summary)}명')


# 1차·2차·3차별 정상/취약/판정불가 인원
print('\n회차별 판정 인원:')
print(
    three.groupby(['round', 'risk_status'])
    .size()
    .unstack(fill_value=0)
)


# 개선·악화·유지 인원
print('\n변화 유형:')
print(summary['change_type'].value_counts())


# 저장된 결과 파일 위치
print('\n결과 파일:')
print(by_round_path)
print(summary_path)


# 측정 순서와 남성 표본 여부 확인 안내
# print('\n주의: 남성 여부와 CSV 행 순서가 실제 측정 순서인지 확인하세요.')
