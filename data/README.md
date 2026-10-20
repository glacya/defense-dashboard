# data

대시보드가 쓰는 데이터를 준비하는 영역입니다. 국민체력100 측정 데이터(원본)를 받아 전처리하고, 가상 장병 데이터를 생성합니다.

데이터 파일을 다루는 규칙(무엇을 Git에 올리는지, 파일을 어디에 두는지)은 [docs/데이터-관리-요령.md](../docs/데이터-관리-요령.md)에 있습니다. 작업 전에 먼저 읽어 주세요.

## 빠른 시작

1. 환경을 준비합니다. 루트의 `setup.ps1`이 conda 환경 `kdt-project-1`을 만들고 프로젝트를 설치(`pip install -e .`)합니다.
2. 원본 데이터 55개(`KS_NFA_FTNESS_MESURE_*.csv`)를 `data/raw/`에 넣습니다.
3. 프로젝트 루트에서 파이프라인을 실행합니다. 인자 없이 실행하면 전처리 -> 합성 -> 분석을 모두 실행하고, `preprocessing`을 붙이면 전처리만 실행합니다.
   ```powershell
   conda activate kdt-project-1
   .\run_data_pipeline.ps1                  # 전체
   .\run_data_pipeline.ps1 preprocessing    # 전처리만
   ```
4. 최종 결과는 `data/processed/`의 두 파일입니다. 측정 데이터 `KS_NFA_PROCESSED.csv`와 운동 처방 데이터 `KS_NFA_PRESCRIPTION.csv`이며, 측정식별번호 `MESURE_ID`로 연결됩니다. 컬럼 구성은 `definitions/`의 `KS_NFA_PROCESSED_DEFINITION.csv`, `KS_NFA_PRESCRIPTION_DEFINITION.csv`를 따르고, 통계 작업은 이 정의서를 기준으로 합니다. 실행 로그는 `data/scripts/logs/`에 남습니다.

## 폴더 구성

| 폴더 | 내용 | Git |
|---|---|---|
| `raw/` | 원본 데이터 (`KS_NFA_FTNESS_MESURE_*.csv` 55개만) | 제외 |
| `definitions/` | 컬럼 정의서 (원본: `KS_NFA_RAW_DEFINITION.csv`, 통합: `KS_NFA_MERGED_DEFINITION.csv`, 최종: `KS_NFA_PROCESSED_DEFINITION.csv`·`KS_NFA_PRESCRIPTION_DEFINITION.csv`) | 추적 |
| `intermediate/` | 전처리 중간 결과물과 단계별 제거 행 | 제외 |
| `processed/` | 전처리 최종 결과물 | 제외 |
| `samples/` | 샘플 데이터 (100행 내외). 데이터 형태를 예시로 볼 때 사용 | 추적 |
| `scripts/` | 전처리·가상 데이터 생성 스크립트. [scripts/README.md](scripts/README.md) 참고 | 추적 |
| `experiments/` | 이전 실험 코드 (현재 파이프라인에서 쓰지 않음, 정리 예정) | 추적 |

폴더 경로는 루트의 `config.py`에 상수(`RAW_DATA_DIR`, `INTERMEDIATE_DIR`, `PROCESSED_DIR` 등)로 정의되어 있습니다. 코드에서는 경로를 직접 쓰지 말고 이 상수를 import해서 씁니다.

## 원본 데이터

- 출처: 문화 빅데이터 플랫폼 — 체력측정 및 운동처방 종합 데이터
  <https://www.bigdata-culture.kr/bigdata/user/data_market/detail.do?id=b3924850-aa65-11ec-8ee4-95f65f846b27>
- 범위: 202201 ~ 202607, 월별 파일 55개, 합계 약 670MB
- 2022년 5~6월 KSPO 송파 일부 센터 기록은 트레드밀 심박수가 거꾸로 입력되어 있습니다. 전처리 1단계에서 이런 행을 제거합니다. 자세한 내용은 [docs/데이터-관리-요령.md](../docs/데이터-관리-요령.md)를 참고하세요.
- 파일 이름은 받은 그대로 둡니다. 전처리는 `KS_NFA_FTNESS_MESURE_*.csv` 이름 패턴으로 원본을 찾습니다.

## 전처리 결과 요약

| 단계 | 결과 | 행 수 (2026-10-14 기준, 원본 55개, 운동 처방 결측 미제거) |
|---|---|---|
| 원본 통합 (19~24세 남성) | `intermediate/KS_NFA_MERGED.csv` | 126,097 |
| 결측치·이상치 제거 | `intermediate/basic_refinement/passed.csv` | 124,107 |
| 입대 후보 조건 필터 | `intermediate/enlistment_filter/passed.csv` | 123,628 |
| 3회 이상 측정 회원의 첫·중간·마지막 기록 | `intermediate/KS_NFA_THREE_MEASURES.csv` | 23,610 (7,870명 × 3건) |
| 최종: 측정 데이터 (`MESURE_ID` 부여) | `processed/KS_NFA_PROCESSED.csv` | 23,610 |
| 최종: 운동 처방 데이터 (처방 1개당 1행) | `processed/KS_NFA_PRESCRIPTION.csv` | 114,589 |

각 단계가 하는 일은 [scripts/README.md](scripts/README.md)를 참고하세요.
