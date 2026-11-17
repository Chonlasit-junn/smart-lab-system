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

$recoveryPath = Join-Path $agentFile.DirectoryName 'SmartLabAgentRecovery.exe'
if (-not (Test-Path -LiteralPath $recoveryPath -PathType Leaf)) {
    throw 'Install the Agent MSI that includes SmartLabAgentRecovery.exe first.'
}
$action = New-ScheduledTaskAction -Execute $recoveryPath
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $LabWindowsUser
$recoveryTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $LabWindowsUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'Smart Lab Agent Recovery' -Action $action `
    -Trigger @($logonTrigger, $recoveryTrigger) -Principal $principal -Settings $settings `
    -Description 'Restart the Smart Lab Agent when it is not running in the Lab Windows session.'
