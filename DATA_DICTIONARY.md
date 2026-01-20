# CV Generator - Data Dictionary

**Purpose:** Single source of truth for all CV data fields, constraints, validation rules, and mappings.

**Format:** Each field documented with type, constraints, validation, examples, and usage across the system.

---

## Quick Reference: Field Categories

| Category | Fields | Status |
|----------|--------|--------|
| Personal | full_name, email, phone, address_lines, nationality | Required |
| Profile | profile, target_role | Recommended |
| Experience | work_experience, further_experience | Required (≥1) |
| Education | education | Required (≥1) |
| Skills & Languages | languages, it_ai_skills | Recommended |
| Certifications | certifications, trainings | Optional |
| Other | interests, publications, references, data_privacy, photo_url | Optional |

---

## Field Definitions

### Personal Information

#### full_name
- **Type:** `string`
- **Required:** YES
- **Constraints:**
  - Min length: 1 char
  - Max length: 50 chars (enforced by validator)
  - Cannot be empty or whitespace-only
- **Format:** "First Last" or full legal name
- **Example:** "Mariusz Horodecki"
- **Validation:** Non-empty string, normalized (trim whitespace), ≤50 chars
- **Used in:** Header, PDF metadata
- **Schema mappings:** 
  - Incoming: `name` → normalized to `full_name`
  - OpenAI: `full_name`
  - Template: `{{ full_name }}`

#### email
- **Type:** `string` (email format)
- **Required:** YES
- **Constraints:**
  - Valid email format (user@domain.ext)
  - Max length: 100 chars
- **Example:** "horodecki.mariusz@gmail.com"
- **Validation:** RFC 5322 compliant email
- **Used in:** Contact header, hyperlink in PDF
- **Notes:** Must be clickable mailto: link in template

#### phone
- **Type:** `string`
- **Required:** YES
- **Constraints:**
  - Min length: 5 chars (e.g. "12345")
  - Max length: 30 chars
  - International format preferred (+41 77 952 24 37)
- **Example:** "+41 77 952 24 37"
- **Validation:** Non-empty, basic length check
- **Used in:** Contact header

#### address_lines
- **Type:** `array[string]`
- **Required:** YES
- **Constraints:**
  - Array of 1-2 lines (enforced by validator)
  - Each line: max 60 chars
  - Total combined: max 120 chars
- **Example:** `["Zer Chirchu 20", "Switzerland"]`
- **Format:** One address component per line
- **Rendered in template as:** `{{ address_lines|join(", ") }}`
- **Validation:** Non-empty array, each string ≤60 chars, max 2 items

#### nationality
- **Type:** `string`
- **Required:** NO (optional)
- **Constraints:**
  - Max length: 50 chars
  - Usually single country name
- **Example:** "Polish"
- **Used in:** Contact info block

#### birth_date
- **Type:** `string` (ISO format or readable)
- **Required:** NO (optional)
- **Format:** "DD.MM.YYYY" or "YYYY-MM-DD"
- **Example:** "15.06.1985"
- **Validation:** Valid date format
- **Used in:** Contact info (if provided)

---

### Profile & Target

#### profile
- **Type:** `string`
- **Required:** YES (for Stage 2 confirmation)
- **Constraints:**
  - Min length: 50 chars
  - Max length: 400 chars
  - Active voice preferred
- **Example:** "Project manager with 10+ years in quality systems, process improvement, and industrialization. Proven leadership of interdisciplinary teams..."
- **Validation:**
  - Length check (50-400 chars)
  - Non-empty
- **Used in:** CV summary section (page 1)
- **Rendering:** Plain text, no formatting

#### target_role
- **Type:** `string`
- **Required:** NO (metadata only)
- **Constraints:**
  - Max length: 200 chars
- **Example:** "Product & Process Engineer — Dietrich engineering consultants S.A."
- **Used in:** Internal tracking, job fit analysis
- **Notes:** Not rendered in PDF, used for context only

