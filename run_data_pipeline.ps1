# data 파이프라인(전처리 -> 합성 -> 분석)을 실행합니다. kdt-project-1 환경이 아니면 활성화하고, 환경이 없으면 setup.ps1로 설치합니다(ensure_env.ps1).
# 인자는 data/scripts/main.py에 그대로 전달됩니다.
#   .\run_data_pipeline.ps1                  # 전체 (all)
#   .\run_data_pipeline.ps1 preprocessing    # 전처리만 (synthesis, analysis도 가능)
# 패키지가 추가·변경되었다면 먼저 아래 줄로 환경을 갱신하세요.
# conda env update -n kdt-project-1 -f environment.yml

. (Join-Path $PSScriptRoot 'ensure_env.ps1')

python data\scripts\main.py @args
exit $LASTEXITCODE
