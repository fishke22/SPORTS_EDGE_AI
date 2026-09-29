$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install uv, then rerun this bootstrap script."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required for the React frontend. Install Node.js/npm, then rerun."
}

uv sync --extra dev
uv run sports-edge init-db
uv run ruff check .
uv run mypy src
uv run pytest -q

npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
uv run sports-edge doctor

Write-Host "SPORTS_EDGE_AI bootstrap complete at $ProjectRoot"
