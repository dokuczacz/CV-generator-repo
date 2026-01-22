---
name: pdf-generation
description: Generate 2-page ATS-compliant PDF CVs using WeasyPrint with multi-language support (EN/DE/PL) and visual regression testing. Use when generating final PDF, running visual tests, debugging layout issues, or iterating on CV template design. Trigger on: "generate PDF", "create CV PDF", "render PDF", "visual regression test", or after successful CV validation.
---

# PDF Generation Skill

## When to Apply

Trigger this skill when:
- User asks to generate final PDF
- After successful CV validation
- Running visual regression tests
- Debugging template layout issues
- Iterating on CV design changes
- Testing multi-language output (EN/DE/PL)

**Prerequisites:** CV data must pass validation first (use cv-validation skill)

---

## Core PDF Generation Workflow

### Step 1: Pre-Generation Validation
**Always validate before generating PDF:**

```bash
python .claude/skills/cv-validation/scripts/validate_schema.py <cv-json-file>
```

**Only proceed if validation passes.** Never generate PDF from invalid data.

### Step 2: Call Generation API
Generate PDF via Azure Function:

```bash
curl -X POST http://localhost:7071/api/generate-cv-action \
  -H "Content-Type: application/json" \
  -d '{
    "cv_data": {...},
    "language": "en",
    "source_docx_base64": null
  }'
```

**Parameters:**
- `cv_data` (required): Complete CV JSON object
- `language` (optional): "en" (default), "de", or "pl"
- `source_docx_base64` (optional): Base64-encoded DOCX for photo extraction

**Response:**
```json
{
  "success": true,
  "preview_html_url": "blob://sessions/.../preview.html",
  "pdf_url": "blob://sessions/.../cv.pdf",
  "session_id": "d03cf26e-0dc1-48f9-91c8-7def7a10ddca"
}
```

### Step 3: Download and Display
Save generated files locally:

```bash
# Download preview HTML
curl "<preview_html_url>" > tmp/preview_<session_id>.html

# Download PDF
curl "<pdf_url>" > tmp/cv_<session_id>.pdf
```

**Show to user:**
```
✅ PDF Generated Successfully

Preview: [tmp/preview_d03cf26e.html](tmp/preview_d03cf26e.html)
PDF: [tmp/cv_d03cf26e.pdf](tmp/cv_d03cf26e.pdf)

Language: English (EN)
Pages: 2
Size: 245 KB

Next steps:
1. Review PDF visually
2. Run visual regression test (/visual-regression)
3. If satisfied, share with user
```

### Step 4: Visual Regression Testing
**Always test generated PDF against baseline:**

```bash
npm test
# Or use command: /visual-regression
```

**Playwright will:**
1. Screenshot generated PDF
2. Compare with approved baseline
3. Report differences (threshold: 5%)

**See:** [references/visual-regression-workflow.md](references/visual-regression-workflow.md)

---

## Extended Thinking Modes

Use Claude's extended thinking for complex PDF generation tasks:

### Standard Generation ("think")
**Use for:** Regular CV generation with validated data
**Example:**
```
think: Generate PDF for validated CV data with English template
```

### Layout Debugging ("think hard")
**Use for:** Content overflow, alignment issues, font problems
**Example:**
```
think hard: Why is the experience section overflowing to page 3?
Analyze template CSS, content estimation, and WeasyPrint rendering.
```

### Multi-Language Edge Cases ("ultrathink")
**Use for:** Complex German/Polish layout issues, character encoding
**Example:**
```
ultrathink: German CV with long compound words breaks template layout.
Analyze word-break rules, hyphenation, character spacing, and CSS constraints.
```

---

## Multi-Language Support

### English (en)
**Template:** `cv_template_2pages_2025_en.html`
**Characteristics:**
- Shorter words (easier to fit)
- Standard sections (Experience, Education, Skills)
- Date format: MM/YYYY or YYYY-MM-DD

**CSS considerations:**
- Default line-height: 1.4
- Word-break: normal

### German (de)
**Template:** `cv_template_2pages_2025_de.html`
**Characteristics:**
- Longer compound words (Projektmanagement, Softwareentwicklung)
- Umlauts (ä, ö, ü, ß) require UTF-8
- Section headers: Berufserfahrung, Ausbildung, Fähigkeiten
- Date format: MM.YYYY

**CSS considerations:**
- Line-height: 1.5 (15% more space)
- Word-break: break-word (allow mid-word breaks)
- Hyphens: auto (enable hyphenation)

**WeasyPrint quirk:** German hyphenation requires language tag:
```html
<html lang="de">
```

