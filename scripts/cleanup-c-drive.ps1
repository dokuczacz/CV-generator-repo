<#
cleanup-c-drive.ps1

Safe, reusable PowerShell script to scan and optionally clean common C: drive targets.
Usage examples:
  # Dry-run (default): show what would be done
  pwsh .\scripts\cleanup-c-drive.ps1

  # Perform actions interactively (prompts)
  pwsh .\scripts\cleanup-c-drive.ps1 -Run

  # Non-interactive, auto-confirm and archive installer cache
  pwsh .\scripts\cleanup-c-drive.ps1 -Run -AutoConfirm -InstallerAction archive -ArchivePath 'C:\Archive\Windows-Installer-Cache'

Params:
  -Run             : actually perform removals (otherwise script simulates)
  -AutoConfirm     : skip prompts (use with care)
  -InstallerAction : 'archive'|'delete'|'skip' (default: 'archive')
  -ArchivePath     : path to move archived installer files (default shown below)
  -TempAgeDays     : age in days for temp cleanup (default 7)
#>

param(
    [switch]$Run,
    [switch]$AutoConfirm,
    [ValidateSet('archive','delete','skip')]
    [string]$InstallerAction = 'archive',
    [string]$ArchivePath = 'C:\Archive\Windows-Installer-Cache',
    [int]$TempAgeDays = 7
)

function Write-Log { param($m) Write-Host "[cleanup] $m" }

function Get-LargestFiles {
    param($Root = 'C:\', $Top = 20)
    Write-Log "Scanning top $Top files under $Root (may take time)..."
    Get-ChildItem -Path $Root -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { -not $_.PSIsContainer } |
        Sort-Object Length -Descending |
        Select-Object -First $Top |
        ForEach-Object { [PSCustomObject]@{ Path=$_.FullName; SizeBytes=$_.Length; SizeMB = [math]::Round($_.Length/1MB,2) } }
}

function Get-LargestFolders {
    param($Root = 'C:\Users', $Top = 20)
    Write-Log "Computing folder sizes at depth=1 for $Root..."
    Get-ChildItem -Path $Root -Directory -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            $size = (Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum).Sum
            [PSCustomObject]@{ Folder = $_.FullName; SizeBytes = $size; SizeMB = [math]::Round(($size/1MB),2) }
        } |
        Sort-Object SizeBytes -Descending |
        Select-Object -First $Top
}

function Clean-Temp {
    param($Days = $TempAgeDays)
    $paths = @($env:TEMP, "$env:SystemRoot\Temp") | Where-Object { $_ -and (Test-Path $_) }
    foreach ($p in $paths) {
        Write-Log "Checking temp path: $p for files older than $Days days"
        $cutoff = (Get-Date).AddDays(-$Days)
        $old = Get-ChildItem -Path $p -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer -and $_.LastWriteTime -lt $cutoff }
        $count = ($old | Measure-Object).Count
        $total = ($old | Measure-Object -Property Length -Sum).Sum
        Write-Log "Found $count files totaling $([math]::Round($total/1MB,2)) MB in $p"
        if ($count -gt 0) {
            if ($Run -or $AutoConfirm) {
                Write-Log "Removing files from $p"
                $old | ForEach-Object {
                    try { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop } catch { Write-Log ('Skipped: ' + $_.FullName + ' - ' + $_.Exception.Message) }
                }
            } else {
                Write-Log "Dry-run: files not removed. Rerun with -Run to delete."
            }
        }
    }
}

