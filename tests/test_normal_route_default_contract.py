from __future__ import annotations

import json

from src.orchestrator.wizard.ui_builder import UiBuilderDeps, build_ui_action


def _deps() -> UiBuilderDeps:
    return UiBuilderDeps(
        cv_enable_cover_letter=True,
        get_pending_confirmation=lambda _m: None,
        openai_enabled=lambda: True,
        format_job_reference_for_display=lambda _jr: "Job summary",
        is_work_role_locked=lambda **_kwargs: False,
    )


def _action_ids(ui_action: dict) -> set[str]:
    acts = ui_action.get("actions") if isinstance(ui_action, dict) else []
    return {str(a.get("id")) for a in acts if isinstance(a, dict) and str(a.get("id") or "").strip()}


def test_normal_route_default_contract_actions_present() -> None:
    deps = _deps()
    cv_data = {
        "work_experience": [
            {
                "title": "Engineer",
                "employer": "ACME",
                "date_range": "2020-01 - 2024-01",
                "location": "Zug",
                "bullets": ["Did X", "Did Y"],
            }
        ],
        "education": [{"title": "BSc", "institution": "Uni", "date_range": "2015-2019"}],
        "it_ai_skills": ["Python"],
        "technical_operational_skills": ["Lean"],
        "interests": "Running",
    }
    readiness = {"can_generate": True, "confirmed_flags": {"contact_confirmed": True, "education_confirmed": True}}

    checks: list[tuple[str, str]] = [
        ("language_selection", "LANGUAGE_SELECT_EN"),
        ("import_gate_pending", "CONFIRM_IMPORT_PREFILL_YES"),
        ("contact", "CONTACT_CONFIRM"),
        ("education", "EDUCATION_CONFIRM"),
        ("job_posting", "JOB_OFFER_CONTINUE"),
        ("work_notes_edit", "WORK_TAILOR_RUN"),
        ("work_tailor_review", "WORK_TAILOR_ACCEPT"),
        ("it_ai_skills", "SKILLS_TAILOR_RUN"),
        ("skills_tailor_review", "SKILLS_TAILOR_ACCEPT"),
        ("review_final", "REQUEST_GENERATE_PDF"),
        ("cover_letter_review", "COVER_LETTER_GENERATE"),
    ]

    for stage, expected_action in checks:
        has_job_ctx = stage in {"job_posting", "work_notes_edit", "work_tailor_review", "it_ai_skills", "skills_tailor_review", "review_final", "cover_letter_review"}
        meta = {
            "flow_mode": "wizard",
            "wizard_stage": stage,
            "target_language": "en",
            "confirmed_flags": {"contact_confirmed": True, "education_confirmed": True},
            "job_posting_text": "Senior engineer role at ACME with Python and delivery ownership." if has_job_ctx else "",
            "job_reference": {"summary": "Job summary"} if has_job_ctx else {},
        }
        ui_action = build_ui_action(stage, cv_data, meta, readiness, deps)
        assert isinstance(ui_action, dict), f"ui_action missing for stage={stage}"
        ids = _action_ids(ui_action)
        assert expected_action in ids, f"expected action {expected_action} missing for stage={stage}; got={sorted(ids)}"


def test_job_data_table_includes_visible_cv_date() -> None:
    deps = _deps()
    cv_data = {}
    meta = {
        "flow_mode": "wizard",
        "wizard_stage": "job_data_table",
        "job_data_table_history": [
            {
                "position_name": "Automation Engineer",
                "company_name": "ACME",
                "company_address": "Zurich",
                "company_email": "",
                "company_phone": "",
                "cv_generated_at": "2026-03-04T17:18:21.010772",
                "updated_at": "2026-03-04T17:18:21.010772",
            }
        ],
    }
    readiness = {"can_generate": True, "confirmed_flags": {"contact_confirmed": True, "education_confirmed": True}}

    ui_action = build_ui_action("job_data_table", cv_data, meta, readiness, deps)
    assert isinstance(ui_action, dict)
    fields = ui_action.get("fields") if isinstance(ui_action.get("fields"), list) else []
    field = next((f for f in fields if isinstance(f, dict) and f.get("key") == "job_data_table_json"), None)
    assert isinstance(field, dict)
    rows = json.loads(str(field.get("value") or "[]"))
    assert isinstance(rows, list) and rows
    first = rows[0]
    assert "CV:" not in str(first.get("position_name") or "")
    assert str(first.get("cv_generated_at") or "")
