# CV-generator

Minimal, self-contained CV renderer for the 2-page template (HTML/CSS → PDF via Playwright).

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
python -m playwright install chromium
npm install

# Generate a quick local preview (uses samples/minimal_cv.json)
python src/render.py

# Start API server
python api.py

# Run deterministic template/DoD checks (Playwright)
npm test
```

## Structure
- `src/render.py` — Core rendering functions (HTML & PDF generation)
- `templates/CV_template_2pages_2025.spec.md` — Layout specification (reference)
- `templates/html/cv_template_2pages_2025.html` — Jinja2 HTML template
- `templates/html/cv_template_2pages_2025.css` — Stylesheet
- `api.py` — Flask API endpoint for GPT integration
- `tests/` — Playwright visual regression tests
- `samples/` — Reference outputs and test data
- `wzory/CV_template_2pages_2025.docx` — Original DOCX template (reference)
- `wzory/Lebenslauf_Mariusz_Horodecki_CH.docx` — Sample data source (reference)

## Install
```
pip install -r requirements.txt
python -m playwright install chromium
npm install
```

## Quick Test
```
python src/render.py
```
Generates `preview.html` and `preview.pdf` in the project root.

## API Server (for GPT Integration)
```
python api.py
```
Runs Flask server on http://localhost:5000

### Endpoints
- `POST /generate-cv` — Generate PDF from JSON
- `POST /preview-html` — Preview HTML from JSON
- `GET /health` — Health check

See [TESTING.md](TESTING.md) for detailed API usage and GPT integration.

## Playwright Testing
```
npm test              # Run all tests
npm run test:ui       # Interactive UI mode
npm run show-report   # View test report
```

Generate test artifacts:
```
python tests/generate_test_artifacts.py
```

See [FINAL_PROCESS.md](FINAL_PROCESS.md) for the exact “how we got here” playbook and pitfalls to avoid when mirroring a new DOCX template.

## API (Python)
```python
from src.render import render_html, render_pdf
html = render_html(cv_dict)
pdf_bytes = render_pdf(cv_dict)
```

## CV JSON fields (suggested)
```
full_name: str
address_lines: list[str]
phone: str
email: str
birth_date: str
nationality: str
profile: str
work_experience: [
  { date_range, employer, location, title, bullets: [..] }
]
education: [
  { date_range, institution, title, details: [..] }
]
languages: list[str]
it_ai_skills: list[str]
trainings: list[str]
interests: str
data_privacy: str
references: str
```

## Definition of Done (DoD)
- Custom GPT może uzupełnić wzorcowe CV, zwracając JSON z polami jak wyżej (teksty + listy).
- Backend potrafi przyjąć JSON, wyrenderować HTML (szablon `cv_template_2pages_2025.html`) i PDF (Playwright/Chromium), bez edycji layoutu przez GPT.
- PDF zapisuje się poprawnie i otwiera w czytnikach (prawidłowe linki mailto/URL).
- Wygenerowany plik ma taki sam styl i układ jak wzór 2-stronicowy (CV_template_2pages_2025).
- Źródłowy wzór DOCX (`templates/CV_template_2pages_2025.docx`) i przykładowe dane (`samples/Lebenslauf_Mariusz_Horodecki_CH.docx`) są w repo.
- Render samodzielny: `python src/render.py` tworzy `preview.pdf` na danych przykładowych.
