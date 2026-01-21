"""
Diagnostic script: shows what CV data is being rendered and basic PDF metadata.
Run this and share the output (or a screenshot).
"""
from pathlib import Path
import sys
import json

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from src.normalize import normalize_cv_data
from src.render import render_pdf, render_html
from src.validator import validate_cv

# Use the same CV data as mariusz_e2e_generate.py
cv_json = r'''
{
  "full_name": "Mariusz Horodecki",
  "email": "mariusz.horodecki@example.com",
  "address_lines": ["Zer Chirchu 20", "3933 Staldenried"],
  "profile": "Project and operations leader with 10+ years in quality systems and process optimisation.",
  "photo_url": "",
  "work_experience": [
    {
      "date_range": "2020-01 – 2025-04",
      "employer": "GL Solutions",
      "location": "Poland / Switzerland",
      "title": "Director",
      "bullets": [
        "Planned and coordinated road and infrastructure projects",
        "Managed schedules, budgets and final documentation"
      ]
    }
  ],
  "education": [
    {
      "date_range": "2012 – 2015",
      "institution": "Poznań University of Technology",
      "title": "Master of Science in Electrical Engineering",
      "details": ["Specialisation: Industrial systems"]
    }
  ],
  "languages": ["Polish — Native", "English — Fluent"],
  "it_ai_skills": ["Quality systems: IATF, VDA"],
  "further_experience": [],
  "interests": "Systems thinking"
}
'''

cv_data = json.loads(cv_json)
print("=== RAW CV_DATA ===")
print(json.dumps(cv_data, indent=2, ensure_ascii=False)[:500])

cv_data = normalize_cv_data(cv_data)
print("\n=== NORMALIZED CV_DATA ===")
print(json.dumps(cv_data, indent=2, ensure_ascii=False)[:500])

validation = validate_cv(cv_data)
print(f"\n=== VALIDATION ===")
print(f"is_valid={validation.is_valid}")
if validation.errors:
    for e in validation.errors[:3]:
        print(f"  - {e.field}: {e.message}")

html = render_html(cv_data, inline_css=True)
print(f"\n=== HTML ===")
print(f"length={len(html)}")
print(f"contains 'Mariusz'={('Mariusz' in html)}")
print(f"contains 'GL Solutions'={('GL Solutions' in html)}")

pdf_bytes = render_pdf(cv_data)
print(f"\n=== PDF ===")
print(f"bytes={len(pdf_bytes)}")
print(f"first_50_bytes={pdf_bytes[:50]}")

# Write diagnostic outputs
out = REPO / "tmp" / "diagnose"
out.mkdir(parents=True, exist_ok=True)
(out / "cv_data.json").write_text(json.dumps(cv_data, indent=2, ensure_ascii=False), encoding="utf-8")
(out / "output.html").write_text(html, encoding="utf-8")
(out / "output.pdf").write_bytes(pdf_bytes)

print(f"\n✓ Wrote: tmp/diagnose/cv_data.json, output.html, output.pdf")
print("Please share this terminal output or a screenshot.")
