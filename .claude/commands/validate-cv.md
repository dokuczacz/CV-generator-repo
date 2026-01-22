# Validate CV Command

Validates CV JSON against the strict 2-page schema and generates preview HTML.

---

## Usage

```
/validate-cv <file-path-or-inline-json>
```

**Examples:**
```
/validate-cv tmp/extracted_cv.json
/validate-cv @data/sample_cv.json --strict
/validate-cv { "firstName": "John", ... }
```

---

## Workflow

### Step 1: Load CV Data
- If `$ARGUMENTS` is a file path: Read the file
- If `$ARGUMENTS` is inline JSON: Parse directly
- Validate JSON structure (must be valid JSON)

### Step 2: Schema Validation (Local)
Before calling API, pre-validate locally:

**Required fields:**
```python
REQUIRED_FIELDS = [
    "firstName", "lastName", "email", "phone",
    "address", "professionalTitle"
]
```

**Size constraints:**
- `photo_url`: ≤32KB (base64, Azure Table limit)
- Experience bullets: ≤90 chars each
- Total content: Must fit 2-page template

**Reference:** [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md)

### Step 3: API Validation
Call the validate-cv Azure Function:

```bash
curl -X POST http://localhost:7071/api/validate-cv \
  -H "Content-Type: application/json" \
  -d @$ARGUMENTS
```

**Expected responses:**
- ✅ Valid: `{ "valid": true, "message": "CV is valid" }`
- ❌ Invalid: `{ "valid": false, "errors": [...] }`

### Step 4: Display Results
If **invalid**:
- Show errors with field paths
- Suggest fixes (e.g., "shorten experience[0].responsibilities[2] by 15 chars")
- Ask: "Edit fields or abort?"

If **valid**:
- Generate preview HTML via generate-cv-action (set `preview_only: true`)
- Save to `tmp/preview_<uuid>.html`
- Link to file: "Preview generated: [tmp/preview_<uuid>.html](tmp/preview_<uuid>.html)"
- Ask: "Proceed to PDF generation?"

### Step 5: Visual Check (Optional)
Use Playwright MCP to screenshot preview:

```bash
npx playwright screenshot tmp/preview_<uuid>.html tmp/preview_<uuid>.png
```

Display screenshot inline for visual validation.

---

## Error Handling

**Common validation errors:**

1. **Missing required field:**
   ```
   Error: Missing required field 'email'
   Fix: Add email field to CV JSON
   ```

2. **Photo URL too large:**
   ```
   Error: photo_url exceeds 32KB limit (current: 45KB)
   Fix: Compress image or reduce resolution
   ```

3. **Bullet too long:**
   ```
   Error: experience[0].responsibilities[1] exceeds 90 chars (current: 112)
   Fix: Shorten to: "Led team of 5 engineers to deliver microservices architecture in 6 months"
   ```

4. **Content overflow:**
   ```
   Error: Content exceeds 2-page limit (estimated: 2.3 pages)
   Fix: Remove less relevant experience or shorten bullets
   ```

---

## Flags

- `--strict`: Enable stricter validation (ATS compliance checks)
- `--preview`: Auto-generate preview HTML after validation
- `--screenshot`: Auto-screenshot preview (requires Playwright MCP)

---

## Output Format

```
Validating CV data...

✅ Schema validation: PASS
✅ Required fields: PASS (9/9)
✅ Size constraints: PASS
  - photo_url: 28KB / 32KB
  - Max bullet length: 87 / 90 chars
✅ API validation: PASS

Preview generated: tmp/preview_d03cf26e.html

Proceed to PDF generation? (yes/no)
```

---

## Related Commands

- `/visual-regression` - Run full visual regression tests
- `/generate-pdf` - Generate final PDF (skips validation)
- `/extract-photo` - Extract photo from DOCX

---

## Technical Notes

**Why validate twice (local + API)?**
- Local validation catches simple errors fast (no API call)
- API validation runs full schema check with business rules
- Two-tier approach reduces API calls and latency

**Why generate preview?**
- Visual confirmation before PDF generation
- Catches layout issues early
- Allows iterative refinement

**Preview vs PDF:**
- Preview: HTML rendering (WeasyPrint CSS subset)
- PDF: Final output (WeasyPrint full render)
- Preview is faster but may have minor differences