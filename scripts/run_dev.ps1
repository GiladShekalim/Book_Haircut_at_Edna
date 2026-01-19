$ErrorActionPreference = "Stop"

Write-Host "Creating venv (.venv) if missing..."
if (!(Test-Path ".venv")) {
    python -m venv .venv
}

Write-Host "Activating venv..."
& .\.venv\Scripts\Activate.ps1

Write-Host "Installing dependencies..."
pip install --quiet -r requirements.txt

Write-Host "Running uvicorn on http://127.0.0.1:5000 ..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
