# CV Generator — Prompts Matrix (By Stage)

**Purpose:** Single source of truth for all AI-generated prompts. Review with CV expert to ensure accuracy and alignment.

**Architecture:**
- **Dashboard prompt:** minimal, stable, tool-less (set once, not changed per stage)
- **Backend prompts:** stage-specific, in `_AI_PROMPT_BY_STAGE` dict in `function_app.py`
- **Enforcement:** backend always sends `text={"format": {"type": "json_schema", ...}}` per stage (schema enforcement, not just prompt)

---

## Dashboard System Prompt (OPENAI_PROMPT_ID)

**Context:** Set once in OpenAI platform; used as baseline for all calls.

**Current text (recommended):**
```
You are an expert assistant for CV processing. 
Return JSON only that strictly matches the provided schema. 
Preserve facts, names, and date ranges exactly; do not invent. 
Do not add line breaks inside any JSON string values.
```

**Why minimal?**
- Backend adds stage-specific rules via `_build_ai_system_prompt(stage=...)`
- Dashboard stays stable; no redeploy needed to adjust logic

---

## Backend Prompts by Stage

### 1. **JOB_POSTING** (Extract job summary → `job_reference`)

**Stage ID:** `job_posting`  
**Triggered by:** `JOB_OFFER_ANALYZE`, `JOB_OFFER_CONTINUE`, `WORK_TAILOR_RUN` (if no prior summary)  
**Input:** Raw job posting text (up to 20k chars)  
**Output schema:** `get_job_reference_response_format()`  
**Max tokens:** 900

**Backend prompt (from `_AI_PROMPT_BY_STAGE["job_posting"]`):**
```
Extract a compact, ATS-oriented job reference from the provided job offer text. 
Focus on role title, company, location, responsibilities, requirements, tools/tech, and keywords. 
Exclude salary, benefits, reporting lines, and employer branding content.
```

**Review checklist:**
- [x] Does it capture all essential job context? **Yes**
- [x] Is "ATS-oriented" the right framing? **Yes**
- [x] Should we exclude salary/benefits/reporting to manager? **Addressed: now excluded**

---

### 2. **EDUCATION_TRANSLATION** (Translate education to target language)

**Stage ID:** `education_translation`  
**Triggered by:** `EDUCATION_CONFIRM` (if `education_translated_to != target_lang`)  
**Input:** Current education list (JSON)  
**Output schema:** Custom schema (see below)  
**Max tokens:** 800  
**Target language placeholder:** `{target_language}` (e.g., "en", "de", "pl")

**Backend prompt (from `_AI_PROMPT_BY_STAGE["education_translation"]`):**
```
Translate all education entries to {target_language}. 
Preserve institution names and date_range exactly. 
Translate free-text fields only (title, specialization, details, location). 
Do NOT add/remove entries or details.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "education": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "institution": {"type": "string"},
          "date_range": {"type": "string"},
          "specialization": {"type": "string"},
          "details": {"type": "array", "items": {"type": "string"}},
          "location": {"type": "string"}
        },
        "required": ["title", "institution", "date_range"]
      }
    }
  },
  "required": ["education"]
}
```

**Review checklist:**
- [ ] Should institution names stay in original language or be translated?
- [ ] Do we want to preserve German terms like "Schwerpunkt" or translate them?
- [ ] Is "date_range" always reliable (e.g., "2012-2015")?
- [ ] Should we add validation for degree types (Bachelor, Master, PhD)?

---

### 3. **WORK_EXPERIENCE** (Tailor work bullets to job posting)

**Stage ID:** `work_experience`  
**Triggered by:** `WORK_TAILOR_RUN`  
**Input:** 
  - `[JOB_SUMMARY]` (extracted from job posting or prior summary)
  - `[CANDIDATE_PROFILE]` (from CV)
  - `[TAILORING_SUGGESTIONS]` (user notes)
  - `[TAILORING_FEEDBACK]` (user feedback from prior attempt)
  - `[CURRENT_WORK_EXPERIENCE]` (existing roles + bullets)
  
**Output schema:** `get_work_experience_bullets_proposal_response_format()`  
**Max tokens:** 900  
**Target language placeholder:** `{target_language}`

