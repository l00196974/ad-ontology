$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = Join-Path "logs" ("{0:yyyy-MM-dd}-start.tee.log" -f (Get-Date))

"=== START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Tee-Object -Append -FilePath $log

if ($env:SKIP_RSS -ne "1") {
  "--- RSS ---" | Tee-Object -Append -FilePath $log
  & (Join-Path $PSScriptRoot "run_rss.ps1")
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($env:SKIP_CRAWL -ne "1") {
  "--- CRAWL ---" | Tee-Object -Append -FilePath $log
  & (Join-Path $PSScriptRoot "run_crawl.ps1")
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
"--- PIPELINE ---" | Tee-Object -Append -FilePath $log
& (Join-Path $PSScriptRoot "run_pipeline.ps1")
exit $LASTEXITCODE
