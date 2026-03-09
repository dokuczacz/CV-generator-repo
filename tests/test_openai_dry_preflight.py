from __future__ import annotations

from src.orchestrator.openai_client import OpenAIJsonSchemaDeps, _dry_test_preflight, openai_json_schema_call
from src import product_config


def _deps_enabled() -> OpenAIJsonSchemaDeps:
    return OpenAIJsonSchemaDeps(
        openai_enabled=lambda: True,
        openai_model=lambda: "gpt-4o-mini",
        get_openai_prompt_id=lambda _stage: None,
        require_openai_prompt_id=lambda: False,
        normalize_stage_env_key=lambda s: str(s or "").upper(),
        bulk_translation_output_budget=lambda user_text, requested: int(requested or 2400),
        coerce_int=lambda v, d: int(v) if str(v or "").strip() else int(d),
        schema_repair_instructions=lambda stage, parse_error: f"repair {stage} {parse_error}",
        now_iso=lambda: "2026-03-08T00:00:00Z",
    )


def test_dry_test_preflight_detects_missing_markers_for_cover_letter() -> None:
    ok, payload = _dry_test_preflight(
        stage="cover_letter",
        system_prompt="Return JSON",
        user_text="minimal text without required markers",
        response_format={"name": "cover"},
    )
    assert ok is False
    assert any(str(x).startswith("missing_markers:") for x in (payload.get("issues") or []))


def test_dry_test_preflight_passes_when_markers_present() -> None:
    ok, payload = _dry_test_preflight(
        stage="cover_letter",
        system_prompt="Return JSON",
        user_text="job context with cover section and work_experience evidence",
        response_format={"name": "cover"},
    )
    assert ok is True
    assert payload.get("issues") == []


def test_openai_call_blocked_when_dry_test_required_and_preflight_fails(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "DRY_TEST_MODE", "required", raising=False)
    monkeypatch.setattr(product_config, "DRY_TEST_ARTIFACTS", False, raising=False)

    ok, parsed, err = openai_json_schema_call(
        deps=_deps_enabled(),
        system_prompt="Return JSON",
        user_text="bad",
        response_format={"name": "cover"},
        stage="cover_letter",
        trace_id="trace-test",
        session_id="sess-test",
    )

    assert ok is False
    assert parsed is None
    assert "DRY_TEST_PRECHECK_FAILED" in str(err)
