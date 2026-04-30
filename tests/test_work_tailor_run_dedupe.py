from __future__ import annotations

from dataclasses import dataclass

from src import product_config
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


@dataclass
class _CoverLetter:
    opening_paragraph: str
    core_paragraphs: list[str]
    closing_paragraph: str
    signoff: str
    notes: str = ""

    def dict(self) -> dict:
        return {
            "opening_paragraph": self.opening_paragraph,
            "core_paragraphs": list(self.core_paragraphs),
            "closing_paragraph": self.closing_paragraph,
            "signoff": self.signoff,
            "notes": self.notes,
        }


@dataclass
class _UnifiedProposal:
    combined_cv: _Proposal
    cover_letter: _CoverLetter
    alignment_notes: str = ""


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

    handled2, _cv2, meta2, resp2 = handle_work_tailor_ai_actions(
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
    assert str(meta2.get("wizard_stage") or "") == "work_tailor_review"
    assert "loaded existing work proposal" in str(resp2[1].get("response") or "").lower()


def test_work_tailor_run_regenerates_when_target_language_changes() -> None:
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

    handled1, _cv1, meta1, _resp1 = handle_work_tailor_ai_actions(
        aid="WORK_TAILOR_RUN",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta,
        session_id="s1",
        trace_id="t1",
        deps=deps,
    )
    assert handled1 is True
    assert calls == ["work_experience"]

    handled2, _cv2, _meta2, resp2 = handle_work_tailor_ai_actions(
        aid="WORK_TAILOR_RUN",
        user_action_payload={"target_language": "de"},
        cv_data=cv_data,
        meta2=meta1,
        session_id="s1",
        trace_id="t2",
        deps=deps,
    )
    assert handled2 is True
    assert resp2 and resp2[0] == 200
    assert calls == ["work_experience", "work_experience"], "language switch must trigger a new generation"


def test_unified_work_tailor_retries_once_when_cover_letter_is_too_short(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "EXPERIMENT_MODE", "variant_unified", raising=False)
    calls: list[str] = []

    short_opening = "I bring strong industrial process improvement experience."
    short_core = [
        "I improved quality systems, standardized workflows, and supported production sites across multiple roles."
    ]
    short_closing = "I would welcome the chance to contribute this background to your team."

    long_opening = "I am applying for this role because it closely matches my experience in process improvement, structured execution, and practical support for manufacturing operations across different industrial settings. Throughout my career, I have worked where quality, process discipline, and reliable delivery had to come together in a practical way."
    long_core = [
        "Across my previous roles, I improved production-related processes, standardized operating methods, and helped teams work with clearer quality and performance expectations. I have worked in demanding environments where disciplined execution, clear documentation, and practical problem solving were essential to stable delivery. In these settings, I learned how to connect operational needs with measurable improvement work and to support teams during implementation rather than stopping at recommendations alone.",
        "I also contributed to process-oriented improvements by organizing workflows, supporting audits and compliance structures, and translating operational problems into concrete changes that teams could implement. That combination helps me connect day-to-day plant reality with broader improvement goals in a reliable and pragmatic way. It also reflects the style I would bring to your environment: structured analysis, calm coordination, and practical follow-through that improves consistency without overcomplicating the work.",
    ]
    long_closing = "I would value the opportunity to discuss how this background can support your team with structured improvement work, disciplined implementation, and dependable collaboration across technical and operational stakeholders. I am especially motivated by roles where careful execution, cross-functional communication, and sustainable process improvement matter day after day."

    def _openai_json_schema_call(**kwargs):
        stage = str(kwargs.get("stage") or "")
        if stage != "cv_cl_unified":
            return False, None, f"unexpected stage {stage}"
        calls.append(str(kwargs.get("user_text") or ""))
        if len(calls) == 1:
            return True, {
                "combined_cv": {
                    "roles": [
                        {
                            "title": "Engineer",
                            "company": "ACME",
                            "date_range": "2020-01 - 2024-01",
                            "location": "Zug",
                            "bullets": ["Delivered X", "Improved Y", "Led Z", "Shipped Q"],
                        }
                    ],
                    "it_ai_skills": ["Python"],
                    "technical_operational_skills": ["Kaizen"],
                    "notes": "ok",
                },
                "cover_letter": {
                    "opening_paragraph": short_opening,
                    "core_paragraphs": short_core,
                    "closing_paragraph": short_closing,
                    "signoff": "Kind regards, John Doe",
                    "notes": "short",
                },
                "alignment_notes": "short",
            }, None
        return True, {
            "combined_cv": {
                "roles": [
                    {
                        "title": "Engineer",
                        "company": "ACME",
                        "date_range": "2020-01 - 2024-01",
                        "location": "Zug",
                        "bullets": ["Delivered X", "Improved Y", "Led Z", "Shipped Q"],
                    }
                ],
                "it_ai_skills": ["Python"],
                "technical_operational_skills": ["Kaizen"],
                "notes": "ok",
            },
            "cover_letter": {
                "opening_paragraph": long_opening,
                "core_paragraphs": long_core,
                "closing_paragraph": long_closing,
                "signoff": "Kind regards, John Doe",
                "notes": "long enough",
            },
            "alignment_notes": "aligned",
        }, None

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
        "full_name": "John Doe",
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
        "target_language": "de",
        "job_reference": {"summary": "Target role summary"},
        "work_tailoring_notes": "Focus on delivery",
        "work_tailoring_feedback": "",
    }

    import src.orchestrator.wizard.action_dispatch_work_tailor_ai as mod

    monkeypatch.setattr(
        mod,
        "parse_unified_cv_cl_proposal",
        lambda d: _UnifiedProposal(
            combined_cv=_Proposal(
                roles=[_Role(**r) for r in list(d.get("combined_cv", {}).get("roles") or [])],
                notes=str(d.get("combined_cv", {}).get("notes") or ""),
            ),
            cover_letter=_CoverLetter(**dict(d.get("cover_letter") or {})),
            alignment_notes=str(d.get("alignment_notes") or ""),
        ),
        raising=True,
    )

    handled, _cv_out, meta_out, resp = handle_work_tailor_ai_actions(
        aid="WORK_TAILOR_RUN",
        user_action_payload={},
        cv_data=cv_data,
        meta2=meta,
        session_id="s1",
        trace_id="t1",
        deps=deps,
    )

    assert handled is True
    assert resp and resp[0] == 200
    assert str(meta_out.get("wizard_stage") or "") == "work_tailor_review"
    assert len(calls) == 2
    assert "[RETRY_CONSTRAINT]" in calls[1]
    assert isinstance(meta_out.get("cover_letter_block"), dict)

