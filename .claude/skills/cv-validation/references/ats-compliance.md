# ATS Compliance Requirements

Applicant Tracking System (ATS) parsing requirements for CV validation.

**Purpose:** Ensure CVs are machine-readable by ATS software used by employers.

---

## What is ATS?

**Applicant Tracking Systems** (ATS) are software tools used by companies to:
- Parse and extract CV data automatically
- Search candidates by keywords
- Filter candidates based on criteria
- Rank candidates by relevance

**Problem:** Many ATS parsers fail on:
- Complex layouts (tables, columns)
- Images/graphics (except photos)
- Colored text/backgrounds
- Non-standard fonts
- PDF files with security restrictions

**Solution:** Follow ATS-safe formatting guidelines.

---

## ATS Compliance Checklist

### ✅ Layout & Structure

**DO:**
- Use simple, single-column layout
- Standard section headers (Experience, Education, Skills)
- Consistent heading hierarchy (H1 for name, H2 for sections)
- Left-aligned text (easier to parse)
- Standard fonts (Arial, Helvetica, Times New Roman)

**DON'T:**
- Multi-column layouts (confuses text extraction order)
- Tables in experience section (many parsers fail)
- Text boxes or frames
- Headers/footers with critical info
- Complex nested structures

### ✅ Formatting

**DO:**
- Use standard bullet points (• or -)
- Bold for emphasis (sparingly)
- Standard date formats (YYYY-MM-DD or MM/YYYY)
- Plain text (no colored backgrounds)

**DON'T:**
- Colored text (some ATS strip formatting)
- Fancy fonts or script fonts
- Underlines (confuses link detection)
- All caps (harder to parse)
- Special characters in section headers

### ✅ Contact Information

**DO:**
- Place at top of CV
- Use standard labels (Email, Phone, Address)
- Include clickable email (mailto: link)
- Use international phone format (+41 77 xxx)

**DON'T:**
- Hide contact info in images
- Use non-standard labels ("Reach me at:")
- Abbreviate (write "Phone" not "Ph")
- Use company email for job search

### ✅ Images & Graphics

**DO:**
- Include professional headshot (if customary)
- Use standard image formats (PNG, JPEG)
- Embed images properly (not as background)

**DON'T:**
- Use images for text/logos
- Include decorative graphics
- Use background images
- Add charts/infographics (some ATS strip)

### ✅ Keywords

**DO:**
- Include relevant skills/technologies
- Use industry-standard terms
- Match job description keywords
- Spell out acronyms first use (e.g., "Search Engine Optimization (SEO)")

**DON'T:**
- Keyword stuff (unnatural repetition)
- Use synonyms excessively
- Hide keywords (white text on white background - flagged as cheating)

### ✅ File Format

**DO:**
- Use PDF/A (archival format)
- Ensure text is selectable (not scanned image)
- Keep file size reasonable (<2MB)
- Use standard PDF features

