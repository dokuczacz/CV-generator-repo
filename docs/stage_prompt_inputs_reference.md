# Stage Prompt Inputs Reference (AI stages only)

## Scope

This document includes only AI prompt stages requested in scope:
- `bulk_translation`
- `job_posting`
- `work_experience`
- `it_ai_skills`
- `interests`
- `cover_letter`

Excluded by scope decision:
- `further_experience`
- `education_translation`

Prompt text below is copied verbatim from `src/prompts/*.txt`.

---

## Shared prompt builder behavior

All stage prompts are loaded from `src/prompts/<stage>.txt` and then combined as:

1. Global base prefix:
   `Return JSON only that strictly matches the provided schema. Preserve facts, names, and date ranges exactly; do not invent. Do not add line breaks inside any JSON string values.`
2. Stage prompt file text (verbatim, shown below)
3. Optional `extra` suffix for some calls (e.g., interests)

`{target_language}` placeholders in prompt files are replaced at runtime with `target_language`.

---

## Stage: `bulk_translation`

### Prompt file
Source: `src/prompts/bulk_translation.txt`

```text
Translate a bulk set of work history, skills, interests, or education entries from the source language to professional {target_language}. Preserve technical terms, company names, and dates; modernize phrasing. Keep output text in {target_language} only.
```

### Runtime input sent (`user_text`)
Source assembly: `_build_bulk_translation_payload(...)` -> `_run_bulk_translation(...)`

`user_text` is `json.dumps(cv_payload, ensure_ascii=False)` where `cv_payload` is:

```json
{
  "profile": "<cv_data.profile>",
  "work_experience": ["<cv_data.work_experience entries>"],
  "further_experience": ["<cv_data.further_experience entries>"],
  "education": ["<cv_data.education entries>"],
  "it_ai_skills": ["<cv_data.it_ai_skills>"],
  "technical_operational_skills": ["<cv_data.technical_operational_skills>"],
  "languages": ["<cv_data.languages>"],
  "interests": "<cv_data.interests>",
  "references": "<cv_data.references>"
}
```

---

## Stage: `job_posting`

### Prompt file
Source: `src/prompts/job_posting.txt`

```text
Extract a compact, ATS-oriented job reference (1-2 pages summary max) from the provided job posting. Preserve key technical and soft skills, domains, certifications, and salary info. Remove unnecessary detail.

Language:
- Use the same language as the job posting; do not translate.

Output JSON: {job_id, company, title, key_skills[], tech_stack[], min_salary, max_salary, highlights[], domain, contract_type}.
```

### Runtime input sent (`user_text`)
Source assembly: `JOB_OFFER_ANALYZE`, `JOB_OFFER_CONTINUE`, and `FAST_RUN` job summary calls.

`user_text` is raw job posting text:

```text
<job_posting_text>
```

Input origin can be:
- direct pasted text (`user_action_payload.job_offer_text`), or
- fetched URL content (if payload is URL), truncated to up to 20,000 chars.

---

## Stage: `work_experience`

### Prompt file
Source: `src/prompts/work_experience.txt`

```text
This is a semantic tailoring task. You are given:
1) Candidate CV (raw work history, skills, education)
2) Job posting (target role, key skills, domain, company, seniority)

Your job: rewrite the candidate's work experience bullets for ATS + human readability, emphasizing alignment with the target job.

Source of truth:
- Candidate CV blocks provided in input are the only evidence of candidate experience.
- Job posting is a matching reference only and must not be used as evidence of candidate skills or hands-on experience.

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

### Runtime input sent (`user_text`)
Source assembly: `WORK_TAILOR_RUN` (and analogous FAST_RUN branch).

```text
[JOB_SUMMARY]
<format_job_reference_for_display(meta.job_reference)>

[TAILORING_SUGGESTIONS]
<meta.work_tailoring_notes>

[TAILORING_FEEDBACK]
<meta.work_tailoring_feedback>

[ALIGNMENT_POLICY]
For EACH role return full alignment section only: alignment_breakdown + alignment_evidence.
Use BOTH CURRENT_WORK_EXPERIENCE and TAILORING_SUGGESTIONS/TAILORING_FEEDBACK as candidate evidence.
Core responsibilities match (0.00-0.40), Methods/tools match (0.00-0.25), Context match (0.00-0.15), Seniority/scope (0.00-0.10), Language/requirements match (0.00-0.10).
Role inclusion threshold is backend-derived from alignment_breakdown sum < <threshold>.

[CURRENT_WORK_EXPERIENCE]
<title | company | date>
- <bullet>
- <bullet>
...

<title | company | date>
- <bullet>
...
```

Notes:
- If `job_reference` is missing but `job_posting_text` exists, system first runs `job_posting` stage to derive compact summary.
- Retry path may inject stricter validation feedback into `[TAILORING_FEEDBACK]`.

---

## Stage: `it_ai_skills`

### Prompt file
Source: `src/prompts/it_ai_skills.txt`

```text
Your task is to derive two complementary skill sections from the candidate's CV + job posting using semantic, evidence-driven inference.

Evidence policy (strict):
- Candidate CV content in input is the only evidence of possessed capabilities.
- Infer skills from concrete CV evidence: actions performed, outcomes delivered, tools/methods used, scope/ownership, and repeated practice.
- Do not treat the job posting as evidence of possession.

