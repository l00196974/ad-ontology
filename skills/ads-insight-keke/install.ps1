$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

if (-not (Test-Path config\env.conf)) {
  Copy-Item config\env.conf.example config\env.conf
  Write-Host "Generated config/env.conf -- please edit it and fill in LLM_API_KEY."
}

Write-Host "Install completed."
