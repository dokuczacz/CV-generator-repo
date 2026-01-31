---
applyTo: "tests/**, playwright.config.ts"
name: Playwright testing conventions
description: Best practices for Playwright tests and visual regression in this repository
---

# Playwright Testing Conventions

This repository includes **LLM-driven orchestration**. For cross-cutting LLM risk controls and the recommended test pyramid, also follow:
- `.github/instructions/llm-orchestration.instructions.md`

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

## LLM / Orchestration Testing Cookbook (portable)

When workflows include an LLM, tests must be designed for **bounded nondeterminism**.

### Recommended test pyramid

1. **Tier 0 — Deterministic checks (fast, always-on)**
  - Prompt builder smoke tests.
  - Schema validation.
  - Stage/state machine logic.

2. **Tier 1 — Contract tests (no browser, no real LLM)**
  - Call the orchestrator boundary directly (API route or backend function).
  - Run with AI disabled/mocked.
  - Assert JSON shape + stage transitions + error handling.

3. **Tier 2 — Record/Replay E2E (deterministic)**
  - Replay recorded successful outputs from fixtures.
  - Assert contract invariants, not exact wording.

4. **Tier 3 — Live LLM canaries (opt-in only)**
  - Must be explicitly enabled via env vars.
  - Run `--workers=1` to reduce rate-limit flakiness.
  - Keep assertions coarse (no exact phrasing).

### What to assert (LLM-safe)

Prefer:
- Response JSON validates against the expected schema.
- Required fields present and types correct.
- Stage/state is correct.
- Output constraints met (e.g., “PDF produced”, “2 pages”, “no error banner”).

Avoid:
- Exact assistant text.
- Exact bullet wording.
- Exact ordering unless it is part of the contract.

### Record/Replay fixtures

Use fixtures to make orchestration tests deterministic.

Guidelines:
- Store fixtures as **inputs → outputs** at the orchestration boundary (API response JSON), not as DOM text.
- Key fixtures by stable identifiers like `(scenario, stage, action_id, schema_version)`.
- Keep fixtures small; avoid embedding full documents when not needed.
- Redact secrets.

This repo already uses stage fixtures under `tests/fixtures/` and a mocked E2E spec; treat that as the starting point for a reusable record/replay approach.

### Live LLM tests (opt-in gating)

Live LLM tests must be opt-in and isolated:
- Require an explicit env flag (e.g., `RUN_OPENAI_E2E=1`) and the API key.
- Keep the suite serial and low-worker.
- Treat these tests as **canaries**, not default CI blockers.

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