**Backend prompt (from `_AI_PROMPT_BY_STAGE["work_experience"]`):**
```
Rewrite CURRENT_WORK_EXPERIENCE into a structured list of roles. 
Use only provided facts from CURRENT_WORK_EXPERIENCE (no new employers/tools/numbers). 
Do not infer or fabricate metrics, tools, team size, scope, or impact. 
Do NOT copy or paraphrase job posting bullets. 
Output language: {target_language}. 
Constraints: select 3-4 most relevant roles; 2-4 bullets per role; total bullets 8-12; 
keep companies and date ranges; translate role titles to the most accurate, standard equivalent job position in the target language (if no clear standard equivalent exists, keep the original title); date_range must be a single line.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "roles": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "company": {"type": "string"},
          "date_range": {"type": "string"},
          "location": {"type": "string"},
          "bullets": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["title", "company", "date_range", "bullets"]
      }
    },
    "notes": {"type": "string"}
  },
  "required": ["roles"]
}
```

**Review checklist:**
- [x] Should we enforce "no new employers" more strictly (e.g., block unknown companies)? **Current approach is correct**
- [x] Is 3-4 roles the right count for a 2-page CV? **Yes, confirmed for senior profiles**
- [x] Should bullets be 80-90 chars (soft) or more flexible? **Flexible is correct (ATS-safe)**
- [x] Does title translation align with target audience? **Addressed: only translate if clear equivalent exists**
- [x] Should we prevent fabricated metrics? **Addressed: added hallucination guard**

---

### 4. **FURTHER_EXPERIENCE** (Tailor technical projects to job posting)

**Stage ID:** `further_experience`  
**Triggered by:** `FURTHER_TAILOR_RUN`  
**Input:** 
  - `[JOB_SUMMARY]` (job reference)
  - `[TAILORING_NOTES]` (user notes)
  - `[CURRENT_FURTHER_EXPERIENCE]` (existing projects)
  
**Output schema:** `get_further_experience_proposal_response_format()`  
**Max tokens:** 600  
**Target language placeholder:** `{target_language}`

**Backend prompt (from `_AI_PROMPT_BY_STAGE["further_experience"]`):**
```
Tailor the Selected Technical Projects section by selecting and rewriting entries most relevant to the job posting. 
Use only provided facts (no invented projects/orgs). 
Focus on: technical projects, certifications, side work, freelance, open-source contributions aligned with job keywords. 
Output language: {target_language}. 
Constraints: select 1-3 most relevant entries; 1-3 bullets per entry; total bullets 3-6.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "projects": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "organization": {"type": "string"},
          "date_range": {"type": "string"},
          "location": {"type": "string"},
          "bullets": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["title", "bullets"]
      }
    },
    "notes": {"type": "string"}
  },
  "required": ["projects"]
}
```

**Review checklist:**
- [ ] Should we prefer certifications over side projects if both exist?
- [ ] Is 1-3 entries appropriate for technical projects section?
- [ ] Should bullets emphasize technical skills used or impact/results?
- [ ] Should we require date_range for all projects?

---

### 5. **SKILLS_RANKING** (Unified IT & AI + Technical & Operational)

**Stage ID:** `it_ai_skills` (unified, triggers both sections)  
**Triggered by:** `SKILLS_TAILOR_RUN`  
**Input:** 
  - `[JOB_SUMMARY]` (job reference)
  - `[CANDIDATE_PROFILE]` (CV profile)
  - `[TAILORING_SUGGESTIONS]` (user notes with achievements)
  - `[RANKING_NOTES]` (user feedback)
  - `[CANDIDATE_SKILLS]` (pooled list from CV + DOCX prefill)
  
**Output schema:** `get_skills_unified_proposal_response_format()`  
**Max tokens:** 1200  
**Target language placeholder:** `{target_language}`

**Backend prompt (from `_AI_PROMPT_BY_STAGE["it_ai_skills"]`):**

**UNIFIED APPROACH:** Single prompt generates both `it_ai_skills` and `technical_operational_skills` arrays in one response.

```
Your task is to derive two complementary skill sections from the provided inputs.

Inputs include:
- a job offer summary,
- the candidate's CV and achievements,
- and user-provided tailoring notes describing real work achievements.

You must:
1) Identify the candidate's most relevant IT & AI skills,
2) Identify the candidate's most relevant Technical & Operational skills.

Guidelines:
- Skills must be grounded in the candidate's real experience and achievements.
- Prefer skills that are demonstrated through actions, systems, or results.
- Do not invent skills that are not supported by the inputs.
- You may generalize from described work (e.g., automation, system design, process optimization), but do not fabricate tools or certifications.

Section definitions:
- IT & AI Skills: digital tools, automation, AI usage, data-driven systems, reporting, and technical enablers.
- Technical & Operational Skills: quality systems, process improvement methods, project delivery, production, construction, and operational governance.

Output rules:
- Provide two separate lists: it_ai_skills and technical_operational_skills.
- Each list should contain 5–8 concise skill entries.
- Skills should be phrased clearly and professionally, suitable for a Swiss industry CV.
- Avoid duplication between the two sections.
- Output language: {target_language}.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "it_ai_skills": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Digital tools, automation, AI usage, data-driven systems, reporting (5-8 items)"
    },
    "technical_operational_skills": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Quality systems, process improvement, project delivery, production, construction, operational governance (5-8 items)"
    },
    "notes": {"type": "string"}
  },
  "required": ["it_ai_skills", "technical_operational_skills"]
}
```

