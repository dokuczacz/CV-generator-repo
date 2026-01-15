from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PyPDF2 import PdfReader  # noqa: E402

from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes  # noqa: E402
from src.normalize import normalize_cv_data  # noqa: E402
from src.render import render_pdf  # noqa: E402
from src.validator import validate_cv  # noqa: E402


def main() -> None:
    # Compact variant intended to satisfy the strict 2-page DoD.
    cv_json = r'''
{
  "full_name": "Mariusz Horodecki",
  "email": "mariusz.horodecki@example.com",
  "address_lines": ["Zer Chirchu 20", "3933 Staldenried"],
  "profile": "Project and operations leader with 10+ years in quality systems and process optimisation. Led cross-functional teams and Greenfield projects in regulated environments.",
  "photo_url": "",
  "work_experience": [
    {
      "date_range": "2020-01 – 2025-04",
      "employer": "GL Solutions",
      "location": "Poland / Switzerland",
      "title": "Director",
      "bullets": [
        "Planned and coordinated road and infrastructure projects in public and private sectors",
        "Managed schedules, budgets and final documentation for complex projects",
        "Supervised sites, subcontractors and compliance with legal and safety rules"
      ]
    },
    {
      "date_range": "2018-11 – 2020-01",
      "employer": "Expondo Polska Sp. z o.o.",
      "location": "Poland",
      "title": "Head of Quality & Product Service",
      "bullets": [
        "Led three departments with a total of 35 employees",
        "Ensured CE conformity and introduced KPI dashboards",
        "Standardised internal processes to improve efficiency"
      ]
    },
    {
      "date_range": "2016-08 – 2018-11",
      "employer": "SE Bordnetze SRL",
      "location": "Moldova",
      "title": "Quality Manager (Greenfield Project)",
      "bullets": [
        "Built quality processes for a Greenfield manufacturing plant",
        "Implemented VDA, Formel-Q and IATF standards",
        "Main contact for OEM customers and certification bodies"
      ]
    },
    {
      "date_range": "2011-03 – 2016-07",
      "employer": "Sumitomo Electric Bordnetze SE",
      "location": "Global",
      "title": "Global Process Improvement Specialist",
      "bullets": [
        "Optimised production workplaces using time studies and data analysis",
        "Reduced costs through efficient production solutions",
        "Coordinated global audits and benchmarking as lead auditor"
      ]
    }
  ],
  "education": [
    {
      "date_range": "2012 – 2015",
      "institution": "Poznań University of Technology",
      "title": "Master of Science in Electrical Engineering",
      "details": ["Specialisation: Industrial and automotive systems"]
    },
    {
      "date_range": "2008 – 2012",
      "institution": "Poznań University of Technology",
      "title": "Bachelor of Engineering in Electrical Engineering",
      "details": ["Specialisation: Microprocessor control systems"]
    }
  ],
  "languages": ["Polish — Native", "English — Fluent", "German — Intermediate"],
  "it_ai_skills": [
    "Technical project management (CAPEX/OPEX)",
    "Quality systems: IATF, VDA, CE, Formel-Q",
    "Process optimisation: FMEA, PDCA, 5 Why",
    "Automation and AI-supported reporting (GPT)"
  ],
  "further_experience": [
    {
      "date_range": "2025-05 – 2025-05",
      "organization": "Imbodden AG",
      "title": "Construction Worker",
      "bullets": [
        "Supported excavation, pipe laying and site logistics",
        "Handled materials and basic machine operations safely"
      ]
    }
  ],
  "interests": "Systems thinking; workflow optimisation; long-distance cycling; hiking; applied AI"
}
'''

    cv_data = json.loads(cv_json)

    # Inject photo from the source DOCX.
    docx_path = REPO_ROOT / "wzory" / "Lebenslauf_Mariusz_Horodecki_CH.docx"
    photo_uri = extract_first_photo_data_uri_from_docx_bytes(docx_path.read_bytes())
    if photo_uri:
        cv_data["photo_url"] = photo_uri

    cv_data = normalize_cv_data(cv_data)

    validation = validate_cv(cv_data)
    if not validation.is_valid:
        raise SystemExit(
            "VALIDATION_FAILED\n" + "\n".join([f"- {e.field}: {e.message}" for e in validation.errors])
        )

    pdf_bytes = render_pdf(cv_data)
    out_pdf = REPO_ROOT / "artifacts" / "mariusz_e2e_compact.pdf"
    out_pdf.write_bytes(pdf_bytes)

    pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    print("Wrote:", out_pdf)
    print("PDF bytes:", len(pdf_bytes))
    print("PyPDF2 pages:", pages)


if __name__ == "__main__":
    main()
