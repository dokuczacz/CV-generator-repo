# Option B: Playwright E2E Tests — Quick Start

## Setup (1 terminal)

```bash
# Terminal 1: Start Azurite (local storage emulator)
azurite -d

# Terminal 2: Start Azure Functions
cd "c:\AI memory\CV-generator-repo"
. .venv\Scripts\Activate.ps1
func start

# Terminal 3: Run tests
cd "c:\AI memory\CV-generator-repo"
npx playwright test tests/delta-e2e.spec.ts --headed
```

## What You'll See

The test suite will:
1. Create a CV session in Azure Functions
2. Confirm the session (stores initial hashes)
3. Edit the work_experience section
4. Generate a context pack with delta markers
5. Verify that:
   - Changed sections (work_experience) have full data
   - Unchanged sections (education) have summaries only
   - Hashes are 16-char hex format
   - PDF generates successfully

## Expected Output

```
✓ Delta Loading E2E (12 steps)
  ✓ Step 1: Create session with sample CV
  ✓ Step 2: Retrieve session and capture initial hashes
  ✓ Step 3: Generate initial context pack (full mode)
  ✓ Step 4: Confirm session (save initial state)
  ✓ Step 5: Modify work_experience section
  ✓ Step 6: Generate delta context pack (delta mode)
  ✓ Step 7: Verify delta mode markers
  ✓ Step 8: Verify changed sections have full data
  ✓ Step 9: Verify unchanged sections are summaries
  ✓ Step 10: Measure token efficiency (pack size)
  ✓ Step 11: Verify section hashes are stable
  ✓ Step 12: Generate PDF to verify workflow end-to-end

✓ Delta Loading Performance
  ✓ Context pack generation with delta < 100ms
```

## Key Assertions

| Test | Expectation |
|------|-------------|
| Step 7 | `work_experience` marked as `changed=true` |
| Step 7 | `education` marked as `changed=false` |
| Step 8 | `work_experience.data` exists and is array |
| Step 9 | `education.count` exists, `education.data` doesn't |
| Step 11 | All hashes match regex `/^[a-f0-9]{16}$/` |
| Performance | Pack generation < 100ms |

## Report

After tests complete, view the HTML report:
```bash
npx playwright show-report
```

This opens detailed test report in browser with:
- Screenshots on each step
- Network logs
- Console output

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot find module 'axios'" | Test is using Playwright's built-in request API, not axios ✓ |
| "Connection refused" | Check `func start` and `azurite -d` are running |
| "Session not found" | Azurite DB may be cleared; restart with `azurite -d` |
| "Delta markers missing" | Verify `CV_DELTA_MODE=1` (it's default in function_app.py) |

## Files Created

- `tests/delta-e2e.spec.ts` — Full E2E test suite (2 test groups, 14 tests)
- `tests/README_DELTA_E2E.md` — Full documentation
- `test-results/delta-test-output.pdf` — Generated during test run

## Next: Option A (Live Smoke Test)

After E2E tests pass, do Option A:
1. Upload a real CV via the UI (http://localhost:3000)
2. Edit a section
3. Verify delta markers in browser console (optional DevTools inspection)
4. Generate PDF

Then report results back! 🚀
