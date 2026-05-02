$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

.\build_exe.ps1

$isccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    $command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($command) {
        $iscc = $command.Source
    }
}
if (-not $iscc) {
    throw "Inno Setup compiler not found. Install Inno Setup 6 or add ISCC.exe to PATH."
}

& $iscc ".\installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path ".\release" | Out-Null
Copy-Item -LiteralPath ".\installer\AutoDownloadWithBT-Setup.exe" -Destination ".\release\AutoDownloadWithBT-Setup.exe" -Force
Write-Host "Built .\release\AutoDownloadWithBT-Setup.exe"
