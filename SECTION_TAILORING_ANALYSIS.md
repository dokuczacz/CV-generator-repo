# CV Section Tailoring Analysis

## Executive Summary

**Current state:** Only **work_experience** and **education** (translation-only) are AI-tailored.

**Skipped sections:** profile, it_ai_skills, languages, certifications, interests, references.

**Opportunity:** Apply the same job-posting-aware tailoring strategy to other sections.

---

## Work Experience Tailoring Pipeline (Current)

### 1. Job Posting Extraction (JOB_POSTING stage)
**Input:** Raw job posting text (20k chars max)
**Process:**
```
job_text → _openai_json_schema_call(stage="job_posting") → job_reference JSON
```
**Output schema:**
```python
{
  "role_title": str,
  "company": str,
  "location": str,
  "responsibilities": [str],
  "must_haves": [str],
  "nice_to_haves": [str],
  "tools_tech": [str],
  "keywords": [str]
}
```
**Storage:** `meta2["job_reference"]` (persisted in session)

### 2. Work Experience Tailoring (WORK_TAILOR_RUN stage)
**Input:**
- `[JOB_SUMMARY]` (formatted job_reference)
- `[CANDIDATE_PROFILE]` (from cv_data["profile"])
- `[TAILORING_SUGGESTIONS]` (from meta2["work_tailoring_notes"])
- `[TAILORING_FEEDBACK]` (from user refinements)
- `[CURRENT_WORK_EXPERIENCE]` (cv_data["work_experience"] formatted as text)

**Process:**
```
Serialize current roles → build user_text (multi-block prompt) 
→ _openai_json_schema_call(stage="work_experience", target_language=target_lang) 
→ roles proposal JSON
```

**Output schema:**
```python
{
  "roles": [
    {
      "title": str,
      "company": str,
      "date_range": str,
      "location": str,
      "bullets": [str]  # 2-4 per role, 8-12 total
    }
  ]
}
```

**Validation post-call:**
- Bullet length constraints (soft: 99 chars, hard: 180 chars)
- Total bullets 8-12
- Roles 3-5 max
- Date format validation

**Storage:** `meta2["work_experience_proposal"]` (in review stage)

### 3. Work Experience Apply (WORK_TAILOR_ACCEPT stage)
**Input:** User-reviewed proposal + original cv_data
**Process:**
```
Apply proposal roles to cv_data["work_experience"] template format
→ Sanitize bullets (single-line, truncate to max length)
→ Cap bullets per role (max 4)
→ Update cv_data["work_experience"]
```
**Output:** Updated cv_data ready for PDF generation

---

## CV Sections: Current State

| Section | Type | Tailoring | Translation | In Template? | Notes |
|---------|------|-----------|-------------|--------------|-------|
| **full_name** | string | ❌ No | ❌ No | ✅ Yes | Contact; rarely needs tailoring |
| **email** | string | ❌ No | ❌ No | ✅ Yes | Contact; fixed |
| **phone** | string | ❌ No | ❌ No | ✅ Yes | Contact; fixed |
| **photo_url** | string | ❌ No | ❌ No | ✅ Yes | Extracted from DOCX |
| **address_lines** | [string] | ❌ No | ❌ No | ✅ Yes | Optional; rarely needs tailoring |
| **birth_date** | string | ❌ No | ❌ No | ✅ Yes | Optional; fixed |
| **nationality** | string | ❌ No | ❌ No | ✅ Yes | Optional; fixed |
| **education** | [{...}] | ❌ No | ✅ **YES** | ✅ Yes | Only translation (target_lang) |
| **work_experience** | [{...}] | ✅ **YES** | ❌ No | ✅ Yes | Full tailoring pipeline |
| **further_experience** | [{...}] | ❌ **SKIPPED** | ❌ No | ✅ Yes (as "Selected Technical Projects") | **Opportunity**: rank + tailor like work_experience |
| **languages** | [string/dict] | ❌ **SKIPPED** | ❌ No | ✅ Yes | **Opportunity**: translate + rank by job |
| **it_ai_skills** | [string] | ❌ **SKIPPED** | ❌ No | ✅ Yes | **Opportunity**: rank by job relevance |
| **technical_operational_skills** | [string] | ❌ **SKIPPED** | ❌ No | ✅ Yes | **Opportunity**: rank by job relevance |
| **interests** | string | ❌ **SKIPPED** | ❌ No | ✅ Yes | **Opportunity**: filter by job posting alignment |
| **references** | string | ❌ **SKIPPED** | ❌ No | ✅ Yes | Fixed text or omit; rarely tailored |
| **profile** | string | ❌ N/A | ❌ N/A | ❌ **NO** | Not in template; remove from tailoring plan |
| **certifications** | [{...}] | ❌ N/A | ❌ N/A | ❌ **NO** | Not in template; remove from tailoring plan |

