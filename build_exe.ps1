$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python312 = "C:\Users\1044\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path -LiteralPath $python312)) {
    $python312 = "python"
}

& $python312 -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "AutoDownloadWithBT" `
    ".\qb_rss_gui.py"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Copy-Item -LiteralPath ".\config.example.toml" -Destination ".\dist\config.example.toml" -Force
Write-Host "Built .\dist\AutoDownloadWithBT.exe"
