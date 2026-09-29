$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

# Match an actual drive-rooted path segment (for example X:\\folder), not
# regex/test escape sequences such as "uses:\\s" or "steps:\\n".
$AbsoluteWindowsPathPattern = '[A-Za-z]:[\\/](?:[A-Za-z0-9._ -]{2,}[\\/]|[A-Za-z0-9._ -]{1,}[A-Za-z0-9._](?=["''\s;,) ]|$))'

$DrivePathFixture = "Z" + ":" + [char]92 + "portable" + [char]92 + "repo"
$RegexEscapeFixture = "uses:" + [char]92 + "s"
$NewlineEscapeFixture = "steps:" + [char]92 + "n"
if ($DrivePathFixture -notmatch $AbsoluteWindowsPathPattern) {
    throw "Portable path scanner failed to detect a drive-rooted path fixture."
}
if (($RegexEscapeFixture -match $AbsoluteWindowsPathPattern) -or
    ($NewlineEscapeFixture -match $AbsoluteWindowsPathPattern)) {
    throw "Portable path scanner produced an escape-sequence false positive."
}

$AllowedExtensions = @(
    ".py", ".ps1", ".toml", ".yaml", ".yml", ".sql", ".json",
    ".ts", ".tsx", ".css", ".html"
)
$ScanRoots = @("src", "scripts", "config", "sql", "tests", "frontend/src", ".github")
$Files = foreach ($relativeRoot in $ScanRoots) {
    $candidate = Join-Path $ProjectRoot $relativeRoot
    if (Test-Path $candidate) {
        Get-ChildItem $candidate -Recurse -File |
            Where-Object { $_.Extension -in $AllowedExtensions }
    }
}

$FrontendRootFiles = @(
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/tsconfig.app.json",
    "frontend/tsconfig.node.json",
    "frontend/vite.config.ts"
) | ForEach-Object {
    $candidate = Join-Path $ProjectRoot $_
    if (Test-Path $candidate) {
        Get-Item $candidate
    }
}

$Hits = @($Files) + @($FrontendRootFiles) |
    Select-String -Pattern $AbsoluteWindowsPathPattern
if ($Hits) {
    $Hits | Format-Table Path, LineNumber, Line -AutoSize
    throw "Portable source contains a hard-coded Windows absolute path."
}

uv run sports-edge health
Write-Host "Portable path scan passed."
