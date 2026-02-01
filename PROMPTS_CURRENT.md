# AI Prompts by Stage (Current Active)

## Base Prompt (All Stages)

```
You are an expert assistant for CV processing.
Return JSON only that strictly matches the provided schema.
Preserve facts, names, and date ranges exactly; do not invent.
Do not add line breaks inside any JSON string values.
```

---

## Stage 1: job_posting

**Purpose:** Extract job offer into structured reference

**Prompt:**
```
Extract a compact, ATS-oriented job reference from the provided job offer text.
Focus on role title, company, location, responsibilities, requirements, tools/tech, and keywords.
Exclude salary, benefits, reporting lines, and employer branding content.
```

**Input:** Job offer text or URL  
**Output:** JobReference (company, title, location, responsibilities[], requirements[], tools[], keywords[])

---

## Stage 2: education_translation

**Purpose:** Translate education entries to target language

**Prompt:**
```
Translate all education entries to {target_language}.
Preserve institution names and date_range exactly.
Translate free-text fields only (title, specialization, details, location).
Do NOT add/remove entries or details.
```

**Input:** Education entries list  
**Output:** Translated education entries (same structure)

---

## Stage 3: work_experience

**Purpose:** Tailor work experience bullets to job posting

**Prompt:**
```
This is a semantic tailoring task, not a translation task.
You MAY rewrite, rephrase, merge, split, or reorder existing content to better match the job context,
as long as all facts remain unchanged and no new information is introduced.
Change HOW the experience is framed, not WHAT is factually true.

Rewrite CURRENT_WORK_EXPERIENCE into a structured list of roles.
Use facts from CURRENT_WORK_EXPERIENCE as the base structure (companies, dates, roles).
When TAILORING_SUGGESTIONS are provided, they take priority over original bullets and MUST be incorporated where relevant.
Do not infer or fabricate metrics, tools, team size, scope, or impact beyond what is stated in CURRENT_WORK_EXPERIENCE or TAILORING_SUGGESTIONS.
Do NOT copy or paraphrase job posting bullets.

For each role: identify the core problem or responsibility relevant to the job;
prioritize achievements and outcomes over general duties;
do not preserve original bullet wording if a clearer, more relevant framing is possible.

Output language: {target_language}.
Constraints: select 3-4 most relevant roles; 2-4 bullets per role; total bullets 8-12;
keep companies and date ranges; translate role titles to the most accurate, standard equivalent job position in the target language (if no clear standard equivalent exists, keep the original title); date_range must be a single line.
```

**Input:**
- `[JOB_SUMMARY]` - extracted job reference
- `[CANDIDATE_PROFILE]` - CV profile/summary
- `[TAILORING_SUGGESTIONS]` - user's notes with achievements/metrics
- `[TAILORING_FEEDBACK]` - iterative feedback (if regenerating)
- `[CURRENT_WORK_EXPERIENCE]` - existing work roles with bullets

**Output:** WorkExperienceBulletsProposal (roles[])

**Key Rules:**
- **TAILORING_SUGGESTIONS take priority** - must be incorporated where relevant
- **Semantic reframing allowed** - rewrite, rephrase, merge, split to match job context
- **Problem-action-impact framing** - identify core problem, prioritize achievements over duties
- Don't fabricate beyond CURRENT_WORK_EXPERIENCE or TAILORING_SUGGESTIONS
- Don't preserve original wording if clearer framing is possible
- Translate role titles to the most accurate standard equivalent (keep original if unclear)

---

## Stage 4: further_experience

**Purpose:** Tailor technical projects to job posting

**Prompt:**
```
This is a semantic tailoring task, not a translation task.
You MAY rewrite, rephrase, merge, split, or reorder existing content to better match the job context,
as long as all facts remain unchanged and no new information is introduced.
Change HOW the experience is framed, not WHAT is factually true.

Tailor the Selected Technical Projects section by selecting and rewriting entries most relevant to the job posting.
Use only provided facts (no invented projects/orgs).
Focus on: technical projects aligned with job keywords.

Frame projects as practical, production-relevant work.
Emphasize reliability, structure, automation, and operational enablement.
Do NOT frame projects as experimentation or research.

Output language: {target_language}.
Constraints: select 1-3 most relevant entries; 1-3 bullets per entry; total bullets 3-6.
```

**Input:**
- `[JOB_SUMMARY]` - extracted job reference
- `[TAILORING_NOTES]` - user's notes
- `[CURRENT_FURTHER_EXPERIENCE]` - list from canonical CV (technical projects)

**Output:** FurtherExperienceProposal (projects[])

**Data Sources:**
- cv_data.further_experience


---

