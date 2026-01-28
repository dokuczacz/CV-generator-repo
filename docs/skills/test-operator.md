# Test Operator Skill (Copilot-adapted)

**Purpose:** Focused testing/verification: pick the smallest relevant test or repro, run it, and report a clear success signal (avoid long suites without confirmation).

## When to use
- User asks for tests/verification: "test", "verify", "CI", "czy działa", "sprawdź"
- You changed behavior and could plausibly regress something

## Stage-based scope (pick the narrowest validation)

1. **Planning / no code change yet**
   - Do **not** run tests; instead define the exact acceptance signal(s) that will be tested later

2. **Just changed code (local iteration)**
   - Run **one focused** test closest to the change OR one deterministic repro if no tests exist

3. **Milestone / "ready to review" / before commit**
   - Run focused test(s) + the smallest "smoke" subset that catches obvious breakage (still avoid full suite unless asked)

4. **Release / CI failing**
   - Prefer the failing test(s) / job-specific subset

## JSON-only contract gate
When validating a backend in "pre-agent baseline" phase, include at least one check that asserts:
- Responses are JSON only (`Content-Type: application/json`)
- No plaintext fallbacks (even on errors)
- `schema_version` is present where applicable
- Invalid JSON is rejected (HTTP 400) with a JSON error payload

## Output format
Provide:
1. **Test target**: the one behavior you are validating (1 sentence)
2. **Copy/paste commands**: 1–3 commands max (PowerShell-first) to run the *smallest* relevant test(s)
3. **Success signal**: 1 line saying what "pass" looks like
4. If no tests exist: propose the smallest deterministic repro command and (optionally) a minimal test file to add

## Rules
- Prefer a single focused test over whole-suite runs
- Never claim confidence without either: test run output OR deterministic repro with observable success signal
- Don't add new test frameworks unless the repo already uses them
- Don't run destructive commands as "tests"
- Keep output compact (no pasted logs unless the user asks)

---

## Examples (PowerShell-first)

### Python / pytest
```powershell
# Run one file
python -m pytest -q tests/test_something.py

# Run one test by node id
python -m pytest -q tests/test_something.py::test_case_name
```
**Success:** `1 passed` (and exit code 0)

### Playwright (this repo)
```powershell
# Run one spec
npm test -- tests/cv-visual.spec.ts

# Run with visible browser
npm run test:headed -- tests/cv-visual.spec.ts
```
**Success:** exit code 0, no failed tests

### JSON contract smoke (generic HTTP)
```powershell
# Health / basic JSON response shape
curl.exe -sS -D - http://localhost:7071/api/health | Select-String -Pattern '^HTTP/|^Content-Type:|^{'

# Invalid JSON should be rejected (400) with JSON error payload
curl.exe -sS -D - http://localhost:7071/api/tools/call -H "Content-Type: application/json" -d "{not json" | Select-String -Pattern '^HTTP/|^Content-Type:|^{'
```
**Success:** headers show `Content-Type: application/json` and status codes match expectations

### Python custom test (this repo)
```powershell
# Wave0 real DOCX test
cd "c:/AI memory/CV-generator-repo"
python tests/test_wave0_real_docx.py
```
**Success:** exit code 0, `✓ All checks passed`

### "Smoke" subset
```powershell
# Fast smoke: run unit tests only (if repo has this split)
python -m pytest -q tests/unit
```
**Success:** exit code 0 and no failures
