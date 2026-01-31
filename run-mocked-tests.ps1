# Test runner for mocked OpenAI CV generator workflow
# Runs Playwright tests that walk through the full CV generation UI without calling OpenAI

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "CV Generator - Mocked AI E2E Tests" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "❌ npm not found. Please install Node.js first." -ForegroundColor Red
    exit 1
}

Write-Host "Prerequisites: ✅" -ForegroundColor Green
Write-Host ""

# Ensure frontend dependencies are installed
if (-not (Test-Path "ui/node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Set-Location ui
    npm install
    Set-Location ..
    Write-Host "Frontend ready: ✅" -ForegroundColor Green
}
else {
    Write-Host "Frontend dependencies: ✅" -ForegroundColor Green
}

# Check if backend is running
Write-Host ""
Write-Host "Checking backend health..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:7071/api/health" -Method Get -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "Backend (localhost:7071): ✅" -ForegroundColor Green
    }
}
catch {
    Write-Host "⚠️  Backend not responding at localhost:7071" -ForegroundColor Yellow
    Write-Host "   Make sure to run: func start (in another terminal)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Checking frontend..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3000" -Method Get -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "Frontend (localhost:3000): ✅" -ForegroundColor Green
    }
}
catch {
    Write-Host "⚠️  Frontend not running at localhost:3000" -ForegroundColor Yellow
    Write-Host "   Make sure to run: npm run dev (in another terminal, from ui/)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Running mocked E2E tests..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Run the specific mocked test file
npm test -- tests/e2e/cv-generator-mocked.spec.ts

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Test Summary:" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✅ = UI stage rendered correctly" -ForegroundColor Green
Write-Host "🔄 = Mocked OpenAI response used (no real API calls)" -ForegroundColor Blue
Write-Host "📊 = Final PDF generated" -ForegroundColor Green
Write-Host ""
Write-Host "Test artifacts saved to: tests/test-output/" -ForegroundColor Gray
Write-Host "=========================================" -ForegroundColor Cyan
