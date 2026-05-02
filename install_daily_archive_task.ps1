$ErrorActionPreference = "Stop"

$taskName = "QbRssAutodlArchive"
$scriptPath = Join-Path $PSScriptRoot "run_archive.ps1"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -Daily -At 12:00
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Description "Archive configured RSS feeds for qb-rss-autodl once per day at 12:00." `
    -Force

Write-Host "Installed scheduled task '$taskName' to run daily at 12:00."
