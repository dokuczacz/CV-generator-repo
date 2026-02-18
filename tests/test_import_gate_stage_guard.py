from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import function_app


@dataclass
class _FakeStore:
    session: dict[str, Any]
    raw_session: dict[str, Any] | None = None

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if session_id != "s1":
            return None
        return self.raw_session if isinstance(self.raw_session, dict) else self.session

    def get_session_with_blob_retrieval(self, session_id: str) -> dict[str, Any] | None:
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


@dataclass
class _FakeStorePersistTooLarge(_FakeStore):
    offload_updates: int = 0

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> None:
        raise RuntimeError("PropertyValueTooLarge")

    def update_session_with_blob_offload(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        if session_id != "s1":
            return False
        self.offload_updates += 1
        self.session = {
            "cv_data": dict(cv_data or {}),
            "metadata": dict(metadata or {}),
        }
        return True


def test_stale_import_prefill_does_not_block_late_cover_actions(monkeypatch):
    store = _FakeStore(
        session={
            "cv_data": {
                "full_name": "Test User",
                "work_experience": [{"title": "Role", "employer": "Company", "bullets": ["A"]}],
                "education": [{"title": "Degree", "institution": "Uni", "date_range": "2020-2022"}],
            },
            "metadata": {
                "flow_mode": "wizard",
                "wizard_stage": "cover_letter_review",
                "language": "en",
                "target_language": "en",
                "pending_confirmation": {"kind": "import_prefill", "created_at": "2026-02-01T10:00:00"},
                "docx_prefill_unconfirmed": {"full_name": "From DOCX"},
            },
        }
    )

    monkeypatch.setattr(function_app, "_get_session_store", lambda: store)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "",
            "language": "en",
            "user_action": {"id": "COVER_LETTER_BACK", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True
    assert payload.get("stage") == "review_final"
    assert payload.get("response") == "Back to PDF generation."

    persisted = store.get_session("s1") or {}
    meta = persisted.get("metadata") if isinstance(persisted.get("metadata"), dict) else {}
    assert meta.get("pending_confirmation") is None


def test_import_prefill_gate_still_blocks_non_import_actions_in_early_stages(monkeypatch):
    store = _FakeStore(
        session={
            "cv_data": {
                "full_name": "Test User",
                "work_experience": [],
                "education": [],
            },
            "metadata": {
                "flow_mode": "wizard",
                "wizard_stage": "contact",
                "language": "en",
                "target_language": "en",
                "pending_confirmation": {"kind": "import_prefill", "created_at": "2026-02-01T10:00:00"},
                "docx_prefill_unconfirmed": {"full_name": "From DOCX"},
            },
        }
    )

    monkeypatch.setattr(function_app, "_get_session_store", lambda: store)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "",
            "language": "en",
            "user_action": {"id": "CONTACT_CONFIRM", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True
    assert "Please confirm whether to import the DOCX prefill." in str(payload.get("response") or "")
    assert payload.get("stage") == "contact"


def test_cover_letter_preview_uses_blob_aware_session_data(monkeypatch):
    captured: dict[str, Any] = {}

    store = _FakeStore(
        session={
            "cv_data": {
                "full_name": "Test User",
                "work_experience": [
                    {
                        "title": "Operations Manager",
                        "employer": "Lonza",
                        "date_range": "2021-01 - 2025-01",
                        "bullets": ["Reduced changeover time by 30%"],
                    }
                ],
                "it_ai_skills": ["Automation"],
                "technical_operational_skills": ["KAIZEN"],
            },
            "metadata": {
                "flow_mode": "wizard",
                "wizard_stage": "cover_letter_review",
                "language": "en",
                "target_language": "en",
                "job_reference": {
                    "role_title": "Operational Excellence Manager",
                    "company": "Lonza",
                    "location": "Visp",
                    "must_haves": ["Lean Six Sigma"],
                    "tools_tech": ["VSM"],
                    "keywords": ["continuous improvement"],
                },
            },
        },
        raw_session={
            "cv_data": {
                "__offloaded__": True,
                "__blob_ref__": "cv-artifacts/s1/cv_data_20260218_000000.json",
                "size_bytes": 90000,
            },
            "metadata": {
                "flow_mode": "wizard",
                "wizard_stage": "cover_letter_review",
                "language": "en",
                "target_language": "en",
                "job_reference": {
                    "role_title": "Operational Excellence Manager",
                    "company": "Lonza",
                    "location": "Visp",
                },
            },
        },
    )

    def _fake_generate_cover_letter_block_via_openai(*, cv_data, meta, trace_id, session_id, target_language):
        captured["work_experience_len"] = len(cv_data.get("work_experience", [])) if isinstance(cv_data.get("work_experience"), list) else 0
        captured["skills_len"] = (
            len(cv_data.get("it_ai_skills", [])) if isinstance(cv_data.get("it_ai_skills"), list) else 0
        ) + (
            len(cv_data.get("technical_operational_skills", []))
            if isinstance(cv_data.get("technical_operational_skills"), list)
            else 0
        )
        return True, {
            "opening_paragraph": "Opening",
            "core_paragraphs": ["Core"],
            "closing_paragraph": "Closing",
            "signoff": "Best regards,\nTest User",
            "notes": "",
        }, ""

    monkeypatch.setattr(function_app, "_get_session_store", lambda: store)
    monkeypatch.setattr(function_app, "_openai_enabled", lambda: True)
    monkeypatch.setattr(function_app.product_config, "CV_ENABLE_COVER_LETTER", True)
    monkeypatch.setattr(function_app, "_generate_cover_letter_block_via_openai", _fake_generate_cover_letter_block_via_openai)

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "",
            "language": "en",
            "user_action": {"id": "COVER_LETTER_PREVIEW", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True
    assert payload.get("stage") == "cover_letter_review"
    assert payload.get("response") == "Cover letter draft ready."
    assert captured.get("work_experience_len", 0) > 0
    assert captured.get("skills_len", 0) > 0


def test_cover_letter_generate_survives_property_value_too_large_on_persist(monkeypatch):
    store = _FakeStorePersistTooLarge(
        session={
            "cv_data": {
                "full_name": "Test User",
                "work_experience": [
                    {
                        "title": "Operations Manager",
                        "employer": "Lonza",
                        "date_range": "2021-01 - 2025-01",
                        "bullets": ["Reduced changeover time by 30%"],
                    }
                ],
                "education": [{"title": "MSc", "institution": "University", "date_range": "2010-2015"}],
                "it_ai_skills": ["Automation"],
                "technical_operational_skills": ["KAIZEN"],
            },
            "metadata": {
                "flow_mode": "wizard",
                "wizard_stage": "cover_letter_review",
                "language": "en",
                "target_language": "en",
                "job_reference": {
                    "role_title": "Operational Excellence Manager",
                    "company": "Lonza",
                    "location": "Visp",
                    "must_haves": ["Lean Six Sigma"],
                    "tools_tech": ["VSM"],
                    "keywords": ["continuous improvement"],
                },
            },
        }
    )

    monkeypatch.setattr(function_app, "_get_session_store", lambda: store)
    monkeypatch.setattr(function_app, "_openai_enabled", lambda: True)
    monkeypatch.setattr(function_app.product_config, "CV_ENABLE_COVER_LETTER", True)

    monkeypatch.setattr(
        function_app,
        "_generate_cover_letter_block_via_openai",
        lambda **kwargs: (
            True,
            {
                "opening_paragraph": "Opening",
                "core_paragraphs": ["Core"],
                "closing_paragraph": "Closing",
                "signoff": "Best regards,\nTest User",
                "notes": "",
            },
            "",
        ),
    )
    monkeypatch.setattr(function_app, "render_cover_letter_pdf", lambda *args, **kwargs: b"%PDF-1.4\ncover-letter\n")
    monkeypatch.setattr(
        function_app,
        "_upload_pdf_blob_for_session",
        lambda **kwargs: {"container": "cv-pdfs", "blob_name": "s1/cover.pdf"},
    )

    status, payload = function_app._tool_process_cv_orchestrated(
        {
            "session_id": "s1",
            "message": "",
            "language": "en",
            "user_action": {"id": "COVER_LETTER_GENERATE", "payload": {}},
        }
    )

    assert status == 200
    assert payload.get("success") is True
    assert payload.get("response") == "Cover letter PDF generated."
    assert store.offload_updates > 0
