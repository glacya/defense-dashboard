# data/scripts

데이터 전처리와 가상 데이터 생성 스크립트입니다. 모든 명령은 **프로젝트 루트**에서 실행합니다.

## 구성

| 파일·폴더 | 역할 |
|---|---|
| `main.py` | 진입점. 전처리 -> 합성 -> 분석 중 하나 또는 전체를 실행합니다. |
| `pipeline.py` | 세 영역이 함께 쓰는 `Step`과 실행기(`run_steps`) |
| `paths.py` | 입출력 경로 상수. 파이프라인과 각 모듈의 단독 실행이 같은 경로를 씁니다. |
| `logging_setup.py` | data 영역 전용 로그 설정. dashboard 쪽 로그와 섞이지 않습니다. |
| `preprocessing/` | 전처리 단계 모듈. 실행 순서는 `preprocessing/pipeline.py` |
| `analysis/` | 데이터를 바꾸지 않고 통계·탐색 결과만 내는 분석 스크립트. 실행 목록은 `analysis/pipeline.py` |
| `synthesis/` | 가상 장병 생성, 체력 연계·부상 확률 계산, 부상 데이터 생성 |
| `logs/` | 실행 로그 (`*.log`는 Git 제외) |
| `soldier_*_sample(100).py` | 이전 구조의 스크립트. 경로가 정리 전 폴더를 가리키므로 그대로는 동작하지 않습니다 (정비 예정). |
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
| 5 | `select_three_measures` | 3회 이상 측정한 회원마다 측정 기록 3건을 고릅니다. 측정 간격이 모두 30일 이상(`MIN_INTERVAL_DAYS`)인 3건 조합 중 전체 기간이 가장 길고 두 간격이 가장 고른 조합을 고르고, 고른 3건의 첫·마지막 측정이 3년(`MAX_SPAN_DAYS`)을 넘는 회원은 제외합니다. 같은 날 중복 입력된 기록은 간격이 0일이라 함께 뽑히지 않습니다. | `intermediate/KS_NFA_THREE_MEASURES.csv` |
| 6 | `apply_final_definition` | 측정일 → 회원식별번호 → 측정일련번호 순으로 정렬해 `MESURE_ID`를 붙이고, 측정 컬럼을 체력 요소 이름(근력·근지구력·심폐지구력·유연성)으로 바꿔 측정 데이터(FINAL 정의서)와 운동 처방 데이터(처방 1개당 1행, PRESCRIPTION 정의서)로 나눠 저장합니다. 운동 처방에는 처방 이름 대신 2단계 상세 테이블의 처방유형번호를 넣습니다(상세 테이블에 없는 이름이 있으면 오류). 같은 측정 안의 중복 처방은 제거합니다. | `processed/KS_NFA_PROCESSED.csv`, `processed/KS_NFA_PRESCRIPTION.csv` |

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

전처리 완료 후 다음 순서로 가상 장병 데이터를 만듭니다. 가상 장병 수는 기본적으로 처리된 체력 데이터(`data/processed/KS_NFA_PROCESSED.csv`)의 측정 행 수와 같으며, 생성 단계에서는 군번과 이름만 만듭니다.

```powershell
python data/scripts/synthesis/generate_synthetic_personnel.py
python data/scripts/synthesis/link_fitness_and_injury_risk.py --injury-rate 10
python data/scripts/synthesis/generate_synthetic_injuries.py
```

또는 전처리 결과가 이미 준비되어 있다면 `python data/scripts/main.py synthesis`로 세 단계를 순서대로 실행할 수 있습니다.

연계 단계는 장병 수와 체력 측정 행 수가 같은지 확인한 뒤, 각 체력 측정 행의 `MESURE_ID`를 기준으로 가상 장병 한 명씩 연결합니다. KMeans 표본 추출 없이 모든 측정 행을 한 번씩 사용하므로 체력값의 경험적 분포와 지표 간 조합을 그대로 보존합니다. 이는 원본 분포를 그대로 유지한다는 뜻이지, 데이터가 반드시 수학적인 정규분포를 따른다는 뜻은 아닙니다. 연결 후 기존 지역·부대·계급 가중치로 장병 속성을 부여합니다.

연계된 BMI·심폐지구력에 이미지의 BMI별·심폐지구력 사분위 등급별 4×3 상대 위험도 표를 적용합니다. 위험도를 해당 장병 집단의 평균 위험도로 나눈 뒤 `INJURY_PROBABILITY = injury_rate / 100 × RELATIVE_INJURY_RISK`를 계산합니다. 이 값은 이름과 달리 부상 생성 단계에서 **장병별 Poisson 분포의 평균 부상 건수(λ)** 로 사용되므로 같은 장병에게 여러 부상 기록이 생길 수 있습니다. 기본 `--injury-rate 10`은 장병 1명당 기대 부상 건수 평균 0.1을 뜻하며, 전체 기대 부상 건수는 확률값의 합과 같지만 실제 건수는 달라집니다. 확률 계산 결과가 1을 넘는 높은 기준 비율은 오류로 처리합니다.

결과는 모두 Git에서 제외되는 `data/intermediate/synthesis/` 아래에 저장됩니다.

| 순서 | 스크립트 | 결과 |
|---|---|---|
| 1 | `generate_synthetic_personnel.py` | `soldier_personal_data.csv` |
| 2 | `link_fitness_and_injury_risk.py` | BMI·CARDIO·범주·상대 위험도·개인별 부상 확률이 추가된 `soldier_personal_injury_risk.csv` |
| 3 | `generate_synthetic_injuries.py` | 개인별 `INJURY_PROBABILITY`를 Poisson 평균 건수로 사용해 생성한 `SOLDIER_INJURY.csv` |

모든 단계의 입력·출력은 `--personnel-csv`, `--fitness-csv`, `--personal-csv`, `--output` 옵션으로 바꿀 수 있습니다. 재현 가능한 연계를 위해 `link_fitness_and_injury_risk.py`와 부상 생성기는 기본 난수 시드 42를 사용합니다. 이 확률은 제공된 상대 위험도 표를 적용한 합성 시뮬레이션 값이며, 실제 개인의 의학적 부상 예측치가 아닙니다.

## 단계 추가·수정

1. `preprocessing/`에 `run(입력 경로, 출력 경로)`와 단독 실행용 `main()`을 가진 모듈을 만듭니다.
2. `paths.py`에 입출력 경로를 추가합니다.
3. 영역의 `pipeline.py`(`preprocessing/pipeline.py` 등)의 `build_steps()` 목록에 `Step`을 추가합니다.

모듈 안에 경로를 직접 쓰지 않고, `print` 대신 로거를 쓰고, 실패하면 예외를 던집니다. 자세한 규칙은 [docs/데이터-관리-요령.md](../../docs/데이터-관리-요령.md)의 "전처리 단계 작성 규칙"과 [docs/모듈-작성-요령.md](../../docs/모듈-작성-요령.md)를 따릅니다. 각 모듈의 `run()` 안에는 단계별 주석(`# 1. ...`)이 달려 있습니다.