---

## Proposed Strategy: Apply to Skipped Sections

### Pattern: Job-Aware Extraction → Ranking → Application

Each skipped section follows this pipeline:

```
[Section] Raw Data 
  → Extract section structure (JSON schema per section)
  → Rank/filter by job_reference relevance
  → Translate to target_language (if needed)
  → Apply back to cv_data
  → PDF render
```

---

## Detailed Proposals for Skipped Sections

### 1. FURTHER_EXPERIENCE Section (Technical Projects)

**Current:** `cv_data["further_experience"]` is a list similar to work_experience but not tailored.

**Template output:** Section titled "Selected Technical Projects" with same structure as work_experience (date_range, title, organization, bullets/details).

**Proposed tailoring:**

**Stage:** `further_experience_tailor` (new)

**Trigger:** After work tailoring, before PDF generation.

**Input:**
```
[JOB_SUMMARY]
[CANDIDATE_FURTHER_EXPERIENCE] (current list)
[CANDIDATE_WORK_EXPERIENCE] (to avoid duplication)
```

**Prompt (to add to `_AI_PROMPT_BY_STAGE`):**
```
Tailor the Selected Technical Projects section by selecting and rewriting entries most relevant to the job posting.
Use only provided facts (no invented projects/orgs).
Focus on: technical projects, certifications, side work, freelance, open-source contributions aligned with {job_keywords}.
Output language: {target_language}.
Constraints: select 1-3 most relevant entries; 1-3 bullets per entry; total bullets 3-6.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "entries": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "organization": {"type": "string"},
          "date_range": {"type": "string"},
          "bullets": {"type": "array", "items": {"type": "string"}},
          "details": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["title", "date_range"]
      },
      "maxItems": 3
    }
  },
  "required": ["entries"]
}
```

**Max tokens:** 600

**Storage:** `meta2["further_experience_proposal"]`

---

### 2. IT_AI_SKILLS Section

**Current:** `cv_data["it_ai_skills"]` is a flat list, not ranked by job.

**Template output:** Section titled "IT & AI Skills" rendered as bullet list.

**Proposed tailoring:**

**Stage:** `skills_rank` (new)

**Trigger:** After job posting extracted, before work tailoring.

**Input:**
```
[JOB_SUMMARY] (esp. tools_tech, keywords)
[CANDIDATE_SKILLS] (list of IT/AI skills from CV)
[CANDIDATE_WORK_EXPERIENCE] (context of where skills were used)
```

**Prompt:**
```
Rank and filter the candidate's IT/AI skills by relevance to the job posting.
Keep only skills that are mentioned in the job posting or closely related (e.g., Python if job wants coding).
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
    }
  },
  "required": ["skills"]
}
```

**Max tokens:** 300

**Storage:** `meta2["skills_proposal"]`

---

### 3. TECHNICAL_OPERATIONAL_SKILLS Section

**Current:** `cv_data["technical_operational_skills"]` is a flat list, not ranked by job.

**Template output:** Section titled "Technical & Operational Skills" rendered as bullet list.

**Proposed tailoring:**

**Stage:** `technical_operational_skills_rank` (new)

**Trigger:** After job posting extracted, before work tailoring.

**Input:**
```
[JOB_SUMMARY] (esp. responsibilities, must_haves)
[CANDIDATE_TECHNICAL_OPERATIONAL_SKILLS] (list from CV)
[CANDIDATE_WORK_EXPERIENCE] (context)
```

**Prompt:**
```
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
    }
  },
  "required": ["skills"]
}
```

**Max tokens:** 300

**Storage:** `meta2["technical_operational_skills_proposal"]`

---

### 4. LANGUAGES Section

**Current:** `cv_data["languages"]` is a list (string or dict with name/level), not ranked or translated.

**Template output:** Section titled "Language Skills" rendered as two-column table (name | level).

**Proposed tailoring:**

**Stage:** `languages_rank` (new)

**Trigger:** After job posting + target_language selected.

**Input:**
```
[JOB_SUMMARY] (job location, language requirements)
[CANDIDATE_LANGUAGES] (list with proficiency levels, e.g., "English (fluent)", "German (B2)")
[TARGET_LANGUAGE] (CV output language)
```