---

### Work Experience

#### work_experience
- **Type:** `array[WorkExperienceEntry]`
- **Required:** YES
- **Constraints:**
  - Min items: 1
  - Max items: 5
  - Items ordered by recency (newest first)
- **Validation:**
  - Must have at least 1 job
  - Each job must have: date_range, employer, title, bullets (required)
  - Total height must fit in ~1.5 pages
- **Rendering:** Page 1 (Work Experience section)

##### WorkExperienceEntry

| Field | Type | Required | Constraints | Example |
|-------|------|----------|-------------|---------|
| date_range | string | YES | Format: "MM/YYYY – MM/YYYY" or "MM/YYYY – Present" | "2020-01 – 2025-04" |
| employer | string | YES | Max 100 chars | "GL Solutions" |
| location | string | NO | Max 80 chars | "Switzerland" |
| title | string | YES | Max 60 chars | "Director" |
| bullets | array[string] | YES | Min 1, Max 4 bullets; each ≤90 chars | `["Managed projects", "Led teams"]` |

**Validation Rules:**
- date_range: Must be valid date format
- employer: Non-empty, ≤100 chars
- location: Optional, ≤80 chars
- title: Non-empty, ≤60 chars
- bullets: 1-4 items, each ≤90 chars (active voice, quantified where possible)

**Normalizations:**
- GPT schema (company/position/description) → template schema (employer/title/bullets)
- start_date + end_date → date_range

**Example:**
```json
{
  "date_range": "2020-01 – 2025-04",
  "employer": "GL Solutions",
  "location": "Switzerland",
  "title": "Director",
  "bullets": [
    "Planned and coordinated infrastructure projects (CAPEX/OPEX)",
    "Managed budgets, schedules, and regulatory compliance",
    "Implemented planning tools to optimize execution"
  ]
}
```

#### further_experience
- **Type:** `array[FurtherExperienceEntry]`
- **Required:** NO (optional, can be empty)
- **Constraints:**
  - Max items: 3
- **Rendering:** Page 2 (Further Experience section)

##### FurtherExperienceEntry

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| date_range | string | NO | Format: "YYYY" or "YYYY – YYYY" |
| organization | string | YES | Max 100 chars |
| title | string | YES | Max 60 chars (role/activity) |
| bullets | array[string] | NO | 0-3 bullets, each ≤90 chars |

---

### Education

#### education
- **Type:** `array[EducationEntry]`
- **Required:** YES
- **Constraints:**
  - Min items: 1
  - Max items: 3
  - Ordered by recency (most recent first)
- **Rendering:** Page 1 (Education section, if space allows)

##### EducationEntry

| Field | Type | Required | Constraints | Example |
|-------|------|----------|-------------|---------|
| date_range | string | YES | Format: "YYYY – YYYY" | "2012 – 2015" |
| institution | string | YES | Max 100 chars | "Poznań University of Technology" |
| title | string | YES | Max 100 chars (degree + field) | "Master of Science in Electrical Engineering" |
| details | array[string] | NO | 0-2 items, each ≤80 chars | `["Focus: Industrial systems"]` |

**Example:**
```json
{
  "date_range": "2012 – 2015",
  "institution": "Poznań University of Technology",
  "title": "Master of Science in Electrical Engineering",
  "details": ["Focus: Industrial and automotive systems"]
}
```

---

### Skills & Languages

#### languages
- **Type:** `array[Language]` OR `array[string]`
- **Required:** YES
- **Constraints:**
  - Min items: 1
  - Max items: 5
- **Rendering:** Page 2 (Languages section)

##### Language (Flexible Schema)

**Option A: Object format**
```json
{
  "language": "English",
  "level": "Fluent"
}
```

**Option B: String format**
```json
"English (Fluent)"
```

**Accepted Level Values:**
- Native
- Fluent / C2 / Advanced
- Intermediate / B1-B2
- Basic / A1-A2

