# CV Generator - All Stage Prompts

This document contains all AI prompts used in the CV Generator workflow, organized by stage.

---

## Stage 1: Job Posting Analysis

**File:** `src/prompts/job_posting.txt`

**Purpose:** Extract structured job reference from raw job posting text

**Prompt:**

```
Extract a compact, ATS-oriented job reference (1-2 pages summary max) from the provided job posting. Preserve key technical and soft skills, domains, certifications, and salary info. Remove unnecessary detail.

Language:
- Use the same language as the job posting; do not translate.

Output JSON: {job_id, company, title, key_skills[], tech_stack[], min_salary, max_salary, highlights[], domain, contract_type}.
```

---

## Stage 2: Work Experience Tailoring

**File:** `src/prompts/work_experience.txt`

**Purpose:** Rewrite work experience bullets to align with target job posting

**Prompt:**

```
This is a semantic tailoring task. You are given:
1) Candidate CV (raw work history, skills, education)
2) Job posting (target role, key skills, domain, company, seniority)

Your job: rewrite the candidate's work experience bullets for ATS + human readability, emphasizing alignment with the target job.

Language:
- Write all output text in {target_language}.
- Do not mix languages.

Rules:
- Keep bullets 1-2 lines max (aim <= 180 chars; hard max 200 chars each).
- Start with an action verb (Led, Architected, Optimized, Delivered, Designed, etc.).
- Include a concrete metric or outcome (time saved, quality gain, revenue impact, scale).
- Highlight job keywords (technical stack, methodologies, domains from the job posting).
- Remove generic phrases ("responsible for", "helped with", "in charge of").
- Max 4 bullets per role; pick the strongest 3-4 that align with the job posting.
- Use domain context (if role is DevOps, highlight infrastructure; if SWE, highlight architecture decisions; etc.).
- Keep all JSON string values single-line (no literal newlines).

Output JSON schema (must match exactly):
{
  "roles": [
    {
      "title": "string",
      "company": "string",
      "date_range": "string (e.g., '2020-01 – 2025-10')",
      "location": "string (optional)",
      "bullets": ["bullet1", "bullet2", "bullet3", "bullet4"]
    }
  ],
  "notes": "string (short, optional)"
}
```

---

## Stage 3: Further Experience Extraction

**File:** `src/prompts/further_experience.txt`

**Purpose:** Summarize side projects, voluntary roles, consulting work

**Prompt:**

```
Given a candidate's full CV and target job posting, summarize any "further experience" sections (side projects, voluntary roles, pro bono, academic research, consulting) that add credibility to the job application.

Language:
- Write all output text in {target_language}.
- Do not mix languages.

Rules:
- Pick **top 1-2 items** that align with target job.
- Format as brief 1-liner: "Advisor, [Project Name] (2022–2024): [1-line impact]".
- Include **domain relevance** if clear (e.g., "ML model review" for AI roles).
- Omit if not relevant or weak alignment.

Output JSON:
{
  "further_experience_items": [
    {
      "role": "string",
      "project_name": "string",
      "period": "string",
      "one_liner": "string (1-2 lines max)"
    }
  ]
}
```

---

## Stage 4: Skills Ranking (IT & AI + Technical & Operational)

**File:** `src/prompts/it_ai_skills.txt`

**Purpose:** Categorize and rank candidate skills into two complementary sections aligned with job posting

**Prompt:**

```
Your task is to derive two complementary skill sections from the candidate's CV + job posting:

1. **IT & AI Skills** – Digital tools, automation, data-driven systems, cloud platforms, programming languages, AI/GPT integration, reporting dashboards, technical frameworks.

2. **Technical & Operational Skills** – Quality systems (IATF, VDA, Formel-Q), process improvement (KAIZEN, VSM, continuous improvement), production/manufacturing experience, team leadership, problem-solving methodologies (FMEA, 5 Whys, PDCA), efficiency optimization, changeover & downtime reduction, operational governance, CAPEX/OPEX project management.

**Job Context Alignment:**
- Prioritize skills matching the **job posting keywords** (e.g., if the role emphasizes "Operational Excellence", "cycle time reduction", or "KAIZEN", surface those capabilities prominently).
- For roles in **production plants, manufacturing, or quality management**, emphasize hands-on operational expertise: shop-floor improvement, standard work, value chain diagnostics, and measurable results (e.g., "reduced changeover time by X%").
- For **technical leadership roles**, balance digital/automation skills (cloud, data pipelines, AI tools) with operational delivery and team coordination.

**Language:**
- Write all output text in {target_language}.
- Do not mix languages.

**Rules:**
- **Max 5-8 skills per section** (aim for the most relevant and impactful).
- List only skills **grounded in CV experience** – not aspirational or generic.
- Use **short, ATS-friendly names**: Python, Azure, IATF, KAIZEN, VSM, Process Optimization, Quality Assurance, Standard Work, etc.
- **No duplication across sections**: If "IATF" is in Technical & Operational, do not repeat it in IT & AI.
- Prefer **measurable, contextual terms** over vague labels (e.g., "Cycle time reduction" instead of just "Lean").

**Operational Excellence Keywords (when relevant to job):**
- Efficiency, Process Optimization, Quality Assurance, KAIZEN, Continuous Improvement, Team Leadership, Problem-Solving, Manufacturing, Standard Work, Shop-Floor Standardization, Value Chain Diagnostics, Changeover Reduction, Downtime Reduction, CAPEX/OPEX Management, Production Planning.

**Output JSON:**
{
  "it_ai_skills": ["skill1", "skill2", ...],
  "technical_operational_skills": ["skill1", "skill2", ...],
  "notes": "Brief explanation of categorization logic or alignment with job posting (max 500 chars)"
}

**Important:**
- Only return the JSON object; no markdown fences or additional commentary.
- Ensure all skills come from the [CANDIDATE_SKILLS] input – never invent skills not present in the CV.
- The notes field should explain your reasoning (e.g., "Emphasized KAIZEN and cycle-time reduction to match Operational Excellence role at Vibe-X").
```

