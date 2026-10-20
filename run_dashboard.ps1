# 대시보드(Streamlit)를 실행합니다. kdt-project-1 환경이 아니면 활성화하고, 환경이 없으면 setup.ps1로 설치합니다(ensure_env.ps1).
# 인자는 streamlit run에 그대로 전달됩니다. 예: .\run_dashboard.ps1 --server.port 8502
# 패키지가 추가·변경되었다면 먼저 아래 줄로 환경을 갱신하세요.
# conda env update -n kdt-project-1 -f environment.yml

. (Join-Path $PSScriptRoot 'ensure_env.ps1')

python -m streamlit run dashboard\app.py @args
exit $LASTEXITCODE
