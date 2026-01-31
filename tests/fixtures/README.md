# Test Fixtures - Recorded OpenAI Responses

## Problem
E2E tests were failing because they need real OpenAI API responses to progress through the wizard. Running tests without an API key causes the backend to hang or fail on AI stages.

## Solution
Store pre-recorded backend responses from successful manual test sessions as fixtures. Tests load these fixtures instead of calling OpenAI.

## Directory Structure
```
tests/fixtures/
  README.md              # This file
  README.json            # Fixture manifest
  session_create.json    # Initial session creation response
  import_docx.json       # Import DOCX prefill response
  job_analyze.json       # Job offer analysis (OpenAI call)
  work_tailor.json       # Work experience tailoring (OpenAI call)
  skills_it_ai.json      # IT/AI skills ranking (OpenAI call)
  skills_tech_ops.json   # Tech/Ops skills ranking (OpenAI call)
  projects_select.json   # Project selection (OpenAI call)
  contact_confirm.json   # Contact stage confirmation (no AI)
  education_confirm.json # Education stage confirmation (no AI)
  generate_pdf.json      # PDF generation response
```

## How to Record New Fixtures

### Option 1: From Temp Files (Quick)
The repo root has `_tmp_*.txt` files from previous manual sessions. These contain raw backend responses:

```bash
# Available temp files:
_tmp_newsession_summary.txt         # Session creation
_tmp_after_import_yes.txt           # After import confirm
_tmp_after_job_offer_analyze_success.txt  # Job analysis
_tmp_after_work_confirm_stage.txt   # Work experience
_tmp_contact_confirm_response.txt   # Contact confirm
_tmp_after_education_confirm.txt    # Education confirm
```

To convert to fixtures:
1. Parse the raw response
2. Extract JSON payload
3. Save as properly formatted fixture

### Option 2: Record Fresh Session (Recommended)
1. **Start backend with OpenAI key**:
   ```bash
   # Ensure local.settings.json has OPENAI_API_KEY
   func start
   ```

2. **Run UI and capture network traffic**:
   ```bash
   cd ui && npm run dev
   # Open browser DevTools > Network tab
   # Filter: /api/process-cv
   ```

3. **Complete full wizard flow**:
   - Upload CV
   - Select language
   - Import DOCX
   - Paste job offer → Analyze
   - Confirm work experience
   - Confirm skills (IT/AI)
   - Confirm skills (Tech/Ops)
   - Confirm projects
   - Confirm contact
   - Confirm education  
   - Generate PDF

4. **Save each response**:
   - Copy response body from Network tab
   - Pretty-print JSON
   - Save to appropriate fixture file

### Option 3: Automated Recording Script

```python
# tests/record_fixtures.py
"""
Record test fixtures by running through full wizard flow
and capturing all backend responses.
"""
import json
import requests
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASE_URL = "http://localhost:7071/api"

def record_session():
    """Run full wizard flow and save all responses as fixtures."""
    
    # 1. Create session
    resp = requests.post(f"{BASE_URL}/process-cv", json={
        "message": "start",
        "docx_base64": "...",  # Base64 encoded CV
    })
    save_fixture("session_create.json", resp.json())
    
    # 2. Language select
    # ... continue for each stage
    
def save_fixture(filename: str, data: dict):
    """Save response as formatted JSON fixture."""
    path = FIXTURES_DIR / filename
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {filename}")
```

## Using Fixtures in Tests

### Playwright E2E Tests (TypeScript)

```typescript
// Load fixtures
import sessionCreate from './fixtures/session_create.json';
import jobAnalyze from './fixtures/job_analyze.json';
// ... etc

// Intercept and inject fixtures
function setupMockInterceptor(page: Page) {
  page.route('**/api/process-cv', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    
    // Check if this is an AI stage that needs mocking
    const actionId = body?.ui_action?.id;
    
    // Map to fixture
    const fixtures = {
      'JOB_POSTING_PASTE': jobAnalyze,
      'WORK_EXPERIENCE_TAILOR_RUN': workTailor,
      'SKILLS_TAILOR_RUN': skillsItAi,
      'TECH_OPS_TAILOR_RUN': skillsTechOps,
      'FURTHER_TAILOR_RUN': projectsSelect
    };
    
    if (actionId && fixtures[actionId]) {
      // Replace AI response with fixture
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixtures[actionId])
      });
    } else {
      // Pass through non-AI stages
      await route.fulfill({ response });
    }
  });
}
```

