# Windows PowerShell dev startup script.
Set-Location $PSScriptRoot\..
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
}
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