**Prompt:**
```
Rank and filter the candidate's languages by relevance to the job posting.
Prioritize languages mentioned in the job (e.g., "fluent English required").
Translate language names to {target_language} (e.g., "Englisch" if German CV, "Anglais" if French).
Translate proficiency levels (e.g., "fluent" → "fließend" in German, "native" → "Muttersprache").
Output 2-5 languages max, ordered by job relevance.
Format: either string "Language (level)" or dict {name, level}.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "languages": {
      "type": "array",
      "items": {
        "oneOf": [
          {"type": "string"},
          {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "level": {"type": "string"}
            },
            "required": ["name", "level"]
          }
        ]
      },
      "maxItems": 5
    }
  },
  "required": ["languages"]
}
```

**Max tokens:** 300

**Storage:** `meta2["languages_proposal"]`

---

### 5. INTERESTS Section

**Current:** `cv_data["interests"]` is a single string (not a list), not tailored.

**Template output:** Section titled "Interests" rendered as paragraph.

**Proposed tailoring:**

**Stage:** `interests_filter` (new)

**Trigger:** Optional, before PDF generation.

**Input:**
```
[JOB_SUMMARY]
[CANDIDATE_INTERESTS] (current text)
```

**Prompt:**
```
Rewrite interests to align with the job posting or company culture.
Remove generic interests. Keep specific, demonstrable interests (max 3-5).
Output as a single short sentence or comma-separated list.
Translate to {target_language}.
Max 60 words.
```

**Output schema:**
```json
{
  "type": "object",
  "properties": {
    "interests": {"type": "string", "maxLength": 100}
  },
  "required": ["interests"]
}
```

**Max tokens:** 150

**Storage:** `meta2["interests_proposal"]`

---

### 6. REFERENCES Section

**Current:** `cv_data["references"]` is a single string (default: "Will be announced on request.").

**Template output:** Section titled "References" rendered as paragraph.

**Proposed tailoring:**

**Not recommended for tailoring.** References are typically static ("available upon request") or omitted entirely from modern CVs. Skip this section.

---

## Implementation Roadmap

### Phase 1: Technical Projects + Skills (High ROI)
1. Add `further_experience_tailor`, `skills_rank`, and `technical_operational_skills_rank` stages to `_AI_PROMPT_BY_STAGE`
2. Create UI confirmations for technical projects + IT/AI skills + technical/operational skills proposals
3. Test + iterate

**Why first?** Technical projects show additional expertise; both skill sections are core fit signals. All highly visible to recruiters.

### Phase 2: Languages
4. Add `languages_rank` stage
5. Integrate translation of language names + proficiency levels
6. Integrate into confirmation flow

### Phase 3: Interests (Low ROI, optional)
7. Add `interests_filter` stage

---

## Questions for CV Expert Review

### Selected Technical Projects
- [ ] Should we filter to "only job-aligned" entries or include all?
- [ ] Max entries: 1, 2, or 3?
- [ ] Should bullets emphasize technical skills used or impact/results delivered?
- [ ] Should we require date_range for all projects?

### IT/AI Skills
- [ ] Should we filter to "only job-mentioned skills" or include related skills?
- [ ] What's the max count? (5, 8, 10?)
- [ ] Should we preserve original order (candidate priority) or always re-rank?

### Technical & Operational Skills
- [ ] Should this section focus on "soft" operational skills (leadership, process) or "hard" technical skills (tools, methods)?
- [ ] What's the max count? (5, 8, 10?)
- [ ] Should we enforce no overlap with IT/AI Skills section?

### Languages
- [ ] Should native languages always appear, or filtered too?
- [ ] What proficiency levels are standard? (native, fluent, C2, B2, intermediate, A2, beginner?)
- [ ] Should we add "job location language" as a signal?
- [ ] Template supports both string "English (fluent)" and dict {name, level} — prefer one?

### Interests
- [ ] Is interests section worth tailoring, or just omit if generic?
- [ ] Should we add company industry/values as signal? (e.g., "tech startup" vs "enterprise")
- [ ] Max word count: 50? 60?

---

## Summary Table: Sections to Enable

| Section | Stage ID | Complexity | Effort | ROI |
|---------|----------|-----------|--------|-----|
| further_experience (→ Technical Projects) | `further_experience_tailor` | Medium | 2-3h | High (shows technical breadth) |
| it_ai_skills | `skills_rank` | Low | 1-2h | High (core fit signal) |
| technical_operational_skills | `technical_operational_skills_rank` | Low | 1-2h | High (operational fit signal) |
| languages | `languages_rank` | Medium | 2h | Medium (nice-to-have + localization) |
| interests | `interests_filter` | Low | 30m | Low (rarely reviewed) |

---

**Next step:** Share this with your CV expert for feedback on prompts + constraints, then implement Phase 1 (profile + skills).
