param(
  [string[]]$Aliases = @('5.0 medium', '5.2 medium', '5.4 medium'),
  [ValidateSet('storage', 'render')]
  [string]$SchemaMode = 'render',
  [ValidateSet('low', 'medium', 'high')]
  [string]$ReasoningEffort = 'medium',
  [string]$ReasoningSummary = 'detailed',
  [string]$CvJson = 'samples/sample_cv.json',
  [string]$TargetLanguage = 'en',
  [int]$RequestedTokens = 6000,
  [string]$OutDir = 'tmp/inline_parity'
)

$ErrorActionPreference = 'Stop'

if (-not $env:OPENAI_API_KEY -or -not $env:OPENAI_API_KEY.Trim()) {
  if (Test-Path 'local.settings.json') {
    try {
      $settings = Get-Content -Raw 'local.settings.json' | ConvertFrom-Json
      $localKey = $settings.Values.OPENAI_API_KEY
      if ($localKey -and $localKey.Trim()) {
        $env:OPENAI_API_KEY = $localKey
      }
    } catch {
      Write-Host 'Warning: could not parse local.settings.json for OPENAI_API_KEY.'
    }
  }
}

if (-not $env:OPENAI_API_KEY -or -not $env:OPENAI_API_KEY.Trim()) {
  Write-Host 'OPENAI_API_KEY is missing. Set env var or configure local.settings.json Values.OPENAI_API_KEY.'
  exit 2
}

$python = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  $python = 'python'
}

$argsOut = @(
  '.\scripts\run_inline_parity_multimodel.py',
  '--aliases'
)
$argsOut += $Aliases
$argsOut += @(
  '--reasoning-effort', $ReasoningEffort,
  '--reasoning-summary', $ReasoningSummary,
  '--schema-mode', $SchemaMode,
  '--cv-json', $CvJson,
  '--target-language', $TargetLanguage,
  '--requested-tokens', "$RequestedTokens",
  '--out-dir', $OutDir
)

Write-Host "Running inline parity: schema=$SchemaMode reasoning=$ReasoningEffort aliases=$($Aliases -join ', ')"
& $python @argsOut
