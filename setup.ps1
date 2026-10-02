# kdt-project-1 환경을 처음부터 다시 만듭니다.
# 기존 환경이 있으면 삭제하므로, 해당 환경이 활성화된 터미널은 모두 닫고 실행하세요.
if (conda env list | Select-String -Pattern '^kdt-project-1\s') {
    conda env remove -n kdt-project-1 -y
}

conda env create -f environment.yml
if ($LASTEXITCODE -ne 0) { exit 1 }

# 프로젝트를 editable 모드로 설치하여 어디서든 `from config import ...` 사용 가능
conda run -n kdt-project-1 pip install -e .
