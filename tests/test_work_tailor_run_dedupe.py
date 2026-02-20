from __future__ import annotations

from dataclasses import dataclass

from src.orchestrator.wizard.action_dispatch_work_tailor_ai import (
    WorkTailorAIActionDeps,
    handle_work_tailor_ai_actions,
)


@dataclass
class _Role:
    title: str
    company: str
    date_range: str
    location: str
    bullets: list[str]


@dataclass
class _Proposal:
    roles: list[_Role]
    notes: str


def test_work_tailor_run_skips_duplicate_generation_for_same_inputs() -> None:
    calls: list[str] = []

    def _openai_json_schema_call(**kwargs):
        stage = str(kwargs.get("stage") or "")
        if stage == "work_experience":
            calls.append("work_experience")
            return True, {
                "roles": [
                    {
                        "title": "Engineer",
                        "company": "ACME",
                        "date_range": "2020-01 - 2024-01",
                        "location": "Zug",
                        "bullets": ["Delivered X", "Improved Y"],
                    }
                ],
                "notes": "ok",
            }, None
        return False, None, "unexpected stage"

    deps = WorkTailorAIActionDeps(
        wizard_set_stage=lambda m, st: {**dict(m or {}), "wizard_stage": st},
        persist=lambda cv, meta: (cv, meta),
        wizard_resp=lambda **kw: (200, {"response": kw.get("assistant_text", "")}),
        openai_enabled=lambda: True,
        append_event=lambda *_a, **_kw: None,
        sha256_text=lambda s: __import__("hashlib").sha256(str(s).encode("utf-8")).hexdigest(),
        now_iso=lambda: "2026-02-20T00:00:00Z",
        format_job_reference_for_display=lambda _jr: "Target role summary",
        escape_user_input_for_prompt=lambda s: str(s or ""),
        openai_json_schema_call=_openai_json_schema_call,
        build_ai_system_prompt=lambda **_kw: "prompt",
        get_job_reference_response_format=lambda: {},
        parse_job_reference=lambda d: d,
        sanitize_for_prompt=lambda s: str(s or ""),
        log_info=lambda *_a, **_kw: None,
        log_warning=lambda *_a, **_kw: None,
        get_work_experience_bullets_proposal_response_format=lambda: {},
        parse_work_experience_bullets_proposal=lambda d: _Proposal(
            roles=[_Role(**r) for r in list(d.get("roles") or [])],
            notes=str(d.get("notes") or ""),
        ),
        work_experience_hard_limit_chars=200,
        extract_e0_corpus_from_labeled_blocks=lambda *_a, **_kw: "",
        find_work_e0_violations=lambda **_kw: [],
        friendly_schema_error_message=lambda e: e,
        normalize_work_role_from_proposal=lambda r: r,
        overwrite_work_experience_from_proposal_roles=lambda **kw: {**dict(kw["cv_data"]), "work_experience": kw["proposal_roles"]},
        backfill_missing_work_locations=lambda **kw: kw["cv_data"],
        find_work_bullet_hard_limit_violations=lambda **_kw: [],
        build_work_bullet_violation_payload=lambda **_kw: {},
        select_roles_by_violation_indices=lambda **_kw: [],
        snapshot_session=lambda *_a, **_kw: None,
    )

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
        "language": "en",
    }
    meta = {
        "wizard_stage": "work_notes_edit",
        "target_language": "en",
        "job_reference": {"summary": "Target role summary"},
        "work_tailoring_notes": "Focus on delivery",
        "work_tailoring_feedback": "",
    }

    handled, _cv1, meta1, resp1 = handle_work_tailor_ai_actions(
        aid="WORK_TAILOR_RUN",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta,
        session_id="s1",
        trace_id="t1",
        deps=deps,
    )
    assert handled is True
    assert resp1 and resp1[0] == 200
    assert calls == ["work_experience"]
    assert str(meta1.get("wizard_stage") or "") == "work_tailor_review"
    assert str(meta1.get("work_experience_proposal_input_sig") or "")

    handled2, _cv2, _meta2, resp2 = handle_work_tailor_ai_actions(
        aid="WORK_TAILOR_RUN",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta1,
        session_id="s1",
        trace_id="t2",
        deps=deps,
    )
    assert handled2 is True
    assert resp2 and resp2[0] == 200
    assert calls == ["work_experience"], "second identical run should not call model again"
    assert "already up to date" in str(resp2[1].get("response") or "").lower()

