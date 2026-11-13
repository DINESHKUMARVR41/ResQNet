# ResQNet Frontend Startup Script (Windows PowerShell)
Set-Location d:\ResQNet\frontend
if (-not (Test-Path .\node_modules)) {
    Write-Host "Installing dependencies..."
    npm install
}
if (-not (Test-Path .\.env)) {
    Copy-Item .\.env.example .\.env
}
Write-Host "Starting ResQNet Frontend on http://localhost:5173"
npm run dev
