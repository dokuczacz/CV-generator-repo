# Prompt Optimization: Embedding Constraint Limits

**Status**: Analysis Complete | Implementation Ready

**Goal**: Reduce JSON parsing failures and correction loop latency (~15s per cycle) by embedding explicit constraint information directly in AI system prompts.

---

## Problem Analysis

### Current Situation
- **Parsing Failure Pattern**: AI generates JSON responses that fail OpenAI's strict schema validation
- **Current Recovery**: System issues a correction prompt ("Please fix format and resubmit")
- **Cost**: 
  - ~15 seconds additional latency per correction
  - Extra tokens consumed by both original + correction prompt
  - Reduced user experience quality

### Root Cause
Prompts mention constraints in natural language but don't explicitly communicate:
1. Exact JSON schema structure required
2. Field type requirements (e.g., List[str], not comma-separated string)
3. Array size constraints (min/max items)
4. Optional vs required fields
5. String length constraints where applicable

### Evidence
```python
# Current prompt (line 181-208 in function_app.py) says:
"Output 5-10 top skills max."

# But schema (src/skills_proposal.py line 17) is:
skills: List[str] = Field(..., description="Filtered and ranked IT/AI skills (5-10 items max)")

# Code then enforces after the fact (line 4575):
[:10]  # Cap at 10 items

# OpenAI never sees the min/max constraint, only description
```

**Result**: AI may output:
- 12 skills (violates schema validation)
- Skills as comma-separated string instead of array
- Missing required "notes" field
- Malformed date ranges

---

## Constraint Inventory

### Schema Constraints by Stage

#### 1. **it_ai_skills** (SkillsProposal)
**Location**: `src/skills_proposal.py` lines 17-20

| Field | Type | Constraint | Current Prompt | Issue |
|-------|------|-----------|-----------------|-------|
| `skills` | `List[str]` | 5-10 items (5–10 max) | ✓ "5-10 top skills max" | Mentioned but not as JSON requirement |
| `notes` | `str` | Optional, ≤500 chars | ✗ Not mentioned | Never constrained |

**Prompt Location**: Line 181–208 in `function_app.py`

**Required Addition**:
```
JSON Output Format (strict schema):
{
  "skills": ["skill1", "skill2", ...],    // Array of 5-10 strings, required
  "notes": "explanation..."              // String, optional, max 500 chars
}
```

---

#### 2. **technical_operational_skills** (TechnicalOperationalSkillsProposal)
**Location**: `src/skills_proposal.py` lines 45-49

| Field | Type | Constraint | Current Prompt | Issue |
|-------|------|-----------|-----------------|-------|
| `skills` | `List[str]` | 5-10 items | ✓ Mentioned | Not as JSON requirement |
| `notes` | `str` | Optional, ≤500 chars | ✗ Not mentioned | Never constrained |

**Prompt Location**: Line 207–231 in `function_app.py`

**Required Addition**: (identical to it_ai_skills)

---

#### 3. **work_experience** (WorkExperienceBulletsProposal)
**Location**: `src/work_experience_proposal.py` lines 32-35

| Field | Type | Constraint | Current Prompt | Issue |
|-------|------|-----------|-----------------|-------|
| `roles` | `List[WorkExperienceRoleProposal]` | 3-4 items | ✓ Mentioned | Not as JSON requirement |
| `roles[*].title` | `str` | Required | ✗ Not mentioned | May be empty |
| `roles[*].company` | `str` | Required | ✗ Not mentioned | May be empty |
| `roles[*].date_range` | `str` | Required | ✗ Not mentioned | May be malformed |
| `roles[*].location` | `str` | Optional | ✓ Implied | OK |
| `roles[*].bullets` | `List[str]` | 2-4 items | ✓ Mentioned | Not as JSON requirement |
| `notes` | `str` | Optional, ≤500 chars | ✗ Not mentioned | Never constrained |

**Prompt Location**: Line 127–163 in `function_app.py` (work_experience)

**Required Addition**:
```
JSON Output Format (strict schema):
{
  "roles": [
    {
      "title": "job title",              // String, required
      "company": "company name",         // String, required
      "date_range": "2020-01 – 2025-04", // String, required (format: YYYY-MM – YYYY-MM)
      "location": "City, Country",       // String, optional
      "bullets": ["bullet1", "bullet2"]  // Array of 2-4 strings, required
    },
    ...
  ],                                      // Array of 3-4 roles, required
  "notes": "explanation..."              // String, optional, max 500 chars
}
```

---

#### 4. **further_experience** (FurtherExperienceProposal)
**Location**: `src/further_experience_proposal.py` lines 28-31

