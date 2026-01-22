# Visual Iteration Workflow

Screenshot-based iterative CV template design with Playwright integration.

**Use case:** Update CV template design with pixel-perfect visual verification

---

## Overview

**Visual iteration** uses screenshot comparison to iteratively refine CV templates:
1. Make CSS/HTML change
2. Generate preview
3. Screenshot with Playwright
4. Compare with target design
5. Accept or iterate

**Benefits:**
- Pixel-perfect design matching
- Faster feedback than manual PDF review
- Objective comparison (not subjective)
- Regression prevention (baseline protection)

---

## Basic Workflow

### Step 1: Capture Target Design
```
User: "Make the section headings larger and bolder, like this design mock"
[User provides screenshot: design_mock.png]

Claude:
1. Save design mock: tmp/design_target.png
2. Identify changes needed:
   - Section headings (h2): 16px → 20px
   - Font weight: 600 → 700
```

### Step 2: Implement Changes
```css
/* templates/html/cv_template_2pages_2025.css */

/* Before */
h2 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 10px;
}

/* After */
h2 {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 12px;
}
```

### Step 3: Generate Preview
```bash
curl -X POST http://localhost:7071/api/generate-cv-action \
  -H "Content-Type: application/json" \
  -d '{
    "cv_data": {...},
    "preview_only": true
  }' \
  > tmp/preview_iteration1.html
```

### Step 4: Screenshot with Playwright
```javascript
// Using Playwright MCP
await page.goto('file:///' + path.resolve('tmp/preview_iteration1.html'));
await page.screenshot({ path: 'tmp/iteration1.png', fullPage: true });
```

**Or use CLI:**
```bash
node scripts/print_pdf_playwright.mjs tmp/preview_iteration1.html tmp/iteration1.png --screenshot-only
```

### Step 5: Visual Comparison
```
Claude (using vision capabilities):
Compare tmp/iteration1.png with tmp/design_target.png

Analysis:
✅ Heading size increased correctly (20px visible)
✅ Font weight bolder (700 vs 600 noticeable)
⚠️ Margin-bottom slightly off (12px vs target 15px)

Diff percentage: 8% (mostly margin difference)

Recommendation: Adjust margin-bottom to 15px and re-test
```

### Step 6: Iterate or Accept
```css
/* Iteration 2 adjustment */
h2 {
  margin-bottom: 15px;  /* was 12px */
}
```

**Re-screenshot:**
```bash
# Generate new preview
curl POST /api/generate-cv-action {...} > tmp/preview_iteration2.html

# Screenshot
node scripts/print_pdf_playwright.mjs tmp/preview_iteration2.html tmp/iteration2.png --screenshot-only
```

**Compare again:**
```
Diff percentage: 2% (within acceptable threshold)

✅ ACCEPT: Update baseline
```

### Step 7: Update Baseline
```bash
# Copy iteration2.png as new baseline
cp tmp/iteration2.png test-results/cv-en-baseline.png

# Commit changes
git add templates/html/cv_template_2pages_2025.css test-results/cv-en-baseline.png
git commit -m "design: increase section heading size and weight

Adjusted h2 styling to match design mock:
- font-size: 16px → 20px
- font-weight: 600 → 700
- margin-bottom: 10px → 15px

Visual regression baseline updated.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Advanced Patterns

### Pattern 1: Multi-Element Iteration
**Goal:** Update multiple design elements in one pass

```
User: "Update header design: larger name, smaller contact info, adjust spacing"

Claude:
Iteration plan:
1. Name (h1): 28px → 32px, weight 700
2. Professional title: 18px → 16px, color #333 → #666
3. Contact info: 14px → 12px, line-height 1.5 → 1.3
4. Header padding: 20px → 30px

Apply all changes → screenshot → compare → adjust as batch
```

**Benefit:** Faster than changing one element at a time

### Pattern 2: Cross-Language Consistency
**Goal:** Ensure design works across EN/DE/PL templates

```
Workflow:
1. Update English template CSS
2. Screenshot EN preview
3. Apply same changes to DE template
4. Screenshot DE preview (watch for long German words)
5. Apply same changes to PL template
6. Screenshot PL preview
7. Compare all 3 side-by-side
8. Adjust language-specific spacing if needed
```

**Example adjustment for German:**
```css
/* German template needs extra line-height for long compound words */
body[lang="de"] h2 {
  line-height: 1.3;  /* vs 1.2 for EN */
}
```

### Pattern 3: Responsive Iteration (Different Page Sizes)
**Goal:** Ensure template works for both A4 and Letter paper

```
Workflow:
1. Generate preview with A4 size (@page { size: A4; })
2. Screenshot A4 version
3. Switch to Letter size (@page { size: Letter; })
4. Screenshot Letter version
5. Compare layouts (Letter is wider, shorter)
6. Adjust margins/padding for Letter if needed
```

---

## Playwright MCP Integration

### Screenshot Single Element
```javascript
// Focus on specific section
const element = await page.$('.experience-section');
await element.screenshot({ path: 'tmp/experience_only.png' });
```

**Use case:** Iterate on one section without full-page screenshots

### Screenshot with Annotations
```javascript
// Add visual markers to screenshot
await page.evaluate(() => {
  const headings = document.querySelectorAll('h2');
  headings.forEach(h => {
    h.style.outline = '2px solid red';  // Highlight for measurement
  });
});
await page.screenshot({ path: 'tmp/headings_annotated.png' });
```

**Use case:** Verify spacing/sizing visually

### Screenshot Comparison Script
```javascript
// Compare two screenshots programmatically
const { compare } = require('resemblejs');