### Polish (pl)
**Template:** `cv_template_2pages_2025_pl.html`
**Characteristics:**
- Polish diacritics (ą, ć, ę, ł, ń, ó, ś, ź, ż)
- Moderately longer words than English
- Section headers: Doświadczenie, Wykształcenie, Umiejętności
- Date format: MM.YYYY

**CSS considerations:**
- Line-height: 1.45 (10% more space)
- Word-break: normal
- Character encoding: UTF-8 (critical)

---

## Visual Iteration Workflow

**For template design changes, use iterative screenshot comparison:**

### Iteration Pattern
1. **Make CSS change** (e.g., increase heading font size)
2. **Generate preview** (POST /api/generate-cv-action with `preview_only: true`)
3. **Screenshot preview** (use Playwright MCP)
4. **Compare with baseline** (visual diff)
5. **Accept or iterate** (update baseline if satisfied)

**Example workflow:**
```
User: "Increase section heading size and test"

Claude:
1. Edit templates/html/cv_template_2pages_2025.css:
   h2 { font-size: 18px; } → h2 { font-size: 20px; }

2. Generate preview:
   curl POST /api/generate-cv-action {"cv_data": {...}, "preview_only": true}

3. Use Playwright MCP to screenshot:
   npx playwright screenshot tmp/preview_abc123.html tmp/preview_abc123.png

4. Compare with baseline:
   compare tmp/preview_abc123.png test-results/cv-en-baseline.png

5. Display diff:
   Diff: 3.2% (increased heading size visible, layout intact)

6. Ask: Accept new design? (yes/no)
```

**See:** [references/visual-iteration-patterns.md](references/visual-iteration-patterns.md)

---

## WeasyPrint CSS Compatibility

**WeasyPrint renders HTML to PDF using a subset of CSS.**

### Supported Features
- ✅ Float layouts (main positioning method)
- ✅ Flexbox (basic support, not all properties)
- ✅ Absolute/relative positioning
- ✅ Margins, padding, borders
- ✅ Fonts (embedded via @font-face)
- ✅ Page breaks (page-break-before, page-break-after)
- ✅ Background colors/images

### **NOT** Supported (or limited)
- ❌ CSS Grid (not supported)
- ❌ CSS Transforms (scale, rotate)
- ❌ CSS Animations
- ❌ CSS Variables (--custom-property)
- ⚠️ Flexbox gaps (use margins instead)
- ⚠️ Sticky positioning

**Important:** Always test template changes with actual PDF generation, not just browser preview.

**See:** [references/weasyprint-quirks.md](references/weasyprint-quirks.md)

---

## Common PDF Generation Issues

### Issue 1: Content Overflow (>2 Pages)
**Symptom:** PDF has 3+ pages
**Root cause:** Too much content or large fonts
**Fix:**
1. Run layout estimation: `.claude/skills/cv-validation/scripts/count_template_space.py`
2. If >2.0 pages estimated, reduce content:
   - Shorten experience bullets
   - Limit experience entries (last 10 years)
   - Remove less relevant skills
3. Or reduce font sizes (last resort):
   ```css
   body { font-size: 10px; } /* was 11px */
   ```

### Issue 2: Photo Not Displaying
**Symptom:** Profile photo missing in PDF
**Root cause:** photo_url invalid or >32KB
**Fix:**
1. Validate photo_url size:
   ```bash
   python .claude/skills/cv-validation/scripts/validate_schema.py <cv-json> | grep photo_url
   ```
2. If >32KB, compress:
   ```bash
   python .claude/skills/cv-validation/scripts/compress_photo.py <image> --max-size=30KB
   ```
3. Verify data URI format:
   ```
   data:image/png;base64,iVBORw0KG...
   ```

### Issue 3: Font Rendering Issues
**Symptom:** Fonts look wrong or fallback to default
**Root cause:** Font files not embedded correctly
**Fix:**
1. Check font files exist: `templates/html/fonts/`
2. Verify @font-face in CSS:
   ```css
   @font-face {
     font-family: 'Roboto';
     src: url('fonts/Roboto-Regular.ttf');
   }
   ```
3. Use WeasyPrint font debugging:
   ```python
   from weasyprint import HTML, CSS
   HTML(string=html).write_pdf('test.pdf', stylesheets=[CSS(string=css)])
   # Check terminal for font warnings
   ```

### Issue 4: Layout Shifts Between Languages
**Symptom:** German CV overflows but English fits
**Root cause:** Longer German words without proper word-breaking
**Fix:**
1. Enable hyphenation in template:
   ```css
   p { hyphens: auto; }
   ```
2. Set HTML lang attribute:
   ```html
   <html lang="de">
   ```
3. Increase line-height for German:
   ```css
   body[lang="de"] { line-height: 1.5; }
   ```

