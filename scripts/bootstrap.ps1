$ErrorActionPreference = "Stop"

function Assert-NativeSuccess([string]$Step, [int]$ExitCode) {
    if ($ExitCode -ne 0) {
        throw "$Step failed with exit code $ExitCode."
    }
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install uv, then rerun this bootstrap script."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required for the React frontend. Install Node.js/npm, then rerun."
}

uv sync --extra dev
Assert-NativeSuccess "uv sync" $LASTEXITCODE
uv run sports-edge init-db
Assert-NativeSuccess "init-db" $LASTEXITCODE
uv run ruff check .
Assert-NativeSuccess "ruff" $LASTEXITCODE
uv run mypy src
Assert-NativeSuccess "mypy" $LASTEXITCODE
uv run pytest -q
Assert-NativeSuccess "pytest" $LASTEXITCODE

npm --prefix frontend ci
Assert-NativeSuccess "npm ci" $LASTEXITCODE
npm --prefix frontend test
Assert-NativeSuccess "frontend test" $LASTEXITCODE
npm --prefix frontend run build
Assert-NativeSuccess "frontend build" $LASTEXITCODE
uv run sports-edge doctor
Assert-NativeSuccess "doctor" $LASTEXITCODE

Write-Host "SPORTS_EDGE_AI bootstrap complete at $ProjectRoot"
