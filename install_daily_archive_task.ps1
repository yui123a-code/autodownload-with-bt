$ErrorActionPreference = "Stop"

$taskName = "QbRssAutodlArchive"
$scriptPath = Join-Path $PSScriptRoot "run_archive.ps1"
$xmlPath = Join-Path $PSScriptRoot ".QbRssAutodlArchive.task.xml"
$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$startBoundary = (Get-Date -Hour 12 -Minute 0 -Second 0).ToString("yyyy-MM-ddTHH:mm:ss")
$escapedScriptPath = [System.Security.SecurityElement]::Escape($scriptPath)

$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Archive configured RSS feeds for qb-rss-autodl daily at 12:00, after missed runs, and at user logon.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Enabled>true</Enabled>
      <StartBoundary>$startBoundary</StartBoundary>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$userSid</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$userSid</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT72H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT15M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "$escapedScriptPath"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

Set-Content -LiteralPath $xmlPath -Value $xml -Encoding Unicode
schtasks /Create /TN $taskName /XML $xmlPath /F | Write-Host

Write-Host "Installed scheduled task '$taskName' to run daily at 12:00, after missed runs, and at user logon."