**DON'T:**
- Password-protect PDF (blocks parsing)
- Scan paper CV to PDF (not text-searchable)
- Use PDF forms (some ATS can't extract)
- Use proprietary formats (.pages, .odt)

---

## Strict Mode Validation

When `--strict` flag is used, validate these additional rules:

### 1. No Tables in Experience
**Rule:** Experience section must use plain text, not tables
**Reason:** Many ATS extract table data incorrectly (mixes columns)

**Bad:**
```
| Position | Company | Dates |
|----------|---------|-------|
| Engineer | TechCo  | 2020  |
```

**Good:**
```
Senior Engineer
TechCo, Zurich, Switzerland
2020-01 to Present
- Responsibilities...
```

### 2. Standard Section Headers
**Rule:** Use exact headers from this list:
- Experience / Work Experience / Professional Experience
- Education
- Skills / Technical Skills
- Languages
- Certifications
- Projects (optional)

**Reason:** ATS expect standard section names

### 3. No Special Characters in Names
**Rule:** First/last names should use only letters, spaces, hyphens, apostrophes
**Allowed:** "Jean-Pierre O'Connor"
**Not allowed:** "Jean★Pierre", "John🚀Doe"

### 4. Phone Number Format
**Rule:** International format with country code
**Example:** "+41 77 952 24 37" or "+1 (555) 123-4567"

### 5. Email Address Validation
**Rule:** Valid email format, professional domain
**Good:** john.doe@example.com, j.doe@company.com
**Bad:** john!!!doe@mail.ru, cooldude69@hotmail.com

### 6. Date Consistency
**Rule:** All dates use same format (prefer ISO 8601: YYYY-MM-DD)
**Good:** All dates "2020-01-15"
**Bad:** Mixed "Jan 2020", "2020-01-15", "15/01/2020"

### 7. PDF/A Compliance
**Rule:** PDF must be PDF/A-1b or PDF/A-2b (archival standard)
**Reason:** Ensures long-term readability and ATS compatibility

**Check with:**
```bash
pdfinfo <cv.pdf> | grep "PDF version"
# Should show: PDF-1.4 (PDF/A-1b) or PDF-1.7 (PDF/A-2b)
```

### 8. No Colored Text (Strict)
**Rule:** All text must be black (#000000) or dark gray (#333333)
**Reason:** Some ATS strip colors, making text invisible

**Exception:** Links can be blue (standard hyperlink color)

### 9. File Naming Convention
**Rule:** Use professional filename
**Good:** `John_Doe_CV.pdf`, `Doe_John_Resume_2024.pdf`
**Bad:** `my resume final FINAL v3 (1).pdf`, `🚀_HIRE_ME.pdf`

---

## ATS Testing Tools

### Online ATS Scanners
- **Jobscan:** jobscan.co (compares CV to job description)
- **Resume Worded:** resumeworded.com (free ATS check)
- **TopResume:** topresume.com (ATS compatibility score)

### Manual Tests

**Test 1: Copy-Paste Test**
1. Open CV in PDF reader
2. Select all text (Ctrl+A)
3. Copy to plain text editor
4. Check if text order makes sense

**Pass:** Text flows logically top-to-bottom
**Fail:** Jumbled text, missing sections, wrong order

**Test 2: Accessibility Checker**
1. Open PDF in Adobe Acrobat
2. Tools → Accessibility → Full Check
3. Review errors/warnings

**Pass:** No critical errors, structure tagged
**Fail:** Untagged content, reading order issues

**Test 3: Search Test**
1. Open CV in PDF reader
2. Search for key skill (Ctrl+F: "Python")
3. Check if found

**Pass:** All keywords searchable
**Fail:** Skills not found (likely in image)

---

## Implementation in Validation Script

### Strict Mode Checks

Add these checks to `validate_schema.py` when `--strict` flag is used:

```python
def validate_ats_compliance(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """ATS compliance checks (strict mode only)."""
    errors = []

    # Check section headers
    if "experience" in data and data["experience"]:
        # Ensure no table structures (check for vertical bars)
        pass

    # Check name for special characters
    if "firstName" in data:
        if not re.match(r"^[a-zA-Z\s\-\']+$", data["firstName"]):
            errors.append({
                "field": "firstName",
                "severity": "MEDIUM",
                "message": "Name contains special characters (ATS may fail to parse)"
            })

    # Check phone format
    if "phone" in data:
        if not re.match(r"^\+\d{1,3}\s?\d+", data["phone"]):
            errors.append({
                "field": "phone",
                "severity": "LOW",
                "message": "Phone should use international format (+XX XXX...)"
            })

    # Check date consistency
    # (all dates same format)

    return errors
```

---

## Language-Specific ATS Considerations

### English CVs
- Standard: ANSI encoding or UTF-8
- Date format: MM/DD/YYYY or YYYY-MM-DD
- Keywords: American vs British spelling (optimize vs optimise)

### German CVs
- Standard: UTF-8 (for umlauts: ä, ö, ü, ß)
- Date format: DD.MM.YYYY or YYYY-MM-DD
- Keywords: Include compound words (Projektmanagement)

### Polish CVs
- Standard: UTF-8 (for Polish characters: ą, ć, ę, ł, ń, ó, ś, ź, ż)
- Date format: DD.MM.YYYY or YYYY-MM-DD
- Keywords: Include diacritics correctly

---

## ATS Scoring Factors

Most ATS rank candidates by:

1. **Keyword match** (40%) - Skills, technologies, job titles
2. **Experience relevance** (30%) - Years, roles, industries
3. **Education match** (15%) - Degrees, institutions, fields
4. **Formatting quality** (10%) - Parsability, structure
5. **Completeness** (5%) - All sections filled

**Optimization tips:**
- Mirror job description keywords
- Quantify achievements (numbers stand out)
- Use standard job titles
- Fill all relevant sections
- Test CV with ATS scanner before applying

---

## Related Files

- [schema-requirements.md](schema-requirements.md) - Complete schema validation
- [../../../templates/html/CV_template_2pages_2025.spec.md](../../../templates/html/CV_template_2pages_2025.spec.md) - Template specification
- [../scripts/validate_schema.py](../scripts/validate_schema.py) - Validation implementation