Role of the job posting:
- Use the job posting only as a ranking/alignment signal to prioritize which CV-evidenced skills should appear first.
- If a requested job skill is not evidenced in CV, do not claim it as possessed.

Anti-parroting:
- Do not mirror exact job-posting phrases unless there is clear CV evidence for that capability.
- Prefer paraphrased, evidence-grounded labels over copied keyword strings.

Canonicalization and normalization:
- Normalize skill names to concise ATS-friendly canonical labels.
- Merge synonyms/near-duplicates into one label (e.g., "Continuous Improvement" + "Kaizen mindset" -> "KAIZEN / Continuous Improvement").
- Avoid redundant variants across or within sections.

Prioritization logic:
- Rank candidate skills by: (1) evidence strength, (2) recency, (3) relevance to job context.
- Evidence strength is higher when CV shows repeated use, measurable outcomes, leadership/ownership, or delivery impact.

Ambiguity handling:
- If evidence is weak or indirect, prefer broader capability wording over specific tool claims.
- Example: use "Cloud Platforms" instead of naming a specific cloud service unless explicitly evidenced.

Section definitions:
1) IT & AI Skills:
- Digital tools, automation, data systems, cloud, programming, AI/GPT usage, dashboards, analytics, technical frameworks.

2) Technical & Operational Skills:
- Quality systems (e.g., IATF, VDA, Formel-Q), process improvement (KAIZEN, VSM, CI), manufacturing/production operations, problem-solving methods (FMEA, 5 Whys, PDCA), efficiency/changeover/downtime optimization, governance, CAPEX/OPEX delivery.

Language:
- Write all output text in {target_language}.
- Do not mix languages.

Hard rules:
- Keep JSON keys exactly: it_ai_skills, technical_operational_skills, notes.
- Max 5-8 skills per section.
- No duplication across sections.
- Include only CV-evidenced capabilities; never invent.
- Skills should be short, canonical ATS labels.

Output JSON schema:
{
  "it_ai_skills": ["skill1", "skill2", "..."],
  "technical_operational_skills": ["skill1", "skill2", "..."],
  "notes": "Brief evidence-based summary of categorization and ranking logic, including job-alignment rationale without claiming non-evidenced skills (max 500 chars)"
}

Return format:
- Return only a strict JSON object.
- No markdown, no code fences, no extra commentary.
```

### Runtime input sent (`user_text`)
Source assembly: `SKILLS_TAILOR_RUN`.

```text
[JOB_SUMMARY]
<format_job_reference_for_display(meta.job_reference)>

[TAILORING_SUGGESTIONS]
<meta.work_tailoring_notes>

[TAILORING_FEEDBACK]
<meta.work_tailoring_feedback>

[WORK_TAILORING_PROPOSAL_NOTES]
<meta.work_experience_proposal_block.notes>

[WORK_EXPERIENCE_TAILORED]
<title | company | date>
- <bullet>
...

[RANKING_NOTES]
<meta.skills_ranking_notes>

[CANDIDATE_SKILLS]
- <skill>
- <skill>
...
```

`[CANDIDATE_SKILLS]` is built from merged sources:
- `cv_data.it_ai_skills`
- `cv_data.technical_operational_skills`
- `meta.docx_prefill_unconfirmed.(it_ai_skills|technical_operational_skills)`
- prior `meta.candidate_skills_input`
- action payload keys: `candidate_skills`, `candidate_skills_text`, `skills_file_text`, `skills_text`
- labeled message block: `[CANDIDATE_SKILLS] ...`

---

## Stage: `interests`

### Prompt file
Source: `src/prompts/interests.txt`

```text
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

### Runtime input sent (`user_text`)
Source assembly: `INTERESTS_TAILOR_RUN`.

`user_text` is `json.dumps(ctx, ensure_ascii=False)` where `ctx` is:

```json
{
  "current_interests": "<cv_data.interests>",
  "job_summary": "<format_job_reference_for_display(meta.job_reference)>",
  "job_text_excerpt": "<meta.job_posting_text first 1200 chars>"
}
```

Extra runtime suffix is appended to system prompt for this stage:

```text
You may reorder or select a subset of the provided interests to best fit the job, but you MUST NOT invent new interests.
Return JSON only.
```

---

## Stage: `cover_letter`

### Prompt file
Source: `src/prompts/cover_letter.txt`

```text
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
Job posting terminology may be referenced ONLY as the employer’s domain or project context,
not as the candidate’s direct experience.

Allowed:
- Referencing the company’s domain, industry, or project focus.
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

### Runtime input sent (`user_text`)
Source assembly: `_generate_cover_letter_block_via_openai(...)`.

```text
[JOB_REFERENCE]
<format_job_reference_for_display(meta.job_reference)>

[STYLE_PROFILE]
<inferred style profile from cv_data>

[WORK_EXPERIENCE]
<title | company | date>
- <bullet>
...

[SKILLS]
- <it_ai_skill>
- <technical_operational_skill>
...
```

Behavior note:
- If `job_reference` is missing and `job_posting_text` length >= 80, system first calls stage `job_posting` to derive compact `job_reference` before generating cover letter.
