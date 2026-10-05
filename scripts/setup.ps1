# One-shot setup for Windows PowerShell.
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Setting up backend"
Set-Location "$Root\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path ".env")) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force -Path "data" | Out-Null

Write-Host "==> Setting up frontend"
Set-Location "$Root\frontend"
npm install

Write-Host ""
Write-Host "Setup complete."
Write-Host "Backend:  cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload"
Write-Host "Frontend: cd frontend; npm run dev"
