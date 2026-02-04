from __future__ import annotations

from src.render import count_pdf_pages, render_cover_letter_pdf


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

