# data

대시보드가 쓰는 데이터를 준비하는 영역입니다. 국민체력100 측정 데이터(원본)를 받아 전처리하고, 가상 장병 데이터를 생성합니다.

데이터 파일을 다루는 규칙(무엇을 Git에 올리는지, 파일을 어디에 두는지)은 [docs/데이터-관리-요령.md](../docs/데이터-관리-요령.md)에 있습니다. 작업 전에 먼저 읽어 주세요.

## 빠른 시작

1. 환경을 준비합니다. 루트의 `setup.ps1`이 conda 환경 `kdt-project-1`을 만들고 프로젝트를 설치(`pip install -e .`)합니다.
2. 원본 데이터 55개(`KS_NFA_FTNESS_MESURE_*.csv`)를 `data/raw/`에 넣습니다.
3. 프로젝트 루트에서 파이프라인을 실행합니다. 인자 없이 실행하면 전처리 -> 합성 -> 분석을 모두 실행하고, `preprocessing`을 붙이면 전처리만 실행합니다.
   ```powershell
   .\run_data_pipeline.ps1                  # 전체 (kdt-project-1 환경이 아니면 스스로 활성화)
   .\run_data_pipeline.ps1 preprocessing    # 전처리만
   ```
4. 전처리 결과는 측정 데이터 `intermediate/KS_NFA_REFINED.csv`(REFINED 정의서)와 `data/processed/`의 운동 처방 데이터 `KS_NFA_PRESCRIPTION.csv`, 운동 처방 상세 `KS_NFA_PRESCRIPTION_DETAIL.csv`입니다(상세 테이블은 전처리 2단계에서 걸러 내기 전 전체 데이터로 만듭니다). 측정 데이터와 운동 처방은 측정식별번호 `MESURE_ID`로, 운동 처방과 처방 상세는 처방유형번호 `PRESCRIPTION_TYPE_ID`로 연결됩니다(처방 이름은 상세 파일에만 있습니다). 최종 측정 데이터 `processed/KS_NFA_PROCESSED.csv`(FINAL 정의서)는 합성 단계에서 REFINED에 회원의 군번(`SOLDIER_ID`)과 부상 위험 그룹 번호(`INJURY_RISK_GROUP_ID`)를 붙이고 국민체력100 식별자(`M_CODE`, `M_SEQ_NO`)는 빼서 만듭니다. 컬럼 구성은 `definitions/`의 정의서를 따르고, 통계 작업은 이 정의서를 기준으로 합니다. 실행 로그는 `data/scripts/logs/`에 남습니다.
5. 합성 단계는 전처리 결과의 회원(`M_CODE`) 한 명당 가상 장병 한 명을 만들어 `data/synthetic/SOLDIER_PERSONNEL.csv`에 저장하고, 장병마다 **가장 최근에 한 측정**의 BMI·심폐지구력으로 기대 부상 건수 λ를 정해 부상을 뽑습니다. 선행 연구에 따라 **장병 1명당 연간 0.3건**을 기준으로 하고, 원본 연구처럼 BMI와 심폐지구력을 각각 백분위 3구간(하위 25%·중간 50%·상위 25%)으로 나눈 부상 위험 그룹 9개마다 기대 부상 건수를 정해 `processed/INJURY_RISK_GROUP.csv`에 저장합니다. 최종 측정 데이터는 측정마다 이 그룹 번호를 가집니다. 기준 0.3은 모든 측정이 같은 해에 이루어졌다고 가정한 값이며, 장병마다 Poisson(λ)에서 건수를 뽑으므로 총 부상 건수는 정확히 0.3N이 아니라 Poisson(0.3N)을 따릅니다. 부상 기록은 `data/synthetic/SOLDIER_INJURY.csv`에 저장합니다. 두 척도의 백분위 경계는 전체 측정으로 정합니다. 그룹별 가중치는 `link_fitness_and_injury_risk.py`의 `INJURY_RISK`에 적습니다. 자세한 내용은 [scripts/README.md](scripts/README.md#가상-장병부상-데이터-생성-synthesis)를 참고하세요.

## 폴더 구성

| 폴더 | 내용 | Git |
|---|---|---|
| `raw/` | 원본 데이터 (`KS_NFA_FTNESS_MESURE_*.csv` 55개만) | 제외 |
| `definitions/` | 컬럼 정의서 (원본: `KS_NFA_RAW_DEFINITION.csv`, 통합: `KS_NFA_MERGED_DEFINITION.csv`, 전처리 결과: `KS_NFA_REFINED_DEFINITION.csv`, 최종: `KS_NFA_FINAL_DEFINITION.csv`·`KS_NFA_PRESCRIPTION_DEFINITION.csv`·`KS_NFA_PRESCRIPTION_DETAIL_DEFINITION.csv`·`INJURY_RISK_GROUP_DEFINITION.csv`, 가상 장병 명단·부상 기록: `SOLDIER_PERSONNEL_DEFINITION.csv`·`SOLDIER_INJURY_DEFINITION.csv`, 가상 장병 연계: `TEMP_SOLDIER_PERSONAL_INJURY_RISK_DEFINITION.csv`(참고용, 코드에서 읽지 않음)) 파일별 내용은 [definitions/README.md](definitions/README.md) 참고 | 추적 |
| `intermediate/` | 전처리 중간 결과물과 단계별 제거 행 | 제외 |
| `processed/` | 최종 결과물 (측정·운동 처방·부상 위험 그룹) | 제외 |
| `synthetic/` | 합성 단계가 만드는 가상 장병 명단·부상 기록 | 제외 |
| `samples/` | 샘플 데이터. 데이터 형태를 예시로 볼 때 사용. 샘플은 `python data/scripts/create_samples.py`로 만듭니다(파이프라인에는 넣지 않음). 최종 체력 측정에서 장병 100명을 무작위로 골라(시드 42) 그 장병의 측정 300행(`KS_NFA_PROCESSED_SAMPLE.csv`), 장병 명단(`SOLDIER_PERSONNEL_SAMPLE.csv`), 부상 기록(`SOLDIER_INJURY_SAMPLE.csv`)을 원본 값 그대로 뽑습니다. 샘플은 독자 참고용이므로 다른 코드의 입력으로 쓰지 않습니다(테스트가 확인). | 추적 |
| `scripts/` | 전처리·가상 데이터 생성 스크립트. [scripts/README.md](scripts/README.md) 참고 | 추적 |
| `experiments/` | 데이터 분석 실험 스크립트(실험용이며 최종 코드가 아님, 코드 규칙을 엄격히 적용하지 않음). 전처리된 체력 측정 데이터로 3차 통과율 예측, 체력 미달자 회차별 변화, 위험 장병 식별, 연령·BMI 집단별 검정(분산분석·t검정·카이제곱), 운동 처방 관련성 등을 분석합니다. 파이프라인에 들어 있지 않아 하나씩 직접 실행하며(대부분 Streamlit 화면), 결과는 `experiments/results/`에 저장합니다. 파일별 내용은 [experiments/README.md](experiments/README.md) 참고 | 추적 |

폴더 경로는 루트의 `config.py`에 상수(`RAW_DATA_DIR`, `INTERMEDIATE_DIR`, `PROCESSED_DIR` 등)로 정의되어 있습니다. 코드에서는 경로를 직접 쓰지 말고 이 상수를 import해서 씁니다.

## 원본 데이터

- 출처: 문화 빅데이터 플랫폼 — 체력측정 및 운동처방 종합 데이터
  <https://www.bigdata-culture.kr/bigdata/user/data_market/detail.do?id=b3924850-aa65-11ec-8ee4-95f65f846b27>
- 범위: 202201 ~ 202607, 월별 파일 55개, 합계 약 670MB
- 2022년 5~6월 KSPO 송파 일부 센터 기록은 트레드밀 심박수가 거꾸로 입력되어 있습니다. 전처리 1단계에서 이런 행을 제거합니다. 자세한 내용은 [docs/데이터-관리-요령.md](../docs/데이터-관리-요령.md)를 참고하세요.
- 파일 이름은 받은 그대로 둡니다. 전처리는 `KS_NFA_FTNESS_MESURE_*.csv` 이름 패턴으로 원본을 찾습니다.

## 전처리 결과 요약

| 단계 | 결과 | 행 수 (2026-10-20 기준, 원본 55개, 심폐지구력 VO₂max 통일) |
|---|---|---|
| 원본 통합 (19~24세 남성) | `intermediate/KS_NFA_MERGED.csv` | 126,097 |
| 운동 처방 상세 (원본 통합 전체의 처방 이름 1개당 1행) | `processed/KS_NFA_PRESCRIPTION_DETAIL.csv` | 521 |
| 결측치·이상치 제거 | `intermediate/basic_refinement/passed.csv` | 124,113 |
| 입대 후보 조건 필터 | `intermediate/enlistment_filter/passed.csv` | 123,634 |
| 3회 이상 측정 회원의 기록 3건 (간격 30일 이상, 3년 이내) | `intermediate/KS_NFA_THREE_MEASURES.csv` | 10,746 (3,582명 × 3건) |
| 전처리 측정 데이터 (`MESURE_ID` 부여, REFINED) | `intermediate/KS_NFA_REFINED.csv` | 10,746 |
| 최종: 운동 처방 데이터 (처방 1개당 1행, 처방유형번호) | `processed/KS_NFA_PRESCRIPTION.csv` | 51,729 |

각 단계가 하는 일은 [scripts/README.md](scripts/README.md)를 참고하세요.
