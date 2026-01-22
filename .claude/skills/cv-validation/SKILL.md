---
name: cv-validation
description: Validate CV data against strict 2-page ATS-compliant schema with comprehensive field checks and size constraints. Use when validating CV JSON before PDF generation, checking field constraints, ensuring 2-page layout compatibility, or verifying ATS compliance. Trigger on: "validate CV", "check CV data", "verify schema", "is this CV valid", or before any PDF generation.
---

# CV Validation Skill

## When to Apply

Trigger this skill when:
- User asks to validate CV JSON
- Before PDF generation (always validate first)
- After manual edits to CV data
- When checking ATS compliance
- User uploads CV and asks "is this valid"
- Debugging layout overflow issues

## Core Validation Workflow

### Step 1: Load Schema Definition
First, understand the complete schema by reading: [references/schema-requirements.md](references/schema-requirements.md)

**Key schema points:**
- Required fields: firstName, lastName, email, phone, address, professionalTitle
- Optional but recommended: photo_url, languages, skills, experience, education
- Size constraints: photo_url ≤32KB, bullets ≤90 chars

### Step 2: Pre-Validation (Fast Local Check)
Before calling API, run deterministic validation script:

```bash
python .claude/skills/cv-validation/scripts/validate_schema.py <cv-json-file>
```

**Script checks:**
- JSON syntax validity
- Required field presence
- Field type correctness (string, array, object)
- Size constraints (photo_url, bullet lengths)
- Character encoding (UTF-8, no invalid chars)

**Output:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": ["photo_url is 28KB, close to 32KB limit"]
}
```

### Step 3: API Validation (Comprehensive)
Call Azure Function for full business rule validation:

```bash
curl -X POST http://localhost:7071/api/validate-cv \
  -H "Content-Type: application/json" \
  -d @<cv-json-file>
```

**API validates:**
- Schema compliance (all pre-validation checks)
- Business rules (e.g., dates in chronological order)
- Language-specific constraints (EN/DE/PL character sets)
- 2-page layout estimation

**Responses:**
- ✅ Valid: `{"valid": true, "message": "CV is valid", "layout_estimate": "1.8 pages"}`
- ❌ Invalid: `{"valid": false, "errors": [{"field": "...", "message": "..."}]}`

### Step 4: Layout Space Estimation
Use script to estimate if content fits 2-page template:

```bash
python .claude/skills/cv-validation/scripts/count_template_space.py <cv-json-file> --language=en
```

**Output:**
```
Estimated pages: 1.9 / 2.0
Margin: 10% (SAFE)

Breakdown:
- Experience section: 1.2 pages
- Education section: 0.3 pages
- Skills section: 0.2 pages
- Languages section: 0.1 pages
- Header/footer: 0.1 pages
```

**Thresholds:**
- ≤1.8 pages: SAFE (plenty of margin)
- 1.8-2.0 pages: WARNING (tight fit, test visually)
- >2.0 pages: ERROR (content overflow, must reduce)

### Step 5: Report Validation Results

**Format (if valid):**
```
✅ CV Validation: PASS

Schema: ✅ All required fields present
Size: ✅ photo_url 28KB / 32KB, longest bullet 87 / 90 chars
Layout: ✅ Estimated 1.9 / 2.0 pages (10% margin)
API: ✅ Business rules satisfied

Ready for PDF generation.

Proceed? (yes/no)
```

**Format (if invalid):**
```
❌ CV Validation: FAIL

Errors (3):
1. [HIGH] experience[0].responsibilities[2]: Bullet exceeds 90 chars (current: 112)
   Current: "Led cross-functional team of 5 engineers to successfully deliver microservices architecture migration completing project 2 weeks ahead of schedule"
   Fix: "Led team of 5 engineers to deliver microservices migration, completing 2 weeks early" (87 chars)

2. [HIGH] photo_url: Size exceeds 32KB limit (current: 45KB)
   Fix: Compress image or reduce resolution (target: <30KB for safety margin)

3. [MEDIUM] experience[0].startDate: Date format invalid (current: "2020-Jan")
   Fix: Use ISO format: "2020-01-01"

Layout: ⚠️ Estimated 2.3 pages (exceeds 2-page limit)

Cannot proceed to PDF generation until errors are fixed.

