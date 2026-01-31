# Mocked AI E2E Tests: CV Generator Full Workflow

**Purpose**: Test the complete CV generation wizard UI flow **without calling OpenAI**. Uses placeholder data and mocked API responses to validate all stages render correctly and data flows properly.

**File**: `tests/e2e/cv-generator-mocked.spec.ts`

---

## Quick Start

### Prerequisites
- Frontend running: `npm run dev` (from `ui/` folder)
- Backend running: `func start` (from root, or Azure Functions emulator)
- Node.js + npm installed

### Run Tests

**Windows (PowerShell)**:
```powershell
.\run-mocked-tests.ps1
```

**Linux/Mac (Bash)**:
```bash
bash run-mocked-tests.sh
```

**Or directly with npm**:
```bash
npm test -- tests/e2e/cv-generator-mocked.spec.ts
```

---

## What Gets Tested

### ✅ UI Stages Render
- [x] Stage 1/6 — Contact (form fields visible)
- [x] Stage 2/6 — Education (data displays)
- [x] Stage 3/6 — Job offer (paste and mock extraction)
- [x] Stage 4/6 — Work experience (mock tailoring proposal)
- [x] Stage 5/6 — IT & AI Skills (mock ranking proposal)
- [x] Stage 5/6 — Technical & Operational Skills (mock ranking proposal)
- [x] Stage 5/6 — Further Experience (mock selection proposal)
- [x] Stage 6/6 — Generate (PDF button visible)

### ✅ Data Flow
- [x] Upload DOCX → Session created
- [x] Import DOCX prefill → Data loaded
- [x] Fill contact info → Saved
- [x] Paste job offer → Mock extracted (no OpenAI call)
- [x] Add tailoring notes → Saved in meta
- [x] Tailor work experience → Mock proposal used
- [x] Rank IT/AI skills → Mock proposal used
- [x] Rank technical skills → Mock proposal used
- [x] Select projects → Mock proposal used
- [x] Generate PDF → Success

### ❌ What's NOT Tested
- Real OpenAI calls (intentionally skipped)
- PDF content accuracy (mocked response)
- Email validation
- File download mechanics

---

## Mock Data Structure

All mock responses are defined in `mockResponses` object at the top of the test file.

### Mock Responses Used

#### 1. job_reference (from JOB_POSTING_PASTE)
```json
{
  "title": "Senior Quality Engineer",
  "company": "TechCorp AG",
  "location": "Zurich, Switzerland",
  "responsibilities": [...],
  "requirements": [...],
  "tools_tech": [...],
  "keywords": [...]
}
```

#### 2. work_experience_proposal (from WORK_EXPERIENCE_TAILOR_RUN)
```json
{
  "roles": [
    {
      "title": "Quality Systems Manager",
      "company": "AutoCorp GmbH",
      "date_range": "2020-03 – 2025-01",
      "location": "Stuttgart, Germany",
      "bullets": [...]
    },
    ...
  ],
  "notes": "Reordered to emphasize..."
}
```

#### 3. it_ai_skills_proposal (from SKILLS_TAILOR_RUN)
```json
{
  "skills": ["Quality Management Systems", "IATF 16949", ...],
  "notes": "Ranked by relevance..."
}
```

#### 4. tech_ops_skills_proposal (from TECH_OPS_TAILOR_RUN)
```json
{
  "skills": ["Process Improvement", "Quality Audits", ...],
  "notes": "Selected operational skills..."
}
```

#### 5. further_experience_proposal (from FURTHER_TAILOR_RUN)
```json
{
  "projects": [
    {
      "title": "IATF 16949 Implementation",
      "organization": "AutoCorp GmbH",
      "date_range": "2020-06 – 2021-03",
      "bullets": [...]
    }
  ],
  "notes": "Selected 1 most relevant..."
}
```

---

## How Mocking Works

### Route Interception
```typescript
page.route('**/api/process-cv', async (route: Route) => {
  // Intercept all /api/process-cv requests
  // Check which action is being called
  // Return mock response for AI-related actions
  // Pass through for other actions (contact save, etc.)
});
```

### Mocked Actions
Only these actions return mock responses (no OpenAI call):

| Action | Mock Response | Purpose |
|--------|---------------|---------|
| `JOB_POSTING_PASTE` | `job_reference` | Extract job details |
| `WORK_EXPERIENCE_TAILOR_RUN` | `work_experience_proposal` | Tailor roles |
| `SKILLS_TAILOR_RUN` | `it_ai_skills_proposal` | Rank IT skills |
| `TECH_OPS_TAILOR_RUN` | `tech_ops_skills_proposal` | Rank operational skills |
| `FURTHER_TAILOR_RUN` | `further_experience_proposal` | Select projects |

### Non-Mocked Actions
These pass through to the real backend (no mock interception):

| Action | Reason |
|--------|--------|
| `SESSION_CREATE` | Session management |
| `CONTACT_CONFIRM` | User data |
| `EDUCATION_CONFIRM` | User data |
| `WORK_NOTES_SAVE` | User data |
| `GENERATE_PDF` | PDF generation |

