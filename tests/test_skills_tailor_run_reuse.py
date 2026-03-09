from __future__ import annotations

from src.orchestrator.wizard.action_dispatch_skills import SkillsActionDeps, handle_skills_actions


class _Prop:
    def __init__(self, it_ai_skills: list[str], technical_operational_skills: list[str], notes: str) -> None:
        self.it_ai_skills = it_ai_skills
        self.technical_operational_skills = technical_operational_skills
        self.notes = notes


def test_skills_tailor_run_reuses_cached_proposal_for_identical_input() -> None:
    calls: list[str] = []

    def _openai_json_schema_call(**kwargs):
        calls.append(str(kwargs.get("stage") or ""))
        return True, {
            "it_ai_skills": ["Python", "SQL"],
            "technical_operational_skills": ["Kaizen", "CAPA"],
            "notes": "ok",
        }, None

    deps = SkillsActionDeps(
        wizard_set_stage=lambda m, st: {**dict(m or {}), "wizard_stage": st},
        persist=lambda cv, meta: (cv, meta),
        wizard_resp=lambda **kw: (200, {"response": kw.get("assistant_text", "")}),
        append_event=lambda *_a, **_kw: None,
        sha256_text=lambda s: __import__("hashlib").sha256(str(s).encode("utf-8")).hexdigest(),
        now_iso=lambda: "2026-03-06T11:00:00Z",
        openai_enabled=lambda: True,
        format_job_reference_for_display=lambda _jr: "Target role summary",
        escape_user_input_for_prompt=lambda s: str(s or ""),
        collect_raw_docx_skills_context=lambda **_kw: ["Python", "Kaizen"],
        sanitize_for_prompt=lambda s: str(s or ""),
        openai_json_schema_call=_openai_json_schema_call,
        build_ai_system_prompt=lambda **_kw: "prompt",
        get_skills_unified_proposal_response_format=lambda: {},
        friendly_schema_error_message=lambda e: str(e),
        parse_skills_unified_proposal=lambda d: _Prop(
            list(d.get("it_ai_skills") or []),
            list(d.get("technical_operational_skills") or []),
            str(d.get("notes") or ""),
        ),
        dedupe_strings_case_insensitive=lambda xs, max_items=8: list(dict.fromkeys([str(x).strip() for x in (xs or []) if str(x).strip()]))[:max_items],
        find_work_bullet_hard_limit_violations=lambda **_kw: [],
        snapshot_session=lambda *_a, **_kw: None,
    )

    cv_data = {
        "language": "en",
        "work_experience": [
            {
                "title": "Engineer",
                "employer": "ACME",
                "date_range": "2020-01 - 2024-01",
                "bullets": ["Did X", "Did Y"],
            }
        ],
    }
    meta = {
        "wizard_stage": "it_ai_skills",
        "target_language": "en",
        "job_reference": {"summary": "Target role summary"},
        "work_tailoring_notes": "Focus on delivery",
    }

    handled1, _cv1, meta1, resp1 = handle_skills_actions(
        aid="SKILLS_TAILOR_RUN",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta,
        session_id="s1",
        trace_id="t1",
        deps=deps,
    )
    assert handled1 is True
    assert resp1 and resp1[0] == 200
    assert calls == ["it_ai_skills"]
    assert str(meta1.get("wizard_stage") or "") == "skills_tailor_review"
    assert str(meta1.get("skills_proposal_input_sig") or "")

    handled2, _cv2, meta2, resp2 = handle_skills_actions(
        aid="SKILLS_TAILOR_RUN",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta1,
        session_id="s1",
        trace_id="t2",
        deps=deps,
    )
    assert handled2 is True
    assert resp2 and resp2[0] == 200
    assert calls == ["it_ai_skills"]
    assert str(meta2.get("wizard_stage") or "") == "skills_tailor_review"
    assert "loaded existing skills proposal" in str(resp2[1].get("response") or "").lower()
