# data/scripts

데이터 전처리와 가상 데이터 생성 스크립트입니다. 모든 명령은 **프로젝트 루트**에서 실행합니다.

## 구성

| 파일·폴더 | 역할 |
|---|---|
| `main.py` | 진입점. 전처리 -> 합성 -> 분석 중 하나 또는 전체를 실행합니다. |
| `pipeline.py` | 세 영역이 함께 쓰는 `Step`과 실행기(`run_steps`) |
| `paths.py` | 입출력 경로 상수. 파이프라인과 각 모듈의 단독 실행이 같은 경로를 씁니다. |
| `logging_setup.py` | data 영역 전용 로그 설정. dashboard 쪽 로그와 섞이지 않습니다. |
| `utils.py` | 여러 모듈이 함께 쓰는 CSV 읽기·쓰기, 정의서 컬럼 고르기, 명령줄 인자 타입 |
| `preprocessing/` | 전처리 단계 모듈. 실행 순서는 `preprocessing/pipeline.py` |
| `analysis/` | 데이터를 바꾸지 않고 통계·탐색 결과만 내는 분석 스크립트. 실행 목록은 `analysis/pipeline.py` |
| `synthesis/` | 가상 장병 명단 생성, 최근 측정 연계·부상 위험 그룹 계산, 부상 기록 생성. 실행 순서는 `synthesis/pipeline.py` |
| `logs/` | 실행 로그 (`*.log`는 Git 제외) |
| `create_samples.py` | 최종 데이터에서 독자 참고용 샘플(`data/samples/`)을 만듭니다. 파이프라인과 따로 직접 실행합니다. |
| `운동기록-이상치-제거.md` | 운동기록 이상치 처리와 셔틀런 잠재능력 지표에 대한 검토 메모 |

## 실행

전체 순서는 **전처리 -> 합성 -> 분석**입니다. 합성은 전처리가 끝난 데이터를 바탕으로 하므로 둘을 동시에 실행하지 않습니다. `main.py`에 영역 이름을 주면 그 영역만, 생략하거나 `all`을 주면 세 영역을 순서대로 실행합니다. 앞 영역이 실패하면 뒤 영역은 실행하지 않습니다.

```powershell
conda run --no-capture-output -n kdt-project-1 python data/scripts/main.py                 # 전체 (all)
conda run --no-capture-output -n kdt-project-1 python data/scripts/main.py preprocessing   # 전처리만
conda run --no-capture-output -n kdt-project-1 python data/scripts/main.py analysis        # 분석만
```

`--no-capture-output`을 빼면 Windows에서 한글 출력 중 `UnicodeEncodeError`가 날 수 있습니다. `conda activate kdt-project-1` 후 `python data/scripts/main.py`로 실행해도 됩니다.

## 전처리

### 단계

앞 단계의 결과가 다음 단계의 입력이 됩니다.

