#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$LabWindowsUser,

    [string]$AgentPath = (Join-Path $env:ProgramFiles 'Smart Lab\Device Agent\SmartLabDevice.exe')
)

$ErrorActionPreference = 'Stop'
$agentFile = Get-Item -LiteralPath $AgentPath
if ($agentFile.PSIsContainer -or $agentFile.Name -ne 'SmartLabDevice.exe') {
    throw 'AgentPath must point to an installed SmartLabDevice.exe.'
}

$agentLiteral = "'" + $agentFile.FullName.Replace("'", "''") + "'"
$checkCommand = @'
$agent = __AGENT_PATH__
if (-not (Test-Path -LiteralPath $agent -PathType Leaf)) { exit }
$session = (Get-Process -Id $PID).SessionId
$running = Get-Process -Name SmartLabDevice -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session -and $_.Path -eq $agent }
if (-not $running) { Start-Process -FilePath $agent }
'@
$checkCommand = ($checkCommand -replace '\r?\n', '; ').Replace('__AGENT_PATH__', $agentLiteral)
$powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $powershellPath -Argument (
    '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + $checkCommand + '"'
)
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $LabWindowsUser
$recoveryTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $LabWindowsUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'Smart Lab Agent Recovery' -Action $action `
    -Trigger @($logonTrigger, $recoveryTrigger) -Principal $principal -Settings $settings `
    -Description 'Restart the Smart Lab Agent when it is not running in the Lab Windows session.'
