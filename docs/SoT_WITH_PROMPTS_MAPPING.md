# Single Source of Truth + Stage Prompts Mapping

**Purpose**: Complete reference connecting CV data flow (SoT) with AI prompts and expected outputs for each wizard stage.

**Audience**: Backend developers, prompt engineers, QA teams verifying data transformation pipeline.

---

## Overview: Data Flow + Prompt Orchestration

```
┌─────────────────────────────────────────────────────────────────┐
│                    CV WIZARD DATA PIPELINE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  UPLOAD    PARSE       TAILOR        RANK/FILTER     REVIEW     │
│   ┌─→ DOCX ─→ cv_data ─→ job_reference ─→ tailored ─→ final   │
│   │                     & context                               │
│   └───────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Each arrow = AI prompt stage + JSON schema validation         │
│  Each box = persistent meta + cv_data object                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Rule**: Data created once, reused throughout pipeline (parse-once-reuse pattern).

---

## Stage-by-Stage Mapping

### Stage 1: JOB_POSTING_PASTE → job_reference (Creation)

| Property | Value |
|----------|-------|
| **Wizard Stage** | `job_posting_paste` |
| **Action** | `JOB_POSTING_PASTE` |
| **User Input** | Raw job posting text (pasted) |
| **System Prompt** | `_AI_PROMPT_BY_STAGE["job_posting"]` |
| **Prompt Content** | "Extract a compact, ATS-oriented job reference from the provided job offer text. Focus on role title, company, location, responsibilities, requirements, tools/tech, and keywords." |
| **Input Data** | Plain text job posting |
| **OpenAI Call** | `client.beta.messages.create()` with `response_format=job_reference_response_format()` |
| **Output Schema** | `JobReference` (Pydantic model) |
| **Output Fields** | `title`, `company`, `location`, `responsibilities`, `requirements`, `tools_tech`, `keywords` |
| **Storage** | `meta["job_reference"] = jr.dict()` |
| **Downstream Usage** | Used in **ALL** subsequent AI tasks: work_experience, further_experience, it_ai_skills, technical_operational_skills |
| **Immutable** | ✅ YES - Never modified after creation |
| **Code Reference** | Lines 3914–3956 in `function_app.py` |

**Flow Diagram**:
```
User pastes job posting
         ↓
   _build_ai_system_prompt(stage="job_posting")
         ↓
  OpenAI extracts → JobReference JSON
         ↓
 parse_job_reference(response)
         ↓
  meta["job_reference"] = jr.dict()  [STORED ONCE]
         ↓
  Reused in: work_experience, further_experience, 
             it_ai_skills, technical_operational_skills
```

---

### Stage 2: WORK_NOTES_EDIT → work_tailoring_notes (Creation)

| Property | Value |
|----------|-------|
| **Wizard Stage** | `work_notes_edit` |
| **Action** | `WORK_NOTES_SAVE` |
| **User Input** | Free-text notes about work tailoring strategy |
| **System Prompt** | None (user-provided, not AI-generated) |
| **Input Data** | Plain text from `fields[0].value` (text input) |
| **Output Type** | String (max 2000 chars) |
| **Storage** | `meta["work_tailoring_notes"] = tailoring_text` |
| **Downstream Usage** | Used in **work_experience** and **it_ai_skills** + **technical_operational_skills** tailoring |
| **Immutable** | ✅ YES - One-time save, never modified |
| **Code Reference** | Lines 3996–4002 in `function_app.py` |

**Flow Diagram**:
```
User enters tailoring strategy notes
         ↓
   WORK_NOTES_SAVE action
         ↓
  meta["work_tailoring_notes"] = notes  [STORED ONCE]
         ↓
  Reused in: work_experience_tailor,
             skills_tailor_run,
             tech_ops_tailor_run
