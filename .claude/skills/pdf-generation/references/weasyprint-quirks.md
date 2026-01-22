# WeasyPrint CSS Quirks & Compatibility

WeasyPrint-specific CSS rendering notes for CV template development.

**WeasyPrint version:** Check with `pip show weasyprint`
**Current template target:** WeasyPrint 59+

---

## Supported CSS Features

### Layout
- ✅ **Float:** Primary layout method (use float: left/right)
- ✅ **Flexbox:** Basic support (flex-direction, justify-content)
- ✅ **Positioning:** absolute, relative, fixed
- ✅ **Display:** block, inline, inline-block, flex, none
- ❌ **Grid:** NOT supported

**Recommendation:** Use float-based layouts for maximum compatibility.

### Typography
- ✅ **@font-face:** Embed custom fonts
- ✅ **font-family, font-size, font-weight**
- ✅ **line-height, letter-spacing**
- ✅ **text-align, text-decoration**
- ✅ **hyphens: auto** (with lang attribute)
- ⚠️ **text-shadow:** Supported but renders poorly in PDF

### Spacing
- ✅ **margin, padding** (all sides)
- ✅ **border** (width, style, color)
- ✅ **width, height** (px, %, em)
- ⚠️ **Flexbox gap:** NOT supported (use margin instead)

### Colors & Backgrounds
- ✅ **color:** Text color (hex, rgb, named)
- ✅ **background-color:** Solid colors
- ✅ **background-image:** Images (embedded or external)
- ⚠️ **Gradients:** Limited support (use solid colors)

### Page Control
- ✅ **@page:** Define page size, margins, headers/footers
- ✅ **page-break-before, page-break-after**
- ✅ **page-break-inside: avoid** (prevent content splitting)

---

## NOT Supported

### Modern CSS
- ❌ **CSS Grid:** Use flexbox or floats instead
- ❌ **CSS Variables (--custom-property):** Use Sass/Less for variables
- ❌ **calc():** Compute values in template logic instead
- ❌ **CSS Transforms:** scale, rotate, skew
- ❌ **CSS Animations:** No @keyframes
- ❌ **Transitions:** No animated property changes

### Advanced Flexbox
- ❌ **gap:** Use margin on children instead
- ❌ **flex-wrap:** Partial support, test carefully
- ❌ **order:** Reorder elements in HTML instead

### Pseudo-Elements
- ⚠️ **::before, ::after:** Supported but content: must be static strings
- ❌ **::first-line, ::first-letter:** Limited support

---

## Common Issues & Solutions

### Issue: Flexbox Gap Not Working
**Problem:**
```css
.skills {
  display: flex;
  gap: 10px;  /* IGNORED by WeasyPrint */
}
```

**Solution:**
```css
.skills {
  display: flex;
}
.skills > * {
  margin-right: 10px;
}
.skills > *:last-child {
  margin-right: 0;
}
```

### Issue: CSS Variables Ignored
**Problem:**
```css
:root {
  --primary-color: #007bff;  /* IGNORED */
}
.header {
  color: var(--primary-color);  /* Falls back to default */
}
```

**Solution:** Use Sass/Less preprocessing or inline values:
```css
.header {
  color: #007bff;
}
```

### Issue: Page Breaks Breaking Layout
**Problem:** Experience section splits across pages awkwardly

**Solution:**
```css
.experience-item {
  page-break-inside: avoid;  /* Keep entry together */
}

.experience-section h2 {
  page-break-after: avoid;  /* Keep heading with content */
}
```

### Issue: Font Not Embedding
**Problem:** PDF uses fallback font (ugly)

**Solution:**
1. Ensure font file exists: `templates/html/fonts/Roboto-Regular.ttf`
2. Use relative path in @font-face:
   ```css
   @font-face {
     font-family: 'Roboto';
     src: url('fonts/Roboto-Regular.ttf') format('truetype');
   }
   ```
3. Verify font loads:
   ```python
   from weasyprint import HTML
   HTML('template.html').write_pdf('test.pdf')
   # Check terminal for font warnings
   ```

### Issue: Background Images Not Showing
**Problem:** Photo or decorative background missing

**Solution:**
1. Use data URI for inline images:
   ```css
   .photo {
     background-image: url('data:image/png;base64,...');
   }
   ```
2. Or ensure external image is accessible:
   ```css
   .logo {
     background-image: url('file:///absolute/path/logo.png');
   }
   ```

---

## WeasyPrint-Specific CSS

### Page Definition
```css
@page {
  size: A4;  /* or Letter */
  margin: 1cm 1.5cm;  /* top/bottom left/right */
}

@page :first {
  margin-top: 0.5cm;  /* Less margin on first page */
}
```

### Force Page Breaks
```css
.section {
  page-break-before: always;  /* Start new page */
}

.keep-together {
  page-break-inside: avoid;  /* Don't split */
}
```

### Hyphenation (for long German words)
```html
<html lang="de">
```

```css
p {
  hyphens: auto;  /* Enable automatic hyphenation */
  -webkit-hyphens: auto;
}
```

**Note:** Requires lang attribute on HTML element.

---

## Testing WeasyPrint Rendering

### Test Script
```python
from weasyprint import HTML, CSS
from pathlib import Path

# Render template
html_path = Path('templates/html/cv_template_2pages_2025.html')
css_path = Path('templates/html/cv_template_2pages_2025.css')

html = HTML(filename=str(html_path))
css = CSS(filename=str(css_path))

html.write_pdf('test.pdf', stylesheets=[css])
print("PDF generated: test.pdf")
```

### Debug Font Loading
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# WeasyPrint will log font loading details
HTML('template.html').write_pdf('test.pdf')
```

**Look for:** `WARNING: Failed to load font ...`

---

## Performance Tips

### Optimize Images
- Use data URIs for small images (<10KB)
- Compress images before embedding
- Limit image dimensions (200x200 for profile photos)

### Simplify Layouts
- Avoid deeply nested flex containers
- Use floats for complex multi-column layouts
- Minimize use of absolute positioning

### Cache Rendered Templates
```python
# Don't re-parse CSS on every render
css_cache = CSS(filename='template.css')

for cv_data in cv_list:
    html = generate_html(cv_data)
    HTML(string=html).write_pdf('output.pdf', stylesheets=[css_cache])
```

---

## Browser Preview vs WeasyPrint Output

**Important:** Browser preview ≠ WeasyPrint PDF output

**Differences:**
- Browsers support modern CSS (Grid, Variables)
- WeasyPrint uses older rendering engine
- Font rendering differs slightly
- Page breaks don't show in browser

**Workflow:**
1. **Design in browser** (Chrome DevTools for layout)
2. **Test in WeasyPrint** (generate actual PDF)
3. **Iterate** (fix WeasyPrint-specific issues)
4. **Visual regression** (compare PDF screenshots)

**Don't trust browser preview alone - always generate PDF to verify!**

---

## Version Compatibility

### WeasyPrint 59+ (Current)
- Improved flexbox support
- Better font embedding
- Faster rendering

### WeasyPrint 52-58
- Basic flexbox support
- Some layout bugs with complex nesting

### WeasyPrint <52
- Limited flexbox
- Use float layouts exclusively

**Check version:**
```bash
pip show weasyprint | grep Version
```

**Lock version in requirements.txt:**
```
weasyprint==59.0
```

---

## Related Files

- [template-specification.md](template-specification.md) - Template structure
- [../../../templates/html/cv_template_2pages_2025.css](../../../templates/html/cv_template_2pages_2025.css) - Actual template CSS
- [../../../src/render.py](../../../src/render.py) - Python rendering code