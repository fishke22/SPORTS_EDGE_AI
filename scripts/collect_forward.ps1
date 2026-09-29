$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:SPORTS_EDGE_ROOT = $ProjectRoot
$LogDirectory = Join-Path $ProjectRoot "logs"
$LogPath = Join-Path $LogDirectory "forward_collection.log"

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
Push-Location $ProjectRoot
try {
    $StartedAt = [DateTimeOffset]::Now.ToString("o")
    $FinalExitCode = 0
    $Output = & uv run sports-edge collect-forward --trigger-kind SCHEDULED 2>&1
    $CollectionExitCode = $LASTEXITCODE
    Add-Content -Path $LogPath -Value ("{0} collection {1}" -f $StartedAt, ($Output -join " "))
    if ($CollectionExitCode -ne 0) {
        $FinalExitCode = $CollectionExitCode
    }
    else {
        $ResearchOutput = & uv run sports-edge research-cycle --trigger-kind SCHEDULED 2>&1
        $ResearchExitCode = $LASTEXITCODE
        Add-Content -Path $LogPath -Value ("{0} research {1}" -f $StartedAt, ($ResearchOutput -join " "))
        if ($ResearchExitCode -ne 0) {
            $FinalExitCode = $ResearchExitCode
        }
    }

    $MonitorOutput = & uv run sports-edge ops-monitor --trigger-kind SCHEDULED 2>&1
    $MonitorExitCode = $LASTEXITCODE
    Add-Content -Path $LogPath -Value ("{0} monitor {1}" -f $StartedAt, ($MonitorOutput -join " "))
    if (($FinalExitCode -eq 0) -and ($MonitorExitCode -ne 0)) {
        $FinalExitCode = $MonitorExitCode
    }
    if ($FinalExitCode -ne 0) {
        exit $FinalExitCode
    }
}
finally {
    Pop-Location
}
