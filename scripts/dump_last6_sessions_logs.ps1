$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $repoRoot 'tmp\\logs'

if (-not (Test-Path $logDir -PathType Container)) {
  throw "Log dir not found: $logDir"
}

$outDir = Join-Path $repoRoot 'tmp\\debug_last6_sessions'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$uiLogs = Get-ChildItem $logDir -Filter 'ui_*.log' | Sort-Object LastWriteTime -Descending
if ($uiLogs.Count -eq 0) {
  throw "No UI logs found under: $logDir (expected ui_*.log)"
}

function Get-RecentSessionIdsFromUiLogs {
  param([System.IO.FileInfo[]]$Files)

  $ids = New-Object System.Collections.Generic.List[string]
  foreach ($f in $Files) {
    $lines = Get-Content $f.FullName
    foreach ($m in ($lines | Select-String -Pattern 'session_id \(returned\):\s*(.+)$')) {
      $sid = $m.Matches[0].Groups[1].Value.Trim()
      if ($sid -and $sid -ne 'none') { [void]$ids.Add($sid) }
    }
  }
  return $ids.ToArray() | Select-Object -Unique
}

function Extract-SessionBlocksFromUiLog {
  param(
    [string]$Raw,
    [string]$SessionId
  )

  $blocks = $Raw -split "=== Backend Process CV Request ==="
  $hits = New-Object System.Collections.Generic.List[string]
  foreach ($b in $blocks) {
    if ($b -match [regex]::Escape("session_id (returned): $SessionId")) {
      [void]$hits.Add("=== Backend Process CV Request ===" + $b)
    }
  }
  return $hits.ToArray()
}

$sessionIds = Get-RecentSessionIdsFromUiLogs -Files $uiLogs | Select-Object -First 6

$index = [ordered]@{
  generated_at = (Get-Date).ToString('o')
  log_dir      = $logDir
  out_dir      = $outDir
  sessions     = @()
}

foreach ($sid in $sessionIds) {
  $found = $false
  foreach ($f in $uiLogs) {
    $raw = Get-Content $f.FullName -Raw
    if ($raw -notmatch [regex]::Escape("session_id (returned): $sid")) { continue }

    $blocks = Extract-SessionBlocksFromUiLog -Raw $raw -SessionId $sid
    if ($blocks.Count -eq 0) { continue }

    $block = $blocks[-1]
    $outPath = Join-Path $outDir ("ui_block_{0}.log" -f $sid)
    $block | Out-File -FilePath $outPath -Encoding utf8 -Force

    $index.sessions += [ordered]@{
      session_id = $sid
      source_log = $f.Name
      block_file = (Split-Path -Leaf $outPath)
      note = "Open block_file to see tool calls + Has PDF + pdf length."
    }

    $found = $true
    break
  }

  if (-not $found) {
    $index.sessions += [ordered]@{
      session_id = $sid
      source_log = $null
      block_file = $null
      has_pdf    = $null
      pdf_base64_length = $null
      tools_used = @()
      note = 'Session id found, but no matching block was located in ui_*.log files.'
    }
  }
}

$indexPath = Join-Path $outDir 'index.json'
$index | ConvertTo-Json -Depth 6 | Set-Content -Path $indexPath -Encoding UTF8

Write-Host ("wrote {0}" -f $indexPath)
Write-Host ("sessions: {0}" -f $index.sessions.Count)
