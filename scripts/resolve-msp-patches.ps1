<#
resolve-msp-patches.ps1

For known .msp filenames, find associated Patch registry keys and map to product DisplayName when possible.
#>

$files = @('d936fb.msp','d9350a.msp','bb5ba.msp','bb3ba.msp','15af0f3a.msp','15af114f.msp','1305f22e.msp','2375622.msp','237555d.msp','eb8e44d.msp')
$patchesRoot = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Patches'

foreach ($f in $files) {
    Write-Output "FILE: $f"
    $foundAny = $false
    if (-not (Test-Path $patchesRoot)) { Write-Output '  Patches registry path not present'; Write-Output '---'; continue }
    Get-ChildItem -Path $patchesRoot -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        $pp = $null
        try { $pp = Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue } catch { $pp = $null }
        if ($pp -and $pp.LocalPackage -and ($pp.LocalPackage -like "*" + $f + "*")) {
            $foundAny = $true
            Write-Output ("  PatchKey: " + $_.PSPath)
            Write-Output ("    LocalPackage=" + $pp.LocalPackage)
            $prodPath = Join-Path -Path $_.PSPath -ChildPath 'Products'
            if (Test-Path $prodPath) {
                Get-ChildItem -Path $prodPath -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                    $p2 = $null
                    try { $p2 = Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue } catch { $p2 = $null }
                    if ($p2) {
                        # Attempt to find product code from key name
                        $prodKeyPath = $_.PSPath
                        Write-Output ("    ProductKey: " + $prodKeyPath)
                        # Try to read DisplayName under corresponding InstallProperties
                        # Transform product key path to Products GUID part
                        $parts = $prodKeyPath -split '\\'
                        $guid = $parts[-1]
                        # Installer stores product info under ...\Products\<guid>\InstallProperties
                        $installProps = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\$guid\InstallProperties"
                        if (Test-Path $installProps) {
                            try { $ip = Get-ItemProperty -Path $installProps -ErrorAction SilentlyContinue } catch { $ip = $null }
                            if ($ip -and $ip.DisplayName) { Write-Output ("      DisplayName: " + $ip.DisplayName) }
                            elseif ($ip -and $ip.ProductName) { Write-Output ("      ProductName: " + $ip.ProductName) }
                            else { Write-Output ("      InstallProperties present but no DisplayName") }
                        } else {
                            # Fallback: try Uninstall key
                            $unKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$guid"
                            if (Test-Path $unKey) {
                                try { $u = Get-ItemProperty -Path $unKey -ErrorAction SilentlyContinue } catch { $u = $null }
                                if ($u -and $u.DisplayName) { Write-Output ("      Uninstall DisplayName: " + $u.DisplayName) }
                            } else {
                                Write-Output ("      No InstallProperties/Uninstall info for product GUID: $guid")
                            }
                        }
                    }
                }
            } else {
                Write-Output "    No Products subkey under patch key"
            }
        }
    }
    if (-not $foundAny) { Write-Output "  No patch registry entry found for $f" }
    Write-Output '---'
}