| 순서 | 모듈 (`preprocessing/`) | 하는 일 | 출력 |
|---|---|---|---|
| 1 | `merge_raw_measurements` | 원본 55개에서 19~24세 남성 행을 모으고, 컬럼을 통합 정의서대로 맞춥니다. BMI는 키·체중으로 계산하고 운동 처방은 본운동만 남깁니다. 심폐지구력(`CARDIO`)은 세 종목의 VO₂max 출력 중 기록된 하나를 쓰고, 두 종목 이상이면 오래달리기 값을 쓰되 `KS_NFA_MERGED_MULTI_CARDIO.csv`에 따로 저장합니다. BMI 계산 불가 행과 트레드밀 심박수 기입 오류 행(3분·6분 심박수 < 안정시)을 제거합니다. | `intermediate/KS_NFA_MERGED.csv`, `intermediate/KS_NFA_MERGED_MULTI_CARDIO.csv` |
| 2 | `build_prescription_details` | 원본 통합 결과 전체(걸러 내기 전)의 운동 처방 목록을 쉼표로 나눠, 서로 다른 처방 이름마다 처방유형번호를 처음 나온 순서대로 1부터 붙입니다(번호 순서에 의미는 없음). 걸러 내기 전 데이터로 만들므로 최종 측정에 쓰이지 않는 처방 이름도 들어 있습니다. | `processed/KS_NFA_PRESCRIPTION_DETAIL.csv` |
| 3 | `remove_missings_and_outliers` | 결측값이 있는 행을 제거한 뒤, 이상치(횟수 종목인 교차윗몸일으키기의 소수 기록, 80 mL/kg/min을 넘는 심폐지구력)가 있는 행을 제거합니다. 운동 처방은 비어 있어도 제거하지 않습니다. | `intermediate/basic_refinement/` |
| 4 | `filter_enlistment_candidates` | 키·체중·BMI·체지방률이 입대 후보 범위 안에 있는 행만 남깁니다. | `intermediate/enlistment_filter/` |
| 5 | `select_three_measures` | 3회 이상 측정한 회원마다 측정 기록 3건을 고릅니다. 측정 간격이 모두 30일 이상(`MIN_INTERVAL_DAYS`)인 3건 조합 중 전체 기간이 가장 길고 두 간격이 가장 고른 조합을 고르고, 고른 3건의 첫·마지막 측정이 3년(`MAX_SPAN_DAYS`)을 넘는 회원은 제외합니다. 같은 날 중복 입력된 기록은 간격이 0일이라 함께 뽑히지 않습니다. 고른 3건에서 측정일이 지났는데 만나이가 줄었거나, 같은 날인데 나이가 다르거나, 흐른 연도에 비해 나이가 너무 많이(연도 차이 + 1살 초과) 또는 너무 적게(연도 차이 - 1살 미만) 늘어난 회원은 3건 모두 제외하고 `intermediate/KS_NFA_THREE_MEASURES_REMOVED_INCONSISTENT.csv`에 `제거 사유`와 함께 저장합니다(이전 `filter_age_time_inconsistencies` 모듈을 합침, 2026-10-26 기준 해당 회원 0명). | `intermediate/KS_NFA_THREE_MEASURES.csv`, `intermediate/KS_NFA_THREE_MEASURES_REMOVED_INCONSISTENT.csv` |
| 6 | `apply_final_definition` | 측정일 → 회원식별번호 → 측정일련번호 순으로 정렬해 `MESURE_ID`를 붙이고, 측정 컬럼을 체력 요소 이름(근력·근지구력·심폐지구력·유연성)으로 바꿔 측정 데이터(REFINED 정의서)와 운동 처방 데이터(처방 1개당 1행, PRESCRIPTION 정의서)로 나눠 저장합니다. 운동 처방에는 처방 이름 대신 2단계 상세 테이블의 처방유형번호를 넣습니다(상세 테이블에 없는 이름이 있으면 오류). 같은 측정 안의 중복 처방은 제거합니다. | `intermediate/KS_NFA_REFINED.csv`, `processed/KS_NFA_PRESCRIPTION.csv` |

`remove_3sigma_outliers`(3σ 이상치 제거)는 현재 파이프라인에서 쓰지 않습니다. 필요하면 단독으로 실행할 수 있습니다.

필터 단계의 폴더에는 통과 행(`passed.csv`)과 제거 행(`removed_*.csv`)이 함께 저장됩니다. 제거 행 파일에는 `제거 사유` 컬럼이 붙습니다.

### 단계 하나만 실행하기

각 모듈은 `paths.py`의 기본 경로로 단독 실행할 수 있습니다. 앞 단계의 결과 파일이 있어야 합니다.

```powershell
conda run --no-capture-output -n kdt-project-1 python data/scripts/preprocessing/remove_missings_and_outliers.py
```

### 로그

화면과 `logs/{yyyymmdd}_{hhmmss}_{실행 이름}.log`에 같은 내용이 남습니다. 실행 이름은 `main.py`로 실행하면 `main.{명령}`(예: `main.all`), 모듈을 단독 실행하면 `data/scripts` 기준 `하위폴더.모듈`(예: `preprocessing.merge_raw_measurements`)입니다. 각 줄에도 기록한 모듈이 같은 형식으로 찍힙니다. 단계별 입력·통과·제거 행 수가 기록되므로, 결과를 확인할 때 로그 파일을 보면 됩니다.

## 분석 스크립트 (`analysis/`)

데이터를 전처리하지 않고 통계·탐색 결과만 내는 스크립트입니다. 각 모듈은 `paths.py`의 기본 경로로 단독 실행합니다. `analysis/pipeline.py`의 실행 목록은 지금 비어 있어 `main.py analysis`는 아무것도 실행하지 않습니다.

