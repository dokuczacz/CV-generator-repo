from __future__ import annotations

import function_app


def test_bulk_translation_response_format_storage_includes_profile_and_further_experience() -> None:
    fmt = function_app._bulk_translation_response_format(mode="storage")
    schema = fmt["schema"]
    props = schema["properties"]
    required = set(schema["required"])

    assert "profile" in props
    assert "further_experience" in props
    assert "profile" in required
    assert "further_experience" in required


def test_bulk_translation_response_format_render_excludes_profile_and_further_experience() -> None:
    fmt = function_app._bulk_translation_response_format(mode="render")
    schema = fmt["schema"]
    props = schema["properties"]
    required = set(schema["required"])

    assert "profile" not in props
    assert "further_experience" not in props
    assert "profile" not in required
    assert "further_experience" not in required

    # Core contract still required for translation parity.
    assert "work_experience" in required
    assert "education" in required
    assert "it_ai_skills" in required
    assert "technical_operational_skills" in required
    assert "languages" in required
    assert "interests" in required
    assert "references" in required
