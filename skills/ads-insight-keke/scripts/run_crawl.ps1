. (Join-Path $PSScriptRoot "_common.ps1")
$log = Join-Path "logs" ("{0:yyyy-MM-dd}-crawl.tee.log" -f (Get-Date))
$ErrorActionPreference = 'Continue'
& python -m ads_insight_keke.web_crawler *>&1 | Tee-Object -FilePath $log -Append
exit $LASTEXITCODE
