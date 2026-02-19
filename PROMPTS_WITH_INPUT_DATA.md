# CV Generator - All Prompts with Input Data

**Date:** 2026-02-13  
**Purpose:** Complete reference of all LLM prompts with input data structures for each stage

---

## Base System Prompt (All Stages)

```
You are a professional CV/resume assistant. Your output must be valid JSON only.
Never return markdown code fences, prose, or explanations.
Follow the exact schema provided.
```

---

## Stage 1: Job Posting Extraction

### Prompt File
`src/prompts/job_posting.txt`

### System Prompt
```
Extract a compact, ATS-oriented job reference (1-2 pages summary max) from the provided job posting. 
Preserve key technical and soft skills, domains, certifications, and salary info. Remove unnecessary detail.

Language:
- Use the same language as the job posting; do not translate.

Output JSON: {job_id, company, title, key_skills[], tech_stack[], min_salary, max_salary, highlights[], domain, contract_type}.
```

### Input Structure
```
[RAW_JOB_POSTING_TEXT]
<paste of job posting HTML or text>
```

### Example Input
```
Lonza
Operational Excellence Manager - Vibe-X (Microbial/Bioconjugates)
Posted Jan 30, 2026
Job ID: R73184

Today, Lonza is a global leader in life sciences operating across five continents...

What you'll do:
- Lead and deliver high-priority, complex performance improvement projects
- Drive the implementation of LBMS standards and tools
- Coordinate and support maturity assessments
...

What we're looking for:
- Proven hands-on experience in cycle time, changeover, and downtime reduction
- Strong background in Operational Excellence
- Bachelor's degree required; Master's preferred
...
```

### Expected Output Schema
```json
{
  "role_title": "string",
  "company": "string",
  "location": "string",
  "seniority": "string",
  "employment_type": "string",
  "responsibilities": ["string", "string", ...],
  "must_haves": ["string", "string", ...],
  "nice_to_haves": ["string", "string", ...],
  "tools_tech": ["string", "string", ...],
  "keywords": ["string", "string", ...]
}
```

---

## Stage 2: Work Experience Tailoring

### Prompt File
`src/prompts/work_experience.txt`

### System Prompt
```
This is a semantic tailoring task. You are given:
1) Candidate CV (raw work history, skills, education)
2) Job posting (target role, key skills, domain, company, seniority)

Your job: rewrite the candidate's work experience bullets for ATS + human readability, 
emphasizing alignment with the target job.

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

### Input Structure
```
[JOB_SUMMARY]
<formatted job reference from Stage 1>

[CANDIDATE_PROFILE]
<CV profile/summary paragraph>

[TAILORING_SUGGESTIONS]
<optional user notes for tailoring>

[TAILORING_FEEDBACK]
<optional user feedback from previous iteration>

[CURRENT_WORK_EXPERIENCE]
<formatted current work experience>

Role 1 | Company Name | 2020-01 - 2025-10
- Bullet point 1
- Bullet point 2
...

Role 2 | Company Name | 2018-11 - 2020-01
- Bullet point 1
- Bullet point 2
...
```

### Example Input
```
[JOB_SUMMARY]
Operational Excellence Manager - Vibe-X at Lonza
Responsibilities: Lead performance improvement projects, drive LBMS standards, coordinate maturity assessments
Must-haves: Cycle time reduction, changeover/downtime reduction, Operational Excellence background, Lean Six Sigma
Keywords: KAIZEN, VSM, Standard Work, value chain diagnostics, continuous improvement

[CANDIDATE_PROFILE]
Project and Operations Manager with over 10 years of experience in quality systems, 
technical process improvements, and infrastructure projects. Proven leadership of 
interdisciplinary teams, establishment of greenfield sites, and delivery of complex projects.

[TAILORING_SUGGESTIONS]
Emphasize KAIZEN and process improvement experience from Sumitomo role. 
Highlight greenfield plant setup in Moldova showing scalability.

[TAILORING_FEEDBACK]
<empty>

[CURRENT_WORK_EXPERIENCE]
Director | GL Solutions Sp. Z o.o. | 2020-01 – 2025-10
- Planning and coordination of road construction and infrastructure projects
- Supervision of construction sites, subcontractors and compliance with legal regulations
- Creation of schedules, budgets and final documentation
- Operational management of public and private contracts

