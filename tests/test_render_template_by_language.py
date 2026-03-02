from src.render import render_html


def _minimal_cv(language: str | None = None) -> dict:
    cv = {
        "full_name": "Max Mustermann",
        "email": "max@example.com",
        "phone": "+49 123 456 789",
        "work_experience": [
            {
                "date_range": "2020 - 2024",
                "title": "Engineer",
                "employer": "Example GmbH",
                "location": "Berlin",
                "bullets": ["Did something useful."],
            }
        ],
        "education": [],
        "languages": [],
        "interests": "",
    }
    if language is not None:
        cv["language"] = language
    return cv


def test_render_html_uses_english_template_by_default() -> None:
    html = render_html(_minimal_cv(), inline_css=False)
    assert "Work experience" in html


def test_render_html_uses_german_template_for_de_language() -> None:
    html = render_html(_minimal_cv("de"), inline_css=False)
    assert "Berufserfahrung" in html
    assert "Work experience" not in html
