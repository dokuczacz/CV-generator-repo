# CV Template Layout Rules

## Overview

This template enforces a **strict 2-page PDF constraint** using a natural flow layout approach. Content flows continuously, and WeasyPrint handles pagination automatically based on overflow.

---

## Core Principles

### ✅ Natural Flow Pagination

**What it means:**
- Content flows continuously from top to bottom
- No artificial "page" boundaries in the HTML/CSS
- WeasyPrint's rendering engine decides where to break pages based on content overflow
- `@page` margins apply to EVERY physical page automatically

**Why it works:**
- Eliminates large whitespace gaps when content doesn't fit perfectly on page 1
- Allows sections to split naturally across pages when needed
- Uses available space efficiently
- Prevents the "3-page overflow" problem

### ❌ What NOT to Do

**DO NOT** try to simulate pages with CSS:
```css
/* ❌ WRONG - causes whitespace and overflow */
.page {
  min-height: 277mm;  /* Don't do this! */
  padding: 20mm;      /* Use @page margin instead */
}
```

**DO NOT** use explicit page break elements:
```html
<!-- ❌ WRONG - unnecessary and can cause layout issues -->
<div class="page-break"></div>
```

**DO NOT** prevent sections from splitting:
```css
/* ❌ WRONG - pushes entire sections to next page, creating gaps */
.section {
  break-inside: avoid;
  page-break-inside: avoid;
}
```

### ✅ What TO Do

**Use @page margins for consistent padding:**
```css
@page {
  size: A4;
  margin: 20mm 22.4mm 20mm 25mm;
}
```

**Keep headings with their content:**
```css
.section-title {
  break-after: avoid;  /* Keep title with first entry */
  page-break-after: avoid;
}

.entry-head {
  break-after: avoid;  /* Keep entry header with bullets/details */
  page-break-after: avoid;
}
```

**Use .page only as a width container for preview:**
```css
.page {
  width: 210mm;       /* A4 width */
  margin: 0 auto;     /* Center for screen preview */
  background: white;
}
```

---

## WeasyPrint CSS Support

### ✅ Supported Features

- **@page rules**: `size`, `margin`, `@top-center`, etc.
- **Break properties**: `break-before`, `break-after`, `break-inside`
- **Legacy syntax**: `page-break-*` (still works)
- **Basic layout**: floats, basic flexbox, tables
- **Typography**: `font-variant`, `letter-spacing`, `text-transform`

### ❌ Limited/Unsupported Features

- **CSS Grid**: Limited support, prefer simpler layouts
- **Flexbox**: Partial support, avoid complex flex layouts
- **Modern CSS**: `backdrop-filter`, `container queries`, `has()`, etc.
- **JavaScript-dependent**: Any layout requiring JS calculations

**Recommendation:** Use float-based or simple flex layouts for maximum compatibility.

---

## Section Order & Expected Layout

### Page 1 (typically)
1. **Header** - Name, contact, photo
2. **Education** - Academic background
3. **Work experience** (start) - Professional experience

### Page 2 (typically)
1. **Work experience** (continued, if needed)
2. **Further experience / commitment**
3. **Language Skills**
4. **IT & AI Skills**
5. **Interests**
6. **References**

**Note:** Exact page boundaries depend on content length. The layout allows Work experience to split naturally across pages.

---

## Common Issues & Solutions

### Issue: PDF has 3+ pages

**Root causes:**
- Too much whitespace on page 1 (section pushed to page 2 unnecessarily)
- Aggressive `break-inside:avoid` preventing natural splits
- Padding/min-height on `.page` simulating fixed page heights

**Solutions:**
1. Remove `min-height` from `.page`
2. Remove `break-inside:avoid` from `.section`
3. Ensure `@page` margins are set correctly
4. Let sections split naturally (especially Work experience)

### Issue: Heading appears alone at bottom of page

**Root cause:** Missing `break-after:avoid` on heading elements

**Solution:**
```css
.section-title,
.entry-head {
  break-after: avoid;
  page-break-after: avoid;
}
```

### Issue: Large gap between sections

**Root cause:** Excessive margins or padding

**Solution:**
```css
.section {
  margin-top: 5mm;  /* Keep spacing consistent and tight */
}
```

---

## Testing Guidelines

### Visual Regression Tests

Run Playwright visual tests after any layout changes:
```bash
npm test
```

### Manual Testing Checklist

1. **Generate PDF with realistic CV data** (not minimal samples)
2. **Verify 2 pages exactly** - no more, no less
3. **Check page breaks** - no orphaned headings, reasonable splits
4. **Measure whitespace** - no large gaps at end of page 1
5. **Test all languages** - EN, DE, PL templates
6. **Test edge cases**:
   - Very long Work experience (many jobs)
   - Short Work experience (1-2 jobs)
   - No photo (photo-box--empty)
   - Long bullet points

### Smoke Test

Generate PDF from test session:
```powershell
$sid = 'd03cf26e-0dc1-48f9-91c8-7def7a10ddca'
$resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:7071/api/generate-cv-from-session" `
  -ContentType "application/json" -Body (ConvertTo-Json @{ session_id=$sid; language='en' })

$out = "tmp\test_output.pdf"
[IO.File]::WriteAllBytes($out, [Convert]::FromBase64String($resp.pdf_base64))
Start-Process (Resolve-Path $out)
```

Count pages with Python:
```python
from pypdf import PdfReader
reader = PdfReader("tmp/test_output.pdf")
assert len(reader.pages) == 2, f"Expected 2 pages, got {len(reader.pages)}"
```

---

## Maintenance Guidelines

### Before Making Layout Changes

1. **Read this document** - understand the natural flow approach
2. **Check existing tests** - `tests/cv-visual.spec.ts`
3. **Generate baseline PDF** - save current output for comparison

### After Making Changes

1. **Run visual tests** - `npm test`
2. **Generate test PDFs** - verify 2-page constraint
3. **Compare before/after** - check for regressions
4. **Update baselines** (if intentional) - `npm test -- --update-snapshots`
5. **Document changes** - update this file if rules change

### Git Workflow

```bash
# Check changes
git status -sb
git diff templates/html/

# Run tests
cd ui && npm run lint
npm test

# Commit with clear message
git add templates/html/
git commit -m "fix(layout): adjust section spacing for better page breaks"
```

---

## References

- **Template spec**: [CV_template_2pages_2025.spec.md](CV_template_2pages_2025.spec.md)
- **WeasyPrint docs**: https://doc.courtbouillon.org/weasyprint/stable/
- **Paged media CSS**: https://developer.mozilla.org/en-US/docs/Web/CSS/@page
- **Break properties**: https://developer.mozilla.org/en-US/docs/Web/CSS/break-before

---

**Last updated:** 2026-01-22
**Related handoff:** [tmp/HANDOFF_2026_01_22.md](../../tmp/HANDOFF_2026_01_22.md)
