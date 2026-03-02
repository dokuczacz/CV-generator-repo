from __future__ import annotations

import function_app as app
from src.orchestrator.wizard.action_dispatch_work_tailor_ai import WorkTailorAIActionDeps, handle_work_tailor_ai_actions


def test_work_tailor_accept_preserves_model_role_order() -> None:
    cv_data = {
        "work_experience": [
            {"employer": "Company Old A", "title": "Role A", "date_range": "2023-01 - 2024-01", "location": "Zurich", "bullets": ["A"]},
            {"employer": "Company Old B", "title": "Role B", "date_range": "2019-01 - 2022-12", "location": "Basel", "bullets": ["B"]},
        ]
    }
    meta = {
        "wizard_stage": "work_tailor_review",
        "work_experience_proposal_block": {
            "roles": [
                {"title": "Role B", "company": "Company New B", "date_range": "2019-01 - 2022-12", "location": "Basel", "bullets": ["B1", "B2", "B3", "B4"]},
                {"title": "Role A", "company": "Company New A", "date_range": "2023-01 - 2024-01", "location": "Zurich", "bullets": ["A1", "A2", "A3", "A4"]},
            ],
            "notes": "ordered by relevance",
        },
    }

    def wizard_set_stage(m: dict, stage: str) -> dict:
        out = dict(m)
        out["wizard_stage"] = stage
        return out

    def persist(cv: dict, m: dict):
        return cv, m

    def wizard_resp(*, assistant_text: str, meta_out: dict, cv_out: dict, **_kwargs):
        return 200, {"response": assistant_text, "metadata": meta_out, "cv_data": cv_out}

    deps = WorkTailorAIActionDeps(
        wizard_set_stage=wizard_set_stage,
        persist=persist,
        wizard_resp=wizard_resp,
        openai_enabled=lambda: True,
        append_event=lambda *_args, **_kwargs: None,
        sha256_text=lambda s: f"sha:{len(str(s))}",
        now_iso=lambda: "2026-02-25T12:00:00Z",
        format_job_reference_for_display=lambda _jr: "",
        escape_user_input_for_prompt=lambda s: str(s),
        openai_json_schema_call=lambda **_kwargs: (False, None, "unused"),
        build_ai_system_prompt=lambda **_kwargs: "",
        get_job_reference_response_format=lambda: {},
        parse_job_reference=lambda _obj: None,
        sanitize_for_prompt=lambda s: str(s),
        log_info=lambda *_args, **_kwargs: None,
        log_warning=lambda *_args, **_kwargs: None,
        get_work_experience_bullets_proposal_response_format=lambda: {},
        parse_work_experience_bullets_proposal=lambda _obj: None,
        work_experience_hard_limit_chars=200,
        extract_e0_corpus_from_labeled_blocks=lambda *_args, **_kwargs: "",
        find_work_e0_violations=lambda **_kwargs: [],
        friendly_schema_error_message=lambda msg: msg,
        normalize_work_role_from_proposal=app._normalize_work_role_from_proposal,
        overwrite_work_experience_from_proposal_roles=app._overwrite_work_experience_from_proposal_roles,
        backfill_missing_work_locations=lambda **kwargs: kwargs["cv_data"],
        find_work_bullet_hard_limit_violations=lambda **_kwargs: [],
        build_work_bullet_violation_payload=lambda **_kwargs: {},
        select_roles_by_violation_indices=lambda **_kwargs: [],
        snapshot_session=lambda *_args, **_kwargs: None,
    )

    handled, cv_out, meta_out, resp = handle_work_tailor_ai_actions(
        aid="WORK_TAILOR_ACCEPT",
        user_action_payload=None,
        cv_data=cv_data,
        meta2=meta,
        session_id="sess",
        trace_id="trace",
        deps=deps,
    )

    assert handled is True
    assert isinstance(resp, tuple)
    roles = cv_out.get("work_experience") if isinstance(cv_out.get("work_experience"), list) else []
    assert len(roles) == 2
    assert str(roles[0].get("employer") or "") == "Company New B"
    assert str(roles[1].get("employer") or "") == "Company New A"
    assert meta_out.get("work_experience_order_source") == "model_relevance_after_accept"
