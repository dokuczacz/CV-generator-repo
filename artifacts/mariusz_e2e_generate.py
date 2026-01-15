from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes  # noqa: E402
from src.normalize import normalize_cv_data  # noqa: E402
from src.render import render_pdf  # noqa: E402
from src.validator import validate_cv  # noqa: E402


def main() -> None:
    repo_root = REPO_ROOT

    cv_json = r'''
{
  "full_name": "Mariusz Horodecki",
  "email": "mariusz.horodecki@example.com",
  "address_lines": ["Zer Chirchu 20", "3933 Staldenried"],
  "profile": "Project and operations leader with 10+ years in quality systems and process optimisation. Led cross-functional teams and Greenfield projects in regulated environments. Strong background in production and quality engineering with focus on automation and AI-supported productivity.",
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
        "Supervised sites, subcontractors and compliance with legal and safety rules",
        "Applied planning and cost tools to optimise on-site execution"
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
        "Managed complaints and continuous product optimisation",
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
        "Led five sections with approximately 80 employees",
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
    },
    {
      "date_range": "2025-05 – 2025-05",
      "employer": "Imbodden AG",
      "location": "Visp, Switzerland",
      "title": "Construction Worker",
      "bullets": [
        "Performed manual work on civil engineering and road construction sites",
        "Supported excavation, pipe laying and site logistics",
        "Handled materials and basic machine operations safely"
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
  "further_experience": [],
  "interests": "Systems thinking and workflow optimisation; process automation and planning architectures; long-distance cycling, outdoor activities and hiking; applied artificial intelligence and language models"
}
'''

    cv_data = json.loads(cv_json)

    # Inject photo from the source DOCX (same behavior as /generate-cv-action)
    docx_path = repo_root / "wzory" / "Lebenslauf_Mariusz_Horodecki_CH.docx"
    photo_uri = extract_first_photo_data_uri_from_docx_bytes(docx_path.read_bytes())
    if photo_uri:
        cv_data["photo_url"] = photo_uri

    cv_data = normalize_cv_data(cv_data)

    validation = validate_cv(cv_data)
    if not validation.is_valid:
        raise SystemExit(
            "VALIDATION_FAILED\n"
            + "\n".join([f"- {e.field}: {e.message}" for e in validation.errors])
        )

    pdf_bytes = render_pdf(cv_data)
    out_pdf = repo_root / "artifacts" / "mariusz_e2e.pdf"
    out_pdf.write_bytes(pdf_bytes)

    # Verify page count (should be exactly 2)
    from PyPDF2 import PdfReader
    import io

    pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    print("Wrote:", out_pdf)
    print("PDF bytes:", len(pdf_bytes))
    print("PyPDF2 pages:", pages)


if __name__ == "__main__":
    main()