#### it_ai_skills
- **Type:** `array[string]`
- **Required:** NO (optional)
- **Constraints:**
  - Max items: 10
  - Each item: max 50 chars
- **Example:** `["Python", "Azure Functions", "Git"]`
- **Rendering:** Page 2 (if section exists in template)

---

### Certifications & Training

#### certifications
- **Type:** `array[string]` OR `array[CertificationEntry]`
- **Required:** NO (optional)
- **Constraints:**
  - Max items: 10
  - Each item: max 100 chars
- **Example:** `["IATF Internal Auditor", "Six Sigma Green Belt"]`

#### trainings
- **Type:** `array[TrainingEntry]`
- **Required:** NO (optional)
- **Constraints:**
  - Max items: 10

##### TrainingEntry

| Field | Type | Required |
|-------|------|----------|
| date | string | NO (e.g. "05/2018") |
| title | string | YES |
| provider | string | NO |

**Example:**
```json
{
  "date": "05/2018",
  "title": "Formel-Q Requirements",
  "provider": "TQM Slovakia"
}
```

---

### Other Fields

#### interests
- **Type:** `string` OR `array[string]`
- **Required:** NO (optional)
- **Constraints:**
  - If string: max 300 chars
  - If array: max 5 items, each ≤50 chars
  - Normalized to single string in template
- **Example:** "Systems thinking, process automation, cycling, applied AI"
- **Rendering:** Page 2 (if template includes it)

#### publications
- **Type:** `array[string]`
- **Required:** NO (optional)
- **Constraints:**
  - Max items: 5
  - Each: max 150 chars
- **Example:** `["Published: 'Lean Manufacturing Guide' (2020)"]`

#### references
- **Type:** `array[string]`
- **Required:** NO (optional)
- **Constraints:**
  - Max items: 3
  - Each: max 200 chars
- **Example:** `["Dr. Jane Smith (former manager) - jane@acme.com"]`

#### data_privacy
- **Type:** `string`
- **Required:** NO (optional)
- **Constraints:**
  - Max 300 chars
- **Example:** "I consent to the processing of my personal data for the purpose of the application procedure."
- **Rendering:** Small print at end of CV

#### photo_url
- **Type:** `string` (data URI or URL)
- **Required:** NO (optional)
- **Format:** Base64 data URI (e.g. `data:image/jpeg;base64,/9j/...`)
- **Constraints:**
  - Size: max 500KB
  - Format: JPEG or PNG
- **Rendering:** Top right corner of CV header
- **Source:** Extracted from DOCX via `extract_photo` tool

---

## Validation Rules by Section

### Page 1 (First Page) Target Height: ~270mm
- Header (name, contact): ~60mm
- Profile: ~40mm (50-400 chars → ~40mm)
- Education: ~60mm (max 4 entries)
- Work Experience: ~100mm (max 5 entries)
- Languages: ~20mm
- Skills: ~20mm
- Margins + spacing: ~40mm

### Page 2 (Second Page) Target Height: ~270mm
- Further Experience: ~100mm
- Certifications: ~50mm
- Trainings: ~50mm
- Interests: ~20mm
- Other sections: ~50mm

**DoD (Definition of Done):** PDF must be exactly 2 pages (enforced by PyPDF2 page count).

---

## Schema Mappings: GPT → Template → Database

### GPT Schema (Input from OpenAI)
```python
{
  "company": "Acme Corp",
  "position": "Engineer",
  "start_date": "2020-01",
  "end_date": "2024-12",
  "description": ["Worked on projects", "Led team"]
}
```

### Template Schema (Canonical)
```python
{
  "employer": "Acme Corp",
  "title": "Engineer",
  "date_range": "2020-01 – 2024-12",
  "bullets": ["Worked on projects", "Led team"]
}
```

### Normalization Logic (normalize.py)
- `company` → `employer`
- `position` → `title`
- `start_date` + `end_date` → `date_range` (format: "MM/YYYY – MM/YYYY")
- `description` → `bullets` (preserve list, ensure ≤90 chars per bullet)

