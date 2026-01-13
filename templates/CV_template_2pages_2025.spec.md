# CV_template_2pages_2025 — layout specification (source: DOCX template)

This specification captures the **layout-only** rules derived from
`wzory/CV_template_2pages_2025.docx`. It is intended as a deterministic
reference for HTML/CSS rendering (content is provided separately).

## Page setup
- **Page size:** A4 portrait (210 × 297 mm).【F:wzory/CV_template_2pages_2025.docx†L1】
- **Margins (Word):**
  - Top: **1134 twips** ≈ **20.0 mm**
  - Right: **1270 twips** ≈ **22.4 mm**
  - Bottom: **1134 twips** ≈ **20.0 mm**
  - Left: **1418 twips** ≈ **25.0 mm**
- **Columns:** single column (no multi-column layout).【F:wzory/CV_template_2pages_2025.docx†L1】

## Typography
- **Font family:** Arial (document-wide).【F:wzory/CV_template_2pages_2025.docx†L1】
- **Font sizes used:** **11 pt**, **14 pt**, **16 pt**.
  - Default paragraph size is **11 pt**.
  - Headline/name uses **16 pt**.
  - Section headings use **11 pt** with small caps + bold.
- **Text color:** black (#000000).
- **Section heading color:** blue (#0000FF).【F:wzory/CV_template_2pages_2025.docx†L1】
- **Photo placeholder background:** light gray (#EEECE1).【F:wzory/CV_template_2pages_2025.docx†L1】

## Layout structure (single column)
The document is one continuous column with tab-aligned fields.

### Header
- **Name** at top, bold, 16 pt.
- **Contact block** as stacked lines (address, phone, email, birth date, nationality).

### Sections
Each section uses:
- **Title** in bold small caps, blue.
- **Content** in normal 11 pt body text.
- **No pill tags, badges, or multi-column grids**.

### Entry layout (tab alignment)
Entries use a tab-aligned left column for dates and a right column for
the corresponding role/description:
- **Tab stops:** ~**37.5 mm** and **42.5 mm** from left margin.
- **Effective date column width:** **~42.5 mm**.
- Body text remains left-aligned (no justification).

### Bullets
Bulleted lists use a **hanging indent**:
- Left indent: **~47.5 mm**
- Hanging indent: **~5.0 mm**

## HTML/CSS mapping guidance
Use a **single-column page** with:
- `padding: 20mm 22.4mm 20mm 25mm`
- `font-family: Arial, Helvetica, sans-serif`
- Section titles in small caps, bold, blue (`#0000FF`)
- Entry heads as a two-column grid (`42.5mm 1fr`)
- Bullets rendered with a dash and a 5mm hanging indent
