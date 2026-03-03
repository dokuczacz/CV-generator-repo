from src.render import render_cover_letter_html, render_html


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


def test_render_cover_letter_uses_english_template_by_default() -> None:
    payload = {
        "sender_name": "Max Mustermann",
        "date": "2026-03-03",
        "opening_paragraph": "Hello",
        "core_paragraphs": ["Core"],
        "closing_paragraph": "Closing",
        "signoff": "Kind regards,\nMax Mustermann",
    }
    html = render_cover_letter_html(payload, inline_css=False)
    assert '<html lang="en">' in html
    assert "<title>Cover Letter</title>" in html


def test_render_cover_letter_uses_german_template_for_de_language() -> None:
    payload = {
        "language": "de",
        "sender_name": "Max Mustermann",
        "date": "2026-03-03",
        "opening_paragraph": "Hallo",
        "core_paragraphs": ["Kern"],
        "closing_paragraph": "Abschluss",
        "signoff": "Mit freundlichen Grüßen,\nMax Mustermann",
    }
    html = render_cover_letter_html(payload, inline_css=False)
    assert '<html lang="de">' in html
    assert "<title>Anschreiben</title>" in html
