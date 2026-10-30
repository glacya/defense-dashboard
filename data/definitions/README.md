# data/definitions

데이터 파일의 **컬럼 정의서**를 모아 둔 폴더입니다. 정의서는 Git에 올리는 몇 안 되는 데이터 파일입니다([데이터 관리 요령](../../docs/데이터-관리-요령.md) 참고).

정의서는 모두 같은 형식의 CSV입니다. 한 행이 한 컬럼을 설명하고, 행 순서가 곧 데이터 파일의 컬럼 순서입니다.

| 열 | 내용 |
|---|---|
| 순서 | 컬럼 순서 |
| 영문속성명 | 데이터 파일의 컬럼 이름. 원본 정의서만 `컬럼영문명` |
| 컬럼한글명 | 컬럼의 한글 이름(화면·문서 표시용) |
| 데이터타입, 길이 | DB에 넣을 때의 자료형과 길이. 예: `VARCHAR` 20, `DECIMAL` `5,2`, `INT`(길이 빈칸). 기록 테이블용으로 `DATE`, `TIMESTAMP`(시간대 포함), `SERIAL`(DB가 매기는 자동 번호)도 씀 |
| PK여부, NOT NULL여부 | 기본 키 여부, 빈값 허용 여부(`Y`/`N`) |
| 데이터 상품명 | 값의 출처. `자동 부여`는 파이프라인이 새로 매기는 번호 |

코드는 `data.scripts.utils.load_definition_columns()`로 `영문속성명`을 읽어, 저장할 컬럼과 순서를 정합니다. 경로 상수는 `data/scripts/paths.py`의 `DEFINITION_*`입니다.

## 정의서 목록

### 국민체력100 측정 데이터 (전처리 단계 순서)

| 파일 | 컬럼 수 | 내용 | 쓰는 곳 |
|---|---|---|---|
| `KS_NFA_RAW_DEFINITION.csv` | 57 | 원본 월별 파일(`KS_NFA_FTNESS_MESURE_*.csv`)의 컬럼. 제공처 정의서라 `컬럼영문명` 열을 씁니다. | 전처리 1단계 입력 |
| `KS_NFA_MERGED_DEFINITION.csv` | 13 | 원본 통합 결과 `intermediate/KS_NFA_MERGED.csv`. 19~24세 남성, 영문 약어 컬럼(`M_CODE`, `REL_GRIP`, `CROSS_UP`, `SIT_REACH`, 심폐 3종목을 하나로 합친 `CARDIO`, 운동 처방 `MVM_PRSCRPTN_CN` 등). | 전처리 1단계 출력 |
| `KS_NFA_REFINED_DEFINITION.csv` | 13 | 전처리 결과 `intermediate/KS_NFA_REFINED.csv`. 새 PK `MESURE_ID`를 붙이고 측정 컬럼을 체력 요소 이름(`STRENGTH`, `ENDURANCE`, `CARDIO`, `FLEXIBILITY`)으로 바꿉니다. 국민체력100 식별자(`M_CODE`, `M_SEQ_NO`)는 아직 남아 있습니다. | 전처리 6단계 출력, 합성 단계 입력 |
| `KS_NFA_FINAL_DEFINITION.csv` | 13 | 최종 측정 데이터 `processed/KS_NFA_PROCESSED.csv`. REFINED에서 국민체력100 식별자를 빼고 군번 `SOLDIER_ID`와 연간 기대 부상 건수 `EXPECTED_INJURY_COUNT_PER_YEAR`(Poisson λ, BMI·심폐지구력 백분위로 선형 보간)를 붙입니다. 사람은 `SOLDIER_ID`, 측정은 `MESURE_ID`로 구분합니다. | 합성 2단계 출력 |
| `KS_NFA_PRESCRIPTION_DEFINITION.csv` | 3 | 운동 처방 `processed/KS_NFA_PRESCRIPTION.csv`. 측정 하나의 처방 목록을 처방 하나당 한 행으로 나눈 것(`PRESCRIPTION_ID`, `MESURE_ID`, `PRESCRIPTION_TYPE_ID`). | 전처리 6단계 출력 |
| `KS_NFA_PRESCRIPTION_DETAIL_DEFINITION.csv` | 2 | 운동 처방 상세 `processed/KS_NFA_PRESCRIPTION_DETAIL.csv`. 처방유형번호와 처방 이름(`PRESCRIPTION`). | 전처리 2단계 출력 |

