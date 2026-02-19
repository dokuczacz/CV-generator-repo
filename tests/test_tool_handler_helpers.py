from function_app import (
    _backfill_missing_work_locations,
    _build_cover_letter_render_payload,
    _render_html_for_tool,
    _validate_cv_data_for_tool,
)


def test_validate_cv_data_for_tool_returns_schema_and_validation():
    cv_data = {
        "full_name": "A B",
        "email": "a@example.com",
        "phone": "+1 555 000 000",
        "work_experience": [{"employer": "ACME", "title": "Role", "date_range": "2020-2021", "bullets": ["Did X"]}],
        "education": [{"institution": "Uni", "title": "MSc", "date_range": "2010-2015"}],
        "languages": ["English (fluent)"],
        "it_ai_skills": [],
        "interests": "",
        "references": "",
    }

    out = _validate_cv_data_for_tool(cv_data)
    assert "schema_valid" in out
    assert "schema_errors" in out
    assert "validation" in out
    assert isinstance(out["validation"], dict)


def test_render_html_for_tool_returns_html():
    cv_data = {
        "full_name": "A B",
        "email": "a@example.com",
        "phone": "+1 555 000 000",
        "work_experience": [{"employer": "ACME", "title": "Role", "date_range": "2020-2021", "bullets": ["Did X"]}],
        "education": [{"institution": "Uni", "title": "MSc", "date_range": "2010-2015"}],
        "languages": ["English (fluent)"],
        "it_ai_skills": [],
        "interests": "",
        "references": "",
    }

    out = _render_html_for_tool(cv_data, inline_css=True)
    assert isinstance(out.get("html"), str)
    assert out.get("html_length", 0) == len(out["html"])


def test_cover_letter_payload_omits_recipient_company():
    cv_data = {
        "full_name": "A B",
        "email": "a@example.com",
        "phone": "+1 555 000 000",
        "address_lines": ["Street 1", "1000 City"],
    }
    meta = {"job_reference": {"company": "Lonza", "title": "Operational Excellence Manager"}}
    block = {
        "opening_paragraph": "Hello",
        "core_paragraphs": ["Core"],
        "closing_paragraph": "Bye",
    }

    payload = _build_cover_letter_render_payload(cv_data=cv_data, meta=meta, block=block)
    assert payload.get("recipient_company") == ""


def test_backfill_missing_work_locations_from_docx_prefill():
    cv_data = {
        "work_experience": [
            {
                "title": "Director",
                "employer": "GL Solutions Sp. Z o.o.",
                "date_range": "2020-01 - 2025-10",
                "location": "",
                "bullets": ["B1"],
            }
        ]
    }
    meta = {
        "docx_prefill_unconfirmed": {
            "work_experience": [
                {
                    "title": "Direktor",
                    "employer": "GL Solutions Sp. Z o.o.",
                    "date_range": "2020-01 – 2025-10",
                    "location": "Zielona Góra, Poland",
                    "bullets": [],
                }
            ]
        }
    }

    out = _backfill_missing_work_locations(cv_data=cv_data, previous_work=None, meta=meta)
    work = out.get("work_experience") if isinstance(out.get("work_experience"), list) else []
    assert work and isinstance(work[0], dict)
    assert work[0].get("location") == "Zielona Góra, Poland"


def test_backfill_hydrates_work_experience_when_empty():
    cv_data = {"work_experience": []}
    meta = {
        "docx_prefill_unconfirmed": {
            "work_experience": [
                {
                    "title": "Quality Manager",
                    "employer": "SE Bordnetze SRL",
                    "date_range": "2016-08 - 2018-11",
                    "location": "Orhei, Moldova",
                    "bullets": ["Built quality system"],
                }
            ]
        }
    }

    out = _backfill_missing_work_locations(cv_data=cv_data, previous_work=None, meta=meta)
    work = out.get("work_experience") if isinstance(out.get("work_experience"), list) else []
    assert len(work) == 1
    assert work[0].get("employer") == "SE Bordnetze SRL"
    assert work[0].get("location") == "Orhei, Moldova"