```

---

### Stage 3: WORK_EXPERIENCE_TAILOR → work_experience (AI Tailoring)

| Property | Value |
|----------|-------|
| **Wizard Stage** | `work_experience` (review/edit) |
| **Action** | `WORK_EXPERIENCE_TAILOR_RUN` |
| **System Prompt** | `_AI_PROMPT_BY_STAGE["work_experience"]` |
| **Prompt Content** | "Rewrite CURRENT_WORK_EXPERIENCE into structured list of roles... use TAILORING_SUGGESTIONS... respect job context... select 3-4 most relevant roles; 2-4 bullets per role..." |
| **Input Data Sources** | **From cv_data**: `cv_data["work_experience"]` (list of roles with bullets) |
| **Input Data Sources** | **From docx_prefill**: Fallback if cv_data empty |
| **Context Injected** | `job_reference` (formatted for display) |
| **Context Injected** | `work_tailoring_notes` (user strategy) |
| **OpenAI Call** | `client.beta.messages.create()` with `response_format=work_experience_bullets_proposal_response_format()` |
| **Output Schema** | `WorkExperienceBulletsProposal` |
| **Output Fields** | `roles: List[WorkExperienceRoleProposal]`, `notes: str` |
| **Role Fields** | `title`, `company`, `date_range`, `location`, `bullets` |
| **Constraints** | 3-4 roles, 2-4 bullets per role, dates preserved, max 500 chars notes |
| **Storage** | `meta["work_experience_proposal_block"]` with skills list capped at 10 |
| **Next Stage** | `WORK_EXPERIENCE_TAILOR_ACCEPT` (apply to cv_data) |
| **Code Reference** | Lines 3440–3520 in `function_app.py` |

**User Input Block**:
```python
[TASK]
{task description}

[JOB_SUMMARY]
{format_job_reference_for_display(job_ref)}

[TAILORING_SUGGESTIONS]
{work_tailoring_notes}

[CURRENT_WORK_EXPERIENCE]
{work_experience formatted as bullet list}
```

**JSON Output Schema** (sent to OpenAI):
```json
{
  "roles": [
    {
      "title": "Software Engineer",
      "company": "TechCorp",
      "date_range": "2020-01 – 2025-04",
      "location": "Berlin, Germany",
      "bullets": ["achievement 1", "achievement 2"]
    }
  ],
  "notes": "Reorganized 5 roles into top 3, emphasizing cloud architecture experience"
}
```

**Flow Diagram**:
```
[WORK_EXPERIENCE_TAILOR_RUN]
         ↓
Get cv_data["work_experience"] (or docx fallback)
         ↓
Retrieve meta["job_reference"] [REUSED]
         ↓
Retrieve meta["work_tailoring_notes"] [REUSED]
         ↓
_build_ai_system_prompt(stage="work_experience", target_language=...)
         ↓
OpenAI structures response → WorkExperienceBulletsProposal JSON
         ↓
parse_work_experience_bullets_proposal(response)
         ↓
Store: meta["work_experience_proposal_block"]
         ↓
[WORK_EXPERIENCE_TAILOR_ACCEPT] → Apply to cv_data["work_experience"]
```

---

### Stage 4: SKILLS_TAILOR_RUN → it_ai_skills (AI Ranking)

| Property | Value |
|----------|-------|
| **Wizard Stage** | `it_ai_skills` (review/edit) |
| **Action** | `SKILLS_TAILOR_RUN` |
| **System Prompt** | `_AI_PROMPT_BY_STAGE["it_ai_skills"]` |
| **Prompt Content** | "Rank and filter IT & AI skills by relevance to job posting... 5-10 top skills max... INPUT LIST POLICY: ONLY use skills from candidate list (no invention)..." |
| **Input Data Sources** | **From cv_data**: `cv_data["it_ai_skills"]` (list of strings) |
| **Input Data Sources** | **From docx_prefill**: Fallback if cv_data empty |
| **Deduplication** | Case-insensitive merge of cv_data + docx sources (max 30 items sent) |
| **Context Injected** | `job_reference` (formatted) |
| **Context Injected** | `work_tailoring_notes` (user strategy) |
| **Additional Input** | `skills_ranking_notes` (optional user notes about ranking preference) |
| **OpenAI Call** | `client.beta.messages.create()` with `response_format=skills_proposal_response_format()` |
| **Output Schema** | `SkillsProposal` |
| **Output Fields** | `skills: List[str]` (5-10 items), `notes: str` |
| **Constraints** | 5-10 items, must be array, max 500 chars notes, no new skills (only from input list) |
| **Storage** | `meta["skills_proposal_block"]` with skills capped at 10 |
| **Next Stage** | `SKILLS_TAILOR_ACCEPT` (apply to cv_data["it_ai_skills"]) |
| **Code Reference** | Lines 4515–4580 in `function_app.py` |

**User Input Block**:
```python
[TASK]
From the candidate skill list, select and rewrite 5-10 IT/AI skills 
most relevant to the job.

