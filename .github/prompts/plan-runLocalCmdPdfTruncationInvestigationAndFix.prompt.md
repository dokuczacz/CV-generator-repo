# Plan: run_local.cmd + PDF Truncation Investigation & Fix

**Created:** 2026-02-11  
**Session:** Planning mode  
**Target:** CV-generator-repo main branch

---

## Executive Summary

Create a local development launcher (`run_local.cmd` → Python script) following OmniFlowBeta's pattern, and fix a critical bullet truncation bug where the validator's 100-char hard limit rejects AI-proposed 200-char bullets, causing position data loss in CVs.

### Critical Issue Found
- **Problem:** Position #1 bullets in Lonza CV truncated
- **Root cause:** Validator hard limit (100 chars) vs AI proposal schema (200 chars)
- **Impact:** Valid AI proposals silently rejected, causing data loss
- **Fix:** Align both to 200 chars with soft warning at 100

---

## Task 1: Create run_local.cmd Script

### Goal
Provide a cross-platform, one-click local development launcher matching OmniFlowBeta's architecture pattern.

### Implementation

#### File: `run_local.cmd` (root)
```batch
@echo off
setlocal
cd /d "%~dp0"

REM Double-click entrypoint for Windows.
REM Starts Azurite + Next.js UI + Azure Functions for CV-generator-repo.

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3.11 scripts\run_local.py
  goto :done
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python scripts\run_local.py
  goto :done
)

echo ERROR: Neither "py" nor "python" found on PATH.
exit /b 1

:done
endlocal
```

#### File: `scripts/run_local.py`
Port from reference implementation at:
- **Source:** `C:\AI memory\NewHope\OmniFlowBeta\scripts\run_local.py`

**Key features:**
- Stop processes on ports: 7071 (Functions), 3000 (Next.js), 10000-10002 (Azurite)
- Create directories: `tmp/logs`, `.azurite`
- Launch in separate PowerShell windows:
  - Azurite: `azurite -d`
  - UI: `cd ui && npm run dev`
  - Functions: `func start` (foreground with logging)
- Cleanup on exit

**Adaptations for CV-generator:**
- Default ports: 7071 (Functions), 3000 (Next.js), 10000-10002 (Azurite)
- Log files: `tmp/logs/azurite_{timestamp}.log`, `tmp/logs/ui_{timestamp}.log`, `tmp/logs/func_{timestamp}.log`
- Working directories: repo root for Functions, `ui/` for Next.js

---

## Task 2: Create Azurite Session Listing Script

### Goal
Find the last session (Lonza CV) and PDF artifacts in Azurite local storage for truncation investigation.

#### File: `scripts/list_azurite_sessions.py`

**Features:**
- Connect to Azurite using development connection string
- List containers: `cv-sessions`, `cv-photos`
- Find most recent session by blob modified timestamp
- Download session JSON and PDF metadata
- Print: session_id, pdf_ref, full_name, work_experience bullet lengths
- Save to: `tmp/last_session_dump.json`

**Usage:**
```bash
python scripts/list_azurite_sessions.py              # Find last session
python scripts/list_azurite_sessions.py --session-id <id>  # Specific session
```

**Output format:**
```
=== LAST SESSION ===
Session ID: abc123...
PDF Ref: abc123-xyz789
Full Name: Mariusz Horodecki
Company: Lonza

Work Experience:
  Position #0: Principal Consultant, SchlauMeyer
    - Bullet 0: 87 chars
    - Bullet 1: 142 chars ⚠️ EXCEEDS 100-char validator limit
    - Bullet 2: 95 chars
  Position #1: Senior Manager Quality, Lonza
    - Bullet 0: 156 chars ⚠️ EXCEEDS 100-char validator limit ← TRUNCATION SUSPECT
    - Bullet 1: 134 chars ⚠️ EXCEEDS 100-char validator limit
    ...

Saved to: tmp/last_session_dump.json
```

---

## Task 3: Fix Bullet Truncation Bug

### Root Cause Analysis

**Evidence from codebase:**

