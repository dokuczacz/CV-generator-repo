from src.render import render_html


def _cv_payload(language: str) -> dict:
    return {
        "language": language,
        "full_name": "Jan Kowalski",
        "email": "jan@example.com",
        "phone": "+41 77 111 22 33",
        "address_lines": ["Zer Chirchu 20", "3933 Staldenried"],
        "work_experience": [
            {
                "date_range": "2021-01 - 2024-01",
                "title": "Operations Manager",
                "employer": "Company A",
                "location": "Visp",
                "bullets": ["Led operational improvements."],
            }
        ],
        "it_ai_skills": ["Excel"],
        "technical_operational_skills": ["Kaizen"],
        "education": [
            {
                "date_range": "2018-01 - 2020-01",
                "institution": "Poznan University",
                "title": "MSc Engineering",
                "specialization": "Industrial systems",
                "details": ["Thesis on optimization."],
            }
        ],
        "languages": ["German (Intermediate)"],
        "interests": "Cycling",
        "references": "Available upon request.",
    }


def test_de_template_is_overlay_with_same_data_logic_as_en() -> None:
    html_en = render_html(_cv_payload("en"), inline_css=False)
    html_de = render_html(_cv_payload("de"), inline_css=False)

    for token in [
        "Jan Kowalski",
        "Company A",
        "Led operational improvements.",
        "Excel",
        "Kaizen",
        "Poznan University",
        "MSc Engineering",
        "German",
        "Cycling",
        "Available upon request.",
    ]:
        assert token in html_en
        assert token in html_de

    assert "Work experience" in html_en
    assert "Berufserfahrung" in html_de
