# 🏆 GOLDEN RULES - Swiss CV Template 2025

**Status**: CRITICAL REFERENCE - DO NOT VIOLATE

---

## 📐 PAGE SETUP (IMMUTABLE)

| Rule | Value | Notes |
|------|-------|-------|
| Page Size | A4 Portrait (210×297mm) | Non-negotiable |
| Top Margin | **20.0mm** | Word: 1134 twips |
| Right Margin | **22.4mm** | Word: 1270 twips |
| Bottom Margin | **20.0mm** | Word: 1134 twips |
| Left Margin | **25.0mm** | Word: 1418 twips |
| Layout | Single Column | No multi-column, no grid mess |

✅ CSS Implementation:
```css
.page {
  padding: 20mm 22.4mm 20mm 25mm;
}
```

---

## 🔤 TYPOGRAPHY (IMMUTABLE)

| Element | Font | Size | Weight | Color | Style |
|---------|------|------|--------|-------|-------|
| Body Text | Arial | **11pt** | normal | #000000 (black) | - |
| Name/Header | Arial | **16pt** | bold | #000000 (black) | UPPERCASE |
| Section Titles | Arial | **11pt** | bold | #0000FF (blue) | SMALL-CAPS |
| Contact Info | Arial | **11pt** | normal | #000000 | - |
| Photo Background | - | - | - | #EEECE1 | light gray |

✅ CSS Implementation:
```css
body {
  font-family: "Arial", "Helvetica", sans-serif;
  font-size: 11pt;
  color: #000000;
}

.name {
  font-size: 16pt;
  font-weight: 700;
  text-transform: uppercase;
}

.section-title {
  font-size: 11pt;
  font-weight: 700;
  font-variant: small-caps;
  color: #0000FF;
}
```

---

## 📄 STRUCTURE ORDER (IMMUTABLE)

**MUST appear in this order:**

1. **Header** (Name + Contact Info + Photo)
2. **Berufserfahrung** (Work Experience)
3. **Ausbildung** (Education)
4. **Sprachen** (Languages)
5. **Fähigkeiten & KI** (Skills)
6. **Weiterbildungen** (Trainings)
7. **Interessen** (Interests)
8. **Datenschutzerklärung** (Data Privacy) - *optional at end*

**NO PROFILE SECTION** - Original template doesn't have one!

---

## 📋 ENTRY LAYOUT (CRITICAL)

### Date & Role Column Structure
**Date column width: 42.5mm** (from tab stop specification)
- Left column: 42.5mm for dates
- Right column: 1fr (flexible, remaining space)
- Gap between columns: 3mm

✅ CSS:
```css
.entry-head {
  display: grid;
  grid-template-columns: 42.5mm 1fr;
  column-gap: 3mm;
}
```

### Bullets (Hanging Indent)
- **Left indent**: ~47.5mm (42.5mm date + 3mm gap + 2mm buffer)
- **Hanging indent**: 5mm
- **List style**: disc (bullet points)

✅ CSS:
```css
.bullets {
  margin-left: 47.5mm;
  margin-right: 0;
  padding-left: 5mm;
  list-style: disc;
}
```

---

## ⚙️ SPACING RULES (CRITICAL)

| Element | Spacing | Type | Notes |
|---------|---------|------|-------|
| Section to next section | 6mm | margin-top | Between `.section` elements |
| Section title to content | 3mm | margin-bottom | After `.section-title` |
| Entry to next entry | 3mm | margin-bottom | Between `.entry` elements |
| Bullet to next bullet | 1.5mm | margin-bottom | Between `li` elements |
| Header to first section | Auto | - | Natural flow |

✅ CSS:
```css
.section {
  margin-top: 6mm;
}

.section-title {
  margin-bottom: 3mm;
}

.entry {
  margin-bottom: 3mm;
}

.bullets li {
  margin-bottom: 1.5mm;
}
```

---

## 🎨 VISUAL STYLE (IMMUTABLE)

