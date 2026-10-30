# 운동 추천 생성

## 목적

등급·군집으로 구분되는 16개 체력 유형마다 운동 8개를 추천하여 총 128행의 CSV를 생성합니다. 운동명과 처방번호는 보유한 운동처방 상세정보를 사용하고, 군집별 상대 체력 편차와 상위 등급을 추천에 반영합니다.

## 구현 파일과 입력 자료

- 생성 코드: `data/scripts/analysis/clustering/build_exercise_recommendations.py`
- 유형표: `data/processed/FITNESS_TYPE.csv`
- 운동처방 상세정보: `data/processed/KS_NFA_PRESCRIPTION_DETAIL.csv`
- 군집별 편차: `data/processed/clustering/grade_1_relative_profile.csv`부터 `grade_4_relative_profile.csv`까지
- 사용 부위 명칭: `data/scripts/synthesis/generate_synthetic_injuries.py`의 `LOCATION_NAMES`

운동처방 상세정보에는 운동명과 처방번호가 있습니다. 체력 요소·동작 난이도·필요 장비·사용 부위는 생성 코드의 `RULES`에 수동으로 정의합니다. 현재 분류된 후보 40개에서 추천하며, 원본 전체 운동을 자동으로 분류하거나 처방 빈도 상위 운동을 선정하는 방식은 아닙니다.

기존 `EXERCISE_RECOMMENDATION_CATALOG.csv`는 현재 생성 과정에서 사용하지 않습니다.

## 유형별 운동 선택

| 유형 | 추천 기준 | 추천 개수 |
| --- | --- | --- |
| 약점형 | 유형명에 명시된 체력 요소만 선택 | 해당 요소 8개 |
| 강점형 | 유형명에 명시된 강점 요소를 제외하고 나머지 세 요소 선택 | 상대 편차가 낮은 순으로 4·2·2개 |

예를 들어 근력 약점형은 `IMPROVEMENT_FOCUS`가 모두 근력인 운동 8개를 추천합니다. 근력 강점형은 근지구력·심폐지구력·유연성 운동을 추천하며, 이 중 상대 편차가 가장 낮은 요소에 4개, 나머지에 각각 2개를 배분합니다.

`TYPE_NAME`은 장병의 체력 유형이고, `IMPROVEMENT_FOCUS`는 각 추천 운동이 보완하는 체력 요소입니다. 강점형에서 제외되지 않은 세 요소가 반드시 절대적인 약점이거나 기준 미달인 것은 아닙니다.

편차 자료의 `STRENGTH_RELATIVE`, `ENDURANCE_RELATIVE`, `CARDIO_RELATIVE`, `FLEXIBILITY_RELATIVE`를 각각 근력·근지구력·심폐지구력·유연성에 연결합니다. 이 값은 해당 종목 백분위와 다른 세 종목 백분위 간 평균 차이(%p)입니다. 동일 편차의 우선순위는 코드에 정의된 요소 순서를 따릅니다.

## 등급별 동작 난이도

| 평균 백분위 등급 | 우선 선택하는 동작 난이도 |
| --- | --- |
| 1등급 | 3: 도전 |
| 2등급 | 2: 일반 |
| 3등급 | 1: 기초 |
| 4등급 | 1: 기초 |

각 체력 요소 안에서 목표 난이도와의 차이가 작은 운동부터 선택합니다. 차이가 같으면 처방번호가 작은 운동을 우선합니다. 필요한 개수를 채우기 위해 다른 난이도의 운동도 포함될 수 있으며, 같은 유형 안에서 동일한 운동명은 중복 선택하지 않습니다.

난이도와 4·2·2 배분은 명시적으로 정한 규칙이며, 운동 효과 데이터로 학습하거나 검증한 최적 처방이 아닙니다. 개인별 횟수·세트·운동 강도·휴식 시간은 생성하지 않습니다.

## 사용 부위

운동별 주요 사용 부위를 `RULES`에 영문 키로 지정하고, `LOCATION_NAMES`의 한글 값으로 변환합니다. 결과 CSV에서는 운동명 바로 다음에 `BODY_PARTS`를 배치하고, 여러 부위는 ` | `로 구분합니다.

예: 팔굽혀펴기 → `어깨 | 팔 | 팔꿈치 | 손목 | 손/손가락`

사용 부위에는 주요 움직임에 관여하는 부위와 지지 관절이 포함됩니다. 부상 자료의 빈도·예방 가능 빈도로 사용 부위를 추론하지 않습니다. 이 매핑은 개인별 부상 위험이나 해당 운동의 금기 여부를 판정하는 값이 아닙니다.

## 출력 자료

출력 경로: `data/processed/FITNESS_TYPE_EXERCISE_RECOMMENDATIONS3.csv`

| 컬럼 | 의미 |
| --- | --- |
| `AVERAGE_PERCENTILE_GRADE` | 상위 평균 백분위 등급 |
| `CLUSTER` | 해당 등급 안의 군집 번호 |
| `TYPE_NAME`, `SOURCE_TYPE_NAME` | 연결된 체력 유형명 |
| `RECOMMENDATION_RANK` | 유형 내 추천 순서 1~8 |
| `PRESCRIPTION_TYPE_ID` | 원본 처방번호 |
| `RECOMMENDED_EXERCISE` | 원본 상세정보의 운동명 |
| `BODY_PARTS` | 사용 부위 |
| `IMPROVEMENT_FOCUS` | 보완할 체력 요소 |
| `EXERCISE_DIFFICULTY` | 수동 분류한 동작 난이도 |
| `REQUIRED_EQUIPMENT` | 필요 장비 |
| `RELATIVE_GAP` | 해당 체력 요소의 군집 상대 편차 |
| `TRAINING_GUIDANCE` | 등급별 선택 기준과 일반 안내 |
| `RECOMMENDATION_BASIS` | 등급·군집·편차·배분 근거 |
| `SOURCE_URL` | 국민체력100 홈페이지 참고 링크 |
| `SOURCE_FILE` | 운동명의 원본 파일명 |

`SOURCE_URL`은 운동별 분류나 난이도를 직접 입증하는 개별 출처가 아닙니다. 원본 운동명 연결은 처방번호와 `SOURCE_FILE`로 확인합니다.

## 실행과 파이프라인

분석 파이프라인 실행:

```powershell
python -m data.scripts.main analysis
```

분석 실행 순서는 다음과 같습니다.

1. 평균 백분위 등급별 측정 나누기
2. 측정별 등급·군집과 유형명 저장 및 상대 편차 자료 생성
3. 체력 유형별 추천 운동·사용 부위 저장
4. 장병별 다음 회차 미달 확률 예측

입력 자료가 이미 있으면 운동 추천만 다시 생성할 수 있습니다.

```powershell
python -m data.scripts.analysis.clustering.build_exercise_recommendations
```

실행하면 기존 추천 CSV를 갱신합니다. 원본 처방정보에 없는 후보 번호, 누락된 군집 편차, 해석할 수 없는 유형명, 잘못된 사용 부위 또는 부족한 후보가 있으면 오류를 발생시킵니다.

## 검증

```powershell
python -m pytest tests/data/test_exercise_recommendations.py tests/data/test_pipeline.py -q
```

테스트는 유형별 서로 다른 운동 8개, 약점형의 단일 요소 선택, 강점형의 강점 제외 및 4·2·2 배분, 원본 운동명 사용, 사용 부위 명칭, 등급별 난이도 차이, 입력 누락 오류를 확인합니다.