**Review checklist:**
- [x] Should we combine both sections in one prompt? **YES — ensures consistency and prevents duplication**
- [x] What max count per section? **5-8 items each (confirmed)**
- [x] How to avoid duplication across sections? **Explicit in prompt + review logic**
- [x] Should we ground skills in real achievements? **YES — only demonstrated through work/systems/results**

---
Rank and filter the candidate's technical and operational skills by relevance to the job posting. 
Focus on: process management, quality systems, operational excellence, lean/six sigma, project management. 
Keep only skills mentioned in the job posting or closely related. 
Order by relevance (most important first). 
Output 5-10 top skills max. 
Output language: {target_language}.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "skills": {
      "type": "array",
      "items": {"type": "string"},
      "maxItems": 10
    },
    "notes": {"type": "string"}
  },
  "required": ["skills"]
}
```

**Review checklist:**
- [ ] Should this section focus on "soft" operational skills (leadership, process) or "hard" technical skills (tools, methods)?
- [ ] What's the ideal max count? (5, 8, 10?)
- [ ] Should we enforce no overlap with IT/AI Skills section?
- [ ] Should we group by subcategory (management, quality, lean)?

---

## Summary: Prompts Configuration Map

| Stage | Prompt ID Env Var | Backend Dict Key | Input Type | Output Schema | Tokens |
|-------|-------------------|------------------|-----------|---------------|--------|
| Job offer extraction | `OPENAI_PROMPT_ID_JOB_POSTING` | `"job_posting"` | Text (20k max) | `job_reference` | 900 |
| Education translation | (inherits OPENAI_PROMPT_ID) | `"education_translation"` | JSON (education[]) | Custom (education[]) | 800 |
| Work experience tailoring | `OPENAI_PROMPT_ID_WORK_TAILOR_RUN` | `"work_experience"` | Text (multi-block) | `work_proposal` (roles[]) | 900 |
| Technical projects tailoring | (inherits OPENAI_PROMPT_ID) | `"further_experience"` | Text (projects) | `further_proposal` (projects[]) | 600 |
| IT/AI skills ranking | (inherits OPENAI_PROMPT_ID) | `"it_ai_skills"` | Text (skills list) | `skills_proposal` | 1000 |
| Tech/Ops skills ranking | (inherits OPENAI_PROMPT_ID) | `"technical_operational_skills"` | Text (skills list) | `tech_ops_proposal` | 1000 |

---

## Configuration Steps (For You)

1. **Set up one dashboard prompt** (if not already done):
   - Use the minimal text above
   - Copy to OpenAI platform
   - Note the prompt ID

2. **Set environment variables** in `local.settings.json`:
   ```json
   {
     "OPENAI_PROMPT_ID": "<your-dashboard-prompt-id>",
     "OPENAI_DASHBOARD_INCLUDE_SYSTEM_PROMPT": "1"
   }
   ```

3. **(Optional) Stage-specific overrides** if you want different prompts:
   ```json
   {
     "OPENAI_PROMPT_ID_JOB_POSTING": "<lighter-extraction-prompt-id>",
     "OPENAI_PROMPT_ID_WORK_TAILOR_RUN": "<heavy-tailoring-prompt-id>"
   }
   ```

4. **Review with CV expert:**
   - [ ] Does the job extraction capture what matters?
   - [ ] Are education translations preserving intent?
   - [ ] Does work tailoring align with ATS + recruiter expectations?
   - [ ] Do technical projects emphasize skills or impact?
   - [ ] Are skills ranked appropriately by job relevance?
   - [ ] Is there clear separation between IT/AI skills and operational skills?

---

## Future Enhancements

- Add role-level constraints (e.g., "manager roles should highlight team size / budget")
- Add industry-specific templates (e.g., "software engineer" vs "operations manager")
- Localize template labels (currently "specialization:" is English even in German CVs)
- Async background translation (currently blocking on confirm)
- Add feedback loop for skills ranking (accept/reject individual skills)
- Add languages ranking (Phase 2)
- Add interests filtering (Phase 3, optional)

---

**Last updated:** 2026-01-28  
**Author:** Backend (auto-generated from `function_app.py`)  
**Review cycle:** Before major CV generation feature rollout
