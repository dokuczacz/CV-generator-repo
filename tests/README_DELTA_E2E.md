# Delta Loading E2E Tests (Option B)

## Overview

These Playwright E2E tests verify the hash-based delta loading implementation (P1 Unit 4). They test the complete workflow:

1. Create session with sample CV
2. Confirm session (stores initial hashes)
3. Edit work_experience section
4. Generate context pack with delta mode
5. Verify sections marked as changed/unchanged
6. Generate PDF end-to-end

## Prerequisites

- Azure Functions running locally: `func start` (see main README)
- Azurite running: `azurite -d` (or via VS Code)
- Node.js + dependencies: `npm install`

## Running the Tests

### All delta tests (headed mode for observation):
```bash
npx playwright test tests/delta-e2e.spec.ts --headed
```

### Specific test by name:
```bash
npx playwright test tests/delta-e2e.spec.ts -g "Step 5"
```

### With debug output:
```bash
npx playwright test tests/delta-e2e.spec.ts --debug
```

### View test report after run:
```bash
npx playwright show-report
```

## Test Structure

### Delta Loading E2E Suite (12 steps)
- **Step 1-3**: Session creation and initial context pack generation
- **Step 4**: Confirm session (triggers hash storage)
- **Step 5**: Edit work_experience
- **Step 6-7**: Generate delta pack and verify delta markers
- **Step 8-9**: Verify changed sections have full data, unchanged sections have summaries
- **Step 10**: Compare pack sizes (efficiency measurement)
- **Step 11**: Verify section hashes (16-char hex format)
- **Step 12**: End-to-end PDF generation

### Delta Loading Performance Suite
- Context pack generation speed (<100ms expected)

## Expected Behavior

When delta mode is enabled (`CV_DELTA_MODE=1`, default):

1. **After confirmation**: Initial hashes stored in session metadata (`section_hashes_prev`)
2. **After edit**: Context pack marks work_experience as `changed=true`
3. **Changed sections**: Full data sent (e.g., `{status: 'changed', hash: '...', data: [...]}`
4. **Unchanged sections**: Summary only (e.g., `{status: 'unchanged', hash: '...', count: 1, preview: {...}}`)

## Output

Test output includes:
- Session IDs created
- Context pack sizes (bytes)
- Section change markers (work_experience: changed, education: unchanged, etc.)
- Hash values (16-char hex)
- PDF generation size and path
- Performance metrics (ms for pack generation)

Example output:
```
✓ Session created: 8a5c9e3f-1234-5678-9abc-def0123456789
✓ Initial context pack: 5234 bytes
✓ Session confirmed and initial hashes stored
✓ Work experience edited (title + bullet)
✓ Delta context pack generated with changes: work_experience
✓ work_experience marked as changed
✓ education marked as unchanged
✓ work_experience sent as full data (2 items)
✓ education sent as summary only (count: 1)
  Initial pack size:  5234 bytes
  Delta pack size:    5312 bytes
✓ All section hashes valid (16-char hex)
  contact: a1b2c3d4e5f6g7h8
  work_experience: x1y2z3a4b5c6d7e8
  ...
✓ PDF generated successfully (45612 bytes)
  Saved to: test-results/delta-test-output.pdf
```

## Debugging

If tests fail:

1. **Connection errors**: Verify `func start` and Azurite are running
2. **Session not found**: Check session_id is valid, Azurite storage is not cleared
3. **Delta markers missing**: Verify `CV_DELTA_MODE=1` is set or section_hashes_prev exists
4. **PDF generation fails**: Check function logs: `func start` with debug output

## Next Steps

After Option B (E2E tests):
- **Option A**: Run live workflow smoke test (manual upload/edit/generate)
- **Option C**: Proceed to P2 work (streaming, tool batching)

## Integration with CI/CD

To run these in CI:
```bash
# Requires services running
CV_DELTA_MODE=1 npm run test:playwright tests/delta-e2e.spec.ts
```

Note: CI environments need Azurite and Functions emulator configured.
