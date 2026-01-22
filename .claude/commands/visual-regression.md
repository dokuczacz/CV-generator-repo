# Visual Regression Command

Runs Playwright visual regression tests and compares generated CVs with approved baselines.

---

## Usage

```
/visual-regression [options]
```

**Examples:**
```
/visual-regression
/visual-regression --update-baselines
/visual-regression --headed
/visual-regression --language=de
```

---

## Workflow

### Step 1: Generate Test Artifacts
Run pre-test script to generate test CVs:

```bash
npm run pretest
# Executes: python tests/generate_test_artifacts.py
```

**Artifacts created:**
- `artifacts/test_cv_en.json` (English CV)
- `artifacts/test_cv_de.json` (German CV)
- `artifacts/test_cv_pl.json` (Polish CV)

### Step 2: Run Playwright Tests
Execute visual regression tests:

```bash
npm test
# Or for headed mode:
npm run test:headed
```

**Tests executed:**
- `tests/test-cv-generation.spec.ts`
  - ✅ Generate English CV
  - ✅ Generate German CV
  - ✅ Generate Polish CV
  - ✅ Compare screenshots with baselines

### Step 3: Analyze Results
Playwright compares screenshots pixel-by-pixel:

**Diff threshold:** 5% (configurable in `playwright.config.ts`)

**Possible outcomes:**
- ✅ **PASS** - Screenshots match baselines (≤5% diff)
- ❌ **FAIL** - Screenshots differ from baselines (>5% diff)
- ⚠️ **NEW** - No baseline exists (first run)

### Step 4: Review Failures
If tests fail, Playwright generates comparison files:

```
test-results/
├── test-cv-generation-english-cv/
│   ├── cv-english-actual.png        # New screenshot
│   ├── cv-english-expected.png      # Baseline
│   └── cv-english-diff.png          # Highlighted differences
```

**Use Playwright MCP to display diffs side-by-side.**

### Step 5: Decision Point
Ask user:

**Option A:** Accept new baselines (intentional change)
```bash
npm test -- --update-snapshots
```

**Option B:** Investigate and fix (unintended change)
- Review CSS changes in [templates/html/cv_template_2pages_2025.css](../../templates/html/cv_template_2pages_2025.css)
- Check HTML template modifications
- Verify WeasyPrint rendering differences

**Option C:** Adjust threshold (minor acceptable differences)
Edit `playwright.config.ts`:
```typescript
expect: {
  toMatchSnapshot: { threshold: 0.1 }  // 10% diff allowed
}
```

---

## Flags

- `--update-baselines` - Accept all current screenshots as new baselines
- `--headed` - Run tests with visible browser
- `--debug` - Run in debug mode (step through tests)
- `--language=<en|de|pl>` - Test specific language only
- `--ui` - Interactive UI mode

---

## Output Format

```
Running visual regression tests...

Generating test artifacts...
✅ artifacts/test_cv_en.json (1.2KB)
✅ artifacts/test_cv_de.json (1.3KB)
✅ artifacts/test_cv_pl.json (1.1KB)

Running Playwright tests...

test-cv-generation.spec.ts:
  ✅ English CV generation (2.3s)
     Diff: 1.2% (below 5% threshold)

  ❌ German CV generation (2.1s)
     Diff: 8.7% (exceeds 5% threshold)
     See: test-results/test-cv-generation-german-cv/cv-german-diff.png

  ✅ Polish CV generation (2.4s)
     Diff: 0.8% (below 5% threshold)

Results: 2 passed, 1 failed

German CV diff detected:
[Display diff image inline if Playwright MCP available]

Accept new baseline for German CV? (yes/no/investigate)
```

---

## Common Failure Scenarios

### 1. Font Rendering Differences
**Symptom:** Small pixel differences in text rendering
**Cause:** Font hinting, anti-aliasing variations
**Fix:** Increase threshold slightly or ensure consistent font files

### 2. WeasyPrint Version Changes
**Symptom:** Layout shifts after WeasyPrint update
**Cause:** CSS rendering engine differences
**Fix:** Pin WeasyPrint version in `requirements.txt` or update baselines

### 3. Template CSS Modifications
**Symptom:** Intentional design changes flagged as failures
**Cause:** Updated styles in `cv_template_2pages_2025.css`
**Fix:** Accept new baselines with `--update-baselines`

### 4. Multi-Language Edge Cases
**Symptom:** German/Polish CVs fail but English passes
**Cause:** Character encoding, special characters, longer words
**Fix:** Review language-specific CSS (word-break, hyphens)

---

## Extended Thinking Mode

For complex visual regressions, use **"think hard"** mode:

```
think hard: Why does the German CV have 8.7% diff when only CSS padding changed?
```

Claude will:
1. Analyze CSS cascade effects
2. Check for language-specific layout impacts
3. Identify potential WeasyPrint quirks
4. Suggest root cause and fix

---

## Related Commands

- `/validate-cv` - Validate CV before visual regression
- `/generate-pdf` - Generate PDF for manual review
- `/update-template` - Update CV template with new design

---

## CI/CD Integration

**GitHub Actions workflow:**
```yaml
- name: Visual Regression Tests
  run: npm test

- name: Upload test results
  if: failure()
  uses: actions/upload-artifact@v3
  with:
    name: playwright-results
    path: test-results/
```

**Headless CI mode (Phase 3):**
```bash
claude -p "Run visual regression tests and report failures" --headless
```

---

## Baselines Location

**Stored in:** `test-results/` (gitignored)

**Baseline management:**
- Keep baselines in version control? **No** (too large, binary files)
- Alternative: Store in Azure Blob Storage with versioning
- Reference baseline hash in git: `baselines.sha256`

**Recommendation:**
```bash
# Generate baseline hashes
find test-results -name "*-expected.png" -exec sha256sum {} \; > baselines.sha256
git add baselines.sha256
git commit -m "docs: update visual regression baselines (German layout fix)"
```

---

## Performance Tips

**Faster test runs:**
1. Test single language: `npm test -- --grep="English CV"`
2. Skip artifact regeneration: `npm test` (without `pretest`)
3. Use headed mode for debugging only
4. Parallelize tests (Playwright does this automatically)

**Baseline storage:**
- Compress PNGs: `optipng test-results/**/*-expected.png`
- Store in blob storage for CI/CD
- Download baselines on-demand