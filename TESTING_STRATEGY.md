# 🧪 TESTING STRATEGY (Final)

This repo validates the template with **deterministic checks**, not pixel snapshots.

The primary goal is: **exactly 2 pages, fixed page break, and no section splits under print**.

## What is tested

### 1) Deterministic HTML/CSS assertions (Playwright)

Tests live in `tests/cv-visual.spec.ts` and validate:

- Header elements exist and have correct computed styles (font, weight, accent color)
- Photo box geometry is correct (mm-based sizing)
- Margins/padding match the DOCX-derived values
- Entry grid uses the correct date-column width (42.5mm)
- Section order is exactly as expected

### 2) Deterministic pagination assertions (Playwright print emulation)

The critical checks run under `page.emulateMedia({ media: 'print' })`:

- Exactly **one** `.page-break` exists
- Each `section.section` stays on a single page (no split)
- Sections start on the expected page (Education + Work on p1, the rest on p2)

This is done by measuring section bounding boxes and simulating the vertical shift introduced by forced page breaks.

### 3) PDF generation and page count (Chromium + PyPDF2)

PDF generation is done by Chromium (Playwright `page.pdf`).

DoD asserts:

- PDF page count is exactly **2** (validated via PyPDF2)

## How to run

1) Generate artifacts (HTML + PDF used by tests)

`python tests/generate_test_artifacts.py`

2) Run tests

`npm test`

3) Quick local preview

`python src/render.py` → writes `preview.html` and `preview.pdf` at repo root (using `samples/minimal_cv.json`).
