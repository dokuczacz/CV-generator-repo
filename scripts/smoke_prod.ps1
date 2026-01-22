param(
  [string]$BaseUrl,
  [string]$FunctionsKey,
  [string]$OutPdfPath
)

# Note:
# - Local session E2E smoke (Functions running on http://127.0.0.1:7071) is in: scripts/smoke_local_session.py

$ErrorActionPreference = 'Stop'

try {
  Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
} catch {
  # Best-effort; some hosts pre-load this already.
}

function Get-HttpErrorBody {
  param([Parameter(Mandatory=$true)]$ErrorRecord)

  try {
    $resp = $ErrorRecord.Exception.Response
    if (-not $resp) { return $null }
    $stream = $resp.GetResponseStream()
    if (-not $stream) { return $null }
    $reader = New-Object System.IO.StreamReader($stream)
    $text = $reader.ReadToEnd()
    $reader.Close()
    return $text
  } catch {
    return $null
  }
}

function Get-EnvValueFromFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Name
  )

  if (-not (Test-Path $Path)) {
    throw "Missing env file: $Path"
  }

  $line = Get-Content -Path $Path | Where-Object { $_ -match "^$([Regex]::Escape($Name))=" } | Select-Object -First 1
  if (-not $line) {
    throw "Missing $Name in $Path"
  }

  return ($line -split '=', 2)[1].Trim()
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$uiEnv = Join-Path $repoRoot 'ui/.env.local'

if (-not $OutPdfPath) {
  $OutPdfPath = Join-Path $repoRoot 'artifacts/prod_smoke_cv.pdf'
}

if (-not $BaseUrl) {
  $BaseUrl = Get-EnvValueFromFile -Path $uiEnv -Name 'NEXT_PUBLIC_AZURE_FUNCTIONS_URL'
}
if (-not $FunctionsKey) {
  $FunctionsKey = Get-EnvValueFromFile -Path $uiEnv -Name 'NEXT_PUBLIC_AZURE_FUNCTIONS_KEY'
}

$headersKeyOnly = @{ 'x-functions-key'=$FunctionsKey }

function New-HttpClient {
  $handler = New-Object System.Net.Http.HttpClientHandler
  $client = New-Object System.Net.Http.HttpClient($handler)
  $client.Timeout = [TimeSpan]::FromSeconds(90)
  if ($FunctionsKey) {
    $client.DefaultRequestHeaders.Remove('x-functions-key') | Out-Null
    $client.DefaultRequestHeaders.Add('x-functions-key', $FunctionsKey)
  }
  return $client
}

function Post-Json {
  param(
    [Parameter(Mandatory=$true)][System.Net.Http.HttpClient]$Client,
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$Json
  )

  $content = New-Object System.Net.Http.StringContent($Json, [System.Text.Encoding]::UTF8, 'application/json')
  $resp = $Client.PostAsync($Url, $content).GetAwaiter().GetResult()
  $text = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
  return @{ StatusCode = [int]$resp.StatusCode; BodyText = $text }
}

Write-Host "Prod smoke tests: $BaseUrl" -ForegroundColor Cyan

$sw = [System.Diagnostics.Stopwatch]::new()

# 1) Health
$sw.Restart()
$health = Invoke-RestMethod -Method GET -Uri "$BaseUrl/health" -Headers $headersKeyOnly
$sw.Stop()
Write-Host ("health: {0}ms status={1} version={2}" -f $sw.ElapsedMilliseconds, $health.status, $health.version)

$client = New-HttpClient

# 2) Validate minimal CV
$cv = Get-Content -Raw (Join-Path $repoRoot 'samples/minimal_cv.json') | ConvertFrom-Json
$body = @{ cv_data = $cv } | ConvertTo-Json -Depth 30
$sw.Restart()
$valResp = Post-Json -Client $client -Url "$BaseUrl/validate-cv" -Json $body
$sw.Stop()
if ($valResp.StatusCode -ge 200 -and $valResp.StatusCode -lt 300) {
  $val = $valResp.BodyText | ConvertFrom-Json
  Write-Host ("validate-cv: {0}ms is_valid={1} est_pages={2}" -f $sw.ElapsedMilliseconds, $val.is_valid, $val.estimated_pages)
} else {
  $snippet = $valResp.BodyText.Substring(0, [Math]::Min(2000, $valResp.BodyText.Length))
  Write-Host ("validate-cv: {0}ms FAILED HTTP {1}`n{2}" -f $sw.ElapsedMilliseconds, $valResp.StatusCode, $snippet) -ForegroundColor Yellow
}

