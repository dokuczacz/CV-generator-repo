from __future__ import annotations

from src.orchestrator.wizard.action_dispatch_cover_pdf import CoverPdfActionDeps, handle_cover_pdf_actions


def _deps_with_counter(counter: dict) -> CoverPdfActionDeps:
    def wizard_set_stage(m: dict, stage: str) -> dict:
        out = dict(m)
        out["wizard_stage"] = stage
        return out

    def persist(cv: dict, m: dict):
        return cv, m

    def wizard_resp(*, assistant_text: str, meta_out: dict, cv_out: dict, **_kwargs):
        return 200, {"success": True, "response": assistant_text, "metadata": meta_out, "cv_data": cv_out}

    def generate_cover_letter_block_via_openai(**_kwargs):
        counter["calls"] = int(counter.get("calls") or 0) + 1
        return True, {
            "opening_paragraph": "Opening",
            "core_paragraphs": ["Core"],
            "closing_paragraph": "Closing",
            "signoff": "Kind regards,\nJane",
        }, ""

    return CoverPdfActionDeps(
        wizard_set_stage=wizard_set_stage,
        persist=persist,
        wizard_resp=wizard_resp,
        cv_enable_cover_letter=True,
        log_info=lambda *_args, **_kwargs: None,
        openai_enabled=lambda: True,
        generate_cover_letter_block_via_openai=generate_cover_letter_block_via_openai,
        friendly_schema_error_message=lambda msg: str(msg),
        validate_cover_letter_block=lambda **_kwargs: (True, []),
        build_cover_letter_render_payload=lambda **_kwargs: {},
        render_cover_letter_pdf=lambda *_args, **_kwargs: b"",
        upload_pdf_blob_for_session=lambda **_kwargs: None,
        compute_cover_letter_download_name=lambda **_kwargs: "cover.pdf",
        now_iso=lambda: "2026-03-06T12:00:00Z",
        wizard_get_stage=lambda m: str(m.get("wizard_stage") or ""),
        tool_generate_cv_from_session=lambda **_kwargs: (400, {"error": "not used"}, "application/json"),
        session_get=lambda _sid: None,
        sync_job_data_table_history=lambda **kwargs: dict(kwargs.get("meta") or {}),
    )


def test_cover_letter_preview_regenerates_when_work_tailoring_notes_change() -> None:
    counter: dict[str, int] = {"calls": 0}
    deps = _deps_with_counter(counter)

    cv_data = {
        "full_name": "Jane Doe",
        "work_experience": [
            {
                "title": "Engineer",
                "employer": "ACME",
                "date_range": "2020-01 - 2024-01",
                "bullets": ["Did X"],
            }
        ],
    }
    meta = {
        "wizard_stage": "cover_letter_review",
        "language": "en",
        "target_language": "de",
        "current_job_sig": "job-sig-1",
        "job_reference": {"title": "Industrialization Engineer"},
        "work_tailoring_notes": "note-a",
    }

    handled1, _cv1, meta1, resp1 = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta,
        session_id="sess",
        trace_id="trace-1",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )
    assert handled1 is True
    assert resp1 and resp1[0] == 200
    assert counter["calls"] == 1

    handled2, _cv2, _meta2, resp2 = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta1,
        session_id="sess",
        trace_id="trace-2",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )
    assert handled2 is True
    assert resp2 and resp2[0] == 200
    assert counter["calls"] == 1

    meta_changed = dict(meta1)
    meta_changed["work_tailoring_notes"] = "note-b"
    handled3, _cv3, _meta3, resp3 = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta_changed,
        session_id="sess",
        trace_id="trace-3",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )
    assert handled3 is True
    assert resp3 and resp3[0] == 200
    assert counter["calls"] == 2


def test_cover_letter_preview_cover_only_variant_ignores_work_notes_changes() -> None:
    counter: dict[str, int] = {"calls": 0}
    deps = _deps_with_counter(counter)

    cv_data = {
        "full_name": "Jane Doe",
        "work_experience": [
            {
                "title": "Engineer",
                "employer": "ACME",
                "date_range": "2020-01 - 2024-01",
                "bullets": ["Did X"],
            }
        ],
    }
    meta = {
        "wizard_stage": "cover_letter_review",
        "language": "en",
        "target_language": "de",
        "current_job_sig": "job-sig-1",
        "job_reference": {"title": "Industrialization Engineer"},
        "work_tailoring_notes": "work-note-a",
        "cover_letter_tailoring_notes": "cover-note-a",
        "cover_letter_notes_variant": "cover_only",
    }

    handled1, _cv1, meta1, resp1 = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta,
        session_id="sess",
        trace_id="trace-1",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )
    assert handled1 is True
    assert resp1 and resp1[0] == 200
    assert counter["calls"] == 1

    meta_changed_work = dict(meta1)
    meta_changed_work["work_tailoring_notes"] = "work-note-b"
    handled2, _cv2, _meta2, resp2 = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta_changed_work,
        session_id="sess",
        trace_id="trace-2",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )
    assert handled2 is True
    assert resp2 and resp2[0] == 200
    assert counter["calls"] == 1, "cover_only variant should ignore work tailoring notes changes"

    meta_changed_cover = dict(meta1)
    meta_changed_cover["cover_letter_tailoring_notes"] = "cover-note-b"
    handled3, _cv3, _meta3, resp3 = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta_changed_cover,
        session_id="sess",
        trace_id="trace-3",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )
    assert handled3 is True
    assert resp3 and resp3[0] == 200
    assert counter["calls"] == 2, "changing cover letter tailoring notes should trigger regeneration"
