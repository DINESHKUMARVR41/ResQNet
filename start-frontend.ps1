# Start the ResQNet Vite frontend from this extracted project folder.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'frontend')
if (-not (Test-Path '.\.env')) {
    Copy-Item '.\.env.example' '.\.env'
}
# Check the actual Vite executable rather than the node_modules directory;
# interrupted npm installs can leave an incomplete node_modules folder behind.
if (-not (Test-Path '.\node_modules\.bin\vite.cmd')) {
    Write-Host 'Installing frontend dependencies from package-lock.json...'
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed. Fix the dependency installation before starting the frontend.' }
}
Write-Host 'ResQNet frontend: http://localhost:5173'
npm run dev -- --host 127.0.0.1
