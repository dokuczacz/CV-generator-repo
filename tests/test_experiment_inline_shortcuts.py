from __future__ import annotations

from src import product_config
from src.orchestrator.wizard.action_dispatch_cover_pdf import CoverPdfActionDeps, handle_cover_pdf_actions
from src.orchestrator.wizard.action_dispatch_skills import SkillsActionDeps, handle_skills_actions


def test_skills_tailor_run_uses_existing_combined_proposal_in_experiment(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "EXPERIMENT_MODE", "variant_split", raising=False)

    deps = SkillsActionDeps(
        wizard_set_stage=lambda m, st: {**dict(m or {}), "wizard_stage": st},
        persist=lambda cv, m: (cv, m),
        wizard_resp=lambda **kw: (200, {"response": kw.get("assistant_text", "")}),
        append_event=lambda *_a, **_kw: None,
        sha256_text=lambda s: "h:" + str(len(str(s))),
        now_iso=lambda: "2026-03-08T00:00:00Z",
        openai_enabled=lambda: True,
        format_job_reference_for_display=lambda _jr: "job",
        escape_user_input_for_prompt=lambda s: str(s or ""),
        collect_raw_docx_skills_context=lambda **_kw: [],
        sanitize_for_prompt=lambda s: str(s or ""),
        openai_json_schema_call=lambda **_kw: (_ for _ in ()).throw(AssertionError("OpenAI call should be skipped")),
        build_ai_system_prompt=lambda **_kw: "prompt",
        get_skills_unified_proposal_response_format=lambda: {},
        friendly_schema_error_message=lambda e: str(e),
        parse_skills_unified_proposal=lambda d: d,
        dedupe_strings_case_insensitive=lambda xs, max_items=8: list(xs or [])[:max_items],
        find_work_bullet_hard_limit_violations=lambda **_kw: [],
        snapshot_session=lambda *_a, **_kw: None,
    )

    meta = {
        "wizard_stage": "it_ai_skills",
        "skills_proposal_block": {
            "it_ai_skills": ["Python"],
            "technical_operational_skills": ["Kaizen"],
            "experiment_mode": "variant_split",
        },
    }
    handled, _cv, out_meta, resp = handle_skills_actions(
        aid="SKILLS_TAILOR_RUN",
        user_action_payload={},
        cv_data={"work_experience": [{"title": "Eng"}]},
        meta2=meta,
        session_id="sess",
        trace_id="trace",
        deps=deps,
    )

    assert handled is True
    assert str(out_meta.get("wizard_stage") or "") == "skills_tailor_review"
    assert resp and resp[0] == 200


def test_cover_preview_uses_unified_draft_in_experiment(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "EXPERIMENT_MODE", "variant_unified", raising=False)

    deps = CoverPdfActionDeps(
        wizard_set_stage=lambda m, st: {**dict(m or {}), "wizard_stage": st},
        persist=lambda cv, m: (cv, m),
        wizard_resp=lambda **kw: (200, {"response": kw.get("assistant_text", "")}),
        cv_enable_cover_letter=True,
        log_info=lambda *_a, **_kw: None,
        openai_enabled=lambda: True,
        generate_cover_letter_block_via_openai=lambda **_kw: (_ for _ in ()).throw(AssertionError("OpenAI call should be skipped")),
        friendly_schema_error_message=lambda e: str(e),
        validate_cover_letter_block=lambda **_kw: (True, []),
        build_cover_letter_render_payload=lambda **_kw: {},
        render_cover_letter_pdf=lambda *_a, **_kw: b"",
        upload_pdf_blob_for_session=lambda **_kw: None,
        compute_cover_letter_download_name=lambda **_kw: "cover.pdf",
        now_iso=lambda: "2026-03-08T00:00:00Z",
        wizard_get_stage=lambda m: str(m.get("wizard_stage") or ""),
        tool_generate_cv_from_session=lambda **_kw: (400, {"error": "not used"}, "application/json"),
        session_get=lambda _sid: None,
        sync_job_data_table_history=lambda **kwargs: dict(kwargs.get("meta") or {}),
    )

    meta = {
        "wizard_stage": "cover_letter_review",
        "target_language": "en",
        "cover_letter_block": {"opening_paragraph": "Hello", "core_paragraphs": ["x"], "closing_paragraph": "c", "signoff": "s"},
        "cover_letter_input_sig": "sig-1",
    }

    handled, _cv, out_meta, resp = handle_cover_pdf_actions(
        aid="COVER_LETTER_PREVIEW",
        user_action_payload={},
        cv_data={"work_experience": [{"title": "Eng"}]},
        meta2=meta,
        session_id="sess",
        trace_id="trace",
        stage_now="cover_letter_review",
        language="en",
        client_context=None,
        deps=deps,
    )

    assert handled is True
    assert str(out_meta.get("wizard_stage") or "") == "cover_letter_review"
    assert resp and resp[0] == 200