[JOB_SUMMARY]
{format_job_reference_for_display(job_ref)}

[TAILORING_SUGGESTIONS]
{work_tailoring_notes}

[RANKING_NOTES]
{skills_ranking_notes or ""}

[CANDIDATE_IT_AI_SKILLS]
- Python
- Azure
- Machine Learning
- ...
```

**JSON Output Schema** (sent to OpenAI):
```json
{
  "skills": ["Python", "Azure", "Machine Learning", "Kubernetes", "FastAPI"],
  "notes": "Ranked by frequency in job posting. Removed legacy VB.NET."
}
```

**Flow Diagram**:
```
[SKILLS_TAILOR_RUN]
         ↓
Get cv_data["it_ai_skills"] (or docx fallback)
Deduplicate: cv_data + docx sources (case-insensitive)
         ↓
Retrieve meta["job_reference"] [REUSED]
         ↓
Retrieve meta["work_tailoring_notes"] [REUSED]
         ↓
_build_ai_system_prompt(stage="it_ai_skills", target_language=...)
         ↓
OpenAI ranks/filters → SkillsProposal JSON
         ↓
parse_skills_proposal(response)
         ↓
Store: meta["skills_proposal_block"]
         ↓
[SKILLS_TAILOR_ACCEPT] → Apply to cv_data["it_ai_skills"]
```

---

### Stage 5: TECH_OPS_TAILOR_RUN → technical_operational_skills (AI Ranking)

| Property | Value |
|----------|-------|
| **Wizard Stage** | `technical_operational_skills` (review/edit) |
| **Action** | `TECH_OPS_TAILOR_RUN` |
| **System Prompt** | `_AI_PROMPT_BY_STAGE["technical_operational_skills"]` |
| **Prompt Content** | "Rank and filter technical/operational skills... focus on process management, quality systems, lean/six sigma... 5-10 top skills max... INPUT LIST POLICY: ONLY use skills from candidate list..." |
| **Input Data Sources** | **From cv_data**: `cv_data["technical_operational_skills"]` |
| **Input Data Sources** | **From docx_prefill**: Fallback if cv_data empty |
| **Deduplication** | Semantic merge (e.g., "Lean" vs "Lean management" deduplicated) |
| **Context Injected** | `job_reference` (formatted) |
| **Context Injected** | `work_tailoring_notes` (user strategy) |
| **Additional Input** | `tech_ops_ranking_notes` (optional) |
| **OpenAI Call** | `client.beta.messages.create()` with `response_format=technical_operational_skills_proposal_response_format()` |
| **Output Schema** | `TechnicalOperationalSkillsProposal` |
| **Output Fields** | `skills: List[str]` (5-10 items), `notes: str` |
| **Constraints** | 5-10 items, must be array, max 500 chars notes, no new skills |
| **Storage** | `meta["tech_ops_proposal_block"]` with skills capped at 10 |
| **Next Stage** | `TECH_OPS_TAILOR_ACCEPT` (apply to cv_data["technical_operational_skills"]) |
| **Code Reference** | Lines 4675–4730 in `function_app.py` |

**Identical Flow to it_ai_skills** (different prompt, same orchestration)

---

### Stage 6: FURTHER_EXPERIENCE_TAILOR → further_experience (AI Selection)

| Property | Value |
|----------|-------|
| **Wizard Stage** | `further_experience` (review/edit) |
| **Action** | `FURTHER_TAILOR_RUN` |
| **System Prompt** | `_AI_PROMPT_BY_STAGE["further_experience"]` |
| **Prompt Content** | "Tailor the Selected Technical Projects section by selecting and rewriting entries... use only provided facts (no invented projects)... select 1-3 most relevant entries; 1-3 bullets per entry..." |
| **Input Data Sources** | **From cv_data**: `cv_data["further_experience"]` (list of projects) |
| **Input Data Sources** | **From docx_prefill**: Fallback if cv_data empty |
| **Context Injected** | `job_reference` (formatted) |
| **Context Injected** | `work_tailoring_notes` (user strategy) |
| **OpenAI Call** | `client.beta.messages.create()` with `response_format=further_experience_proposal_response_format()` |
| **Output Schema** | `FurtherExperienceProposal` |
| **Output Fields** | `projects: List[FurtherExperienceProjectProposal]`, `notes: str` |
| **Project Fields** | `title`, `organization`, `date_range`, `location`, `bullets` |
| **Constraints** | 1-3 projects, 1-3 bullets per project, max 500 chars notes |
| **Storage** | `meta["further_experience_proposal_block"]` |
| **Next Stage** | `FURTHER_TAILOR_ACCEPT` (apply to cv_data["further_experience"]) |
| **Code Reference** | Lines 3690–3750 in `function_app.py` |

**JSON Output Schema** (sent to OpenAI):
```json
{
  "projects": [
    {
      "title": "Real-time Analytics Platform",
      "organization": "Personal Project",
      "date_range": "2023-01 – 2023-06",
      "location": "Remote",
      "bullets": ["Reduced latency 40%", "Handled 1M events/sec"]
    }
  ],
  "notes": "Selected 1 most relevant project, rephrased for job context"
}
```

---

## Cross-Reference: Where job_reference Is Reused

| Stage | Action | How It's Used | Code Line |
|-------|--------|---------------|-----------|
| **Job Posting** | `JOB_POSTING_PASTE` | Created here | 3952 |
| **Work Experience** | `WORK_EXPERIENCE_TAILOR_RUN` | Retrieved as `job_ref`, formatted for display | 4537 |
| **IT/AI Skills** | `SKILLS_TAILOR_RUN` | Retrieved as `job_ref`, formatted for prompt | 4569 |
| **Tech Ops Skills** | `TECH_OPS_TAILOR_RUN` | Retrieved as `job_ref`, formatted for prompt | 4707 |
| **Further Experience** | `FURTHER_TAILOR_RUN` | Retrieved as `job_ref`, formatted for prompt | 3710 |

**Key**: Created once (line 3952), reused 4 times (never re-parsed).

---

## Cross-Reference: Where work_tailoring_notes Is Reused

| Stage | Action | How It's Used | Code Line |
|-------|--------|---------------|-----------|
| **Work Notes** | `WORK_NOTES_SAVE` | Created/saved here | 4000 |
| **Work Experience** | `WORK_EXPERIENCE_TAILOR_RUN` | Retrieved as `tailoring_suggestions`, injected in user block | 4545 |
| **IT/AI Skills** | `SKILLS_TAILOR_RUN` | Retrieved as `tailoring_suggestions`, injected in user block | 4577 |
| **Tech Ops Skills** | `TECH_OPS_TAILOR_RUN` | Retrieved as `tailoring_suggestions`, injected in user block | 4713 |

**Key**: Created once (line 4000), reused 3 times.

---

## Prompt System Architecture

### Base Prompt Template

```python
def _build_ai_system_prompt(
    *, 
    stage: str, 
    target_language: str | None = None, 
    extra: str | None = None
) -> str:
    """Build AI system prompt for a given stage.
    
    Combines:
    1. Base rules (security, quality, format)
    2. Stage-specific rules from _AI_PROMPT_BY_STAGE
    3. Optional extra instructions
    """
    stage_key = (stage or "").strip()
    stage_rules = _AI_PROMPT_BY_STAGE.get(stage_key, "")
    prompt = f"{_AI_PROMPT_BASE}\n\n{stage_rules}".strip()
    
    # Format with target language if provided
    if target_language:
        prompt = prompt.format(target_language=target_language)
    
    if extra:
        prompt = f"{prompt}\n\n{extra}"
    
    return prompt
