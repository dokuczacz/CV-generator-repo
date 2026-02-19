from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import function_app


@dataclass
class _FakeStore:
    session: dict[str, Any]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if session_id != "s1":
            return None
        return self.session

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> None:
        if session_id != "s1":
            return
        self.session = {
            "cv_data": dict(cv_data or {}),
            "metadata": dict(metadata or {}),
        }

    def append_event(self, session_id: str, event: dict) -> None:
        return None


class _OpenAICapture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        system_prompt: str,
        user_text: str,
        trace_id: str | None = None,
        session_id: str | None = None,
        response_format: dict | None = None,
        max_output_tokens: int = 0,
        stage: str = "",
    ) -> tuple[bool, dict, str]:
        self.calls.append(
            {
                "stage": stage,
                "system_prompt": system_prompt,
                "user_text": user_text,
                "trace_id": trace_id,
                "session_id": session_id,
                "response_format": response_format,
                "max_output_tokens": max_output_tokens,
            }
        )

        if stage == "job_posting":
            return (
                True,
                {
                    "role_title": "Quality Manager",
                    "company": "Lonza",
                    "location": "Visp",
                    "seniority": "Senior",
                    "employment_type": "Full-time",
                    "responsibilities": ["Lead quality projects"],
                    "must_haves": ["IATF"],
                    "nice_to_haves": ["Lean"],
                    "tools_tech": ["IATF", "KAIZEN"],
                    "keywords": ["quality management", "process improvement"],
                },
                "",
            )

        if stage == "work_experience":
            return (
                True,
                {
                    "roles": [
                        {
                            "title": "Director",
                            "company": "GL Solutions",
                            "date_range": "2020-01 – 2025-04",
                            "location": "PL",
                            "bullets": [
                                "Led road and infrastructure projects for public and private contracts.",
                                "Managed subcontractors and compliance across multi-site execution.",
                                "Built schedules and budgets and optimized on-site delivery workflows.",
                            ],
                            "alignment_breakdown": {
                                "core_responsibilities_match": 0.35,
                                "methods_tools_match": 0.20,
                                "context_match": 0.13,
                                "seniority_scope": 0.10,
                                "language_requirements_match": 0.08,
                            },
                            "alignment_evidence": [
                                "Managed subcontractors and compliance across multi-site execution.",
                                "Built schedules and budgets and optimized on-site delivery workflows.",
                            ],
                        }
                    ],
                    "notes": "Tailored to quality/process focus.",
                },
                "",
            )

        if stage == "it_ai_skills":
            return (
                True,
                {
                    "it_ai_skills": ["Python", "Automation", "Reporting"],
                    "technical_operational_skills": ["IATF", "KAIZEN", "Quality systems"],
                    "notes": "Ranked from candidate data.",
                },
                "",
            )

        if stage == "cover_letter":
            return (
                True,
                {
                    "header": {
                        "sender_name": "",
                        "sender_email": "",
                        "sender_phone": "",
                        "sender_address": "",
                        "date": "",
                        "recipient_company": "",
                        "recipient_job_title": "",
                    },
                    "opening_paragraph": "I am applying for the role based on my documented quality and operations experience.",
                    "core_paragraphs": [
                        "I led quality and process initiatives across production and infrastructure contexts.",
                    ],
                    "closing_paragraph": "Thank you for your consideration.",
                    "signoff": "Kind regards",
                    "notes": "",
                },
                "",
            )

        return True, {}, ""


def _base_cv_data() -> dict[str, Any]:
    return {
        "full_name": "Mariusz Horodecki",
        "email": "m@example.com",
        "phone": "+41 79 000 0000",
        "language": "en",
        "profile": "Project and Operations Manager with quality and process improvement background.",
        "work_experience": [
            {
                "title": "Director",
                "employer": "GL Solutions",
                "date_range": "2020-01 – 2025-04",
                "location": "Zielona Góra, Poland",
                "bullets": [
                    "Planned and coordinated infrastructure projects.",
                    "Supervised sites and subcontractors.",
                    "Prepared schedules and budgets.",
                ],
            }
        ],
        "education": [
            {
                "institution": "Technical University",
                "title": "MSc",
                "date_range": "2008-2013",
            }
        ],
        "it_ai_skills": ["Python", "Automation"],
        "technical_operational_skills": ["IATF", "KAIZEN"],
    }


def _wizard_metadata() -> dict[str, Any]:
    return {
        "flow_mode": "wizard",
        "wizard_stage": "job_posting",
        "language": "en",
        "target_language": "en",
    }


def _setup(monkeypatch, *, cv_data: dict[str, Any], metadata: dict[str, Any]) -> _OpenAICapture:
    store = _FakeStore(session={"cv_data": cv_data, "metadata": metadata})
    capture = _OpenAICapture()

    monkeypatch.setattr(function_app, "_get_session_store", lambda: store)
    monkeypatch.setattr(function_app, "_openai_enabled", lambda: True)
    monkeypatch.setattr(function_app, "_openai_json_schema_call", capture)
    return capture


