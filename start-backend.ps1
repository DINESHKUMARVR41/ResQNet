# ResQNet Backend Startup Script (Windows PowerShell)
Set-Location d:\ResQNet\backend
if (-not (Test-Path .\.venv)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
if (-not (Test-Path .\requirements.txt)) {
    Write-Host "requirements.txt not found!"
    exit 1
}
pip install -r requirements.txt --quiet
if (-not (Test-Path .\.env)) {
    Copy-Item .\.env.example .\.env
    Write-Host "Created .env from example. Edit it before production use."
}
python -m alembic upgrade head
Write-Host "Starting ResQNet Backend on http://localhost:8000"
Write-Host "API docs at http://localhost:8000/docs"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