| 모듈 | 하는 일 | 출력 |
|---|---|---|
| `summarize_official_cut_ratios` | 심폐지구력(`CARDIO`, VO₂max)에 공식 등급 컷(42.0/44.8/47.6)을 적용해 등급별 비율과 컷 미만 비율을 설계(30/50/70%)와 함께 정리합니다. | `intermediate/official_cut_ratios/` |
| `view_fitness_statistics` | 최종 측정 데이터(`processed/KS_NFA_PROCESSED.csv`)의 프로파일링 보고서를 만들고 한국어로 바꿉니다. 30분 넘게 걸립니다. | `intermediate/fitness_profile/` |

심폐지구력을 종목별로 비교하던 실험 스크립트(셔틀런 잠재 점수, 종목별 Z점수, 컷 기준 선형 변환, 종목 집단 비교)는 VO₂max 통일 결정 뒤 삭제했습니다. 코드는 Git 기록에 남아 있습니다.

```powershell
python data/scripts/analysis/summarize_official_cut_ratios.py
```

## 가상 장병·부상 데이터 생성 (`synthesis/`)

전처리가 끝난 뒤 다음 순서로 가상 데이터를 만듭니다. 장병 수는 전처리된 측정 데이터(`data/intermediate/KS_NFA_REFINED.csv`)의 **회원(`M_CODE`) 수**와 같습니다(회원 한 명당 장병 한 명). 저장하는 CSV의 컬럼 이름은 모두 정의서의 영문 이름입니다.

```powershell
python data/scripts/main.py synthesis                                       # 세 단계를 순서대로
python data/scripts/synthesis/generate_synthetic_personnel.py --seed 42     # 단계 하나만 (기본 경로)
python data/scripts/synthesis/link_fitness_and_injury_risk.py --injuries-per-person 0.3
python data/scripts/synthesis/generate_synthetic_injuries.py --seed 42
```

| 순서 | 모듈 | 결과 |
|---|---|---|
| 1 | `generate_synthetic_personnel` | 가상 장병 명단 `data/synthetic/SOLDIER_PERSONNEL.csv` (`SOLDIER_PERSONNEL_DEFINITION.csv`: 군번·이름·지역·부대·계급·전후방 구분) |
| 2 | `link_fitness_and_injury_risk` | 부상 위험 그룹 표 `processed/INJURY_RISK_GROUP.csv`, 최종 측정 데이터 `processed/KS_NFA_PROCESSED.csv`(FINAL: REFINED에서 `M_SEQ_NO`·`M_CODE`를 빼고 `SOLDIER_ID`·`INJURY_RISK_GROUP_ID`를 더함), 장병 연계 결과 `intermediate/synthesis/soldier_personal_injury_risk.csv`(3단계의 입력) |
| 3 | `generate_synthetic_injuries` | 부상 기록 `data/synthetic/SOLDIER_INJURY.csv` (`SOLDIER_INJURY_DEFINITION.csv`, 예방 가능 여부 `PREVENTABILITY`는 Y/N) |

**1. 장병 명단**: 군번·이름·지역·부대·계급을 만듭니다. 기본 시드는 42라 실행할 때마다 같은 명단이 나오고, `--seed`로 바꿀 수 있습니다(코드에서는 `seed=None`이면 매번 달라집니다).

**2. 최근 측정 연계와 부상 위험 그룹**: 회원마다 **가장 최근에 한 측정** 한 건(측정일이 가장 늦은 측정, 같은 날이면 `MESURE_ID`가 큰 측정)을 골라 `MESURE_ID` 순서로 장병에게 하나씩 연결합니다. 부상도 이 최근 측정을 바탕으로 생성합니다.

