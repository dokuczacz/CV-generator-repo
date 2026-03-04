from __future__ import annotations

from src.orchestrator.wizard.action_dispatch_cover_pdf import CoverPdfActionDeps, handle_cover_pdf_actions


def test_cover_letter_feedback_apply_stores_capsule_and_updates_draft() -> None:
    cv_data = {
        "work_experience": [
            {"title": "Operations Manager", "employer": "Company A", "date_range": "2020-01 - 2024-01", "bullets": ["Led operations"]}
        ]
    }
    meta = {
        "wizard_stage": "cover_letter_review",
        "job_reference": {"title": "Ops"},
        "cover_letter_block": {"opening_paragraph": "Old", "core_paragraphs": ["Old core"], "closing_paragraph": "Old close", "signoff": "Kind regards,\nJane"},
        "work_tailoring_notes": "Focus on regulated manufacturing.",
    }

    def wizard_set_stage(m: dict, stage: str) -> dict:
        out = dict(m)
        out["wizard_stage"] = stage
        return out

    def persist(cv: dict, m: dict):
        return cv, m

    def wizard_resp(*, assistant_text: str, meta_out: dict, cv_out: dict, **_kwargs):
        return 200, {"success": True, "response": assistant_text, "metadata": meta_out, "cv_data": cv_out}

    def generate_cover_letter_block_via_openai(**_kwargs):
        return True, {
            "opening_paragraph": "Updated opening with Company A.",
            "core_paragraphs": ["Updated core paragraph."],
            "closing_paragraph": "Updated closing.",
            "signoff": "Kind regards,\nJane",
        }, ""

    deps = CoverPdfActionDeps(
        wizard_set_stage=wizard_set_stage,
        persist=persist,
        wizard_resp=wizard_resp,
        cv_enable_cover_letter=True,
        log_info=lambda *_args, **_kwargs: None,
        openai_enabled=lambda: True,
        generate_cover_letter_block_via_openai=generate_cover_letter_block_via_openai,
        friendly_schema_error_message=lambda msg: msg,
        validate_cover_letter_block=lambda **_kwargs: (True, []),
        build_cover_letter_render_payload=lambda **_kwargs: {},
        render_cover_letter_pdf=lambda *_args, **_kwargs: b"",
        upload_pdf_blob_for_session=lambda **_kwargs: None,
        compute_cover_letter_download_name=lambda **_kwargs: "cover-letter.pdf",
        now_iso=lambda: "2026-02-25T12:00:00Z",
        wizard_get_stage=lambda m: str(m.get("wizard_stage") or ""),
        tool_generate_cv_from_session=lambda **_kwargs: (400, {"error": "not used"}, "application/json"),
        session_get=lambda _sid: None,
        sync_job_data_table_history=lambda **kwargs: dict(kwargs.get("meta") or {}),
    )

    handled, cv_out, meta_out, resp = handle_cover_pdf_actions(
        aid="COVER_LETTER_FEEDBACK_APPLY",
        user_action_payload={"cover_letter_feedback": "Please mention all roles and tighten opening."},
        cv_data=cv_data,
        meta2=meta,
        session_id="sess",
        trace_id="trace",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )

    assert handled is True
    assert isinstance(resp, tuple)
    assert cv_out is cv_data
    assert meta_out.get("cover_letter_feedback") == "Please mention all roles and tighten opening."
    assert meta_out.get("cover_letter_feedback_applied_at") == "2026-02-25T12:00:00Z"
    capsule = meta_out.get("cover_letter_feedback_capsule")
    assert isinstance(capsule, dict)
    assert capsule.get("feedback") == "Please mention all roles and tighten opening."
    assert isinstance(meta_out.get("cover_letter_block"), dict)