### Python Integration Tests

```python
# tests/conftest.py
import json
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def mock_openai_responses():
    """Load all fixture responses."""
    return {
        'job_analyze': json.loads((FIXTURES_DIR / 'job_analyze.json').read_text()),
        'work_tailor': json.loads((FIXTURES_DIR / 'work_tailor.json').read_text()),
        # ... etc
    }

# tests/test_with_fixtures.py
def test_wizard_flow_mocked(mock_openai_responses):
    """Test full wizard flow using pre-recorded responses."""
    # Mock Azure Function responses with fixtures
    # ... test implementation
```

## Fixture Schema

Each fixture file should follow this structure:

```json
{
  "success": true,
  "response": "Assistant message text",
  "model_response": {
    "payload": {
      // AI-generated structured data specific to stage
    }
  },
  "session_id": "uuid",
  "stage": "stage_name",
  "ui_action": {
    "id": "ACTION_ID",
    "label": "Button text",
    // ... other UI action fields
  },
  "schema_version": "1.0"
}
```

## Benefits

✅ **No OpenAI API key needed** - Tests run offline using recorded responses  
✅ **Deterministic tests** - Same input always produces same output  
✅ **Fast execution** - No network latency from OpenAI API calls  
✅ **Cost-free** - No API usage charges for test runs  
✅ **CI/CD friendly** - Tests run in pipelines without secrets  
✅ **Reproducible bugs** - Exact responses can be replayed  

## Maintenance

**When to update fixtures:**
- After changing prompt templates
- After modifying structured output schemas
- After changing wizard flow/stages
- When testing new CV template versions

**Versioning:**
- Tag fixture sets with date or version
- Keep old fixtures for regression testing
- Document which OpenAI model was used (gpt-4o, etc.)

## Current Status

**Existing Fixtures (from temp files):**
- `_tmp_newsession_summary.txt` - Session creation
- `_tmp_after_import_yes.txt` - Import DOCX  
- `_tmp_after_job_offer_analyze_success.txt` - Job analysis (COMPLETE, ~8KB)
- `_tmp_after_work_confirm_stage.txt` - Work experience
- `_tmp_contact_confirm_response.txt` - Contact confirm
- `_tmp_after_education_confirm.txt` - Education confirm

**TODO:**
- [ ] Parse temp files into proper JSON fixtures
- [ ] Add missing stages (skills IT/AI, skills tech/ops, projects)
- [ ] Create fixture loading utility
- [ ] Update Playwright tests to use fixtures
- [ ] Create Python fixture loader
- [ ] Add fixture validation script
- [ ] Document fixture recording process

## Example: Converting Temp File to Fixture

```bash
# Input: _tmp_after_job_offer_analyze_success.txt
# Output: tests/fixtures/job_analyze.json

# 1. Read temp file
cat _tmp_after_job_offer_analyze_success.txt

# 2. Extract JSON (it's the raw response)
# 3. Pretty print
jq '.' _tmp_after_job_offer_analyze_success.txt > tests/fixtures/job_analyze.json

# 4. Verify structure
jq 'keys' tests/fixtures/job_analyze.json
# Expected: ["success", "response", "model_response", "session_id", "stage", ...]
```

## Next Steps

1. **Parse existing `_tmp_*.txt` files** into JSON fixtures
2. **Record missing stages** by running a fresh session with OpenAI
3. **Update `cv-generator-mocked.spec.ts`** to load from fixtures directory
4. **Create fixture validation** to ensure schema compliance
5. **Add to CI/CD** as pre-test setup step