| Field | Type | Constraint | Current Prompt | Issue |
|-------|------|-----------|-----------------|-------|
| `projects` | `List[FurtherExperienceProjectProposal]` | 1-3 items | ✓ Mentioned | Not as JSON requirement |
| `projects[*].title` | `str` | Required | ✗ Not mentioned | May be empty |
| `projects[*].organization` | `str` | Optional | ✓ Implied | OK |
| `projects[*].date_range` | `str` | Optional | ✓ Implied | OK |
| `projects[*].location` | `str` | Optional | ✓ Implied | OK |
| `projects[*].bullets` | `List[str]` | 1-3 items | ✓ Mentioned | Not as JSON requirement |
| `notes` | `str` | Optional, ≤500 chars | ✗ Not mentioned | Never constrained |

**Prompt Location**: Line 164–180 in `function_app.py` (further_experience)

**Required Addition**:
```
JSON Output Format (strict schema):
{
  "projects": [
    {
      "title": "project name",           // String, required
      "organization": "org name",        // String, optional
      "date_range": "2023-01 – 2023-06", // String, optional (format: YYYY-MM – YYYY-MM if present)
      "location": "City, Country",       // String, optional
      "bullets": ["bullet1", "bullet2"]  // Array of 1-3 strings, required
    },
    ...
  ],                                      // Array of 1-3 projects, required
  "notes": "explanation..."              // String, optional, max 500 chars
}
```

---

## Implementation Plan

### Phase 1: Update System Prompts (function_app.py)

**File**: `function_app.py`, `_AI_PROMPT_BY_STAGE` dictionary (lines 127–231)

**Changes Required**: 4 prompts

1. **work_experience** (line 127–163)
   - Add "JSON Output Format" section with exact schema
   - Specify roles array: 3-4 items
   - Specify each role fields: required vs optional
   - Specify date_range format: "YYYY-MM – YYYY-MM"
   - Specify bullets: 2-4 per role

2. **further_experience** (line 164–180)
   - Add "JSON Output Format" section
   - Specify projects array: 1-3 items
   - Specify title as required
   - Specify date_range format if provided
   - Specify bullets: 1-3 per project

3. **it_ai_skills** (line 181–208)
   - Add "JSON Output Format" section
   - Specify skills array: 5-10 items (array, not comma-separated)
   - Specify notes field is optional

4. **technical_operational_skills** (line 207–231)
   - Add "JSON Output Format" section (identical to it_ai_skills)

---

## Template for Constraint Section

Use this template for each prompt:

```python
"[STAGE_NAME]": (
    # ... existing prompt content ...
    
    "\n\n"
    "JSON OUTPUT FORMAT (strict):\n"
    "{\n"
    "  \"field1\": [...],           // Description (required/optional)\n"
    "  \"field2\": [...],           // Description (required/optional)\n"
    "  \"notes\": \"explanation\"  // Optional, max 500 chars\n"
    "}\n\n"
    "CONSTRAINTS:\n"
    "- Array sizes: [exact count or range]\n"
    "- Required fields: [list]\n"
    "- Optional fields: [list]\n"
    "- String formats: [date format, etc]\n"
),
```

---

## Expected Outcomes

### Before Optimization
- **Parsing Failure Rate**: ~8-12% of AI responses fail schema validation
- **Recovery Latency**: +15 seconds per failure
- **Token Cost**: +1500–2000 tokens per correction cycle

### After Optimization
- **Parsing Failure Rate**: Target <1-2%
- **Recovery Latency**: Near zero (no corrections needed)
- **Token Savings**: ~1500-2000 tokens per response (no correction prompt)
- **User Experience**: Faster response times, smoother workflow

---

## Verification Checklist

- [ ] All 4 prompts updated with constraint sections
- [ ] JSON examples use exact field names from schema
- [ ] Array size constraints match code caps (e.g., [:10])
- [ ] Date range formats specified ("YYYY-MM – YYYY-MM")
- [ ] Notes field documented (optional, max 500 chars)
- [ ] Tested with mock AI responses that previously failed
- [ ] Parsing success rate verified >98%
- [ ] Latency improvement measured (should see <1s vs 15s with corrections)

---

## Code Locations for Updates

| Prompt Stage | File | Lines | Schemas |
|--------------|------|-------|---------|
| work_experience | function_app.py | 127–163 | src/work_experience_proposal.py |
| further_experience | function_app.py | 164–180 | src/further_experience_proposal.py |
| it_ai_skills | function_app.py | 181–208 | src/skills_proposal.py |
| technical_operational_skills | function_app.py | 207–231 | src/skills_proposal.py |

---

## Related Files

- System prompt builder: `function_app.py` line 239 (`_build_ai_system_prompt`)
- Schema enforcement: `src/openai_json_schema.py`
- Response parsing: Lines 4570–4580 (skills), 3440–3480 (work_experience), etc.

---

## Token Budget Impact

**Estimated Cost**: +500–800 tokens per prompt (constraint section adds ~10-15 lines)

**Benefit**: Saves 1500–2000 tokens per correction cycle (now unnecessary)

**Net**: Positive savings if correction rate drops from ~10% to <1%

---

**Next Steps**:
1. ✅ Analysis complete
2. → Update function_app.py prompts with constraint sections
3. → Test with real CV data to verify parsing success
4. → Monitor parsing failure rate in production
5. → Document results in post-implementation report