Edit CV data? (yes/no)
```

## Common Validation Errors

### Required Field Missing
**Error:** `Missing required field 'email'`
**Fix:** Add email to CV JSON
```json
{
  "email": "john.doe@example.com"
}
```

### Photo URL Too Large
**Error:** `photo_url exceeds 32KB limit (current: 45KB)`
**Root cause:** Azure Table Storage property size limit
**Fix:**
1. Compress image with lossless compression
2. Reduce image dimensions (200x200px sufficient)
3. Convert to WebP format (better compression)
4. Store in blob storage and use reference URL instead

**Script to compress:**
```bash
python .claude/skills/cv-validation/scripts/compress_photo.py <image-file> --max-size=30KB
```

### Experience Bullet Too Long
**Error:** `experience[0].responsibilities[1] exceeds 90 chars (current: 112)`
**Root cause:** Template has limited space per bullet
**Fix:**
1. Remove filler words ("successfully", "effectively", "efficiently")
2. Use abbreviations (e.g., "implemented" → "built", "collaborated with" → "worked with")
3. Split into two bullets if genuinely complex
4. Focus on impact, remove process details

**Before:**
```
"Successfully collaborated with cross-functional stakeholders to effectively implement enterprise-wide authentication system serving over 10,000 users across multiple regions"
```

**After:**
```
"Built enterprise auth system for 10K+ users across multiple regions" (68 chars)
```

### Content Overflow (>2 Pages)
**Error:** `Content exceeds 2-page limit (estimated: 2.3 pages)`
**Root cause:** Too much experience, too many skills, or verbose bullets
**Fix:**
1. Limit experience to last 10 years or 5 most relevant roles
2. Reduce bullets per role (max 4-5 per position)
3. Consolidate similar skills
4. Remove outdated skills/certifications
5. Shorten professional summary

**Priority for reduction:**
1. Oldest experience entries (>10 years ago)
2. Less relevant roles (if applying to specific position)
3. Redundant skills (e.g., "JavaScript", "ES6", "React" → "React (JavaScript/ES6)")
4. Long bullets (reduce to 60-70 chars if possible)

### Invalid Date Format
**Error:** `experience[0].startDate: Date format invalid (current: "2020-Jan")`
**Root cause:** Schema requires ISO 8601 format
**Fix:** Use `YYYY-MM-DD` format
```json
{
  "startDate": "2020-01-01",
  "endDate": "2022-12-31"
}
```

**Handling "Present":**
```json
{
  "startDate": "2020-01-01",
  "endDate": null  // or omit field entirely
}
```

## Validation Scripts

### validate_schema.py
**Location:** [scripts/validate_schema.py](scripts/validate_schema.py)
**Purpose:** Fast local JSON schema validation
**Usage:**
```bash
python .claude/skills/cv-validation/scripts/validate_schema.py <cv-json>
python .claude/skills/cv-validation/scripts/validate_schema.py <cv-json> --strict
```

**Returns:** JSON with validation results
**Execution time:** ~50ms (fast pre-check)

### count_template_space.py
**Location:** [scripts/count_template_space.py](scripts/count_template_space.py)
**Purpose:** Estimate if content fits 2-page template
**Usage:**
```bash
python .claude/skills/cv-validation/scripts/count_template_space.py <cv-json> --language=en
```

**Algorithm:**
- Counts characters per section
- Applies language-specific multipliers (German words longer than English)
- Estimates lines based on template CSS
- Accounts for margins, headers, footers

**Returns:** Page estimation with safety margin

### compress_photo.py
**Location:** [scripts/compress_photo.py](scripts/compress_photo.py)
**Purpose:** Compress photo to meet 32KB limit
**Usage:**
```bash
python .claude/skills/cv-validation/scripts/compress_photo.py <image-file> --max-size=30KB --output=<output-file>
```

**Strategies:**
1. Lossless compression (PNG optimization)
2. Format conversion (PNG → WebP)
3. Dimension reduction (maintain aspect ratio)
4. Quality reduction (JPEG quality 80-90)

## Progressive Disclosure

**Level 1 (Metadata):** Skill name + description (always loaded)
**Level 2 (This file):** SKILL.md body (loaded when skill triggers)
**Level 3 (References):**
- Read [references/schema-requirements.md](references/schema-requirements.md) for complete schema
- Read [references/ats-compliance.md](references/ats-compliance.md) for ATS-specific rules
- Read [references/layout-constraints.md](references/layout-constraints.md) for 2-page template details

**Only load references when:**
- User asks for "detailed schema" or "complete reference"
- Validation errors are unclear and need deeper explanation
- Debugging complex layout issues

## ATS Compliance Checks

For strict ATS compliance (when `--strict` flag used):

**Additional validations:**
- No tables in experience section (ATS parsers fail on tables)
- No images except profile photo
- No colored text (some ATS strip formatting)
- Standard section headers (Experience, Education, Skills)
- Phone number in standard format (E.164 or national)
- Email address valid format
- No special characters in name fields
- PDF/A compliance (archival format)

**See:** [references/ats-compliance.md](references/ats-compliance.md)

## Integration with Other Commands

**Typical workflow:**
1. User uploads CV
2. `/validate-cv` → Pre-check + API validation
3. If valid: Generate preview HTML
4. `/visual-regression` → Screenshot + compare baseline
5. If visual OK: Generate PDF
6. If invalid: Show errors, ask for fixes, return to step 2

**Chaining:**
```
User: "Validate this CV and generate PDF if valid"

Claude:
1. /validate-cv data.json
2. [If valid] Call generate-cv-action API
3. [If invalid] Show errors, abort PDF generation
```

## Performance Notes

**Validation timing:**
- Local schema check: ~50ms
- API validation: ~200ms
- Layout estimation: ~100ms
- Total: <400ms (fast feedback loop)

**Optimization:**
- Cache schema definition (don't re-read on every validation)
- Parallelize local + API validation
- Skip layout estimation if pre-validation fails

## Error Recovery

**If validation API fails:**
1. Fall back to local validation only
2. Warn user: "API unavailable, basic validation only"
3. Skip business rules (dates, language constraints)
4. Proceed with PDF generation at user's risk

**If script execution fails:**
1. Check Python availability: `python --version`
2. Install dependencies: `pip install -r requirements.txt`
3. Fall back to manual validation (read schema, check fields)

## References

**Read these files for detailed information:**
- [references/schema-requirements.md](references/schema-requirements.md) - Complete JSON schema
- [references/ats-compliance.md](references/ats-compliance.md) - ATS-specific validation rules
- [references/layout-constraints.md](references/layout-constraints.md) - 2-page template constraints

**Project files:**
- Schema source: [../../DATA_DICTIONARY.md](../../DATA_DICTIONARY.md)
- API implementation: [../../src/schema_validator.py](../../src/schema_validator.py)
- Template spec: [../../templates/html/CV_template_2pages_2025.spec.md](../../templates/html/CV_template_2pages_2025.spec.md)

---

**Last updated:** 2026-01-22
**Skill version:** 1.0.0