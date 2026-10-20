# data 파이프라인(전처리 -> 합성 -> 분석)을 실행합니다. 먼저 'conda activate kdt-project-1'을 실행하세요.
# 인자는 data/scripts/main.py에 그대로 전달됩니다.
#   .\run_data_pipeline.ps1                  # 전체 (all)
#   .\run_data_pipeline.ps1 preprocessing    # 전처리만 (synthesis, analysis도 가능)
# 패키지가 추가·변경되었다면 먼저 아래 줄로 환경을 갱신하세요.
# conda env update -n kdt-project-1 -f environment.yml

# 활성화된 conda 환경이 다르면 다른 패키지 버전으로 실행되므로 미리 막는다.
if ($env:CONDA_DEFAULT_ENV -ne 'kdt-project-1') {
    Write-Error "conda 환경 kdt-project-1이 활성화되어 있지 않습니다. 먼저 'conda activate kdt-project-1'을 실행하세요."
    exit 1
}

python data\scripts\main.py @args
exit $LASTEXITCODE
