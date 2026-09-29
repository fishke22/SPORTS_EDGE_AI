[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "SPORTS_EDGE_AI Forward Collection"
)

$ErrorActionPreference = "Stop"
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $Existing) {
    Write-Output ("Task '{0}' is not registered." -f $TaskName)
    exit 0
}

if ($PSCmdlet.ShouldProcess($TaskName, "Unregister forward collection scheduled task")) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output ("Unregistered task '{0}'." -f $TaskName)
}