function Handle-InstallerCache {
    param($Action = $InstallerAction, $Archive = $ArchivePath)
    $installerDir = 'C:\Windows\Installer'
    if (-not (Test-Path $installerDir)) { Write-Log "Installer folder not found: $installerDir"; return }
    $top = Get-ChildItem -Path $installerDir -Filter '*.msp' -File -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 10
    if (-not $top) { Write-Log "No .msp files found in $installerDir"; return }
    Write-Log "Top .msp files:"; $top | ForEach-Object { Write-Host ("  {0}  {1}MB" -f $_.FullName, [math]::Round($_.Length/1MB,2)) }
    $total = ($top | Measure-Object -Property Length -Sum).Sum
    Write-Log "Top 10 total: $([math]::Round($total/1MB,2)) MB"

    if ($Action -eq 'skip') { Write-Log "InstallerAction=skip, no changes made."; return }

    if ($Action -eq 'archive') {
        if (-not (Test-Path $Archive)) { Write-Log "Creating archive folder: $Archive"; New-Item -ItemType Directory -Path $Archive -Force | Out-Null }
        foreach ($f in $top) {
            $dest = Join-Path -Path $Archive -ChildPath $f.Name
            if ($Run -or $AutoConfirm) {
                try { Move-Item -LiteralPath $f.FullName -Destination $dest -Force -ErrorAction Stop; Write-Log ('Moved ' + $f.Name + ' -> ' + $dest) } catch { Write-Log ('Failed to move ' + $f.Name + ': ' + $_.Exception.Message) }
            } else { Write-Log ('Dry-run: would move ' + $f.FullName + ' -> ' + $dest) }
        }
    }
    elseif ($Action -eq 'delete') {
        foreach ($f in $top) {
            if ($Run -or $AutoConfirm) {
                try { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop; Write-Log ('Deleted ' + $f.Name) } catch { Write-Log ('Failed to delete ' + $f.Name + ': ' + $_.Exception.Message) }
            } else { Write-Log ('Dry-run: would delete ' + $f.FullName) }
        }
    }
}

function Remove-DockerVHDX {
    $candidates = @(
        "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx",
        "$env:LOCALAPPDATA\Docker\wsl\data\docker_desktop.vhdx",
        "$env:LOCALAPPDATA\DockerDesktop\vm-data\*vhdx"
    )
    foreach ($p in $candidates) {
        $glob = Resolve-Path -LiteralPath $p -ErrorAction SilentlyContinue | ForEach-Object { $_.ProviderPath } 2>$null
        foreach ($path in $glob) {
            if (Test-Path $path) {
                $size = (Get-Item -LiteralPath $path).Length
                Write-Log "Found Docker VHDX: $path ($([math]::Round($size/1GB,2)) GB)"
                if ($Run -or $AutoConfirm) {
                    try { Remove-Item -LiteralPath $path -Force -ErrorAction Stop; Write-Log ('Deleted ' + $path) } catch { Write-Log ('Failed to delete ' + $path + ': ' + $_.Exception.Message) }
                } else { Write-Log ('Dry-run: would delete ' + $path) }
            }
        }
    }
}

function Report-FreeSpace {
    $vol = Get-PSDrive -Name C -ErrorAction SilentlyContinue
    if ($vol) { Write-Log "C: Free=$([math]::Round($vol.Free/1GB,2))GB  Used=$([math]::Round(($vol.Used/1GB),2))GB" } else { Write-Log "Unable to read C: drive info" }
}

# Execution
Write-Log "Starting cleanup script (Run=$Run, AutoConfirm=$AutoConfirm, InstallerAction=$InstallerAction)"
Report-FreeSpace

Write-Log "Listing largest files (top 10) on C:\"
Get-LargestFiles -Root 'C:\' -Top 10 | Format-Table -AutoSize

Write-Log "Listing large folders under C:\Users (top 10)"
Get-LargestFolders -Root 'C:\Users' -Top 10 | Format-Table -AutoSize

Clean-Temp -Days $TempAgeDays
Handle-InstallerCache -Action $InstallerAction -Archive $ArchivePath
Remove-DockerVHDX

Write-Log "Final free space summary"
Report-FreeSpace

Write-Log "Done. Re-run with -Run to execute deletions, or -Run -AutoConfirm for non-interactive execution."
