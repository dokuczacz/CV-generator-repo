param(
    [switch]$NoAzurite,
    [switch]$NoUi
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $repoRoot "tmp\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$startedProcesses = @()

function Start-PwshBackgroundProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDir,
        [Parameter(Mandatory = $true)][string]$CommandLine
    )

    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("Set-Location '$WorkingDir'; $CommandLine"))
    $proc = Start-Process -FilePath "pwsh" -ArgumentList @("-NoProfile", "-EncodedCommand", $encoded) -PassThru -WindowStyle Hidden
    Write-Host "[run-local] $Name started in pwsh process PID=$($proc.Id)"
    return $proc
}

if (-not $NoAzurite) {
    $azuriteLog = ".\tmp\logs\azurite_$ts.log"
    $proc = Start-PwshBackgroundProcess -Name "Azurite" -WorkingDir $repoRoot -CommandLine "azurite -d 2>&1 | Tee-Object -FilePath '$azuriteLog'"
    $startedProcesses += $proc
    Write-Host "[run-local] Azurite log: $azuriteLog"
}

if (-not $NoUi) {
    $uiLog = ".\tmp\logs\ui_$ts.log"
    $uiDir = Join-Path $repoRoot "ui"
    $proc = Start-PwshBackgroundProcess -Name "UI" -WorkingDir $uiDir -CommandLine "npm run dev 2>&1 | Tee-Object -FilePath '$uiLog'"
    $startedProcesses += $proc
    Write-Host "[run-local] UI log: $uiLog"
}

$funcLog = ".\tmp\logs\func_$ts.log"
Write-Host "[run-local] Backend starting in foreground (log: $funcLog)"

try {
    func start false 2>&1 | Tee-Object -FilePath $funcLog
}
finally {
    if ($startedProcesses.Count -gt 0) {
        Write-Host "[run-local] Stopping background pwsh processes..."
        foreach ($proc in $startedProcesses) {
            try {
                if (-not $proc.HasExited) {
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                }
            } catch {}
        }
    }
}
