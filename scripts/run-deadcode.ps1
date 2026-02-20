param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$args = @("scripts/deadcode_scan.py")
if ($Strict) {
    $args += "--fail-on-findings"
}

& $python @args
exit $LASTEXITCODE