compare('tmp/iteration1.png', 'tmp/design_target.png', (err, data) => {
  console.log(`Diff: ${data.misMatchPercentage}%`);
  if (data.misMatchPercentage > 5) {
    console.log('Significant differences detected');
  }
});
```

---

## Design Mock Integration

### User Provides Design Mock
```
User: [Uploads design_mock.png]
"Make the CV look like this"

Claude:
1. Analyze design_mock.png using vision:
   - Extract fonts (Roboto, size 14px body, 20px headings)
   - Extract colors (#000 text, #007bff accent)
   - Extract spacing (30px margins, 15px section gaps)
   - Extract layout (single column, photo top-right)
2. Document changes needed
3. Implement CSS changes
4. Iterate with screenshot comparison
```

### Claude Generates Design Variations
```
User: "Show me 3 design variations for the header"

Claude:
1. Generate 3 CSS variants:
   - Variant A: Centered, large name, photo above
   - Variant B: Left-aligned, photo left, info right
   - Variant C: Horizontal bar, name left, contact right
2. Generate 3 previews
3. Screenshot all 3
4. Display side-by-side for user selection
```

---

## Measuring Design Accuracy

### Pixel-Perfect Metrics
- **Exact match:** 0% diff (impossible in practice due to font rendering)
- **Acceptable:** <2% diff (minor antialiasing differences)
- **Needs review:** 2-5% diff (small layout differences)
- **Significant:** >5% diff (major layout differences)

### What Counts as "Close Enough"?
- ✅ Font sizes within 1px
- ✅ Spacing within 2px
- ✅ Color differences <5% luminance
- ✅ Layout alignment within 3px
- ❌ Text wrapping differently
- ❌ Element positions off by >5px

---

## Tools & Scripts

### Playwright Screenshot Script
```javascript
// scripts/screenshot_preview.mjs
import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('file:///' + process.argv[2]);
await page.screenshot({
  path: process.argv[3],
  fullPage: true
});
await browser.close();
```

**Usage:**
```bash
node scripts/screenshot_preview.mjs tmp/preview.html tmp/screenshot.png
```

### Image Comparison Script
```python
# scripts/compare_images.py
from PIL import Image, ImageChops

def compare_images(img1_path, img2_path):
    img1 = Image.open(img1_path)
    img2 = Image.open(img2_path)

    diff = ImageChops.difference(img1, img2)

    # Calculate percentage difference
    diff_pixels = sum(sum(px) for px in diff.getdata())
    total_pixels = img1.size[0] * img1.size[1] * 3  # RGB
    diff_percent = (diff_pixels / total_pixels) * 100

    print(f"Difference: {diff_percent:.2f}%")

    # Save diff image
    diff.save('tmp/diff.png')

compare_images('tmp/iteration1.png', 'tmp/design_target.png')
```

---

## Integration with Visual Regression Tests

### Update Baseline After Design Change
```bash
# 1. Iterate until design matches
# (screenshot comparisons above)

# 2. Generate final preview
curl POST /api/generate-cv-action {...} > tmp/preview_final.html

# 3. Screenshot final version
node scripts/screenshot_preview.mjs tmp/preview_final.html tmp/final.png

# 4. Update baseline
cp tmp/final.png test-results/cv-en-baseline.png

# 5. Run visual regression to verify
npm test

# Should pass with 0% diff (same image)
```

### Prevent Regressions
```bash
# Before any CSS change
git checkout main
npm test  # Establish baseline (should pass)

# Make design changes on branch
git checkout feature/new-header-design

# After changes
npm test  # Should fail (intentional change)

# Accept new baseline
npm test -- --update-snapshots

# Commit baseline with CSS
git add test-results/ templates/html/
git commit -m "design: new header layout with updated baseline"
```

---

## Best Practices

1. **Save intermediate screenshots:** Keep iteration1.png, iteration2.png, etc. for comparison
2. **Document changes:** Write design rationale in commit messages
3. **Test all languages:** Don't assume EN CSS works for DE/PL
4. **Update baselines intentionally:** Never auto-accept without review
5. **Use vision mode for analysis:** Claude can spot differences you might miss

---

## Related Documentation

- [/visual-regression](../.claude/commands/visual-regression.md) - Slash command for visual tests
- [pdf-generation skill](../.claude/skills/pdf-generation/SKILL.md) - PDF generation workflow
- [playwright.config.ts](../../playwright.config.ts) - Visual regression configuration