# 3) Extract photo from sample DOCX
$docxPath = Join-Path $repoRoot 'samples/Lebenslauf_Mariusz_Horodecki_CH.docx'
$docxBytes = [IO.File]::ReadAllBytes($docxPath)
$docxB64 = [Convert]::ToBase64String($docxBytes)
$body = @{ docx_base64 = $docxB64 } | ConvertTo-Json -Depth 5
$sw.Restart()
$photoResp = Post-Json -Client $client -Url "$BaseUrl/extract-photo" -Json $body
$sw.Stop()
if ($photoResp.StatusCode -ge 200 -and $photoResp.StatusCode -lt 300) {
  $photo = $photoResp.BodyText | ConvertFrom-Json
  $hasPhoto = [bool]$photo.photo_data_uri
  $prefix = if ($photo.photo_data_uri) { $photo.photo_data_uri.Substring(0, [Math]::Min(20, $photo.photo_data_uri.Length)) } else { '' }
  Write-Host ("extract-photo: {0}ms has_photo={1} data_uri_prefix={2}" -f $sw.ElapsedMilliseconds, $hasPhoto, $prefix)
} else {
  $snippet = $photoResp.BodyText.Substring(0, [Math]::Min(2000, $photoResp.BodyText.Length))
  Write-Host ("extract-photo: {0}ms FAILED HTTP {1}`n{2}" -f $sw.ElapsedMilliseconds, $photoResp.StatusCode, $snippet) -ForegroundColor Yellow
}

# 4) Generate CV Action (max payload + inject source_docx_base64)
$payload = Get-Content -Raw (Join-Path $repoRoot 'samples/max_valid_cv_payload.json') | ConvertFrom-Json
$payload | Add-Member -NotePropertyName source_docx_base64 -NotePropertyValue $docxB64 -Force
$body = $payload | ConvertTo-Json -Depth 60
$sw.Restart()
$genResp = Post-Json -Client $client -Url "$BaseUrl/generate-cv-action" -Json $body
$sw.Stop()
if ($genResp.StatusCode -ge 200 -and $genResp.StatusCode -lt 300) {
  $gen = $genResp.BodyText | ConvertFrom-Json
  $pdfLen = if ($gen.pdf_base64) { $gen.pdf_base64.Length } else { 0 }
  Write-Host ("generate-cv-action: {0}ms success={1} pdf_len={2} debug_allow_pages={3}" -f $sw.ElapsedMilliseconds, $gen.success, $pdfLen, $gen.debug_allow_pages)

  if ($gen.success -and $gen.pdf_base64) {
    $outPath = $OutPdfPath
    $outDir = Split-Path -Parent $outPath
    if ($outDir -and -not (Test-Path $outDir)) {
      New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    try {
      $pdfBytes = [Convert]::FromBase64String($gen.pdf_base64)
      [IO.File]::WriteAllBytes($outPath, $pdfBytes)
      Write-Host ("Saved prod PDF: {0} ({1} bytes)" -f $outPath, $pdfBytes.Length) -ForegroundColor Green
    } catch {
      Write-Host ("Failed to save PDF to {0}: {1}" -f $outPath, $_.Exception.Message) -ForegroundColor Yellow
    }
  }
} else {
  $snippet = $genResp.BodyText.Substring(0, [Math]::Min(2000, $genResp.BodyText.Length))
  Write-Host ("generate-cv-action: {0}ms FAILED HTTP {1}`n{2}" -f $sw.ElapsedMilliseconds, $genResp.StatusCode, $snippet) -ForegroundColor Yellow
}

Write-Host "OK: prod smoke tests finished" -ForegroundColor Green
