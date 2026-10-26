# data/definitions

데이터 파일의 **컬럼 정의서**를 모아 둔 폴더입니다. 정의서는 Git에 올리는 몇 안 되는 데이터 파일입니다([데이터 관리 요령](../../docs/데이터-관리-요령.md) 참고).

정의서는 모두 같은 형식의 CSV입니다. 한 행이 한 컬럼을 설명하고, 행 순서가 곧 데이터 파일의 컬럼 순서입니다.

| 열 | 내용 |
|---|---|
| 순서 | 컬럼 순서 |
| 영문속성명 | 데이터 파일의 컬럼 이름. 원본 정의서만 `컬럼영문명` |
| 컬럼한글명 | 컬럼의 한글 이름(화면·문서 표시용) |
| 데이터타입, 길이 | DB에 넣을 때의 자료형과 길이. 예: `VARCHAR` 20, `DECIMAL` `5,2`, `INT`(길이 빈칸) |
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
| `KS_NFA_FINAL_DEFINITION.csv` | 13 | 최종 측정 데이터 `processed/KS_NFA_PROCESSED.csv`. REFINED에서 국민체력100 식별자를 빼고 군번 `SOLDIER_ID`와 부상 위험 그룹 번호 `INJURY_RISK_GROUP_ID`를 붙입니다. 사람은 `SOLDIER_ID`, 측정은 `MESURE_ID`로 구분합니다. | 합성 2단계 출력 |
| `KS_NFA_PRESCRIPTION_DEFINITION.csv` | 3 | 운동 처방 `processed/KS_NFA_PRESCRIPTION.csv`. 측정 하나의 처방 목록을 처방 하나당 한 행으로 나눈 것(`PRESCRIPTION_ID`, `MESURE_ID`, `PRESCRIPTION_TYPE_ID`). | 전처리 6단계 출력 |
| `KS_NFA_PRESCRIPTION_DETAIL_DEFINITION.csv` | 2 | 운동 처방 상세 `processed/KS_NFA_PRESCRIPTION_DETAIL.csv`. 처방유형번호와 처방 이름(`PRESCRIPTION`). | 전처리 2단계 출력 |

### 가상 장병·부상 데이터 (합성 단계)

| 파일 | 컬럼 수 | 내용 | 쓰는 곳 |
|---|---|---|---|
| `SOLDIER_PERSONNEL_DEFINITION.csv` | 6 | 가상 장병 명단 `synthetic/SOLDIER_PERSONNEL.csv`: 군번, 이름, 지역, 부대, 계급, 전후방 구분. | 합성 1단계 출력 |
| `INJURY_RISK_GROUP_DEFINITION.csv` | 4 | 부상 위험 그룹 표 `processed/INJURY_RISK_GROUP.csv`: BMI 구간 × 심폐지구력 구간(각각 백분위 3구간) 9개 그룹의 기대 부상 건수(Poisson λ). | 합성 2단계 출력 |
| `SOLDIER_INJURY_DEFINITION.csv` | 6 | 가상 부상 기록 `synthetic/SOLDIER_INJURY.csv`: 부상식별번호, 군번, 부상 대분류·세부 부위, 예방 가능 여부(Y/N), 심각도. | 합성 3단계 출력 |

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