---

## Stage 5: Interests Summary

**File:** `src/prompts/interests.txt`

**Purpose:** Extract and polish interests/hobbies into professional 1-2 line summary

**Prompt:**

```
Extract and polish the candidate's interests/hobbies from their CV into a brief, professional "About / Interests" section (1-2 lines max, <= 200 chars).

Language:
- Write all output text in {target_language}.
- Do not mix languages.

Rules:
- Keep only interests that **enhance professional image** (tech hobbies, open-source, volunteering, etc.).
- Skip overly personal (political, religious, or niche hobby focus).
- If no interests on CV, return empty or generic: "Interested in [domain] and tech community engagement."

Output JSON:
{
  "interests_summary": "string (1-2 lines, <= 200 chars, e.g., 'Open source contributor; interested in cloud architecture and mentoring junior developers.')"
}
```

---

## Stage 6: Cover Letter Generation

**File:** `src/prompts/cover_letter.txt`

**Purpose:** Generate formal European-style cover letter (1 page)

**Prompt:**

```
You are generating a formal European (CH/EU) cover letter (1 page, ~1,800–2,200 chars) from:
1. **Candidate CV** (background, key achievements, skills).
2. **Job posting** (company, role, key qualifications).
3. **Optional motivation** (candidate's reason for applying, if provided).

Style:
- **Professional, formal tone** (suitable for Switzerland/EU job market).
- **No emojis or excessive enthusiasm**; let competence speak.
- Write the cover letter in {target_language}.
- Structure: Opening → Why you fit the role (2–3 key reasons) → Closing.
- **Personalize**: Reference company vision/domain if possible.
- **Max 1 page**; single-spaced.

CRITICAL CONSTRAINT:
Do NOT attribute tools, technologies, domains, or hands-on experience to the candidate
unless they are explicitly present in the Candidate CV, Work Experience, Skills,
or Tailoring Notes.
Job posting terminology may be referenced ONLY as the employer's domain or project context,
not as the candidate's direct experience.

Allowed:
- Referencing the company's domain, industry, or project focus.
- Stating transferability of experience (e.g. "experience applicable to regulated environments").

Forbidden:
- Claiming hands-on experience with tools, systems, or technologies
	that appear only in the job posting and not in candidate inputs.

When in doubt, prefer conservative phrasing that avoids naming
specific tools or technologies and instead describes experience
at the level of process, responsibility, or outcome.

ANTI-HAPPY-INPUT HARDENING:

Writing mode:
- Use a REFERENTIAL, non-interpretative writing style.
- Each sentence must be directly traceable to one or more explicit CV facts.
- Do not summarize, generalize, or extrapolate beyond stated CV content.

Forbidden language patterns:
- Statements about being "well suited", "a strong fit", "highly relevant", or "able to contribute".
- Forward-looking claims about future performance or value.
- Any phrasing that evaluates or praises the candidate.

Abstraction control:
- Avoid abstract nouns such as: expertise, capability, background, proficiency, strength.
- Prefer concrete actions, roles, or outcomes explicitly stated in the CV.

Job reference usage:
- Do not mirror or echo the wording of the job posting.
- Do not align phrasing stylistically with the job description.
- Use the job reference only to select which CV facts to mention, not how to phrase them.

Interview defensibility guard:
- If a sentence cannot be defended verbatim in a factual interview, rewrite it or remove it.

Output format (plain text, NOT JSON):
[Full cover letter text, ready to paste into an email or application form.]
```

---

## Utility Stage A: Bulk Translation

**File:** `src/prompts/bulk_translation.txt`

**Purpose:** Translate entire CV sections to target language while preserving formatting

**Prompt:**

```
Translate a bulk set of work history, skills, interests, or education entries from the source language to professional {target_language}. Preserve technical terms, company names, and dates; modernize phrasing. Keep output text in {target_language} only.
```

---

## Utility Stage B: Education Translation

**File:** `src/prompts/education_translation.txt`

**Purpose:** Translate and expand education entries with ATS-friendly formatting

**Prompt:**

```
Translate education entries to professional, concise ATS-friendly {target_language}. For each entry, preserve degree, field, university, graduation date. Expand abbreviations (e.g., "MGR" → "Master's"); add relevance hint (e.g., "foundational for ML roles" or "enterprise architecture focus"). Output JSON: {education_entries: [{degree, field_of_study, institution, graduation_date, notes}]}.
```

---

## Prompt Variables Reference

All prompts support the following template variables:

- `{target_language}` - Target output language (e.g., "en", "de", "pl")
- User inputs are inserted into labeled sections like `[JOB_SUMMARY]`, `[CANDIDATE_PROFILE]`, `[WORK_EXPERIENCE]`, etc.

---

## System Prompt Base

All stage prompts are prefixed with a common system prompt defined in `function_app.py` as `_AI_PROMPT_BASE`.

---

**Last Updated:** 2026-02-13  
**Version:** 1.0 (Post Master Plan Implementation)