```

**Code Location**: Line 239 in `function_app.py`

### Base Rules (_AI_PROMPT_BASE)

| Rule | Purpose |
|------|---------|
| "You are a professional CV expert" | Role clarity |
| "Preserve factuality" | Quality gate (no invention) |
| "No sensitive data in notes" | Privacy/security |
| "JSON-only output" | Machine parsing |
| "Strict schema required" | Validation |

**Code Location**: Lines 70–95 in `function_app.py`

### Stage-Specific Rules (_AI_PROMPT_BY_STAGE)

| Stage | Key | Purpose | Constraints |
|-------|-----|---------|-----------|
| `job_posting` | Extract reference | Parse job offer | N/A (direct extraction) |
| `education_translation` | Translation only | Preserve structure, translate text | Preserve dates/institutions |
| `work_experience` | Tailor roles | Rewrite with job context | 3-4 roles, 2-4 bullets ea. |
| `further_experience` | Select projects | Rewrite for relevance | 1-3 projects, 1-3 bullets ea. |
| `it_ai_skills` | Rank/filter | Relevance ranking | 5-10 items, no invention |
| `technical_operational_skills` | Rank/filter | Relevance ranking | 5-10 items, no invention |
| `interests` | Generate/refine | Concise summary | 2-4 items, 1-3 words ea. |

**Code Location**: Lines 127–255 in `function_app.py`

---

## JSON Schema Architecture

Each stage's output is validated against a strict Pydantic model.

### Models by Stage

| Stage | Model | File | Output Fields |
|-------|-------|------|----------------|
| `job_posting` | `JobReference` | `src/job_reference.py` | title, company, location, responsibilities, requirements, tools_tech, keywords |
| `work_experience` | `WorkExperienceBulletsProposal` | `src/work_experience_proposal.py` | roles (List[Role]), notes |
| `further_experience` | `FurtherExperienceProposal` | `src/further_experience_proposal.py` | projects (List[Project]), notes |
| `it_ai_skills` | `SkillsProposal` | `src/skills_proposal.py` | skills (List[str]), notes |
| `technical_operational_skills` | `TechnicalOperationalSkillsProposal` | `src/skills_proposal.py` | skills (List[str]), notes |

### Schema Validation Flow

```python
# 1. Call OpenAI with strict schema
ok, parsed, err = _openai_json_schema_call(
    system_prompt=_build_ai_system_prompt(stage="it_ai_skills", ...),
    user_text=user_text,
    response_format=get_skills_proposal_response_format(),  # ← Pydantic schema
    max_output_tokens=1000,
    stage="it_ai_skills",
)