def test_job_posting_analyze_uses_raw_job_text_as_input(monkeypatch):
    capture = _setup(monkeypatch, cv_data=_base_cv_data(), metadata=_wizard_metadata())
    job_text = (
        "Quality Manager role at Lonza. Responsibilities include quality leadership, audits, process improvement, "
        "cross-functional collaboration, and production quality governance in regulated environments."
    )

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "analyze",
            "language": "en",
            "user_action": {
                "id": "JOB_OFFER_ANALYZE",
                "payload": {"job_offer_text": job_text},
            },
        }
    )

    assert status == 200
    assert payload.get("success") is True

    job_calls = [c for c in capture.calls if c["stage"] == "job_posting"]
    assert len(job_calls) == 1
    assert job_calls[0]["user_text"] == job_text


def test_work_tailor_run_payload_matches_runtime_capsules(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Quality Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead quality systems"],
        "must_haves": ["IATF"],
        "nice_to_haves": ["Lean"],
        "tools_tech": ["IATF", "KAIZEN"],
        "keywords": ["quality", "process improvement"],
    }
    metadata["work_tailoring_notes"] = "Focus on claims reduction and audits."
    metadata["work_tailoring_feedback"] = "Keep bullets concise."

    capture = _setup(monkeypatch, cv_data=_base_cv_data(), metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run work tailoring",
            "language": "en",
            "user_action": {"id": "WORK_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    work_calls = [c for c in capture.calls if c["stage"] == "work_experience"]
    assert len(work_calls) == 1
    user_text = work_calls[0]["user_text"]

    assert "[JOB_SUMMARY]" in user_text
    assert "[TAILORING_SUGGESTIONS]" in user_text
    assert "[TAILORING_FEEDBACK]" in user_text
    assert "[ALIGNMENT_POLICY]" not in user_text
    assert "[CURRENT_WORK_EXPERIENCE]" in user_text
    assert "Zielona Góra, Poland" in user_text


def test_skills_tailor_run_payload_matches_runtime_capsules(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Quality Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead quality systems"],
        "must_haves": ["IATF"],
        "nice_to_haves": ["Lean"],
        "tools_tech": ["IATF", "KAIZEN"],
        "keywords": ["quality", "process improvement"],
    }
    metadata["work_tailoring_notes"] = "Prioritize quality transformation examples."
    metadata["work_tailoring_feedback"] = "Emphasize measurable outcomes."
    metadata["work_experience_proposal_block"] = {"roles": [], "notes": "Prior tailoring pass notes."}

    capture = _setup(monkeypatch, cv_data=_base_cv_data(), metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[JOB_SUMMARY]" in user_text
    assert "[TAILORING_SUGGESTIONS]" in user_text
    assert "[TAILORING_FEEDBACK]" in user_text
    assert "[WORK_EXPERIENCE_TAILORED]" in user_text
    assert "[RAW_DOCX_SKILLS]" in user_text
    assert "[WORK_TAILORING_PROPOSAL_NOTES]" not in user_text
    assert "[RANKING_NOTES]" not in user_text
    assert "[CANDIDATE_SKILLS]" not in user_text


def test_skills_tailor_run_ignores_payload_candidate_skills_capsule(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Quality Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead quality systems"],
        "must_haves": ["IATF"],
        "nice_to_haves": ["Lean"],
        "tools_tech": ["IATF", "KAIZEN"],
        "keywords": ["quality", "process improvement"],
    }
    metadata["work_experience_proposal_block"] = {"roles": [], "notes": "Prior tailoring pass notes."}

    capture = _setup(monkeypatch, cv_data=_base_cv_data(), metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {
                "id": "SKILLS_TAILOR_RUN",
                "payload": {
                    "candidate_skills": ["Kubernetes", "terraform"],
                    "candidate_skills_text": "Azure DevOps\nGitHub Actions",
                },
            },
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[CANDIDATE_SKILLS]" not in user_text
    assert "Kubernetes" not in user_text
    assert "terraform" not in user_text
    assert "Azure DevOps" not in user_text
    assert "GitHub Actions" not in user_text


def test_skills_tailor_run_ignores_message_block_candidate_skills(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Quality Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead quality systems"],
        "must_haves": ["IATF"],
        "nice_to_haves": ["Lean"],
        "tools_tech": ["IATF", "KAIZEN"],
        "keywords": ["quality", "process improvement"],
    }
    metadata["work_experience_proposal_block"] = {"roles": [], "notes": "Prior tailoring pass notes."}

    capture = _setup(monkeypatch, cv_data=_base_cv_data(), metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring\n[CANDIDATE_SKILLS]\n- Databricks\nSnowflake\n\n[NOTES]\nPrefer cloud analytics",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[CANDIDATE_SKILLS]" not in user_text
    assert "Databricks" not in user_text
    assert "Snowflake" not in user_text


def test_skills_tailor_run_uses_contextual_seeds_when_skills_empty(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Operational Excellence Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead improvement initiatives"],
        "must_haves": ["Cycle time reduction"],
        "nice_to_haves": ["Lean Six Sigma"],
        "tools_tech": ["VSM", "Standard Work"],
        "keywords": ["operational excellence", "continuous improvement"],
    }
    metadata["work_tailoring_notes"] = "Use operational excellence, KAIZEN and cycle time achievements."
    metadata["docx_prefill_unconfirmed"] = {
        "it_ai_skills": ["Azure Functions", "GPT automation"],
        "technical_operational_skills": ["IATF", "KAIZEN"],
    }

    cv_data = _base_cv_data()
    cv_data["it_ai_skills"] = []
    cv_data["technical_operational_skills"] = []

    capture = _setup(monkeypatch, cv_data=cv_data, metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[RAW_DOCX_SKILLS]" in user_text
    assert "Azure Functions" in user_text
    assert "KAIZEN" in user_text


def test_skills_tailor_feedback_is_consumed_once(monkeypatch):
    metadata = _wizard_metadata()
    metadata["wizard_stage"] = "it_ai_skills"
    metadata["job_reference"] = {
        "role_title": "Operational Excellence Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead improvement initiatives"],
        "must_haves": ["Cycle time reduction"],
        "nice_to_haves": ["Lean Six Sigma"],
        "tools_tech": ["VSM", "Standard Work"],
        "keywords": ["operational excellence", "continuous improvement"],
    }
    metadata["work_tailoring_feedback"] = "This should be sent once only."

    cv_data = _base_cv_data()
    cv_data["it_ai_skills"] = []
    cv_data["technical_operational_skills"] = []

    store = _FakeStore(session={"cv_data": cv_data, "metadata": metadata})
    capture = _OpenAICapture()
    monkeypatch.setattr(function_app, "_get_session_store", lambda: store)
    monkeypatch.setattr(function_app, "_openai_enabled", lambda: True)
    monkeypatch.setattr(function_app, "_openai_json_schema_call", capture)

    status1, payload1 = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )
    assert status1 == 200
    assert payload1.get("success") is True

    first_call = [c for c in capture.calls if c["stage"] == "it_ai_skills"][0]
    assert "This should be sent once only." in first_call["user_text"]

    # Force stage back so we can execute SKILLS_TAILOR_RUN again on same session.
    updated = store.get_session("s1")
    assert updated is not None
    updated_meta = dict(updated.get("metadata") or {})
    updated_meta["wizard_stage"] = "it_ai_skills"
    store.update_session("s1", updated.get("cv_data") or {}, updated_meta)

    status2, payload2 = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring again",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )
    assert status2 == 200
    assert payload2.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) >= 2
    assert "This should be sent once only." not in skill_calls[1]["user_text"]


def test_skills_tailor_run_uses_docx_raw_skill_lines(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Operational Excellence Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead improvement initiatives"],
        "must_haves": ["Cycle time reduction"],
        "nice_to_haves": ["Lean Six Sigma"],
        "tools_tech": ["VSM", "Standard Work"],
        "keywords": ["operational excellence", "continuous improvement"],
    }
    metadata["docx_prefill_unconfirmed"] = {
        "skills_raw_lines": [
            "FÄHIGKEITEN & KOMPETENZENIndependent Technical Development, GitHub: https://github.com/dokuczacz/",
            "Technisches Projektmanagement (CAPEX/OPEX)",
            "Ursachenanalysen & Prozessverbesserungen (FMEA, 5 Why, PDCA)",
        ]
    }

    cv_data = _base_cv_data()
    cv_data["it_ai_skills"] = []
    cv_data["technical_operational_skills"] = []

    capture = _setup(monkeypatch, cv_data=cv_data, metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[RAW_DOCX_SKILLS]" in user_text
    assert "Independent Technical Development" in user_text
    assert "github.com/dokuczacz" in user_text.lower()
    assert "CAPEX/OPEX" in user_text
    assert "FÄHIGKEITEN & KOMPETENZEN" not in user_text


def test_skills_tailor_run_sanitizes_legacy_prefill_skill_lines(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Operational Excellence Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead improvement initiatives"],
        "must_haves": ["Cycle time reduction"],
        "nice_to_haves": ["Lean Six Sigma"],
        "tools_tech": ["VSM", "Standard Work"],
        "keywords": ["operational excellence", "continuous improvement"],
    }
    metadata["docx_prefill_unconfirmed"] = {
        "it_ai_skills": [
            "FÄHIGKEITEN & KOMPETENZENIndependent Technical Development, Git Hub: h",
            "Technisches Projektmanagement (CAPEX/OPEX)",
        ],
        "technical_operational_skills": [
            "Ursachenanalysen & Prozessverbesserungen (FMEA, 5 Why, PDCA)",
        ],
    }

    cv_data = _base_cv_data()
    cv_data["it_ai_skills"] = []
    cv_data["technical_operational_skills"] = []

    capture = _setup(monkeypatch, cv_data=cv_data, metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[RAW_DOCX_SKILLS]" in user_text
    assert "Independent Technical Development" in user_text
    assert "Git Hub: h" not in user_text
    assert "FÄHIGKEITEN & KOMPETENZEN" not in user_text


def test_skills_tailor_run_preserves_long_raw_skill_line(monkeypatch):
    metadata = _wizard_metadata()
    metadata["job_reference"] = {
        "role_title": "Operational Excellence Manager",
        "company": "Lonza",
        "location": "Visp",
        "seniority": "Senior",
        "employment_type": "Full-time",
        "responsibilities": ["Lead improvement initiatives"],
        "must_haves": ["Cycle time reduction"],
        "nice_to_haves": ["Lean Six Sigma"],
        "tools_tech": ["VSM", "Standard Work"],
        "keywords": ["operational excellence", "continuous improvement"],
    }
    long_skill = (
        "Designed and developed OmniFlow Beta, a multi-user AI agent backend built on Azure Functions and Azure Blob Storage, "
        "providing deterministic tool orchestration, user-isolated data storage, and semantic JSON pipelines for LLM-driven workflows"
    )
    metadata["docx_prefill_unconfirmed"] = {
        "skills_raw_lines": [
            "Independent Technical Development, GitHub: https://github.com/dokuczacz/",
            long_skill,
            "Technisches Projektmanagement (CAPEX/OPEX)",
        ]
    }

    cv_data = _base_cv_data()
    cv_data["it_ai_skills"] = []
    cv_data["technical_operational_skills"] = []

    capture = _setup(monkeypatch, cv_data=cv_data, metadata=metadata)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "run skills tailoring",
            "language": "en",
            "user_action": {"id": "SKILLS_TAILOR_RUN", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True

    skill_calls = [c for c in capture.calls if c["stage"] == "it_ai_skills"]
    assert len(skill_calls) == 1
    user_text = skill_calls[0]["user_text"]

    assert "[RAW_DOCX_SKILLS]" in user_text
    assert "OmniFlow Beta" in user_text
    assert "LLM-driven workflows" in user_text


def test_cover_letter_payload_matches_runtime_capsules(monkeypatch):
    capture = _OpenAICapture()
    monkeypatch.setattr(function_app, "_openai_json_schema_call", capture)

    cv_data = _base_cv_data()
    metadata = {
        "language": "en",
        "target_language": "en",
        "job_reference": {
            "role_title": "Quality Manager",
            "company": "Lonza",
            "location": "Visp",
            "seniority": "Senior",
            "employment_type": "Full-time",
            "responsibilities": ["Lead quality systems"],
            "must_haves": ["IATF"],
            "nice_to_haves": ["Lean"],
            "tools_tech": ["IATF", "KAIZEN"],
            "keywords": ["quality", "process improvement"],
        },
    }

    ok, block, err = function_app._generate_cover_letter_block_via_openai(
        cv_data=cv_data,
        meta=metadata,
        target_language="en",
        trace_id="t1",
        session_id="s1",
    )

    assert ok is True, err
    assert isinstance(block, dict)

    cl_calls = [c for c in capture.calls if c["stage"] == "cover_letter"]
    assert len(cl_calls) == 1
    user_text = cl_calls[0]["user_text"]

    assert "[JOB_REFERENCE]" in user_text
    assert "[STYLE_PROFILE]" in user_text
    assert "[CV_PROFILE]" not in user_text
    assert "[WORK_EXPERIENCE]" in user_text
    assert "[SKILLS]" in user_text


def test_cover_letter_generation_fails_without_job_context(monkeypatch):
    capture = _OpenAICapture()
    monkeypatch.setattr(function_app, "_openai_json_schema_call", capture)

    cv_data = _base_cv_data()
    metadata = {
        "language": "en",
        "target_language": "en",
        "job_reference": {},
        "job_posting_text": "",
    }

    ok, block, err = function_app._generate_cover_letter_block_via_openai(
        cv_data=cv_data,
        meta=metadata,
        target_language="en",
        trace_id="t1",
        session_id="s1",
    )

    assert ok is False
    assert block is None
    assert "Job reference is missing" in str(err)
    cl_calls = [c for c in capture.calls if c["stage"] == "cover_letter"]
    assert len(cl_calls) == 0
