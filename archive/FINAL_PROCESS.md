# Final process (how we got to the 10/10 match)

This repo’s goal is **not** “a nice looking CV”. It is: **mirror the Zurich University 2‑page DOCX template into a deterministic HTML/CSS → PDF renderer**, and validate the result with **Definition of Done (DoD)** checks that are stable across machines.

## What is “final” in this repo

- **Template**: `templates/html/cv_template_2pages_2025.html` + `templates/html/cv_template_2pages_2025.css`
- **Renderer** (HTML + PDF + DoD checks): `src/render.py`
- **DOCX style extraction** (font + margins): `src/style_extractor.py`
- **Deterministic template tests**: `tests/cv-visual.spec.ts`
- **Artifact generator** (writes `tests/test-output/preview.html` + PDF): `tests/generate_test_artifacts.py`

## The reproducible workflow (step-by-step)

### 1) Mirror the DOCX structure in HTML first

- Recreate the DOCX *structure* (header, photo box, section titles, entries, bullets) in HTML.
- Keep HTML semantic and stable:
  - sections are `section.section`
  - titles are `.section-title`
  - entries use the `.entry` + `.entry-head` grid

Why: the DoD validation relies on stable selectors (it measures these nodes).

### 2) Use print-native CSS units for geometry

- Use **mm** for page padding, column widths, photo box dimensions.
- Keep typography in **pt**.

This avoids “pixel drift” between environments.

### 3) Make pagination deterministic

The template is hard-2-page with a fixed split.

- Use an explicit page break element in HTML:
  - `<div class="page-break"></div>`
- In CSS, enforce it under print:
  - `break-before: page;` / `page-break-before: always;`

Also enforce “no section split”:
- `section.section { break-inside: avoid; page-break-inside: avoid; }`

### 4) Validate pagination deterministically (no screenshots)

We moved away from screenshot-based tests (flaky) and use **deterministic assertions**:

- Playwright loads `tests/test-output/preview.html`
- It emulates print media: `page.emulateMedia({ media: 'print' })`
- It measures each section’s bounding box and **simulates the vertical shift introduced by forced page breaks**
- Assertions:
  - exactly **1** `.page-break`
  - each section stays on exactly one page (no split)
  - expected sections start on expected pages

Additionally, PDF generation is validated:
- PDF is generated via Chromium’s print engine
- Page count is verified via PyPDF2 (must be exactly **2**)

### 5) Extract styles from DOCX the “reliable” way

`python-docx` often returns `None` for font sizes because Word styles are inherited.

Final reliable approach:

- Read `word/styles.xml` directly from the DOCX (zip)
  - use `docDefaults/w:rPrDefault/w:rPr` for default font + size + color
- For specific paragraphs (name, section title, body):
  - prefer **run-level XML overrides** (`w:rPr/w:sz`, `w:rFonts`, `w:color`)
  - then fall back through style chain (basedOn)
  - then fall back to `Normal`
  - then fall back to docDefaults

Pitfall to avoid:
- **Do not treat `python-docx` Length objects as numbers**. Use `.pt` when available. DOCX `w:sz` is stored in half-points.

### 6) Windows file locking: make artifact generation robust

On Windows, `preview.pdf` can be locked by a PDF viewer.

Final behavior in `tests/generate_test_artifacts.py`:
- try `preview.pdf`
- fallback `preview.generated.pdf`
- fallback timestamped `preview.generated-YYYYMMDD-HHMMSS.pdf`

## Best practices (what to do again)

- Validate layout via **DOM measurements**, not screenshots.
- Keep selectors stable (tests depend on them).
- Use mm/pt for print fidelity.
- Force pagination explicitly; don’t “hope” it lands on 2 pages.
- Extract DOCX defaults from `styles.xml` to avoid missing values.

## Things to avoid (what caused the earlier issues)

- Snapshot/pixel regression as the primary correctness signal (too environment dependent)
- Absolute-positioned header “clearance hacks” (easy to regress; causes overlaps)
- Guessing font sizes when `python-docx` returns None (must use docDefaults/run XML)
- Overwriting PDFs on Windows without a fallback strategy

## How to run the final pipeline

- Generate regression artifacts:
  - `python tests/generate_test_artifacts.py`
- Run deterministic DoD tests:
  - `npm test`
- Quick local preview (minimal always-valid input):
  - `python src/render.py` → writes `preview.html` and `preview.pdf`

## Incoming JSON compatibility notes

The template expects `interests` as a single string, but GPTs often return an array.
The backend normalizes these payloads:

- `interests`: string OR list of strings (list is joined with `; `)
- `professional_summary`: optional list/string; mapped to `profile` for compatibility (the current Zurich template does not render a separate summary section)
