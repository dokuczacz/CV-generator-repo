# CV-generator

Minimal, self-contained CV renderer for the 2-page template (HTML/CSS → PDF via Playwright).

## Structure
- `templates/CV_template_2pages_2025.docx` — oryginalny wzór (referencja).
- `templates/html/cv_template_2pages_2025.html` — szablon HTML.
- `templates/html/cv_template_2pages_2025.css` — styl.
- `samples/Lebenslauf_Mariusz_Horodecki_CH.docx` — przykładowe dane źródłowe (referencja treści).
- `src/render.py` — funkcje renderujące (HTML i PDF).

## Install
```
pip install -r requirements.txt
python -m playwright install chromium
```

## Render
```
python src/render.py
```
Zapisze `preview.pdf` w katalogu głównym projektu.

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
references: str
```

## Definition of Done (DoD)
- Custom GPT może uzupełnić wzorcowe CV, zwracając JSON z polami jak wyżej (teksty + listy).
- Backend potrafi przyjąć JSON, wyrenderować HTML (szablon `cv_template_2pages_2025.html`) i PDF (Playwright/Chromium), bez edycji layoutu przez GPT.
- PDF zapisuje się poprawnie i otwiera w czytnikach (prawidłowe linki mailto/URL).
- Źródłowy wzór DOCX (`templates/CV_template_2pages_2025.docx`) i przykładowe dane (`samples/Lebenslauf_Mariusz_Horodecki_CH.docx`) są w repo.
- Render samodzielny: `python src/render.py` tworzy `preview.pdf` na danych przykładowych.