Head of Quality & Product Service | Expondo Polska Sp. z o.o. | 2018-11 – 2020-01
- Management of 3 departments with a total of 35 employees
- Ensuring CE conformity, introduction of KPI dashboards and process improvements
- Complaint management, product and process optimization
- Standardization and improvement of internal processes

Quality Manager | SE Bordnetze SRL | 2016-08 – 2018-11
- Management of a department with 5 sections and 80 employees
- Setup of a greenfield plant, introduction of processes and quality systems
- Implementation of VDA, Formel-Q and IATF standards
- Contact person for OEM customers and certification bodies

Global Process Improvement Specialist | Sumitomo Electric Bordnetze SE | 2011-03 – 2016-07
- Optimization of workplaces and processes, conducting time studies
- Cost reduction through efficient production solutions
- Main auditor (PK) – Coordination of global audits, benchmarking, customer requirement adaptation
```

### Expected Output Schema
```json
{
  "roles": [
    {
      "title": "Director",
      "company": "GL Solutions Sp. Z o.o.",
      "date_range": "2020-01 – 2025-10",
      "location": "Zielona Góra, Poland",
      "bullets": [
        "Built construction company from scratch delivering 30-40k EUR projects, achieving commercial viability and repeatable project delivery.",
        "Streamlined site operations and subcontractor workflows, cutting on-site process steps and improving project throughput by measurable lead-time reductions.",
        "Optimized scheduling and budgeting controls to reduce rework and delays, improving on-time delivery rate for public and private contracts."
      ]
    },
    {
      "title": "Head of Quality & Product Service",
      "company": "Expondo Polska Sp. z o.o.",
      "date_range": "2018-11 – 2020-01",
      "location": "Zielona Góra, Poland",
      "bullets": [
        "Led three departments (35 people) and introduced KPI dashboards and standard work, improving visibility and process compliance across quality functions.",
        "Resolved a 3-year product quality issue, reducing customer claims by 70% through root-cause fixes and supplier quality controls.",
        "Reorganized warehouse workflows and locations, halving the number of handling steps and eliminating legacy backlog within three months."
      ]
    }
  ],
  "notes": "Emphasized measurable cycle-time and cost reductions to align with Operational Excellence Manager role at Vibe-X"
}
```

---

## Stage 3: Skills Ranking (Unified IT/AI + Technical/Operational)

### Prompt File
`src/prompts/it_ai_skills.txt`

### System Prompt
```
Your task is to derive two complementary skill sections from the candidate's CV + job posting:

1. **IT & AI Skills** – Digital tools, automation, data-driven systems, cloud platforms, 
   programming languages, AI/GPT integration, reporting dashboards, technical frameworks.

2. **Technical & Operational Skills** – Quality systems (IATF, VDA, Formel-Q), 
   process improvement (KAIZEN, VSM, continuous improvement), production/manufacturing experience, 
   team leadership, problem-solving methodologies (FMEA, 5 Whys, PDCA), efficiency optimization, 
   changeover & downtime reduction, operational governance, CAPEX/OPEX project management.

**Job Context Alignment:**
- Prioritize skills matching the **job posting keywords** (e.g., if the role emphasizes 
  "Operational Excellence", "cycle time reduction", or "KAIZEN", surface those capabilities prominently).
- For roles in **production plants, manufacturing, or quality management**, emphasize hands-on 
  operational expertise: shop-floor improvement, standard work, value chain diagnostics, and 
  measurable results (e.g., "reduced changeover time by X%").
- For **technical leadership roles**, balance digital/automation skills (cloud, data pipelines, 
  AI tools) with operational delivery and team coordination.

**Language:**
- Write all output text in {target_language}.
- Do not mix languages.

**Rules:**
- **Max 5-8 skills per section** (aim for the most relevant and impactful).
- List only skills **grounded in CV experience** – not aspirational or generic.
- Use **short, ATS-friendly names**: Python, Azure, IATF, KAIZEN, VSM, Process Optimization, 
  Quality Assurance, Standard Work, etc.
- **No duplication across sections**: If "IATF" is in Technical & Operational, do not repeat it in IT & AI.
- Prefer **measurable, contextual terms** over vague labels (e.g., "Cycle time reduction" instead of just "Lean").

**Operational Excellence Keywords (when relevant to job):**
- Efficiency, Process Optimization, Quality Assurance, KAIZEN, Continuous Improvement, 
  Team Leadership, Problem-Solving, Manufacturing, Standard Work, Shop-Floor Standardization, 
  Value Chain Diagnostics, Changeover Reduction, Downtime Reduction, CAPEX/OPEX Management, 
  Production Planning.

