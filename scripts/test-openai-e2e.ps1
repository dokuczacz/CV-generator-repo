param(
  [int]$Workers = 1,
  [string]$Grep,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PlaywrightArgs
)

$ErrorActionPreference = 'Stop'

if ($env:RUN_OPENAI_E2E -ne '1') {
  Write-Host 'RUN_OPENAI_E2E is not set to 1. Refusing to run real OpenAI E2E tests.'
  Write-Host 'Set $env:RUN_OPENAI_E2E=1 and ensure OPENAI_API_KEY is set, then re-run.'
  exit 2
}

if (-not $env:OPENAI_API_KEY -or -not $env:OPENAI_API_KEY.Trim()) {
  Write-Host 'OPENAI_API_KEY is missing/empty. Refusing to run real OpenAI E2E tests.'
  exit 2
}

Write-Host "Running OpenAI E2E tests (workers=$Workers)..."

# Ensure the backend actually runs with AI enabled (playwright-start-backend defaults AI off for mocked runs).
if ($env:CV_ENABLE_AI -ne '0') {
  $env:CV_ENABLE_AI = '1'
}

# Default to a more reliable model for strict JSON-schema output.
# You can override via $env:OPENAI_MODEL.
if (-not $env:OPENAI_MODEL -or -not $env:OPENAI_MODEL.Trim()) {
  $env:OPENAI_MODEL = 'gpt-4o'
}

# Improve resilience to occasional empty/invalid outputs.
if (-not $env:OPENAI_JSON_SCHEMA_MAX_ATTEMPTS -or -not $env:OPENAI_JSON_SCHEMA_MAX_ATTEMPTS.Trim()) {
  $env:OPENAI_JSON_SCHEMA_MAX_ATTEMPTS = '3'
}

# Run only the OpenAI E2E spec; keep workers=1 to avoid rate-limit flakiness.
$argsOut = @()
if ($PlaywrightArgs) { $argsOut += $PlaywrightArgs }
if ($Grep -and $Grep.Trim()) { $argsOut += @('--grep', $Grep) }

npx playwright test tests/e2e/openai-e2e.spec.ts --workers=$Workers @argsOut
