# CV Generator — Handoff (2026-01-29)

This is the “ready to resume work” handoff from the current state of the repo.

## Goal / DoD (what we’re driving toward)

- Real end-to-end (no mocking) generates a tailored CV PDF.
- Output is English and not a copy/paste of the input doc.
- Tests never “hang”: they fail within a hard timeout and emit enough artifacts/logs to diagnose where the flow stalled.

## Current state (what is implemented right now)

### Playwright global behavior

- Hard test timeout is enforced at **300s** in [playwright.config.ts](playwright.config.ts).
- UI + Azure Functions startup timeouts are also **300s** via `webServer` config.
- Failure artifacts are retained:
  - `trace: 'retain-on-failure'`
  - `video: 'retain-on-failure'`
  - `screenshot: 'only-on-failure'`
- Defaults to make stalls debuggable:
  - `actionTimeout: 30_000`
  - `navigationTimeout: 60_000`
  - Reporter: `line` + `html`

Artifacts are written to `test-results/`.

### E2E tests added / updated

- Mocked E2E flow (deterministic “full wizard”):
  - [tests/e2e/cv-generator-mocked.spec.ts](tests/e2e/cv-generator-mocked.spec.ts)
  - Adds a 10s “heartbeat” that prints the current step + detected stage, so a stall shows *where* it is stuck.
  - On failure (including timeouts) attaches:
    - `page-url.txt`
    - `page.html`
  - Pipes browser `console` and `pageerror` into runner output.
  - Extracts the generated PDF (base64) and validates key sections are not empty using PyPDF2.

- Real OpenAI E2E (no mocking):
  - [tests/e2e/openai-e2e.spec.ts](tests/e2e/openai-e2e.spec.ts)
  - Gated (opt-in) to avoid accidental paid/online runs:
    - Requires `RUN_OPENAI_E2E=1`
    - Requires `OPENAI_API_KEY`
  - Adds frequent logs around every `/api/process-cv` wait (status + time + small payload preview).
  - Adds a heartbeat that prints current stage and last `[Action] ...` line while waiting.
  - Saves returned PDFs into Playwright artifacts and runs lightweight checks:
    - skills sections are non-empty
    - work experience is “mostly English” (coarse heuristic)

- Fixture capture utilities:
  - [tests/e2e/capture-fixtures.spec.ts](tests/e2e/capture-fixtures.spec.ts) logs every `/api/process-cv` response as JSONL.
  - [tests/parse-capture.ts](tests/parse-capture.ts) converts `tests/capture-responses.jsonl` into individual fixture JSON files.

- Stage “Source of Truth” mocked backend state machine:
  - [tests/e2e/stage-sot-mocked.spec.ts](tests/e2e/stage-sot-mocked.spec.ts)
  - This does NOT hit the backend at all; it mocks `/api/process-cv` with a deterministic state machine to validate wizard expectations.

- Small smoke E2E:
  - [tests/e2e/smoke-test.spec.ts](tests/e2e/smoke-test.spec.ts)

### Test fixtures currently present

Recorded fixture JSONs exist under:
- [tests/fixtures](tests/fixtures)

See:
- [tests/fixtures/README.md](tests/fixtures/README.md)

Note: fixture completeness may vary (some are full UI `ui_action` objects, others are partial experiments).

## How to run (fastest path)

### 1) Mocked E2E (cheap, deterministic)

From repo root:

- `npm test -- tests/e2e/cv-generator-mocked.spec.ts`

If you want fresh servers every run:

- `PW_REUSE_SERVER=0 npm test -- tests/e2e/cv-generator-mocked.spec.ts`

### 2) Real OpenAI E2E (paid/online; opt-in)

Prereqs:
- Azure Functions emulator works locally (Playwright starts it via `scripts/playwright-start-backend.js`).
- UI works locally (Playwright starts it via `scripts/playwright-start-frontend.js`).
- Environment variables:
  - `RUN_OPENAI_E2E=1`
  - `OPENAI_API_KEY=...`

Recommended runner:
- [scripts/test-openai-e2e.ps1](scripts/test-openai-e2e.ps1)

Example:
- `./scripts/test-openai-e2e.ps1 -Workers 1`

This script also sets sane defaults if missing:
- `CV_ENABLE_AI=1`
- `OPENAI_MODEL=gpt-4o` (override if needed)
- `OPENAI_JSON_SCHEMA_MAX_ATTEMPTS=3`

## Where to look when something “stalls”

1) Playwright live output (line reporter)
- You should see regular heartbeat lines (every ~10–15s) reporting `step=...` and `stage=...`.

2) HTML report + artifacts
- `npx playwright show-report`
- In the failing test, open:
  - trace
  - video
  - attachments (`page.html`, `page-url.txt`, saved PDF)

3) Backend logs
- If the UI is waiting on `/api/process-cv`, backend failures typically show as 500s.
- The real OpenAI spec prints `/api/process-cv` request timings and status codes.

## Known issues / current gaps

- DoD is still not “fully guaranteed”: real model output can drift (German remnants, or content that feels copied). The tests now *detect* this more reliably (English heuristic + non-empty sections), but backend prompts may still need tightening.
- The fixtures directory currently contains a mix of “stage-named fixtures” and experimental captures; if the mocked flow needs to become fully fixture-backed, we should standardize the mapping to one naming convention.

## Suggested next steps (concrete)

1) Run the real OpenAI scenario and see the first failure reason:
- `./scripts/test-openai-e2e.ps1 -Workers 1`

2) If it fails the English/tailoring checks:
- Fix at the source: strengthen backend constraints for target language + “rewrite, don’t copy”, then re-run real E2E.

3) If it times out:
- Use trace/video + `page.html` attachment to pinpoint the wizard stage.
- Then correlate to the last `/api/process-cv` request logged by the spec.

4) Standardize fixtures (if desired):
- Capture a fresh successful run via [tests/e2e/capture-fixtures.spec.ts](tests/e2e/capture-fixtures.spec.ts)
- Convert with [tests/parse-capture.ts](tests/parse-capture.ts)
- Wire the mocked spec to only use the generated fixtures (and fail if missing).
