from __future__ import annotations

from types import SimpleNamespace

from src.render import count_pdf_pages, render_cover_letter_pdf
from src.i18n import get_cover_letter_signoff


def test_cover_letter_pdf_renders_one_page() -> None:
    payload = {
        "sender_name": "Jane Doe",
        "sender_email": "jane@example.com",
        "sender_phone": "+41 00 000 00 00",
        "sender_address": "Zurich, Switzerland",
        "date": "2026-02-04",
        "recipient_company": "Acme AG",
        "recipient_job_title": "Project Manager Engineering",
        "opening_paragraph": "I am an engineering project manager with experience in process optimization and delivery.",
        "core_paragraphs": [
            "I have led cross-functional initiatives to improve quality, standardize workflows, and reduce operational waste.",
            "In parallel, I build lightweight automation and reporting systems to support decision-making and execution.",
        ],
        "closing_paragraph": "I would welcome the opportunity to discuss how my experience aligns with your needs.",
        "signoff": "Kind regards,\nJane Doe",
    }
    pdf = render_cover_letter_pdf(payload, enforce_one_page=True, use_cache=False)
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 5_000
    assert count_pdf_pages(bytes(pdf)) == 1


def test_cover_letter_validation_rejects_bullets() -> None:
    import function_app as app

    cv_data = {"full_name": "Jane Doe"}
    block = {
        "opening_paragraph": "Opening paragraph.",
        "core_paragraphs": ["- Bullet-like line should fail"],
        "closing_paragraph": "Closing paragraph.",
        "signoff": "Kind regards,\nJane Doe",
    }
    ok, errs = app._validate_cover_letter_block(block=block, cv_data=cv_data)
    assert ok is False
    assert any("Bullet" in e or "bullet" in e.lower() for e in errs)


def test_cover_letter_signoff_translations() -> None:
    """Test that cover letter signoffs are correctly translated."""
    # Test English
    en_signoff = get_cover_letter_signoff("en")
    assert en_signoff == "Kind regards"
    
    # Test German
    de_signoff = get_cover_letter_signoff("de")
    assert de_signoff == "Mit freundlichen Grüßen"
    
    # Test Polish
    pl_signoff = get_cover_letter_signoff("pl")
    assert pl_signoff == "Z poważaniem"
    
    # Test fallback for unknown language
    fr_signoff = get_cover_letter_signoff("fr")
    assert fr_signoff == "Kind regards"  # Falls back to English


def test_cover_letter_german_signoff_formatting() -> None:
    """Test that German cover letter uses correct signoff."""
    de_signoff = get_cover_letter_signoff("de")
    full_name = "Mariusz Horodecki"
    signoff = f"{de_signoff},\n{full_name}"
    
    # Verify correct German closing
    assert signoff == "Mit freundlichen Grüßen,\nMariusz Horodecki"
    
    # Test PDF rendering with German signoff
    payload = {
        "sender_name": full_name,
        "sender_email": "mariusz@example.com",
        "sender_phone": "+41 00 000 00 00",
        "sender_address": "Zürich, Schweiz",
        "date": "2026-02-05",
        "recipient_company": "Lonza AG",
        "recipient_job_title": "Senior Engineer",
        "opening_paragraph": "Ich bin ein erfahrener Ingenieur mit Schwerpunkt auf Prozessoptimierung.",
        "core_paragraphs": [
            "Ich habe mehrere erfolgreiche Projekte geleitet.",
        ],
        "closing_paragraph": "Ich würde mich freuen, meine Erfahrung einzubringen.",
        "signoff": signoff,
    }
    pdf = render_cover_letter_pdf(payload, enforce_one_page=True, use_cache=False)
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 5_000
    assert count_pdf_pages(bytes(pdf)) == 1


def test_cover_letter_generation_retries_for_missing_role_references(monkeypatch) -> None:
    import function_app as app

    cv_data = {
        "full_name": "Jane Doe",
        "work_experience": [
            {"title": "Operations Manager", "employer": "Company Alpha", "date_range": "2021-01 - 2024-01", "bullets": ["Led operations"]},
            {"title": "Quality Engineer", "employer": "Company Beta", "date_range": "2018-01 - 2020-12", "bullets": ["Improved quality"]},
        ],
        "it_ai_skills": ["Lean", "KPI"],
        "technical_operational_skills": ["FMEA"],
    }
    meta = {"job_reference": {"title": "Ops Lead"}}

    monkeypatch.setattr(app, "format_job_reference_for_display", lambda _jr: "Operations leadership role")
    monkeypatch.setattr(app, "_build_ai_system_prompt", lambda **_kwargs: "prompt")

    calls: list[dict] = []

    def _openai_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return True, {"opening": "I worked at Company Alpha.", "core": ["I led operations."], "closing": "Thank you."}, None
        return True, {"opening": "I worked at Company Alpha and Company Beta.", "core": ["As Operations Manager and Quality Engineer, I delivered results."], "closing": "Thank you."}, None

    monkeypatch.setattr(app, "_openai_json_schema_call", _openai_call)

    def _parse(payload):
        return SimpleNamespace(
            opening_paragraph=str(payload.get("opening") or ""),
            core_paragraphs=list(payload.get("core") or []),
            closing_paragraph=str(payload.get("closing") or ""),
            notes="",
        )

    monkeypatch.setattr(app, "parse_cover_letter_proposal", _parse)

    ok, block, err = app._generate_cover_letter_block_via_openai(
        cv_data=cv_data,
        meta=meta,
        trace_id="trace",
        session_id="session",
        target_language="en",
    )

    assert ok is True, err
    assert isinstance(block, dict)
    assert len(calls) == 2
    assert "[ROLE_CHECKLIST]" in str(calls[0].get("user_text") or "")
