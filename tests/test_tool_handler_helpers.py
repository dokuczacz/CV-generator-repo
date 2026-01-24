from function_app import _render_html_for_tool, _validate_cv_data_for_tool


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