### Issue 5: Visual Regression Test Fails
**Symptom:** Playwright reports >5% diff
**Root cause:** Intentional change or unexpected regression
**Fix:**
1. View diff image:
   ```
   test-results/cv-german-diff.png
   ```
2. If intentional change (e.g., font size update), accept new baseline:
   ```bash
   npm test -- --update-snapshots
   ```
3. If unintended regression, investigate:
   - Check recent CSS changes
   - Review template modifications
   - Test WeasyPrint version consistency

---

## Scripts

### print_pdf_playwright.mjs
**Location:** [scripts/print_pdf_playwright.mjs](../../scripts/print_pdf_playwright.mjs)
**Purpose:** Headless PDF generation using Playwright
**Usage:**
```bash
node scripts/print_pdf_playwright.mjs <html-file> <output-pdf>
```

**Features:**
- Headless Chromium rendering
- Pixel-perfect PDF output
- Used by visual regression tests

**Alternative to WeasyPrint:** Use when debugging browser-specific rendering issues.

---

## Progressive Disclosure

**Level 1 (Metadata):** Skill name + description (always loaded)
**Level 2 (This file):** SKILL.md body (loaded when skill triggers)
**Level 3 (References):**
- Read [references/template-specification.md](references/template-specification.md) for template structure
- Read [references/weasyprint-quirks.md](references/weasyprint-quirks.md) for CSS compatibility
- Read [references/visual-iteration-patterns.md](references/visual-iteration-patterns.md) for design workflows

**Only load references when:**
- Debugging complex layout issues
- Learning template structure
- Implementing new template features

---

## Integration with Other Commands/Skills

### cv-validation → pdf-generation
**Flow:**
1. `/validate-cv` → Pre-check + API validation
2. If valid: Automatically offer PDF generation
3. User confirms
4. Generate PDF + preview

### pdf-generation → visual-regression
**Flow:**
1. Generate PDF
2. `/visual-regression` → Screenshot + compare
3. If diff <5%: Accept PDF
4. If diff ≥5%: Review changes, update baseline if intentional

### Visual iteration loop
**Flow:**
1. Edit template CSS
2. Generate preview (no full PDF)
3. Screenshot with Playwright MCP
4. Compare with design mock (not baseline)
5. Iterate until pixel-perfect
6. Generate final PDF + update baseline

---

## Performance Optimization

**PDF generation timing:**
- Validation: ~200ms (API call)
- HTML rendering: ~500ms (template + data injection)
- WeasyPrint PDF: ~1-2s (complex layout)
- Total: ~2-3s per PDF

**Optimization tips:**
1. Cache validated data (don't re-validate on retry)
2. Reuse template instances (don't re-parse CSS)
3. Parallelize multi-language generation:
   ```bash
   # Generate EN, DE, PL in parallel
   curl POST /api/generate-cv-action {"language": "en"} &
   curl POST /api/generate-cv-action {"language": "de"} &
   curl POST /api/generate-cv-action {"language": "pl"} &
   wait
   ```

---

## Headless CI/CD Integration (Phase 3)

**GitHub Actions workflow:**

```yaml
name: Visual Regression Tests

on: [pull_request]

jobs:
  test-cv-generation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
      - uses: actions/setup-python@v4

      - name: Install dependencies
        run: |
          npm install
          pip install -r requirements.txt

      - name: Generate test PDFs
        run: |
          npm run pretest  # Generate test artifacts
          python scripts/generate_all_languages.py

      - name: Run visual regression
        run: npm test

      - name: Upload diff images
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: visual-diffs
          path: test-results/**/*-diff.png
```

**Claude Code headless mode:**
```bash
# Run PDF generation + visual test via Claude agent
claude -p "Generate CV PDF and run visual regression tests" \
  --headless \
  --output test-results/claude-report.md
```

---

## References

**Read these files for detailed information:**
- [references/template-specification.md](references/template-specification.md) - 2-page template structure
- [references/weasyprint-quirks.md](references/weasyprint-quirks.md) - CSS compatibility notes
- [references/visual-iteration-patterns.md](references/visual-iteration-patterns.md) - Design iteration workflows
- [references/visual-regression-workflow.md](references/visual-regression-workflow.md) - Testing patterns

**Project files:**
- Template files: [../../templates/html/](../../templates/html/)
- Template spec: [../../templates/html/CV_template_2pages_2025.spec.md](../../templates/html/CV_template_2pages_2025.spec.md)
- API implementation: [../../src/render.py](../../src/render.py)
- Playwright config: [../../playwright.config.ts](../../playwright.config.ts)

---

**Last updated:** 2026-01-22
**Skill version:** 1.0.0