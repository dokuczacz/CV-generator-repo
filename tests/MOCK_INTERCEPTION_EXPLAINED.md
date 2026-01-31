# Mock Interception: How It Works

**This explains the routing and interception logic in the mocked E2E tests.**

---

## Route Interception Mechanism

### Playwright's `page.route()` API

```typescript
page.route('**/api/process-cv', async (route: Route) => {
  // This intercepts ALL POST requests to /api/process-cv
  // You can inspect the request and decide:
  //   1. Pass through (route.continue()) → Real backend
  //   2. Mock response (route.fulfill())   → Return fake data
  //   3. Block (route.abort())              → Simulate error
});
```

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                        │
│  ┌─────────────────────────────────────┐                       │
│  │  UI Component                       │                       │
│  │  (e.g., "Tailor work experience")   │                       │
│  └────────────────┬────────────────────┘                       │
│                   │                                             │
│                   ↓ fetch(/api/process-cv, {                   │
│                      action: "WORK_EXPERIENCE_TAILOR_RUN"      │
│                   })                                            │
│                   │                                             │
└───────────────────┼─────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────┐
│  Playwright Route Interceptor                                  │
│  ┌─────────────────────────────────────┐                       │
│  │ Check action_name                   │                       │
│  │                                     │                       │
│  │ Is it AI-related?                   │                       │
│  │   YES → Return mock response        │                       │
│  │   NO  → Pass to real backend        │                       │
│  └────────────────┬────────────────────┘                       │
│                   │                                             │
└───────────────────┼─────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ↓ (AI action)           ↓ (Regular action)
    ┌─────────────┐         ┌────────────────┐
    │ Mock Data   │         │ Real Backend   │
    │ Returned    │         │ (localhost:    │
    │ Instantly   │         │  7071/api/...) │
    └────────┬────┘         └────────┬───────┘
             │                       │
             └───────────┬───────────┘
                         ↓
                    Response to UI
```

---

## Example: Job Reference Extraction

### What Normally Happens (Real OpenAI)

```
User pastes job offer text
         ↓
UI sends POST /api/process-cv with action="JOB_POSTING_PASTE"
         ↓
Backend receives request
         ↓
Backend calls OpenAI API (costs money $$)
         ↓
OpenAI returns job_reference JSON
         ↓
Backend persists to meta["job_reference"]
         ↓
Response returns to UI
         ↓
Total latency: 2-5 seconds
```

### What Happens in Mocked Test

```
User pastes job offer text
         ↓
UI sends POST /api/process-cv with action="JOB_POSTING_PASTE"
         ↓
Playwright route interceptor intercepts request
         ↓
Check: action == "JOB_POSTING_PASTE"? YES
         ↓
Return mock response (instant, no API call)
         ↓
