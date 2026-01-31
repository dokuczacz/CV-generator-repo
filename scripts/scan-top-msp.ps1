<#
scan-top-msp.ps1

Scans top N .msp files in C:\Windows\Installer for digital signature and
searches for a small set of identifying strings. Uses a timeout per file.

Usage: pwsh .\scripts\scan-top-msp.ps1 -Top 3 -TimeoutSec 8
#>

param(
    [int]$Top = 3,
    [int]$TimeoutSec = 8
)

$patterns = @('Visual C','Visual Studio','Microsoft Visual C++','VC Runtime','Microsoft Corporation')

$installer = 'C:\Windows\Installer'
if (-not (Test-Path $installer)) { Write-Host "Installer folder not found: $installer"; exit 0 }

$topFiles = Get-ChildItem -Path $installer -Filter '*.msp' -File -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First $Top
if (-not $topFiles -or $topFiles.Count -eq 0) { Write-Host "No .msp files found"; exit 0 }

foreach ($f in $topFiles) {
    Write-Host "FILE: $($f.FullName) SIZE: $([math]::Round($f.Length/1MB,2))MB"
    try { $sig = Get-AuthenticodeSignature -FilePath $f.FullName -ErrorAction Stop } catch { $sig = $null }
    if ($sig -and $sig.SignerCertificate) { Write-Host ('  Signer: ' + $sig.SignerCertificate.Subject) } else { Write-Host '  Signer: None/Unsigned' }

    $job = Start-Job -ScriptBlock {
        param($path,$patterns)
        foreach ($p in $patterns) {
            try {
                if (Select-String -Path $path -Pattern $p -SimpleMatch -Quiet) { Write-Output ('  Contains: ' + $p) }
            } catch {}
        }
    } -ArgumentList $f.FullName,$patterns

    if (Wait-Job $job -Timeout $TimeoutSec) {
        Receive-Job $job | ForEach-Object { Write-Host $_ }
    } else {
        Write-Host '  Scan timed out'
        Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
    }
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    Write-Host '---'
}
