# Quick Start: Mocked UI Testing

**Goal**: Test the full CV wizard UI flow without any OpenAI API calls. Uses placeholder data and intercepts API responses.

---

## 3-Step Setup

### 1. Start Backend
```powershell
func start
```
Runs Azure Functions locally at `http://localhost:7071`

### 2. Start Frontend
```powershell
cd ui
npm run dev
```
Frontend available at `http://localhost:3000`

### 3. Run Mocked Tests
```powershell
.\run-mocked-tests.ps1
```

Or directly:
```powershell
npm test -- tests/e2e/cv-generator-mocked.spec.ts
```

---

## What You Get

✅ **Full UI flow** - All 8 stages from upload to PDF generation  
✅ **No OpenAI costs** - Uses mocked responses  
✅ **Fast execution** - ~18 seconds total (vs 60+ with real API)  
✅ **Deterministic** - Same results every run  
✅ **Console logs** - Shows which stage is running  

---

## Test Flow

```
[Upload DOCX]
      ↓
[Import Prefill] ← User imports from DOCX
      ↓
[Stage 1: Contact] → Fill user data
      ↓
[Stage 2: Education] → Confirm from prefill
      ↓
[Stage 3: Job Offer] → Paste text, get mocked job_reference 🔄
      ↓
[Stage 4: Work Experience] → Tailor roles, get mocked proposal 🔄
      ↓
[Stage 5a: IT/AI Skills] → Rank skills, get mocked proposal 🔄
      ↓
[Stage 5b: Tech/Ops Skills] → Rank skills, get mocked proposal 🔄
      ↓
[Stage 5c: Further Experience] → Select projects, get mocked proposal 🔄
      ↓
[Stage 6: Generate] → Create PDF (mocked response)
      ↓
[Download PDF] ✅
```

🔄 = Uses mocked OpenAI response (no real API call)

---

## Mock Data

All mock responses in `mockResponses` object at top of test file:

| Response | Stage | Example |
|----------|-------|---------|
| `job_reference` | Job Posting → Parse | Title, company, skills needed |
| `work_experience_proposal` | Work Experience → Tailor | Rewritten roles + bullets |
| `it_ai_skills_proposal` | IT Skills → Rank | Ranked list of skills |
| `tech_ops_skills_proposal` | Tech Skills → Rank | Ranked operational skills |
| `further_experience_proposal` | Projects → Select | Selected projects |

Modify mock data to test different scenarios:
```typescript
const mockResponses = {
  it_ai_skills_proposal: {
    skills: ["Python", "Azure"],  // Test with only 2 skills
    notes: "Minimal dataset"
  }
};
```

---

## Files Created

1. **Test file**: `tests/e2e/cv-generator-mocked.spec.ts`
   - Main test with route interception
   - 2 test scenarios (full flow + UI verification)
   - Helper functions for each stage

2. **README**: `tests/MOCKED_E2E_README.md`
   - Detailed documentation
   - Troubleshooting guide
   - Adding more scenarios

3. **Run scripts**:
   - `run-mocked-tests.ps1` (Windows PowerShell)
   - `run-mocked-tests.sh` (Linux/Mac)

---

## Typical Output

```
========================================
CV Generator - Mocked AI E2E Tests
========================================

Prerequisites: ✅
Frontend dependencies: ✅
Backend (localhost:7071): ✅
Frontend (localhost:3000): ✅

=========================================
Running mocked E2E tests...
=========================================

[test] Stage 1: Contact
[test] Stage 2: Education
[test] Stage 3: Job offer (with mocked OpenAI extraction)
[test] Stage 4: Work experience (with mocked tailoring)
[test] Stage 5a: IT/AI Skills (with mocked ranking)
[test] Stage 5b: Technical & Operational Skills (with mocked ranking)
[test] Stage 5c: Further Experience (with mocked selection)
[test] Stage 6: Generate PDF
[test] ✅ CV generated successfully with mocked AI responses

3 passed (45s)

=========================================
Test Summary:
=========================================
✅ = UI stage rendered correctly
🔄 = Mocked OpenAI response used (no real API calls)
📊 = Final PDF generated

Test artifacts saved to: tests/test-output/
=========================================
```

---

## Key Points

| What | Why | How |
|------|-----|-----|
| **No OpenAI calls** | Save costs, test locally | Mock `/api/process-cv` routes |
| **Fast execution** | Quick feedback loop | Mocked responses instant |
| **Realistic data** | Verify UI handles real shapes | Mock data matches schemas |
| **All stages tested** | Comprehensive coverage | Sequential stage flow |
| **Easy to extend** | Add more scenarios | Update `mockResponses` object |

---

## Common Tweaks

### Test only Stage 3-4 (faster feedback)
Remove stages from test or comment out `completeStage...()` calls.

### Use different mock data
Edit `mockResponses` before test runs:
```typescript
mockResponses.job_reference.title = "Your Custom Title";
mockResponses.it_ai_skills_proposal.skills = ["Skill1", "Skill2"];
```

### Increase timeout (if running slow)
```typescript
test.setTimeout(300_000);  // 5 minutes instead of 3
```

### Add console logs
```typescript
console.log('[test] Current stage:', page.url());
```

---

## Next: Real OpenAI Testing

When ready to test with real API:

1. Set environment variable:
   ```powershell
   $env:OPENAI_API_KEY = "sk-..."
   ```

2. Comment out mock interceptor:
   ```typescript
   // setupMockInterceptor(page);  ← Comment this line
   ```

3. Run test (will now call real OpenAI):
   ```powershell
   npm test -- tests/e2e/cv-generator-mocked.spec.ts
   ```

**Cost estimate**: ~$0.10-0.30 per full run (depending on response sizes)

---

**Documentation**: See `tests/MOCKED_E2E_README.md` for complete guide  
**Status**: ✅ Ready to use  
**Estimated runtime**: 18-25 seconds
