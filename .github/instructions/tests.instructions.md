---
applyTo: "tests/**, playwright.config.ts"
name: Playwright testing conventions
description: Best practices for Playwright tests and visual regression in this repository
---

# Playwright Testing Conventions

## Test Structure

- **Location:** `/tests/` directory at repo root.
- **Pattern:** `*.spec.ts` for test files.
- **Naming:** Describe what is tested: `test-cv-generation.spec.ts`, not `test.spec.ts`.
- **Organization:** Group related tests in describe blocks.

Example:
```typescript
import { test, expect } from '@playwright/test';

test.describe('CV Generation', () => {
  test('should upload DOCX and generate PDF', async ({ page }) => {
    await page.goto('http://localhost:3000');
    // Test steps...
  });

  test('should validate CV data before generation', async ({ page }) => {
    // Test steps...
  });
});
```

## Visual Regression Testing

- **Use `toHaveScreenshot()`** for visual comparisons.
- **Screenshots stored:** `tests/<test-file>-<test-name>-<browser>.png`
- **Update baseline:** Use `--update-snapshots` flag when intentional changes made.
- **CI mode:** Screenshots compared automatically in CI (see `playwright.config.ts`).

Example:
```typescript
test('CV PDF should render correctly', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.fill('input[type="file"]', 'sample.docx');
  await page.click('button:has-text("Generate CV")');
  await expect(page).toHaveScreenshot('cv-generated.png');
});
```

## Test Fixtures & Artifacts

- **Pretest:** `npm run pretest` runs `tests/generate_test_artifacts.py` to create test fixtures.
- **Fixtures location:** `tests/fixtures/` or `artifacts/`.
- **Generated data:** Sample DOCX, JSON, PDF files used by tests.
- **Don't commit generated artifacts:** Git-ignore `test-results/` and artifact directories.

Example (`tests/generate_test_artifacts.py`):
```python
import json
import pathlib

fixtures_dir = pathlib.Path(__file__).parent / 'fixtures'
fixtures_dir.mkdir(exist_ok=True)

# Generate sample CV data
cv_data = {
    'full_name': 'John Doe',
    'email': 'john@example.com',
    'phone': '+41 76 123 4567',
    # ...
}

(fixtures_dir / 'sample_cv.json').write_text(json.dumps(cv_data, indent=2))
```

## Configuration

- **Config file:** `playwright.config.ts` at repo root.
- **Test directory:** `./tests/`
- **Output directory:** `./test-results/` (git-ignored).
- **Report:** HTML report in `playwright-report/`.
- **Browsers:** Currently configured for Chromium (add more if needed: Firefox, Safari).

Key settings:
```typescript
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,  // Fail in CI if `.only` found
  retries: process.env.CI ? 2 : 0,  // Retry 2x in CI
  workers: process.env.CI ? 1 : undefined,  // 1 worker in CI, auto in local
  reporter: 'html',  // HTML report
  outputDir: 'test-results/',
});
```

## Running Tests

```bash
# Run all tests
npm test

# Run with browser visible (headed mode)
npm run test:headed

# Interactive UI mode
npm run test:ui

# Debug specific test
npm run test:debug

# Update visual baselines
npm test -- --update-snapshots

# View HTML report
npm run show-report
```

## Best Practices

- **One test per scenario:** Don't test multiple things in one test.
- **Clear assertions:** Use specific assertions, not just `expect(something).toBeTruthy()`.
- **Wait for elements:** Use `page.waitForSelector()`, not arbitrary `page.waitForTimeout()`.
- **Clean state:** Start each test from known state (clear cache, reset DB if needed).
- **No hardcoded delays:** Use Playwright's wait functions.

Example (good):
```typescript
test('should show error for missing email', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.fill('input[name="full_name"]', 'John Doe');
  // Skip email field
  await page.click('button[type="submit"]');
  await expect(page.locator('text=Email is required')).toBeVisible();
});
```

## Test Artifacts

- **Location:** `test-results/` directory (created after test run).
- **Contents:**
  - HTML report: `index.html`
  - Screenshots: `*.png` (on failure or `toHaveScreenshot()`)
  - Videos: `*.webm` (if configured)
  - Traces: `*.zip` (for debugging)

## Troubleshooting

**Tests timeout:**
```bash
# Increase timeout in config or per test
test.setTimeout(60000); // 60 seconds
```

**Screenshots don't match (intentional change):**
```bash
npm test -- --update-snapshots
```

**Test can't find element:**
```typescript
// Debug: inspect page DOM
await page.pause(); // Interactive debugger
// Or check what's actually rendered
console.log(await page.content());
```

## Avoid

- ❌ Hard-coded `page.waitForTimeout(5000)` — use `page.waitForSelector()`.
- ❌ Flaky tests (missing waits, race conditions) — use `waitForNavigation()`, `waitForLoadState()`.
- ❌ Committing generated artifacts (`test-results/`, browser downloads).
- ❌ Tests that modify global state (use `test.afterEach()` cleanup).
- ❌ Tests that depend on external services — mock or use `@playwright/test` fixtures.

## References

- [Playwright Documentation](https://playwright.dev)
- [Visual Comparisons](https://playwright.dev/docs/test-snapshots)
- [Configuration Guide](https://playwright.dev/docs/test-configuration)
- [Best Practices](https://playwright.dev/docs/best-practices)

