# data

대시보드가 쓰는 데이터를 준비하는 영역입니다. 국민체력100 측정 데이터(원본)를 받아 전처리하고, 가상 장병 데이터를 생성합니다.

데이터 파일을 다루는 규칙(무엇을 Git에 올리는지, 파일을 어디에 두는지)은 [docs/데이터-관리-요령.md](../docs/데이터-관리-요령.md)에 있습니다. 작업 전에 먼저 읽어 주세요.

## 빠른 시작

1. 환경을 준비합니다. 루트의 `setup.ps1`이 conda 환경 `kdt-project-1`을 만들고 프로젝트를 설치(`pip install -e .`)합니다.
2. 원본 데이터 54개(`KS_NFA_FTNESS_MESURE_*.csv`)를 `data/raw/`에 넣습니다.
3. 프로젝트 루트에서 전처리를 실행합니다.
   ```powershell
   conda run --no-capture-output -n kdt-project-1 python data/scripts/main.py
   ```
4. 최종 결과는 `data/processed/KS_NFA_PROCESSED.csv`에 저장됩니다. 실행 로그는 `data/scripts/logs/`에 남습니다.

## 폴더 구성

| 폴더 | 내용 | Git |
|---|---|---|
| `raw/` | 원본 데이터 (`KS_NFA_FTNESS_MESURE_*.csv` 54개만) | 제외 |
| `definitions/` | 컬럼 정의서 (원본: `KS_NFA_RAW_DEFINITION.csv`, 통합: `KS_NFA_MERGED_DEFINITION.csv`) | 추적 |
| `intermediate/` | 전처리 중간 결과물과 단계별 제거 행 | 제외 |
| `processed/` | 전처리 최종 결과물 | 제외 |
| `samples/` | 샘플 데이터 (100행 내외). 데이터 형태를 예시로 볼 때 사용 | 추적 |
| `scripts/` | 전처리·가상 데이터 생성 스크립트. [scripts/README.md](scripts/README.md) 참고 | 추적 |
| `experiments/` | 이전 실험 코드 (현재 파이프라인에서 쓰지 않음, 정리 예정) | 추적 |
| `old/` | 폴더 정리 전 파일 보관 (정리 예정) | 일부 제외 |

폴더 경로는 루트의 `config.py`에 상수(`RAW_DATA_DIR`, `INTERMEDIATE_DIR`, `PROCESSED_DIR` 등)로 정의되어 있습니다. 코드에서는 경로를 직접 쓰지 말고 이 상수를 import해서 씁니다.

## 원본 데이터

- 출처: 문화 빅데이터 플랫폼 — 체력측정 및 운동처방 종합 데이터
  <https://www.bigdata-culture.kr/bigdata/user/data_market/detail.do?id=b3924850-aa65-11ec-8ee4-95f65f846b27>
- 범위: 202201 ~ 202607 (202205 제외), 월별 파일 54개, 합계 약 600MB
- 파일 이름은 받은 그대로 둡니다. 전처리는 `KS_NFA_FTNESS_MESURE_*.csv` 이름 패턴으로 원본을 찾습니다.

## 전처리 결과 요약

| 단계 | 결과 | 행 수 (2026-10-13 기준) |
|---|---|---|
| 원본 통합 (19~24세 남성) | `intermediate/KS_NFA_MERGED.csv` | 121,924 |
| 심폐 단일 종목 필터 | `intermediate/cardio_filter/passed.csv` | 101,213 |
| 입대 후보 조건 필터 | `intermediate/enlistment_filter/passed.csv` | 100,823 |
| 3회 이상 측정 회원의 첫·중간·마지막 기록 | `processed/KS_NFA_PROCESSED.csv` | 17,124 (5,708명 × 3건) |

각 단계가 하는 일은 [scripts/README.md](scripts/README.md)를 참고하세요.