---

## Test Scenarios

### Test 1: Full Wizard Flow (Mocked AI)
```
Upload DOCX
   ↓
Import prefill
   ↓
Stage 1: Confirm contact
   ↓
Stage 2: Confirm education
   ↓
Stage 3: Paste job offer → MOCK extraction
   ↓
Stage 4: Tailor work experience → MOCK proposal
   ↓
Stage 5a: Rank IT/AI skills → MOCK proposal
   ↓
Stage 5b: Rank technical skills → MOCK proposal
   ↓
Stage 5c: Select projects → MOCK proposal
   ↓
Stage 6: Generate PDF
   ↓
Download button visible
```

**Expected**: All stages complete, PDF generated (using mock responses)

### Test 2: UI Rendering Verification
```
For each stage:
  - Check stage header renders
  - Click through to next stage
  - Verify buttons are visible
```

**Expected**: All 8 stage headers render without errors

---

## Adding More Mock Data

To test different scenarios, update the `mockResponses` object:

```typescript
const mockResponses: Record<string, any> = {
  job_reference: {
    // Modify to test different job profiles
    title: "Your custom title",
    company: "Your company",
    // ...
  },
  // Add more scenarios as needed
};
```

Example: Test for "minimal skills" scenario:
```typescript
it_ai_skills_proposal: {
  skills: ["Python", "Azure"],  // Only 2 skills
  notes: "Minimal skill set"
}
```

---

## Test Output

### Console Logs
```
[test] Stage 1: Contact
[test] Stage 2: Education
[test] Stage 3: Job offer (with mocked OpenAI extraction)
[test] Stage 4: Work experience (with mocked tailoring)
[test] Stage 5a: IT/AI Skills (with mocked ranking)
[test] Stage 5b: Technical & Operational Skills (with mocked ranking)
[test] Stage 5c: Further Experience (with mocked selection)
[test] Stage 6: Generate PDF
[test] ✅ CV generated successfully with mocked AI responses
```

### Test Report
- HTML report: `test-results/index.html`
- Screenshots: `test-results/` (if failures occur)
- Artifacts: `tests/test-output/` (generated files)

---

## Troubleshooting

### "No response received"
- Make sure frontend is running: `npm run dev` (from ui/)
- Make sure backend is running: `func start`
- Check both are accessible: `curl http://localhost:3000` and `curl http://localhost:7071/api/health`

### "Timeout waiting for Stage X"
- The stage header didn't render
- Check browser console for JavaScript errors
- Increase timeout: `{ timeout: 60_000 }`

### "Button not found"
- Button name might have changed in UI
- Check button text in browser dev tools
- Update button name in test helper functions

### "Mock response not being used"
- Check that the action name matches in `setupMockInterceptor`
- Verify route pattern `**/api/process-cv`
- Add console logs to route handler: `console.log('Intercepting action:', action)`

---

## Integration with Real OpenAI (When Ready)

To switch from mocked to real API calls:

1. **Remove mock interceptor**:
   ```typescript
   // Comment out this line:
   // setupMockInterceptor(page);
   ```

2. **Set OpenAI API key**:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

3. **Run test**:
   ```bash
   npm test -- tests/e2e/cv-generator-mocked.spec.ts
   ```

Now real OpenAI calls will be made (with cost impact).

---

## Performance Metrics (Mocked)

| Stage | Time | Note |
|-------|------|------|
| Setup + Upload | ~2s | File input |
| Import Prefill | ~1s | Local parse |
| Stage 1-2 | ~2s | User input |
| Stage 3 (Paste) | ~1s | Mock extraction (instant) |
| Stage 4 (Work Experience) | ~2s | Mock proposal |
| Stage 5a (IT Skills) | ~1s | Mock ranking |
| Stage 5b (Tech Skills) | ~1s | Mock ranking |
| Stage 5c (Projects) | ~1s | Mock selection |
| Stage 6 (Generate) | ~5s | Local PDF render |
| **Total** | **~18s** | No OpenAI latency |

Compare to real OpenAI (est. +30-45s per AI call): **~63-98s total**

---

## Best Practices

1. **Keep mocks updated** - When you change schema, update mocks
2. **Test both paths** - Add tests for error cases (invalid input, etc.)
3. **Use realistic data** - Mock data should resemble real OpenAI responses
4. **Separate concerns** - Don't mix mocked and real API calls in one test
5. **Add scenario variants** - Test "minimal", "maximal", "edge case" data

---

## Related Files

- **Main test**: `tests/e2e/cv-generator-mocked.spec.ts`
- **Prompt mapping**: `docs/SoT_WITH_PROMPTS_MAPPING.md`
- **Schema definitions**: `src/*_proposal.py`
- **Backend**: `function_app.py` (lines 4515-4600 for actual flows)

---

**Last Updated**: 2025-01-29  
**Status**: Ready to use  
**Test Coverage**: Full wizard flow (mocked AI)