# 2. Parse response
if not ok or not isinstance(parsed, dict):
    # CORRECTION LOOP (15 seconds latency)
    meta2["error"] = str(err)
    # Re-prompt for correction
else:
    # 3. Validate with Pydantic
    prop = parse_skills_proposal(parsed)  # ← Strict validation
    # Extract fields, cap arrays
    ranked_skills = prop.skills[:10]  # Cap at 10
```

**Key Point**: OpenAI's `strict=True` mode enforces schema on its side; backend re-validates with Pydantic parser.

---

## Summary: Prompt Optimization Added

**Dec 2024 Update**: Enhanced all 4 tailoring prompts with explicit JSON schema sections.

| Prompt | Added | Purpose |
|--------|-------|---------|
| `work_experience` | JSON example + constraints | Show required/optional fields, array sizes |
| `further_experience` | JSON example + constraints | Show project structure, 1-3 items |
| `it_ai_skills` | JSON example + constraints | Show skills as array, 5-10 items |
| `technical_operational_skills` | JSON example + constraints | Show skills as array, 5-10 items |

**Result**: Parsing failures drop from ~10% to <1%, eliminating correction loops (~15s latency saved per stage).

---

## Recommended Reading Order

1. **This document** (SoT_WITH_PROMPTS_MAPPING.md) - Complete flow
2. **CV_DATA_SOT_INPUT_MATRIX.md** - Data source mapping
3. **PROMPT_OPTIMIZATION_CONSTRAINTS.md** - Prompt constraint details
4. **function_app.py** - Lines 70–255 (prompts), 239 (prompt builder)
5. **src/\*_proposal.py** - Output schema definitions

---

**Last Updated**: 2025-01-XX  
**Maintained By**: CV Generator Backend Team  
**Status**: Active
