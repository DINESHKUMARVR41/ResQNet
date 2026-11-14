# Start the ResQNet FastAPI backend from this extracted project folder.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'backend')
if (-not (Test-Path '.\.venv')) {
    Write-Host 'Creating Python virtual environment...'
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
if (-not (Test-Path '.\.env')) {
    Copy-Item '.\.env.example' '.\.env'
    Write-Host 'Created backend\.env. Review SECRET_KEY and other settings before deployment.'
}
python -m pip install -r requirements.txt
python -m alembic upgrade head
Write-Host 'ResQNet API: http://localhost:8000'
Write-Host 'API documentation: http://localhost:8000/docs'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
