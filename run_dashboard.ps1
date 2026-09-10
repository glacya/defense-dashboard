./test.ps1

if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 5) {

    Write-Host ""
    Write-Host "Test failed."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Test success! Running Streamlit application.."

conda run -n kdt-project-1 streamlit run dashboard\app.py