### 가상 장병·부상 데이터 (합성 단계)

| 파일 | 컬럼 수 | 내용 | 쓰는 곳 |
|---|---|---|---|
| `SOLDIER_PERSONNEL_DEFINITION.csv` | 6 | 가상 장병 명단 `synthetic/SOLDIER_PERSONNEL.csv`: 군번, 이름, 지역, 부대, 계급, 전후방 구분. | 합성 1단계 출력 |
| `SOLDIER_INJURY_DEFINITION.csv` | 6 | 가상 부상 기록 `synthetic/SOLDIER_INJURY.csv`: 부상식별번호, 군번, 부상 대분류·세부 부위, 예방 가능 여부(Y/N), 심각도. | 합성 3단계 출력 |

### 체력 유형·미달 예측 (분석 단계)

| 파일 | 컬럼 수 | 내용 | 쓰는 곳 |
|---|---|---|---|
| `MEASUREMENT_CLASSIFICATION_DEFINITION.csv` | 11 | 측정별 평균 백분위 등급·군집·종목 등급·백분위 `processed/MEASUREMENT_CLASSIFICATION.csv`: 측정식별번호(PK, 측정 FK), 평균백분위등급, 군집번호(둘을 묶어 유형명 표 FK), 종목별 체력 등급 4개(`{종목}_GRADE`, `fitness_standards.fitness_grade`: 1~3등급, 3등급 하한 미만 0), 종목별 백분위 4개(`{종목}_PERCENTILE`, 전체 측정 안 `rank(pct=True)*100`, DECIMAL(5,2)). 대시보드가 등급·백분위를 다시 계산하지 않도록 저장. | 분석 2단계 출력 |
| `FITNESS_TYPE_DEFINITION.csv` | 7 | 등급·군집별 유형명 `processed/FITNESS_TYPE.csv`: 평균백분위등급·군집번호(둘을 묶어 PK), 유형명, 종목별 상대 편차 4개(`{종목}_RELATIVE`, 군집 중심에서 그 종목 백분위 − 나머지 세 종목 백분위의 평균, DECIMAL(5,2); `processed/clustering/grade_*_relative_profile.csv`와 같은 값). | 분석 2단계 출력 |
| `EXERCISE_CLASSIFICATION_DEFINITION.csv` | 4 | 운동 분류 `processed/EXERCISE_CLASSIFICATION.csv`(사람이 분류한 처방 40개, `build_exercise_recommendations.RULES`): 처방유형번호(PK, 처방 상세 FK), 향상 체력 요소(근력/근지구력/심폐지구력/유연성), 동작 난이도(1 기초·2 일반·3 도전), 필요 장비. | 분석 3단계 출력 |
| `EXERCISE_BODY_PART_DEFINITION.csv` | 2 | 운동별 사용 부위 `processed/EXERCISE_BODY_PART.csv`: 처방유형번호(운동 분류 FK)·사용 부위(둘을 묶어 PK). 부위 이름은 부상 기록 `INJURY_LOCATION`과 같은 한글 이름. | 분석 3단계 출력 |
| `RECOMMENDED_EXERCISE_DEFINITION.csv` | 4 | 체력 유형별 추천 운동 `processed/RECOMMENDED_EXERCISE.csv`(16유형 × 8 = 128행): 평균백분위등급·군집번호(유형 표 FK)·추천순위 1~8(셋을 묶어 PK), 처방유형번호(운동 분류 FK). 운동 이름·속성·유형명은 JOIN으로 가져옴. | 분석 3단계 출력 |
| `SOLDIER_FAILURE_PROBABILITY_DEFINITION.csv` | 2 | 장병별 다음 회차 미달 확률 `processed/SOLDIER_FAILURE_PROBABILITY.csv`: 군번(PK, 장병 FK), 미달 확률(0~1). | 분석 4단계 출력 |

