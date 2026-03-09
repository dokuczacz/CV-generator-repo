from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import function_app


class FakeStore:
    def __init__(self, session: dict[str, Any]) -> None:
        self.session = session

    def get_session_with_blob_retrieval(self, session_id: str) -> dict[str, Any] | None:
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if session_id != "s1":
            return None
        return self.session

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        if session_id != "s1":
            return False
        self.session = {"cv_data": dict(cv_data or {}), "metadata": dict(metadata or {})}
        return True

    def update_session_with_blob_offload(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        return self.update_session(session_id, cv_data, metadata)

    def append_event(self, session_id: str, event: dict) -> None:
        _ = session_id
        _ = event


class OpenAICapture:
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
                    "role_title": "Operational Excellence Manager",
                    "company": "Lonza",
                    "location": "Visp",
                    "seniority": "Senior",
                    "employment_type": "Full-time",
                    "responsibilities": ["Lead operational excellence"],
                    "must_haves": ["IATF"],
                    "nice_to_haves": ["Lean"],
                    "tools_tech": ["IATF", "KAIZEN"],
                    "keywords": ["quality", "process improvement"],
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
                            "date_range": "2020-01 - 2025-10",
                            "location": "Zielona Gora, Poland",
                            "bullets": [
                                "Led road infrastructure projects and delivery planning.",
                                "Coordinated compliance and documentation for contracts.",
                                "Improved site operations and workflow predictability.",
                                "Managed stakeholders across public and private projects.",
                            ],
                        }
                    ],
                    "notes": "Tailored for operational excellence focus",
                },
                "",
            )

        if stage == "it_ai_skills":
            return (
                True,
                {
                    "it_ai_skills": ["Excel", "Prompt engineering", "Reporting"],
                    "technical_operational_skills": ["IATF", "KAIZEN", "FMEA"],
                    "notes": "Ranked from candidate evidence",
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
                    "opening_paragraph": "I am applying based on my proven operational and quality track record.",
                    "core_paragraphs": ["I led quality and process improvements in prior roles."],
                    "closing_paragraph": "Thank you for your consideration.",
                    "signoff": "Kind regards",
                    "notes": "",
                },
                "",
            )

        return True, {}, ""


def base_cv_data() -> dict[str, Any]:
    return {
        "full_name": "Mariusz Horodecki",
        "email": "horodecki.mariusz@gmail.com",
        "phone": "+41 77 952 24 37",
        "language": "en",
        "profile": "Operations and quality leader",
        "work_experience": [
            {
                "title": "Director",
                "employer": "GL Solutions",
                "date_range": "2020-01 - 2025-10",
                "location": "Zielona Gora, Poland",
                "bullets": [
                    "Led planning and execution of infrastructure projects.",
                    "Managed compliance and delivery quality.",
                    "Improved workflows and daily operations.",
                    "Coordinated stakeholders and contracts.",
                ],
            }
        ],
        "education": [{"institution": "Poznan University of Technology", "title": "MSc", "date_range": "2012-2015"}],
        "it_ai_skills": ["Excel", "Prompt engineering"],
        "technical_operational_skills": ["IATF", "KAIZEN"],
    }


def base_metadata() -> dict[str, Any]:
    return {
        "flow_mode": "wizard",
        "wizard_stage": "job_posting",
        "language": "en",
        "target_language": "en",
        "job_reference": {
            "role_title": "Operational Excellence Manager",
            "company": "Lonza",
            "location": "Visp",
            "seniority": "Senior",
            "employment_type": "Full-time",
            "responsibilities": ["Lead improvement initiatives"],
            "must_haves": ["IATF"],
            "nice_to_haves": ["Lean"],
            "tools_tech": ["IATF", "KAIZEN"],
            "keywords": ["quality", "process improvement"],
        },
        "work_tailoring_notes": "Focus on measurable quality impact",
        "work_tailoring_feedback": "Keep concise bullet wording",
        "cover_letter_tailoring_notes": "Show fit to operational excellence manager role",
        "skills_ranking_notes": "Prioritize manufacturing quality/process skills",
    }


def run_inspection() -> list[dict[str, Any]]:
    store = FakeStore(session={"cv_data": base_cv_data(), "metadata": base_metadata()})
    capture = OpenAICapture()

    function_app._get_session_store = lambda: store  # type: ignore[method-assign]
    function_app._openai_enabled = lambda: True  # type: ignore[method-assign]
    function_app._openai_json_schema_call = capture  # type: ignore[method-assign]

    actions = [
        {"id": "WORK_TAILOR_RUN", "message": "run work tailoring"},
        {"id": "SKILLS_TAILOR_RUN", "message": "run skills tailoring"},
    ]

    for a in actions:
        function_app._tool_process_cv_orchestrated(
            {
                "session_id": "s1",
                "message": a["message"],
                "language": "en",
                "user_action": {"id": a["id"], "payload": {}},
            }
        )

    # Capture cover-letter stage payload directly from production generator.
    sess = store.get_session("s1") or {}
    function_app._generate_cover_letter_block_via_openai(
        cv_data=dict(sess.get("cv_data") or {}),
        meta=dict(sess.get("metadata") or {}),
        trace_id="inspect-cover-stage",
        session_id="s1",
        target_language="en",
    )

    return capture.calls


def main() -> int:
    calls = run_inspection()
    out_dir = Path("tmp/payload_inspection")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    for idx, c in enumerate(calls, start=1):
        stage = str(c.get("stage") or "unknown")
        rec = {
            "idx": idx,
            "stage": stage,
            "trace_id": c.get("trace_id"),
            "session_id": c.get("session_id"),
            "system_prompt_len": len(str(c.get("system_prompt") or "")),
            "user_text_len": len(str(c.get("user_text") or "")),
            "max_output_tokens": c.get("max_output_tokens"),
        }
        summary.append(rec)

        payload_path = out_dir / f"{idx:02d}_{stage}.json"
        payload_path.write_text(
            json.dumps(
                {
                    "stage": stage,
                    "system_prompt": c.get("system_prompt") or "",
                    "user_text": c.get("user_text") or "",
                    "response_format": c.get("response_format") or {},
                    "max_output_tokens": c.get("max_output_tokens"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human-friendly markdown report.
    md_lines = [
        "# Wizard Payload Inspection\n\n",
        "| idx | stage | system_prompt_len | user_text_len | max_output_tokens |\n",
        "|---|---|---:|---:|---:|\n",
    ]
    for s in summary:
        md_lines.append(
            f"| {s['idx']} | {s['stage']} | {s['system_prompt_len']} | {s['user_text_len']} | {s['max_output_tokens']} |\n"
        )
    (out_dir / "summary.md").write_text("".join(md_lines), encoding="utf-8")

    print(json.dumps({"out_dir": str(out_dir), "calls": len(calls)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
