# Project 1 - 국방 대시보드 시각화 프로젝트

체력검정 기록을 바탕으로 장병 개인의 취약한 체력요소를 진단하고, 부대 단위로 관리할 수 있게 보여 주는 Streamlit 대시보드입니다.

- **목적**: 부대 관리자가 핵심 체력 지표를 한눈에 보고, 불합격 위험 인원을 식별해 맞춤 운동 처방까지 이어지도록 돕습니다.
- **데이터**: 국민체력100(KS_NFA) 체력측정·운동처방 공공데이터 중 입대 연령대(19~24세) 남성 기록을 전처리해 장병 체력의 기준 분포로 쓰고, 이를 바탕으로 가상 장병 데이터를 합성합니다.

## 폴더 구성

| 폴더 | 내용 |
|---|---|
| `dashboard/` | Streamlit 대시보드 앱과 화면 구성 코드. 자세한 내용은 `dashboard/README.md` (작성 예정) |
| `data/` | 데이터 파일과 데이터 파이프라인(전처리 -> 가상 데이터 합성 -> 분석). 자세한 내용은 [data/README.md](data/README.md) |
| `docs/` | 팀 작업 규칙. 코드를 쓰기 전에 읽어 주세요. [모듈 작성 요령](docs/모듈-작성-요령.md), [테스트 작성법](docs/테스트-작성법.md), [데이터 관리 요령](docs/데이터-관리-요령.md) |
| `tests/` | pytest 테스트. 대상 코드 위치에 맞춰 `dashboard/`, `data/`, `utils/`로 나눕니다. |
| `.github/` | GitHub Actions 설정. push와 `main` 대상 PR마다 Ubuntu·Windows에서 Python 3.10으로 테스트를 실행합니다. |

## 최상위 파일

| 파일 | 내용 |
|---|---|
| `config.py` | 프로젝트 전역 경로 상수. `dashboard`와 `data` 모두 경로는 여기서 import합니다. |
| `requirements.txt` | 의존성 목록(버전 고정). 패키지를 추가하면 여기에 `==` 버전으로 적습니다. |
| `environment.yml` | conda 환경 `kdt-project-1` 정의(Python 3.10). 패키지 목록은 `requirements.txt`를 참조합니다. |
| `pyproject.toml` | 프로젝트 설치 설정(`pip install -e .`)과 pytest 설정 |
| `setup.ps1` | conda 환경을 새로 만들고 프로젝트를 editable 모드로 설치한 뒤 환경을 활성화합니다. 기존 환경은 삭제됩니다. |
| `run_dashboard.ps1` | 대시보드를 실행합니다. |
| `run_data_pipeline.ps1` | 데이터 파이프라인을 실행합니다. 인자 없이 실행하면 전체, `preprocessing`·`synthesis`·`analysis`를 주면 그 영역만 실행합니다. |
| `test.ps1` | 전체 테스트를 실행합니다. 인자는 pytest에 그대로 전달됩니다. |
| `.gitignore` | Git에서 제외할 파일. 원본·중간·결과 데이터는 올리지 않습니다. |

## 시작하기

Windows PowerShell 기준이며, 모든 명령은 프로젝트 루트에서 실행합니다.

1. conda를 PowerShell에서 쓸 수 있게 초기화합니다(처음 한 번만). 초기화 후 터미널을 다시 엽니다.
   ```powershell
   conda init powershell
   ```
2. 환경을 만들고 프로젝트를 설치합니다. 끝나면 `kdt-project-1` 환경이 활성화된 상태가 됩니다.
   ```powershell
   .\setup.ps1
   ```
3. 이후 새 터미널에서는 환경을 먼저 활성화하고 스크립트를 실행합니다. `run_*.ps1`과 `test.ps1`은 환경이 활성화되어 있지 않으면 실행하지 않습니다.
   ```powershell
   conda activate kdt-project-1
   .\run_data_pipeline.ps1   # 데이터 파이프라인 (원본 데이터 준비는 data/README.md 참고)
   .\run_dashboard.ps1       # 대시보드
   .\test.ps1                # 테스트
   ```

> 스크립트 실행이 막히면(`이 시스템에서 스크립트를 실행할 수 없으므로…`) 현재 사용자에 한해 실행 정책을 바꿉니다: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