### 후속조치 기록 (대시보드 입력, 2026-10-30 초안)

데이터 파이프라인이 만드는 CSV가 없고, 대시보드 사용자가 입력하는 기록입니다(`paths.DB_RECORD_TABLES`). `setup_database.py`는 이 테이블을 없을 때만 만들고 재적재해도 지우거나 비우지 않습니다(구조를 바꿀 때는 DB에서 직접 DROP). 테이블 이름 키는 정의서 이름에서 `_DEFINITION`을 뗀 것(`FITNESS_FOLLOWUP` 등)입니다. 지금 CSV 모드는 `dashboard/py/management_store.py`가 `MANAGEMENT_DIR/{종류}.csv`에 씁니다. 기록식별번호는 `SERIAL`(DB가 매기는 정수), 날짜는 `DATE`, 저장 시각은 `TIMESTAMP`(시간대 포함, `TIMESTAMPTZ`)입니다. 사용자가 필요한 컬럼만 남길 예정입니다.

| 파일 | 컬럼 수 | 내용 | 쓰는 곳 |
|---|---|---|---|
| `FITNESS_FOLLOWUP_DEFINITION.csv` | 11 | 체력 상담·후속조치 기록(현재 `followup_records.csv`, DB `fitness_followups`): 기록식별번호(PK, 자동 번호), 군번(장병 FK, 장병과 이어지는 유일한 컬럼), 최초저장·최종수정 시각, 담당자, 상담일, 상담 내용, 후속조치 내용, 다음 점검일, 진행 상태(점검 대기/진행 중/완료/취소), 완료일. | p07 체력 지도·후속조치(장병별·그룹별 등록), 메인 화면 완료율 |
| `INJURY_FOLLOWUP_DEFINITION.csv` | 12 | 부상 후속조치 기록(현재 `injury_followup.csv`, DB `injury_followups`): 기록식별번호(PK, 자동 번호), 최초저장·최종수정 시각, 부상식별번호(부상 FK, 장병은 부상 기록으로 JOIN), 확인일, 후속조치 상태, 후속조치 내용, 회복 상태(확인 중/회복 중/회복 확인/제한 지속/미확인), 운동 제한 내용·시작일·종료일, 비고. | p08 부상 후속조치, 메인 화면 완료율 |

## 컬럼 정의서가 아닌 파일

### `grade3_male_19_24.csv` (추후 제거 예정)

19~24세 남성 체력 **3등급 기준표**입니다. 컬럼 정의서가 아니라 기준값 표라 형식이 다릅니다(`sex, age_min, age_max, exercise, description, rule, min_value, max_value, unit`).

| 항목 | 기준 |
|---|---|
| 근력(`STRENGTH`) | 51.8% 이상 |
| 근지구력(`ENDURANCE`) | 42회 이상 |
| 심폐지구력(`CARDIO`, VO₂max) | 42 ml/kg/min 이상 |
| 유연성(`FLEXIBILITY`) | 6.1cm 이상 |
| BMI | 18.5 이상 25 미만 |
| 체지방률(`BODY_FAT_PERCENTAGE`) | 7% 초과 27% 미만 |

같은 값을 코드로 옮긴 `data/scripts/fitness_standards.py`가 이 파일을 대신합니다. 저장소의 코드(`data/experiments`, `data/scripts/analysis`)는 이제 이 파일을 읽지 않고 `fitness_standards.grade3_standards()`(이 CSV를 읽은 것과 같은 표)와 `grade_cut_table()`을 씁니다. 2026-10-26에 한 번 지웠다가, 팀원 작업을 위해 다시 넣어 두었습니다. 기준값을 바꿀 때는 `fitness_standards.py`를 고치고, 이 파일은 지울 때까지 같은 값으로 유지합니다.