**Output JSON:**
{
  "it_ai_skills": ["skill1", "skill2", ...],
  "technical_operational_skills": ["skill1", "skill2", ...],
  "notes": "Brief explanation of categorization logic or alignment with job posting (max 500 chars)"
}

**Important:**
- Only return the JSON object; no markdown fences or additional commentary.
- Ensure all skills come from the [CANDIDATE_SKILLS] input – never invent skills not present in the CV.
- The notes field should explain your reasoning (e.g., "Emphasized KAIZEN and cycle-time reduction 
  to match Operational Excellence role at Vibe-X").
```

### Input Structure
```
[JOB_SUMMARY]
<formatted job reference>

[CANDIDATE_PROFILE]
<CV profile paragraph>

[TAILORING_SUGGESTIONS]
<optional user notes>

[TAILORING_FEEDBACK]
<optional feedback from previous iteration>

[WORK_TAILORING_PROPOSAL_NOTES]
<notes from work experience tailoring>

[WORK_EXPERIENCE_TAILORED]
<tailored work experience bullets>

[RANKING_NOTES]
<optional user notes for skills ranking>

[CANDIDATE_SKILLS]
<deduplicated list of all skills from CV>
- Python
- Azure
- IATF
- KAIZEN
- SPC
- Quality systems
...
```

### Example Input
```
[JOB_SUMMARY]
Operational Excellence Manager - Vibe-X at Lonza
Keywords: KAIZEN, VSM, Standard Work, cycle time reduction, changeover reduction, 
value chain diagnostics, continuous improvement, Lean Six Sigma

[CANDIDATE_PROFILE]
Project and Operations Manager with over 10 years of experience in quality systems, 
technical process improvements, and infrastructure projects.

[TAILORING_SUGGESTIONS]
Focus on international experience and automation skills

[TAILORING_FEEDBACK]
<empty>

[WORK_TAILORING_PROPOSAL_NOTES]
Emphasized measurable cycle-time and cost reductions

[WORK_EXPERIENCE_TAILORED]
Director | GL Solutions | 2020-01 – 2025-10
- Built construction company from scratch delivering 30-40k EUR projects
- Streamlined site operations cutting on-site process steps

Head of Quality & Product Service | Expondo Polska | 2018-11 – 2020-01
- Led three departments (35 people) introducing KPI dashboards and standard work
- Resolved 3-year quality issue, reducing customer claims by 70%

Quality Manager | SE Bordnetze SRL | 2016-08 – 2018-11
- Established greenfield plant and quality systems for 80 employees
- Implemented VDA, Formel-Q and IATF standards, achieved IATF compliance on first audit

Global Process Improvement Specialist | Sumitomo Electric | 2011-03 – 2016-07
- Led shop-floor standardization and KAIZEN programs driving cycle-time reductions
- Conducted value chain diagnostics and benchmarking as lead auditor

[RANKING_NOTES]
<empty>

[CANDIDATE_SKILLS]
- Azure Functions
- Azure Blob Storage
- GitHub
- OpenAI / GPT integration
- Deterministic tool orchestration
- OAuth integration
- Automated PDF generation
- KPI dashboards / reporting
- Operational Excellence
- Process Improvement (Kaizen, VSM)
- Quality Systems (IATF, VDA, Formel-Q)
- Standard Work & SOPs
- Value Chain Diagnostics
- Changeover & Downtime Reduction
- Root Cause Analysis (FMEA, 5 Whys, PDCA)
- CAPEX/OPEX Project Management
```

### Expected Output Schema
```json
{
  "it_ai_skills": [
    "Azure Functions",
    "Azure Blob Storage",
    "GitHub",
    "OpenAI / GPT integration",
    "Automated PDF generation",
    "KPI dashboards / reporting"
  ],
  "technical_operational_skills": [
    "Operational Excellence",
    "Process Improvement (Kaizen, VSM)",
    "Quality Systems (IATF, VDA, Formel-Q)",
    "Standard Work & SOPs",
    "Value Chain Diagnostics",
    "Changeover & Downtime Reduction",
    "Root Cause Analysis (FMEA, 5 Whys, PDCA)",
    "CAPEX/OPEX Project Management"
  ],
  "notes": "Combined technical cloud/automation capabilities with strong operational skills (quality systems, Kaizen, process improvement) to support OE initiatives and AI-enabled productivity tools. Emphasized KAIZEN and cycle-time reduction to match Operational Excellence role at Vibe-X."
}
```

---

## Stage 4: Further Experience (Optional)

### Prompt File
`src/prompts/further_experience.txt`

### System Prompt
```
Given a candidate's full CV and target job posting, summarize any "further experience" sections 
(side projects, voluntary roles, pro bono, academic research, consulting) that add credibility 
to the job application.

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

### Input Structure
```
[JOB_SUMMARY]
<formatted job reference>

[CANDIDATE_PROFILE]
<CV profile>

[CURRENT_FURTHER_EXPERIENCE]
<existing further experience entries from CV>

[TAILORING_NOTES]
<optional user notes>
```

### Example Input
```
[JOB_SUMMARY]
Operational Excellence Manager - Vibe-X at Lonza

[CANDIDATE_PROFILE]
Project and Operations Manager with over 10 years of experience...

[CURRENT_FURTHER_EXPERIENCE]
Formel Q Requirements – TQM Slovakia (05/2018)
Core Tools (APQP, FMEA, MSA, SPC, PPAP) – RQM Certification s.r.l. (04/2018)
Internal Auditor for IATF – RQM Certification s.r.l. (12/2017)
IATF for Managers – RQM Certification s.r.l. (11/2017)

[TAILORING_NOTES]
<empty>
```

### Expected Output Schema
```json
{
  "further_experience_items": [
    {
      "role": "Certified Internal Auditor",
      "project_name": "IATF 16949",
      "period": "2017-2018",
      "one_liner": "Completed IATF certification and Core Tools training (FMEA, SPC, PPAP) supporting quality system implementation"
    }
  ]
}
```

---

## Stage 5: Cover Letter Generation

### Prompt File
`src/prompts/cover_letter.txt`

### System Prompt
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

Output JSON:
{
  "opening_paragraph": "string (2-4 sentences)",
  "core_paragraphs": ["paragraph1", "paragraph2"],
  "closing_paragraph": "string (2-3 sentences)",
  "signoff": "string (e.g., 'Mit freundlichen Grüßen' or 'Best regards')"
}
```

### Input Structure
```
[JOB_POSTING]
<full job posting text>

[CANDIDATE_CV]
<complete CV data including profile, work experience, education, skills>

[MOTIVATION]
<optional user-provided motivation text>
```

### Example Input
```
[JOB_POSTING]
Lonza - Operational Excellence Manager - Vibe-X
Lead performance improvement projects in growth project Vibe-X combining 
Microbial and Bioconjugation technology...

[CANDIDATE_CV]
Full Name: Mariusz Horodecki
Profile: Project and Operations Manager with over 10 years of experience...
Work Experience: [tailored bullets from Stage 2]
Skills: [ranked skills from Stage 3]
Education: Master of Science in Electrical Engineering

[MOTIVATION]
<empty>
```

### Expected Output Schema
```json
{
  "opening_paragraph": "I am writing to express my interest in the Operational Excellence Manager position at Lonza for the Vibe-X project in Visp. With over 10 years of experience in quality systems and process improvement across international manufacturing environments, I have consistently delivered measurable operational improvements.",
  "core_paragraphs": [
    "In my role as Global Process Improvement Specialist at Sumitomo Electric Bordnetze SE, I led shop-floor standardization and KAIZEN programs across multiple sites, driving cycle-time and cost reductions through time studies and process redesign. I conducted value chain diagnostics and benchmarking as lead auditor, aligning global audits and adapting best practices to customer requirements.",
    "As Quality Manager at SE Bordnetze SRL, I established a greenfield plant and quality systems for 5 sections and 80 employees, enabling production readiness and scalable operations. I implemented VDA, Formel-Q and IATF standards and achieved IATF compliance on first audit through structured standard work and training."
  ],
  "closing_paragraph": "I am confident that my proven track record in operational excellence, combined with my hands-on experience in KAIZEN implementation and quality system management, would enable me to contribute effectively to the Vibe-X project. I look forward to the opportunity to discuss how my experience aligns with Lonza's objectives.",
  "signoff": "Best regards"
}
```

---

## Stage 6: Bulk Translation

### Prompt File
`src/prompts/bulk_translation.txt`

### System Prompt
```
Translate a bulk set of work history, skills, interests, or education entries from 
the source language to professional {target_language}. Preserve technical terms, 
company names, and dates; modernize phrasing. Keep output text in {target_language} only.
```

### Input Structure
```
[SOURCE_LANGUAGE]
<detected or specified source language>

[TARGET_LANGUAGE]
{target_language}

[CONTENT_TO_TRANSLATE]
<JSON structure with work_experience, education, languages, skills, etc.>
```

### Example Input
```
[SOURCE_LANGUAGE]
German

[TARGET_LANGUAGE]
English

[CONTENT_TO_TRANSLATE]
{
  "work_experience": [
    {
      "title": "Direktor",
      "employer": "GL Solutions Sp. Z o.o.",
      "date_range": "2020-01 – 2025-10",
      "bullets": [
        "Planung und Koordination von Strassenbau- und Infrastrukturprojekten",
        "Überwachung von Baustellen, Subunternehmern und Einhaltung gesetzlicher Vorschriften"
      ]
    }
  ],
  "languages": [
    "Polnisch (Muttersprache)",
    "Englisch (fliessend)",
    "Deutsch (mittelstufe)"
  ]
}
```

### Expected Output Schema
```json
{
  "work_experience": [
    {
      "title": "Director",
      "employer": "GL Solutions Sp. Z o.o.",
      "date_range": "2020-01 – 2025-10",
      "bullets": [
        "Planning and coordination of road construction and infrastructure projects",
        "Supervision of construction sites, subcontractors and compliance with legal regulations"
      ]
    }
  ],
  "languages": [
    "Polish (native)",
    "English (fluent)",
    "German (intermediate)"
  ]
}
```

---

## Common Input Data Sanitization Rules

All user inputs are sanitized before being passed to the LLM:

```python
def _sanitize_for_prompt(text: str) -> str:
    """Remove control characters and normalize whitespace"""
    # Remove null bytes, control characters
    # Collapse multiple spaces/newlines
    # Limit maximum length (usually 2000-5000 chars depending on field)
    return sanitized_text

def _escape_user_input_for_prompt(text: str) -> str:
    """Escape user input to prevent prompt injection"""
    # Additional escaping for user-provided notes/feedback
    return escaped_text
```

---

## Response Format Enforcement

All stages use structured JSON output with strict schema validation:

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "stage_name",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": { ... },
            "required": [ ... ],
            "additionalProperties": False
        }
    }
}
```

This ensures:
- No markdown code fences
- No prose or explanations
- Strict adherence to expected schema
- Deterministic parsing and validation

---

## Error Handling & Retry Logic

For critical stages (work experience, skills), the system implements:

1. **Schema validation** - Verify JSON structure
2. **Hard limit checks** - Ensure bullets respect character limits (200 chars for EN, 250 for DE)
3. **Auto-retry** - Up to 3 attempts with feedback if limits violated
4. **Fallback** - If all retries fail, return error to user with actionable feedback

Example:
```
Attempt 1: Model returns bullets > 200 chars
→ Retry with feedback: "Bullets exceed 200 char limit. Shorten to <= 180 chars."

Attempt 2: Still too long
→ Retry with feedback: "Bullets still too long. Use single-line format, remove filler words."

Attempt 3: Success or final failure
→ Return result or error message to user
```

---

## Session State & Caching

To optimize performance and costs:

- **Job reference** cached by `job_sig` (SHA256 of job posting text)
- **Work experience proposal** cached by `job_sig` + `base_cv_sig`
- **Skills proposal** cached by `job_sig` + `base_sig`

Cached responses bypass LLM calls when:
1. Session exists
2. Job posting unchanged
3. Base CV data unchanged
4. No user feedback requesting regeneration

---

## Observability & Debugging

Every LLM call includes:
- `trace_id` - Unique identifier for debugging
- `session_id` - Links to session storage
- `stage` - Current workflow stage
- `openai_response_id` - OpenAI API response ID

Logged metadata:
```json
{
  "trace_id": "uuid",
  "session_id": "uuid",
  "stage": "work_experience",
  "model_calls": 1,
  "total_tokens": 1234,
  "openai_response_id": "resp_abc123...",
  "created_at": "2026-02-11T22:04:17.112110"
}
```

This enables:
- End-to-end tracing of requests
- Cost analysis per stage
- Debugging prompt/response pairs
- Session replay for testing

---

**End of Document**
