$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] archive start" | Out-File -LiteralPath ".\archive.log" -Append -Encoding utf8
python .\qb_rss_autodl.py archive *>&1 | Tee-Object -FilePath ".\archive.log" -Append
