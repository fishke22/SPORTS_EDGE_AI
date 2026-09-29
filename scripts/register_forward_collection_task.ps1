[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "SPORTS_EDGE_AI Forward Collection",
    [int]$WakeIntervalMinutes = 60
)

$ErrorActionPreference = "Stop"
if ($WakeIntervalMinutes -lt 15) {
    throw "WakeIntervalMinutes must be at least 15."
}

$CollectorScript = Join-Path $PSScriptRoot "collect_forward.ps1"
if (-not (Test-Path $CollectorScript)) {
    throw "collect_forward.ps1 was not found next to this registration script."
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $CollectorScript)
$Trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $WakeIntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if ($PSCmdlet.ShouldProcess($TaskName, "Register forward collection scheduled task")) {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "SPORTS_EDGE_AI forward point-in-time odds/scores collection." -Force | Out-Null
    Write-Output ("Registered task '{0}' every {1} minutes." -f $TaskName, $WakeIntervalMinutes)
}
else {
    Write-Output ("Validated task '{0}' every {1} minutes; task was not registered." -f $TaskName, $WakeIntervalMinutes)
}
Write-Output "The collector itself enforces provider cadence and credit budget."
