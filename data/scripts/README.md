# data/scripts

데이터 전처리와 가상 데이터 생성 스크립트입니다. 모든 명령은 **프로젝트 루트**에서 실행합니다.

## 구성

| 파일·폴더 | 역할 |
|---|---|
| `main.py` | 전처리 진입점. 단계의 실행 순서와 입출력 연결을 정합니다. |
| `paths.py` | 전처리 입출력 경로 상수. `main.py`와 각 단계의 단독 실행이 같은 경로를 씁니다. |
| `logging_setup.py` | data 영역 전용 로그 설정. dashboard 쪽 로그와 섞이지 않습니다. |
| `preprocessing/` | 전처리 단계 모듈 |
| `synthesis/` | 가상 장병 데이터 생성 스크립트 (정비 예정) |
| `logs/` | 실행 로그 (`*.log`는 Git 제외) |
| `soldier_*_sample(100).py`, `stats_view.py` | 이전 구조의 스크립트. 경로가 정리 전 폴더를 가리키므로 그대로는 동작하지 않습니다 (정비 예정). |
| `운동기록-이상치-제거.md` | 운동기록 이상치 처리와 셔틀런 잠재능력 지표에 대한 검토 메모 |

## 전처리 실행

```powershell
conda run --no-capture-output -n kdt-project-1 python data/scripts/main.py
```

`--no-capture-output`을 빼면 Windows에서 한글 출력 중 `UnicodeEncodeError`가 날 수 있습니다. `conda activate kdt-project-1` 후 `python data/scripts/main.py`로 실행해도 됩니다.

### 단계

앞 단계의 결과가 다음 단계의 입력이 됩니다.

| 순서 | 모듈 (`preprocessing/`) | 하는 일 | 출력 |
|---|---|---|---|
| 1 | `merge_raw_measurements` | 원본 55개에서 19~24세 남성 행을 모으고, 컬럼을 통합 정의서대로 맞춥니다. BMI는 키·체중으로 계산하고 운동 처방은 본운동만 남깁니다. BMI 계산 불가 행과 트레드밀 심박수 기입 오류 행(3분·6분 심박수 < 안정시)을 제거합니다. | `intermediate/KS_NFA_MERGED.csv` |
| 2 | `filter_single_cardio_records` | 심폐 종목(트레드밀·스텝검사·20m 왕복 오래달리기) 중 정확히 하나만 기록된 행을 남깁니다. 운동 처방은 비어 있어도 제거하지 않습니다. | `intermediate/cardio_filter/` |
| 3 | `filter_enlistment_candidates` | 키·체중·BMI·체지방률이 입대 후보 범위 안에 있는 행만 남깁니다. | `intermediate/enlistment_filter/` |
| 4 | `select_three_measures` | 3회 이상 측정한 회원마다 측정일 기준 첫·중간·마지막 기록 3건을 고릅니다. | `intermediate/KS_NFA_THREE_MEASURES.csv` |
| 5 | `apply_processed_definition` | 측정일 → 회원식별번호 → 측정일련번호 순으로 정렬해 `MESURE_ID`를 붙이고, 측정 데이터(PROCESSED 정의서)와 운동 처방 데이터(처방 1개당 1행, PRESCRIPTION 정의서)로 나눠 저장합니다. 같은 측정 안의 중복 처방은 제거합니다. | `processed/KS_NFA_PROCESSED.csv`, `processed/KS_NFA_PRESCRIPTION.csv` |

`remove_3sigma_outliers`(3σ 이상치 제거)와 `estimate_shuttle_run_latent_scores`(셔틀런 잠재 점수 추정)는 현재 파이프라인에서 쓰지 않습니다. 필요하면 단독으로 실행할 수 있습니다.

필터 단계의 폴더에는 통과 행(`passed.csv`)과 제거 행(`removed_*.csv`)이 함께 저장됩니다. 제거 행 파일에는 `제거 사유` 컬럼이 붙습니다.

### 단계 하나만 실행하기

각 모듈은 `paths.py`의 기본 경로로 단독 실행할 수 있습니다. 앞 단계의 결과 파일이 있어야 합니다.

```powershell
conda run --no-capture-output -n kdt-project-1 python data/scripts/preprocessing/filter_single_cardio_records.py
```

### 로그

화면과 `logs/{yyyymmdd}_{hhmmss}_{실행한 모듈}.log`에 같은 내용이 남습니다. 단계별 입력·통과·제거 행 수가 기록되므로, 결과를 확인할 때 로그 파일을 보면 됩니다.

## 단계 추가·수정

1. `preprocessing/`에 `run(입력 경로, 출력 경로)`와 단독 실행용 `main()`을 가진 모듈을 만듭니다.
2. `paths.py`에 입출력 경로를 추가합니다.
3. `main.py`의 `build_pipeline()` 목록에 `Step`을 추가합니다.

모듈 안에 경로를 직접 쓰지 않고, `print` 대신 로거를 쓰고, 실패하면 예외를 던집니다. 자세한 규칙은 [docs/데이터-관리-요령.md](../../docs/데이터-관리-요령.md)의 "전처리 단계 작성 규칙"과 [docs/모듈-작성-요령.md](../../docs/모듈-작성-요령.md)를 따릅니다. 각 모듈의 `run()` 안에는 단계별 주석(`# 1. ...`)이 달려 있습니다.
