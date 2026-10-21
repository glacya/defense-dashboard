# kdt-project-1 환경이 활성화되도록 맞춥니다. run_*.ps1과 test.ps1이 맨 앞에서 dot-source(. .\ensure_env.ps1)로 불러옵니다.
# 1. 이미 활성화되어 있으면 아무것도 하지 않습니다.
# 2. 아니면 conda activate kdt-project-1을 실행합니다.
# 3. 활성화에 실패했고 환경이 아예 없으면 setup.ps1로 설치합니다(설치 후 활성화까지 됨).
# 실패하면 오류를 던져 불러온 스크립트까지 멈춥니다. 활성화 결과는 현재 터미널에도 남습니다.
# dot-source한 파일 안의 exit는 이 파일만 끝내고 불러온 스크립트는 계속 실행되므로, 실패는 exit가 아니라 throw로 알린다.
$EnvName = 'kdt-project-1'

if ($env:CONDA_DEFAULT_ENV -ne $EnvName) {
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        throw "conda를 찾을 수 없습니다. Anaconda를 설치하고 'conda init powershell' 후 터미널을 다시 여세요."
    }
    # 환경이 없으면 conda가 오류를 출력한다. 아래에서 환경 이름으로 결과를 확인하므로 여기서는 멈추지 않는다.
    try { conda activate $EnvName } catch { }
}

if ($env:CONDA_DEFAULT_ENV -ne $EnvName) {
    # setup.ps1은 기존 환경을 지우고 다시 만들므로, 환경이 있는데 활성화만 실패한 경우에는 실행하지 않는다.
    if (conda env list | Select-String -Pattern "^$EnvName\s") {
        throw "conda 환경 ${EnvName}은 있지만 활성화하지 못했습니다. 'conda init powershell' 후 터미널을 다시 열고 실행하세요."
    }
    Write-Host "conda 환경 ${EnvName}이 없어 setup.ps1로 설치합니다."
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0 -or $env:CONDA_DEFAULT_ENV -ne $EnvName) {
        throw "conda 환경 ${EnvName} 설치 또는 활성화에 실패했습니다. 위 출력을 확인하세요."
    }
}
