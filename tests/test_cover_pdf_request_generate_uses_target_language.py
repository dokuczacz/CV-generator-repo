from __future__ import annotations

from src.orchestrator.wizard.action_dispatch_cover_pdf import CoverPdfActionDeps, handle_cover_pdf_actions


def test_request_generate_pdf_uses_target_language_from_metadata() -> None:
    called: dict = {}

    def _wizard_set_stage(meta: dict, stage: str) -> dict:
        out = dict(meta)
        out["wizard_stage"] = stage
        return out

    def _persist(cv: dict, meta: dict):
        return cv, meta

    def _wizard_resp(*, assistant_text: str, meta_out: dict, cv_out: dict, **_kwargs):
        return 200, {"assistant_text": assistant_text, "metadata": meta_out, "cv_data": cv_out}

    def _tool_generate_cv_from_session(*, session_id: str, language: str | None, client_context, session):
        called["language"] = language
        return 200, {"pdf_bytes": b"%PDF-1.4", "pdf_metadata": {"pdf_ref": "abc"}}, "application/pdf"

    deps = CoverPdfActionDeps(
        wizard_set_stage=_wizard_set_stage,
        persist=_persist,
        wizard_resp=_wizard_resp,
        cv_enable_cover_letter=False,
        log_info=lambda *_args, **_kwargs: None,
        openai_enabled=lambda: True,
        generate_cover_letter_block_via_openai=lambda **_kwargs: (False, None, "unused"),
        friendly_schema_error_message=lambda msg: str(msg),
        validate_cover_letter_block=lambda **_kwargs: (True, []),
        build_cover_letter_render_payload=lambda **_kwargs: {},
        render_cover_letter_pdf=lambda *_args, **_kwargs: b"",
        upload_pdf_blob_for_session=lambda **_kwargs: None,
        compute_cover_letter_download_name=lambda **_kwargs: "cover.pdf",
        now_iso=lambda: "2026-03-02T15:00:00Z",
        wizard_get_stage=lambda m: str(m.get("wizard_stage") or ""),
        tool_generate_cv_from_session=_tool_generate_cv_from_session,
        session_get=lambda _sid: {"cv_data": {}, "metadata": {"target_language": "de", "language": "en"}},
    )

    handled, _cv_out, _meta_out, resp = handle_cover_pdf_actions(
        aid="REQUEST_GENERATE_PDF",
        user_action_payload=None,
        cv_data={},
        meta2={"target_language": "de", "language": "en", "wizard_stage": "review_final"},
        session_id="sess-1",
        trace_id="trace-1",
        stage_now="review_final",
        language="en",
        client_context=None,
        deps=deps,
    )

    assert handled is True
    assert isinstance(resp, tuple)
    assert called.get("language") == "de"


def test_download_pdf_returns_wizard_response_shape() -> None:
    def _wizard_set_stage(meta: dict, stage: str) -> dict:
        out = dict(meta)
        out["wizard_stage"] = stage
        return out

    def _persist(cv: dict, meta: dict):
        return cv, meta

    def _wizard_resp(*, assistant_text: str, meta_out: dict, cv_out: dict, **_kwargs):
        return 200, {"assistant_text": assistant_text, "metadata": meta_out, "cv_data": cv_out}

    def _tool_generate_cv_from_session(*, session_id: str, language: str | None, client_context, session):
        return 200, {"pdf_bytes": b"%PDF-1.4", "pdf_metadata": {"pdf_ref": "abc"}}, "application/pdf"

    deps = CoverPdfActionDeps(
        wizard_set_stage=_wizard_set_stage,
        persist=_persist,
        wizard_resp=_wizard_resp,
        cv_enable_cover_letter=False,
        log_info=lambda *_args, **_kwargs: None,
        openai_enabled=lambda: True,
        generate_cover_letter_block_via_openai=lambda **_kwargs: (False, None, "unused"),
        friendly_schema_error_message=lambda msg: str(msg),
        validate_cover_letter_block=lambda **_kwargs: (True, []),
        build_cover_letter_render_payload=lambda **_kwargs: {},
        render_cover_letter_pdf=lambda *_args, **_kwargs: b"",
        upload_pdf_blob_for_session=lambda **_kwargs: None,
        compute_cover_letter_download_name=lambda **_kwargs: "cover.pdf",
        now_iso=lambda: "2026-03-02T15:00:00Z",
        wizard_get_stage=lambda m: str(m.get("wizard_stage") or ""),
        tool_generate_cv_from_session=_tool_generate_cv_from_session,
        session_get=lambda _sid: {"cv_data": {}, "metadata": {"target_language": "en", "language": "en"}},
    )

    handled, _cv_out, _meta_out, resp = handle_cover_pdf_actions(
        aid="DOWNLOAD_PDF",
        user_action_payload=None,
        cv_data={},
        meta2={"target_language": "en", "language": "en", "wizard_stage": "review_final"},
        session_id="sess-2",
        trace_id="trace-2",
        stage_now="review_final",
        language="en",
        client_context=None,
        deps=deps,
    )

    assert handled is True
    assert isinstance(resp, tuple)
    assert len(resp) == 2
    assert isinstance(resp[1], dict)