```

**Mock response object**:
```typescript
{
  status: 'ok',
  wizard_stage: 'job_offer',
  meta_out: {
    job_reference: {
      title: 'Senior Quality Engineer',
      company: 'TechCorp AG',
      location: 'Zurich, Switzerland',
      // ... all fields
    }
  },
  cv_out: {},
  assistant_text: 'Job reference extracted. Ready to tailor your CV.'
}
```

**Result**: Same response shape as real backend, but instant (0.1s vs 3s)

---

## Route Setup Code

```typescript
function setupMockInterceptor(page: Page) {
  page.route('**/api/process-cv', async (route: Route) => {
    // 1. Extract request data
    const request = route.request();
    const body = await request.postDataJSON().catch(() => ({}));
    const action = body.action_name;

    // 2. Check if should mock
    const shouldMock = [
      'JOB_POSTING_PASTE',
      'WORK_EXPERIENCE_TAILOR_RUN',
      'SKILLS_TAILOR_RUN',
      'TECH_OPS_TAILOR_RUN',
      'FURTHER_TAILOR_RUN'
    ].includes(action);

    // 3. Route: Pass through or mock
    if (!shouldMock) {
      // Real backend request
      route.continue();
      return;
    }

    // 4. Build mock response
    let mockData = null;
    switch (action) {
      case 'JOB_POSTING_PASTE':
        mockData = {
          status: 'ok',
          wizard_stage: 'job_offer',
          meta_out: { job_reference: mockResponses.job_reference },
          cv_out: {},
          assistant_text: 'Job reference extracted.'
        };
        break;
      // ... more cases
    }

    // 5. Return mock response
    await route.abort('blockedbyclient');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockData)
    });
  });
}
```

---

## Which Actions Are Mocked vs Real

### ✅ Mocked (No Real Backend Call)

| Action | Why | Mock Source |
|--------|-----|-------------|
| `JOB_POSTING_PASTE` | Extract job details | `mockResponses.job_reference` |
| `WORK_EXPERIENCE_TAILOR_RUN` | Tailor roles | `mockResponses.work_experience_proposal` |
| `SKILLS_TAILOR_RUN` | Rank IT skills | `mockResponses.it_ai_skills_proposal` |
| `TECH_OPS_TAILOR_RUN` | Rank ops skills | `mockResponses.tech_ops_skills_proposal` |
| `FURTHER_TAILOR_RUN` | Select projects | `mockResponses.further_experience_proposal` |

These are **AI-intensive** and would cost $$ with OpenAI.

### ❌ Not Mocked (Real Backend Call)

| Action | Why | Real Call |
|--------|-----|-----------|
| `SESSION_CREATE` | Session init | Fast, local |
| `CONTACT_CONFIRM` | Save contact | Just DB write |
| `EDUCATION_CONFIRM` | Save education | Just DB write |
| `IMPORT_PREFILL` | Parse DOCX | Local file read |
| `WORK_NOTES_SAVE` | Save user notes | Just DB write |
| `GENERATE_PDF` | Render PDF | Local template |

These are **deterministic and fast** - worth testing with real backend.

---

## Response Format Matching

### Key Rule
Mock response structure **must match exactly** what real backend returns.

#### Example: It_ai_skills Response

**Real OpenAI Response** (from backend):
```json
{
  "status": "ok",
  "wizard_stage": "skills_tailor_review",
  "meta_out": {
    "skills_proposal_block": {
      "skills": ["Python", "Azure", "..."],
      "notes": "Ranked by frequency...",
      "openai_response_id": "chatcmpl-...",
      "created_at": "2025-01-29T..."
    }
  },
  "cv_out": {},
  "assistant_text": "IT/AI skills ranked by relevance."
}
```

**Mock Response** (from test):
```typescript
mockData = {
  status: 'ok',
  wizard_stage: 'skills_tailor_review',
  meta_out: {
    skills_proposal_block: mockResponses.it_ai_skills_proposal
  },
  cv_out: {},
  assistant_text: 'IT/AI skills ranked by relevance.'
};
```

**Why matching matters**: UI code expects this exact structure. If mock is wrong, UI won't render correctly.

---

## Adding New Mocked Stages

### Step 1: Add to mockResponses

```typescript
const mockResponses: Record<string, any> = {
  // ... existing mocks ...
  my_new_proposal: {
    // Structure matching Pydantic schema
    field1: "value",
    field2: ["list", "of", "items"],
    notes: "explanation"
  }
};
```

### Step 2: Add case to route interceptor

```typescript
switch (action) {
  // ... existing cases ...
  case 'MY_NEW_ACTION':
    mockData = {
      status: 'ok',
      wizard_stage: 'my_new_stage',
      meta_out: {
        my_new_proposal_block: mockResponses.my_new_proposal
      },
      cv_out: {},
      assistant_text: 'My new action completed.'
    };
    break;
}
```

### Step 3: Verify UI renders

```typescript
test('should render MY_NEW_STAGE', async ({ page }) => {
  setupMockInterceptor(page);
  // ... navigate to stage ...
  await expect(page.getByText('Stage X — My New Stage')).toBeVisible();
});
```

---

## Performance Comparison

| Scenario | Time | Note |
|----------|------|------|
| **Mocked AI Calls** | ~18 seconds | All 5 AI actions return instantly |
| **Real OpenAI Calls** | ~60-90 seconds | Each call takes 2-5s |
| **Real + Errors** | ~120 seconds | Correction loops add 15-30s each |
| **Backend Only (no UI)** | ~35 seconds | Just API calls, no UI rendering |

**Savings**: ~42-72 seconds per test run when mocked.

---

## Debugging Mock Responses

### Add logging to route handler

```typescript
page.route('**/api/process-cv', async (route: Route) => {
  const body = await request.postDataJSON().catch(() => ({}));
  const action = body.action_name;
  
  // Log what's happening
  console.log(`[mock] Intercepted action: ${action}`);
  
  if (shouldMock) {
    console.log(`[mock] Returning mock response for: ${action}`);
    console.log(`[mock] Response keys:`, Object.keys(mockData));
  } else {
    console.log(`[mock] Passing through to backend: ${action}`);
    route.continue();
  }
});
```

### Check UI received mock data

```typescript
// After action completes
const bodyText = await page.evaluate(() => document.body.innerText);
console.log('UI text after action:', bodyText.slice(0, 200));
```

### Verify mock response structure

```typescript
// Before fulfill()
console.log('Mock response:', JSON.stringify(mockData, null, 2));
```

---

## Common Issues

### "Mock response returned but UI didn't update"
**Cause**: Response structure doesn't match what UI expects  
**Fix**: Compare with real backend response, add all required fields

### "Action passed through but backend returned error"
**Cause**: Backend encountered real error  
**Fix**: Check backend logs, ensure session exists

### "Test passes but real backend fails"
**Cause**: Mock data is unrealistic  
**Fix**: Use real OpenAI response as template for mock

### "Two tests interfering with each other"
**Cause**: Route interceptor persists across tests  
**Fix**: Reset interceptor in `beforeEach()`:
```typescript
test.beforeEach(async ({ page }) => {
  page.unroute('**/api/process-cv');  // Clear old
  setupMockInterceptor(page);          // Set new
});
```

---

## Best Practices

1. **Keep mocks realistic** - Match real OpenAI response structure
2. **Test both paths** - Mocked tests + occasional real API tests
3. **Document mocks** - Comment what each mock represents
4. **Version mocks** - Update when schema changes
5. **Monitor differences** - If real API behaves differently, update mocks
6. **Use for regression** - Mocked tests should pass before touching backend

---

**File**: `tests/e2e/cv-generator-mocked.spec.ts`  
**Core function**: `setupMockInterceptor(page)`  
**Lines**: 8–100 (route setup)  
**Related**: `mockResponses` object (lines 1–50)
