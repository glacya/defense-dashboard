# kdt-project-1 환경을 처음부터 다시 만들고, 프로젝트를 editable 모드로 설치한 뒤 환경을 활성화합니다.
# 기존 환경이 있으면 삭제하므로, 다른 터미널에서 이 환경을 쓰고 있다면 닫고 실행하세요.
# conda activate를 쓰므로 PowerShell에 conda가 초기화되어 있어야 합니다(한 번만: conda init powershell).
$EnvName = 'kdt-project-1'

# 지금 터미널에서 활성화된 환경은 삭제할 수 없으므로 먼저 빠져나온다.
if ($env:CONDA_DEFAULT_ENV -eq $EnvName) {
    conda deactivate
}

if (conda env list | Select-String -Pattern "^$EnvName\s") {
    conda env remove -n $EnvName -y
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

conda env create -f environment.yml
if ($LASTEXITCODE -ne 0) { exit 1 }

conda activate $EnvName
if ($env:CONDA_DEFAULT_ENV -ne $EnvName) {
    # 변수 뒤에 한글이 바로 붙으면 변수 이름으로 읽히므로 ${}로 감싼다.
    Write-Error "conda 환경 ${EnvName}을 활성화하지 못했습니다. 'conda init powershell' 후 터미널을 다시 열고 실행하세요."
    exit 1
}

# 반드시 -e(editable)로 설치해야 config.py의 경로가 프로젝트 폴더를 가리킨다.
python -m pip install -e .
exit $LASTEXITCODE