| Element | Rule | Notes |
|---------|------|-------|
| Section title line | Blue (#0000FF) accent line to right | After title |
| Photo box | 45mm×55mm | Light gray border with photo |
| Photo border | 1px solid #0000FF | Blue accent |
| Text alignment | Left-aligned, not justified | Natural flow |
| No shadows, no gradients | Minimal design | Professional Swiss style |

---

## ❌ DO NOT DO (CRITICAL VIOLATIONS)

❌ **DO NOT:**
- Change margins from spec (breaks layout)
- Add/remove sections (breaks structure)
- Use profile section (not in original template)
- Change entry column width from 42.5mm (spec-defined)
- Reduce spacing below 3mm between entries (causes crowding)
- Change section title color from blue #0000FF
- Use small fonts < 11pt (readability issue)
- Add decorative elements (gradients, rounded corners, shadows)
- Use justified text (spec says left-aligned)
- Add padding inside bullets (breaks indent alignment)

---

## ✅ CURRENT VIOLATIONS FOUND

After review, these violate GOLDEN RULES:

1. ❌ **Padding changed** from `20mm 22.4mm 20mm 25mm` → `15mm 18mm 12mm 18mm`
   - **FIX**: Restore to **exact spec values**

2. ❌ **Section margins reduced** from 6mm → 4mm
   - **FIX**: Restore to **6mm**

3. ❌ **Section title margin-bottom** from 3mm → 2mm
   - **FIX**: Restore to **3mm**

4. ❌ **Entry margins** from 3mm → 2mm
   - **FIX**: Restore to **3mm**

5. ❌ **Bullet spacing** from 1.5mm → 0.5mm
   - **FIX**: Restore to **1.5mm**

6. ❌ **Entry column width** should be **42.5mm** not 35mm
   - **FIX**: Change back to **42.5mm**

7. ❌ **Bullet indent** broken (should be 47.5mm)
   - **FIX**: Set proper margin-left for `.bullets`

---

## 🎯 PRIORITY FIX ORDER

1. **FIRST**: Restore all margins to spec (20/22.4/20/25mm)
2. **SECOND**: Restore spacing (6mm sections, 3mm entries, 1.5mm bullets)
3. **THIRD**: Fix entry column width (42.5mm not 35mm)
4. **FOURTH**: Fix bullet indentation (47.5mm left margin)
5. **FIFTH**: Remove page 2 spacing tricks (just use normal page break)
6. **SIXTH**: Test visual alignment with original template

---

## 📏 CALCULATION: AVAILABLE VERTICAL SPACE

- **Page height**: 297mm
- **Top margin**: 20mm
- **Bottom margin**: 20mm
- **Available**: 297 - 20 - 20 = **257mm per page**
- **2 pages total**: 257 × 2 = **514mm available**
- **Current content estimate**: ~450mm (fits with buffer!)

✅ **Conclusion**: We have **plenty of space** - no need to compress spacing!

---

## ✨ EXCELLENCE CHECKLIST

Before rendering, verify:

- [ ] All margins exactly: 20/22.4/20/25mm
- [ ] All section margins: 6mm
- [ ] All entry margins: 3mm
- [ ] All bullet margins: 1.5mm
- [ ] Entry columns: **42.5mm | 1fr**
- [ ] Section titles: bold, small-caps, blue
- [ ] Bullet indent: 47.5mm left, 5mm hanging
- [ ] No profile section in template
- [ ] Sections in correct order
- [ ] Font sizes: 16pt name, 11pt everything else
- [ ] Font family: Arial throughout
- [ ] Text color: black (#000000)
- [ ] Section title color: blue (#0000FF)
- [ ] No decorative elements
- [ ] Page breaks clean (no orphaned headers)

---

## 🔒 THIS IS FINAL

These golden rules are **IMMUTABLE** and derive directly from the original DOCX template spec. Any deviation breaks the professional appearance and Swiss market standards.

**Changes are ONLY allowed if justified with reference to original spec.**

---

**Last Updated**: January 15, 2026  
**Status**: 🔒 LOCKED - REFERENCE ONLY