## Stage 5: skills_ranking (Unified IT & AI + Technical & Operational)

**Purpose:** Derive two complementary skill sections from job posting + CV + user achievements

**Prompt:**
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

**Input:**
- `[JOB_SUMMARY]` - extracted job reference
- `[CANDIDATE_PROFILE]` - CV profile/summary
- `[TAILORING_SUGGESTIONS]` - user's notes with achievements/metrics
- `[RANKING_NOTES]` - optional user feedback
- `[CANDIDATE_SKILLS]` - pooled skill list from CV + DOCX prefill

**Output:** SkillsUnifiedProposal (it_ai_skills[], technical_operational_skills[], notes)

**Key Rules:**
- Both sections filled in single prompt for consistency and avoidance of duplication
- Output: 5-8 skills per section (max 8 each)
- Grounded in real achievements; no invention of tools/certs
- Phrased professionally for Swiss industry context
### Token Limits
- job_posting: 800 tokens
- education_translation: 800 tokens
- work_experience: 900 tokens
- further_experience: 1000 tokens
- skills_ranking (unified it_ai + tech_ops): 1200 tokens

### Reasoning Control
All stages use: `reasoning: None` to prevent o1-style thinking from consuming output tokens

### Dashboard Prompt
- Prompt ID: `pmpt_696f593c42148195ab41b3a3aaeaa55d029c2c08c553971f`
- Model: gpt-5-mini (configured in dashboard)
- System prompt is omitted when using dashboard prompt to save tokens (unless < 600 chars or override enabled)

**Per-stage prompt IDs (recommended for stateless stage control):**
- Set `OPENAI_PROMPT_ID_<STAGE>` (e.g., `OPENAI_PROMPT_ID_REVIEW_SESSION`, `OPENAI_PROMPT_ID_WORK_EXPERIENCE`, `OPENAI_PROMPT_ID_IT_AI_SKILLS`).
- Optionally enforce via `REQUIRE_OPENAI_PROMPT_ID_PER_STAGE=1`.

### Data Merging Strategy
Tailoring/ranking stages use canonical `cv_data` as the base source of truth.

- Work experience tailoring uses `cv_data` plus user tailoring suggestions/feedback.
- Skills ranking now combines both sections (IT & AI + Technical & Operational) in a single unified prompt to ensure consistency and avoid duplication.

---

## Expert Improvements Applied

### v2.1 (2026-01-31) - Unified Skills Ranking

**Core Change:** Skills ranking merged from 2 separate stages (5a/5b) into 1 unified prompt

**Reason:** Ensure consistency between IT & AI and Technical & Operational sections, prevent duplication, ground both sections in real achievements.

**New Schema:** SkillsUnifiedProposal with `it_ai_skills[]` + `technical_operational_skills[]` + `notes`

**Prompt Focus:** 
- Grounded skills (demonstrated through actions/systems/results)
- Clear section definitions (IT enablers vs process/operational)
- 5-8 items per section max
- Professional phrasing for Swiss industry CV

### v2.0 (2026-01-28) - Semantic Tailoring Authorization

**Core Change:** All tailoring stages now explicitly authorize semantic reframing

**Mandatory Block Added:**
```
This is a semantic tailoring task, not a translation task.
You MAY rewrite, rephrase, merge, split, or reorder existing content to better match the job context,
as long as all facts remain unchanged and no new information is introduced.
Change HOW the experience is framed, not WHAT is factually true.
```

**Stage-Specific Reinforcements:**

1. **work_experience:**
   - TAILORING_SUGGESTIONS take priority over original bullets
   - Problem-action-impact framing required
   - Original wording preservation not required if better framing exists

2. **further_experience (technical projects):**
   - Frame as production-relevant, not experimental
   - Emphasize reliability, structure, automation, operational enablement

3. **it_ai_skills + technical_operational_skills:**
   - Explicit relevance-ranking task (not inventory)
   - Job-priority ordering (not CV order)
   - Hard operational methods over soft skills (tech/ops only)

**Expected Outcomes:**
- ❌ No more translation-only behavior
- ✅ Clear problem–action–impact framing
- ✅ Strong differentiation per job posting
- ✅ AI positioned as enabler, not experimentation
- ✅ CV reads as intentionally tailored

### v1.0 - Foundation

1. **Job posting extraction:** Exclude salary, benefits, reporting lines, employer branding
2. **Work experience hallucination guard:** Do not infer/fabricate metrics, tools, team size, scope, impact
3. **Role title translation:** Translate only if clear, standard equivalent exists (DACH market consideration)
4. **Source data enhancement:** Unconfirmed extraction data is used only for recovery/confirmation flows; tailoring/ranking stages rely on canonical `cv_data`.