---

## Constraints Summary

| Constraint | Value | Rationale |
|-----------|-------|-----------|
| Full name length | 1-50 chars | Header space limit |
| Email length | max 100 chars | Realistic max email |
| Address lines | 1-2 lines, ≤60 chars each | Compact formatting |
| Profile length | 50-400 chars | Brief summary |
| Bullet length (work) | max 90 chars | Line wrapping on CV |
| Bullet length (further) | max 80 chars | Line wrapping on CV |
| Work experience entries | 1-5 | 2-page constraint |
| Education entries | 1-3 | Space limit |
| Further experience entries | 1-4 | Page 2 space |
| Bullets per job | 1-4 | Space limit (~30mm per job) |
| Bullets per further entry | 0-3 | Space limit |
| Languages | 1-5 items | Space limit |
| PDF pages | exactly 2 | Hard DoD requirement |

---

## Validation Errors & Guidance

When validation fails, return structured response:

```json
{
  "error": "Validation failed",
  "validation": {
    "is_valid": false,
    "errors": [
      {
        "field": "work_experience[1].bullets",
        "current_value": 5,
        "limit": 4,
        "excess": 1,
        "message": "Entry 1: 5 bullets exceeds limit of 4",
        "suggestion": "Remove 1 bullet(s) or combine them"
      }
    ]
  }
}
```

---

## Backend Processing Pipeline

1. **Extract** (extract_photo tool)
   - Input: DOCX file
   - Output: photo_url (data URI)

2. **Normalize** (normalize.py)
   - Input: Any CV schema variant
   - Output: Canonical template schema
   - Mappings: GPT → template field names

3. **Validate** (validator.py)
   - Input: Canonical schema
   - Output: Validation result (is_valid, errors[], warnings[])
   - Checks: Constraints, page fit, required fields

4. **Render** (render.py)
   - Input: Canonical schema + photo_url
   - Output: PDF bytes
   - Template: Jinja2 HTML → WeasyPrint → PDF

5. **Return** (function_app.py)
   - Output: JSON with pdf_base64, validation metadata
   - On error: Structured guidance + example_structure

---

## Usage Examples

### Correct Minimal CV
```json
{
  "full_name": "John Doe",
  "email": "john@example.com",
  "phone": "+1 555 0123",
  "address_lines": ["123 Main St", "New York, NY", "USA"],
  "profile": "Software engineer with 5+ years experience in cloud architecture and team leadership.",
  "work_experience": [
    {
      "date_range": "2020-01 – Present",
      "employer": "Tech Corp",
      "title": "Senior Engineer",
      "bullets": ["Led microservices migration", "Reduced latency by 40%"]
    }
  ],
  "education": [
    {
      "date_range": "2016 – 2020",
      "institution": "State University",
      "title": "BS Computer Science",
      "details": []
    }
  ],
  "languages": [
    {"language": "English", "level": "Native"},
    {"language": "Spanish", "level": "Intermediate"}
  ]
}
```

### Common Errors & Fixes

**Error:** `full_name is empty`
- **Fix:** Provide non-empty full_name

**Error:** `work_experience.bullets[0] exceeds 90 chars`
- **Fix:** Shorten bullet to ≤90 chars; split into 2 bullets if needed

**Error:** `DoD violation: pages != 2 (got 3)`
- **Fix:** Reduce content (fewer bullets, shorter profile) or increase page limit with debug_allow_pages=true

---

## Versioning

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-21 | Initial data dictionary |

---

## Related Documents

- [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) - User workflow
- [TOOLS_CONFIG.md](TOOLS_CONFIG.md) - OpenAI tool schemas
- [src/validator.py](src/validator.py) - Validation implementation
- [src/normalize.py](src/normalize.py) - Normalization logic
- [templates/html/cv_template_2pages_2025.html](templates/html/cv_template_2pages_2025.html) - Template rendering
