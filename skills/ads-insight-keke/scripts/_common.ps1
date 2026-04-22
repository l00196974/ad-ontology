$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$envFile = Join-Path $ProjectRoot "config\env.conf"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*export\s+([A-Z_][A-Z0-9_]*)\s*=\s*"?(.*?)"?\s*$') {
      Set-Item -Path "env:$($matches[1])" -Value $matches[2]
    }
  }
}

$activate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $activate) { & $activate }

$srcPath = Join-Path $ProjectRoot "src"
if ($env:PYTHONPATH) {
  $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
  $env:PYTHONPATH = $srcPath
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

New-Item -ItemType Directory -Force -Path logs, data | Out-Null
