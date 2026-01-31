<#
map-msp-to-product.ps1

Search common Installer/Uninstall registry locations for references to .msp filenames.
Outputs simple text mapping for each filename.
#>

$files = @('d936fb.msp','d9350a.msp','bb5ba.msp','bb3ba.msp','15af0f3a.msp','15af114f.msp','1305f22e.msp','2375622.msp','237555d.msp','eb8e44d.msp')
$roots = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer',
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData'
)

foreach ($f in $files) {
    Write-Output "FILE: $f"
    $found = $false
    foreach ($r in $roots) {
        if (-not (Test-Path $r)) { continue }
        try {
            Get-ChildItem -Path $r -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                $p = $null
                try { $p = Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue } catch { $p = $null }
                if ($p) {
                    foreach ($prop in $p.PSObject.Properties) {
                        $val = $prop.Value
                        if ($val -and ($val -is [string]) -and ($val -like "*${f}*")) {
                            Write-Output ("  RegistryMatch: Root=$r Key=" + $_.PSPath + " Prop=" + $prop.Name + " Value=" + $val)
                            $found = $true
                        }
                    }
                }
            }
        } catch {}
    }
    if (-not $found) { Write-Output "  No registry text match found for $f" }
    Write-Output '---'
}