1. **AI Proposal Schema** ([src/work_experience_proposal.py#L59](c:\AI memory\CV-generator-repo\src\work_experience_proposal.py#L59)):
   ```python
   _BULLET_MAXLEN_HARD = 200
   
   WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA["schema"] = _apply_bullet_max_length(
       WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA["schema"],
       max_len=_BULLET_MAXLEN_HARD,
   )
   ```
   **AI legally proposes bullets up to 200 chars**

2. **Validator Limits** ([src/validator.py#L78](c:\AI memory\CV-generator-repo\src\validator.py#L78)):
   ```python
   "bullets": {
       "max_count": 4,
       "max_chars_per_bullet": 100,  ← CONFLICT!
       "height_mm_per_bullet": 4.5,
       "reason": "Achievement bullets"
   }
   ```
   **Validator rejects bullets > 100 chars as invalid**

3. **Validation Logic** ([src/validator.py#L351-400](c:\AI memory\CV-generator-repo\src\validator.py#L351)):
   ```python
   def _validate_work_experience(self, entries: List[Dict], warnings: List[str]):
       # Enforces 100-char hard limit
       # Any bullet >100 chars → ValidationError
   ```

**Result:** Valid AI proposals (100-200 chars) get rejected → data loss

### Fix Strategy

**Align validator to match AI proposal schema (200 chars) with soft warnings:**

#### Change 1: Update CV_LIMITS ([src/validator.py#L78](c:\AI memory\CV-generator-repo\src\validator.py#L78))
```python
"bullets": {
    "max_count": 4,
    "max_chars_per_bullet": 200,  # Changed from 100 to align with AI schema
    "soft_limit": 100,             # NEW: Guide AI toward concise bullets
    "height_mm_per_bullet": 4.5,
    "reason": "Achievement bullets (200 hard, 100 soft recommended)"
}
```

#### Change 2: Update Validation Logic ([src/validator.py#L351+](c:\AI memory\CV-generator-repo\src\validator.py#L351))
```python
def _validate_work_experience(self, entries: List[Dict], warnings: List[str]):
    for i, entry in enumerate(entries):
        bullets = entry.get("bullets", [])
        for j, bullet in enumerate(bullets):
            blen = len(str(bullet))
            
            # Hard error only for extreme outliers (>200 chars)
            if blen > 200:
                errors.append(ValidationError(
                    field=f"work_experience[{i}].bullets[{j}]",
                    current_value=blen,
                    limit=200,
                    excess=blen - 200,
                    message=f"Bullet exceeds 200-char hard limit",
                    suggestion=f"Reduce by {blen - 200} characters"
                ))
            # Soft warning for verbose bullets (100-200 chars)
            elif blen > 100:
                warnings.append(
                    f"work_experience[{i}].bullets[{j}]: {blen} chars "
                    f"(verbose but OK; recommended <100 for conciseness)"
                )
```

**Rationale:**
- **Schema is source of truth:** AI proposal enforces 200 chars; validator must not contradict
- **Swiss/EU CV context:** Professional roles sometimes need longer achievement descriptions
- **Soft warning preserves UX:** AI still guided toward concise bullets without breaking valid proposals

---

## Task 4: Investigate Specific Truncation (Lonza PDF)

### Procedure

1. **Run listing script:**
   ```bash
   python scripts/list_azurite_sessions.py
   ```

2. **Load session data:**
   - Read `tmp/last_session_dump.json`
   - Extract `work_experience[0]` (first position, likely Lonza)
   - Measure all bullet lengths

3. **Compare against limits:**
   - Document which bullets exceeded 100 chars
   - Check if they were applied to CV data or rejected
   - Verify PDF content (if blob is readable text)

4. **Document findings:**
   Create `tmp/truncation_investigation.md` with:
   - Session ID and PDF ref
   - Bullet-by-bullet length analysis
   - Confirmation of root cause
   - Before/after validator change impact

**Expected outcome:**
Position #1 bullets >100 chars were rejected by validator → proposal not applied → position appears truncated in final PDF.

---

## Verification Plan

### 1. run_local.cmd Launch Test
```bash
# From repo root
run_local.cmd

# Expected output:
# - Azurite starts on ports 10000-10002
# - UI starts on http://localhost:3000
# - Functions start on http://localhost:7071
# - Logs appear in tmp/logs/
```

### 2. Session Listing Test
```bash
python scripts/list_azurite_sessions.py

# Expected output:
# - Finds cv-sessions container
# - Lists most recent session (Lonza CV)
# - Shows bullet length warnings
# - Saves tmp/last_session_dump.json
```

### 3. Validation Fix Test

**Create test CV with mixed bullet lengths:**
```json
{
  "work_experience": [{
    "employer": "Test Corp",
    "title": "Test Role",
    "date_range": "2020-01 - 2025-01",
    "bullets": [
      "Short bullet (50 chars)",
      "Medium bullet that is exactly one hundred characters long to test the soft warning boundary marker",
      "Very long bullet that exceeds one hundred characters but stays under two hundred characters to verify it passes validation with only a soft warning instead of a hard error",
      "Extremely verbose bullet that deliberately exceeds the two hundred character hard limit and should trigger a validation error because it is simply too long for any reasonable CV formatting constraint"
    ]
  }]
}
```

**Run validation:**
```python
from src.validator import CVValidator
result = validator.validate(test_cv)

# Expected results:
# - Bullet 0 (50 chars): ✓ Pass
# - Bullet 1 (100 chars): ✓ Pass (soft warning)
# - Bullet 2 (150 chars): ✓ Pass (soft warning "verbose but OK")
# - Bullet 3 (210 chars): ✗ Error (exceeds 200-char hard limit)
```

---

## Files to Create/Modify

### New Files
- **run_local.cmd** (root) — Windows launcher
- **scripts/run_local.py** — Cross-platform service launcher
- **scripts/list_azurite_sessions.py** — Session/PDF investigation tool
- **tmp/truncation_investigation.md** — Investigation findings (generated)

### Modified Files
- **src/validator.py** — Fix CV_LIMITS and validation logic
- **README.md** — Add run_local.cmd to setup instructions

### Reference Files (Read-only)
See "Referenced Files" section below.

---

## Referenced Files During Planning

### Primary Investigation Files
1. **C:\AI memory\NewHope\OmniFlowBeta\run_local.cmd** — Reference launcher pattern
2. **C:\AI memory\NewHope\OmniFlowBeta\scripts\run_local.py** — Reference Python launcher (1-179)
3. **c:\AI memory\CV-generator-repo\scripts\run-local.ps1** — Existing PowerShell launcher (1-100)
4. **c:\AI memory\CV-generator-repo\README.md** — Project overview and setup (1-100)
5. **c:\AI memory\CV-generator-repo\DEPLOYMENT.md** — Deployment guide and env vars (1-100)

### Truncation Bug Investigation Files
6. **c:\AI memory\CV-generator-repo\src\validator.py** — CV validation logic (40-150, 200-400)
   - Line 44-150: CV_LIMITS definition with `max_chars_per_bullet: 100`
   - Line 351+: `_validate_work_experience` enforcement logic
7. **c:\AI memory\CV-generator-repo\src\work_experience_proposal.py** — AI proposal schema (1-100)
   - Line 59: `_BULLET_MAXLEN_HARD = 200`
   - Line 88: Schema enforcement with 200-char limit
8. **c:\AI memory\CV-generator-repo\src\context_pack.py** — Context packaging (100-260)
   - Line 143: Comment "Preserve work_experience[*].bullets verbatim (never truncated)"
   - Line 223-254: Truncation logic (excludes bullets)

### Storage & Session Management Files
9. **c:\AI memory\CV-generator-repo\src\blob_store.py** — Blob storage operations (1-150)
   - BlobServiceClient usage, upload/download patterns
10. **c:\AI memory\CV-generator-repo\src\profile_store.py** — Profile caching (1-200)
    - Session storage patterns, blob listing
11. **c:\AI memory\CV-generator-repo\function_app.py** — Main backend orchestrator (9151-9200)
    - `_upload_pdf_blob_for_session` function
    - Session persistence logic

### Configuration & Documentation Files
12. **c:\AI memory\CV-generator-repo\.github\copilot-instructions.md** — Setup instructions (1-50)
13. **c:\AI memory\CV-generator-repo\AGENTS.md** — Agent behavior rules
14. **c:\AI memory\CV-generator-repo\.github\instructions\llm-orchestration.instructions.md** — LLM best practices (attached)
15. **c:\AI memory\CV-generator-repo\.github\instructions\planning-gate.instructions.md** — Planning requirements (attached)

### Test Files (Context)
16. **c:\AI memory\CV-generator-repo\tests\test_work_experience_bullet_limit_200.py** — Related test
17. **c:\AI memory\CV-generator-repo\tests\test_readiness_and_search.py** — Truncation checks (line 38)
18. **c:\AI memory\CV-generator-repo\tests\test_context_pack.py** — Context pack tests (lines 29-35)

### Sample Data Files (for Investigation)
19. **c:\AI memory\CV-generator-repo\samples\Lebenslauf_Mariusz_Horodecki_CH.docx** — Test CV (referenced in 20+ tests)

---

## Design Decisions

### Decision 1: Python Script Pattern
**Chosen:** Call `scripts/run_local.py` from `run_local.cmd`  
**Rationale:**
- Matches OmniFlowBeta architecture for cross-repo consistency
- Easier to maintain platform-specific logic in Python
- Can reuse utility functions across repos

**Alternative considered:** Inline CMD scripting  
**Rejected:** Less portable, harder to debug

### Decision 2: 200-char Hard Limit with Soft Warning
**Chosen:** Align validator to AI schema (200 hard, 100 soft)  
**Rationale:**
- Schema is source of truth (AI proposals must not be silently rejected)
- Swiss/EU professional CVs sometimes need longer achievement descriptions
- Soft warning preserves UX without breaking valid proposals
- Prevents silent data loss

**Alternative considered:** Keep 100-char hard limit, lower AI schema to 100  
**Rejected:** Would require retraining AI prompts and might not fit all valid use cases

### Decision 3: Session Listing Over Manual Search
**Chosen:** Automated script with timestamp sorting  
**Rationale:**
- User indicated "last session" without specific session_id
- Azurite can have many sessions; manual search is error-prone
- Script provides reusable diagnostic tool for future issues

---

## Next Steps (for Implementation)

1. Create `run_local.cmd` and `scripts/run_local.py`
2. Test launcher on Windows (verify all 3 services start)
3. Create `scripts/list_azurite_sessions.py`
4. Run investigation script to find Lonza CV session
5. Apply validator fixes to `src/validator.py`
6. Create test with 50/100/150/210-char bullets
7. Run validation test to confirm fix
8. Document findings in `tmp/truncation_investigation.md`
9. Update `README.md` with new launcher option

---

**Plan Status:** Ready for implementation  
**Estimated effort:** 2-3 hours (includes testing)  
**Risk level:** Low (backward compatible, adds soft warnings only)