1. 원본 연구처럼 BMI와 심폐지구력을 **각각 백분위로** 하위 25%(`LOW`, 25 백분위수 이하)·중간 50%(`MODERATE`)·상위 25%(`HIGH`, 75 백분위수 이상)로 나눠 3 × 3 = 9개 **부상 위험 그룹**(`INJURY_RISK_GROUP_ID` 1~9)을 만듭니다. 번호는 BMI 구간 순서 × 심폐 구간 순서로 고정되어 1번이 BMI 하위·심폐 하위, 2번이 BMI 하위·심폐 중간, 9번이 BMI 상위·심폐 상위입니다. 백분위 경계는 **전체 측정**(최근 측정이 아닌 측정 포함)으로 정하고, 모든 측정과 장병에게 같은 경계를 씁니다.
2. 그룹마다 3×3 상대 위험도 표(`link_fitness_and_injury_risk.py`의 `INJURY_RISK[BMI 구간][심폐 구간]`. National Research Council(2006) *Assessing Fitness for Military Enlistment* Table 4-6의 남성 부상 위험(%)으로, 원자료는 Jones·Darakjy·Knapik(2004)의 Fort Jackson 기초군사훈련생 1997~2001. 표의 2마일 달리기 Fast·Medium·Slow를 심폐 HIGH·MODERATE·LOW에 대응)의 값을 장병 평균 위험도로 나눠 평균을 1로 맞춥니다(`RELATIVE_INJURY_RISK`).
3. 그룹의 기대 부상 건수 `EXPECTED_INJURY_COUNT = 0.3 × 상대 위험도`. 0.3은 선행 연구의 **장병 1명당 연간 부상 건수**(`INJURIES_PER_PERSON_YEAR`)이며 모든 측정이 같은 해에 이루어졌다고 가정합니다. 장병 N명의 기대 부상 건수 합은 0.3N입니다(그룹 표 값을 소수 6자리로 반올림한 만큼의 차이만 있음).

측정 테이블(FINAL)에는 λ 대신 그룹 번호만 두고, 그룹별 λ는 그룹 표에 둡니다. 같은 회원의 측정은 모두 같은 군번을 갖습니다. 최종 측정 데이터에는 국민체력100 식별자(회원식별번호 `M_CODE`, 측정일련번호 `M_SEQ_NO`)를 남기지 않고 군번으로만 장병과 연결합니다(연계 단계 안에서는 `M_CODE`로 회원을 찾습니다).

**3. 부상 기록**: 장병마다 **Poisson(`EXPECTED_INJURY_COUNT`)** 에서 부상 건수를 따로 뽑습니다(0, 1, 2, ...건). 서로 독립인 Poisson 변수의 합도 Poisson이므로 총 부상 건수는 **Poisson(0.3N)** 을 따르며, 정확히 0.3N건이 아니라 시드마다 조금씩 달라집니다(3,582명이면 평균 약 1,075건, 표준편차 약 33건). `EXPECTED_INJURY_COUNT`는 확률이 아니라 Poisson 평균이므로 1을 넘어도 됩니다. 부상 부위와 부위별 예방 가능 비율은 선행 논문 표(Table 4)의 빈도를 따르고, 한 장병이 같은 부위를 두 번 다치지 않게 부위 수(17)로 건수를 자릅니다(λ가 작아 실제로 잘리는 일은 사실상 없음). `--count`를 주면 Poisson 대신 정확히 그 건수를 λ에 비례해 나눕니다. 부대·지역·전후방별 부상 요약은 로그에 남습니다. 테스트(`tests/data/test_synthesis_injury_linkage.py`)가 총 건수의 평균과 분산이 모두 0.3N인지 확인합니다.

기대 부상 건수는 제공된 상대 위험도 표를 적용한 합성 시뮬레이션 값이며, 실제 개인의 의학적 부상 예측치가 아닙니다.

## 단계 추가·수정

1. `preprocessing/`에 `run(입력 경로, 출력 경로)`와 단독 실행용 `main()`을 가진 모듈을 만듭니다.
2. `paths.py`에 입출력 경로를 추가합니다.
3. 영역의 `pipeline.py`(`preprocessing/pipeline.py` 등)의 `build_steps()` 목록에 `Step`을 추가합니다.

모듈 안에 경로를 직접 쓰지 않고, `print` 대신 로거를 쓰고, 실패하면 예외를 던집니다. 자세한 규칙은 [docs/데이터-관리-요령.md](../../docs/데이터-관리-요령.md)의 "전처리 단계 작성 규칙"과 [docs/모듈-작성-요령.md](../../docs/모듈-작성-요령.md)를 따릅니다. 각 모듈의 `run()` 안에는 단계별 주석(`# 1. ...`)이 달려 있습니다.
