# 🚀 Quick Reference Card

## Commands to Remember

```bash
# Development
npm test                    # Run all Playwright tests
npm run test:ui             # Interactive test mode
npm run test:headed         # Run tests with visible browser
npm run show-report         # View test report

# API Server
python api.py              # Start Flask server (localhost:5000)

# Data & Artifacts
python tests/generate_test_artifacts.py    # Generate HTML/PDF for template regression
python src/render.py                       # Quick local preview (writes preview.pdf)

# File Locations
samples/extracted_cv.json                  # Your CV data (JSON)
samples/minimal_cv.json                    # Minimal CV that always passes DoD
tests/test-output/preview.html             # Rendered HTML
tests/test-output/preview.pdf              # Generated PDF
```

## API Endpoints

```bash
# Generate PDF from CV JSON
POST http://localhost:5000/generate-cv
Content-Type: application/json
Body: {cv_data_json}

# Preview as HTML
POST http://localhost:5000/preview-html
Content-Type: application/json
Body: {cv_data_json}

# Health check
GET http://localhost:5000/health
```

## Test Results Summary

- **Total Tests:** 12
- **Status:** ✅ ALL PASSING (100%)
- **Test Categories:**
  - Visual Regression: 8 tests
  - Content Validation: 4 tests

## CV Sections Validated

✅ Profil  
✅ Berufserfahrung (5 entries)  
✅ Ausbildung (2 entries)  
✅ Sprachen (3 languages)  
✅ Fähigkeiten & KI (6 skills)  
✅ Weiterbildungen (6 courses)  
✅ Interessen  
✅ Datenschutzerklärung  

## Key Files

| File | Purpose |
|------|---------|
| [src/render.py](src/render.py) | Core rendering (HTML/PDF) |
| [api.py](api.py) | Flask API endpoint |
| [tests/cv-visual.spec.ts](tests/cv-visual.spec.ts) | Playwright test suite |
| [samples/extracted_cv.json](samples/extracted_cv.json) | Your CV data |
| [TESTING.md](TESTING.md) | Full documentation |
| [TEST_REPORT.md](TEST_REPORT.md) | Test results |

## Next Steps

1. ✅ Run tests: `npm test`
2. ✅ Start API: `python api.py`
3. ⬜ Deploy API to production
4. ⬜ Configure Custom GPT Actions
5. ⬜ Test end-to-end flow

## Testing the API

```powershell
# Terminal 1: Start API
python api.py

# Terminal 2: Test endpoint
$cv = Get-Content samples/extracted_cv.json
$cv | curl -X POST http://localhost:5000/generate-cv \
  -H "Content-Type: application/json" \
  -d @- \
  --output my_cv.pdf
```

## View Test Report

```bash
npm run show-report
```

This opens an interactive HTML report showing all test results, screenshots, and timing.

## Troubleshooting

```bash
# Playwright browser not found
python -m playwright install chromium

# Node dependencies missing
npm install

# Python dependencies
pip install -r requirements.txt
```

---

**Last Updated:** January 14, 2026  
**Status:** Production Ready ✅
