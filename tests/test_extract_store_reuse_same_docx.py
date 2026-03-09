from __future__ import annotations

import base64
import hashlib

from src.orchestrator.tools.session_tools import ExtractStoreToolDeps, tool_extract_and_store_cv


class ReuseStoreStub:
    def __init__(self) -> None:
        self.create_called = False

    def find_latest_session_by_source_docx_hash(self, source_hash: str) -> str | None:
        return "sess-existing" if source_hash else None

    def get_session_with_blob_retrieval(self, session_id: str) -> dict | None:
        if session_id != "sess-existing":
            return None
        return {
            "session_id": session_id,
            "cv_data": {
                "full_name": "Jan Kowalski",
                "email": "jan@example.com",
                "phone": "+49 111",
                "work_experience": [{"employer": "ACME"}],
                "education": [{"institution": "PUT"}],
            },
            "metadata": {"source_docx_sha256": "x"},
            "expires_at": "2099-12-31T23:59:59",
        }

    def create_session(self, cv_data: dict, metadata: dict) -> str:
        self.create_called = True
        return "sess-new"


class CreateStoreStub:
    def __init__(self) -> None:
        self.last_metadata: dict | None = None

    def find_latest_session_by_source_docx_hash(self, source_hash: str) -> str | None:
        return None

    def create_session(self, cv_data: dict, metadata: dict) -> str:
        self.last_metadata = dict(metadata)
        return "sess-new"

    def get_session(self, session_id: str) -> dict | None:
        return {"expires_at": "2099-12-31T23:59:59"}

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        return True


def _build_deps(store):
    return ExtractStoreToolDeps(
        get_session_store=lambda: store,
        cleanup_expired_once=lambda _store: None,
        extract_first_photo_from_docx_bytes=lambda _docx: (_ for _ in ()).throw(AssertionError("extract should not run")),
        prefill_cv_from_docx_bytes=lambda _docx: (_ for _ in ()).throw(AssertionError("prefill should not run")),
        now_iso=lambda: "2026-03-06T10:00:00",
        looks_like_job_posting_text=lambda txt: (bool(txt), ""),
        fetch_text_from_url=lambda url, timeout=8.0: (False, "", "not-used"),
        blob_store_factory=lambda: None,
        stage_prepare_value="prepare",
    )


def test_extract_and_store_reuses_existing_session_for_same_docx_hash() -> None:
    store = ReuseStoreStub()
    deps = _build_deps(store)
    docx = b"same-cv-content"

    status, payload = tool_extract_and_store_cv(
        docx_base64=base64.b64encode(docx).decode("ascii"),
        language="en",
        extract_photo_flag=True,
        job_posting_url=None,
        job_posting_text=None,
        deps=deps,
    )

    assert status == 200
    assert payload["success"] is True
    assert payload["session_id"] == "sess-existing"
    assert payload["reused_session"] is True
    assert payload["reuse_reason"] == "same_docx_hash"
    assert payload["source_docx_sha256"] == hashlib.sha256(docx).hexdigest()
    assert store.create_called is False


def test_extract_and_store_persists_source_docx_hash_on_new_session() -> None:
    store = CreateStoreStub()

    # New-session path should execute prefill/extract functions, so provide safe no-op versions here.
    deps = ExtractStoreToolDeps(
        get_session_store=lambda: store,
        cleanup_expired_once=lambda _store: None,
        extract_first_photo_from_docx_bytes=lambda _docx: None,
        prefill_cv_from_docx_bytes=lambda _docx: {},
        now_iso=lambda: "2026-03-06T10:00:00",
        looks_like_job_posting_text=lambda txt: (bool(txt), ""),
        fetch_text_from_url=lambda url, timeout=8.0: (False, "", "not-used"),
        blob_store_factory=lambda: None,
        stage_prepare_value="prepare",
    )

    docx = b"brand-new-cv-content"
    expected_hash = hashlib.sha256(docx).hexdigest()

    status, payload = tool_extract_and_store_cv(
        docx_base64=base64.b64encode(docx).decode("ascii"),
        language="en",
        extract_photo_flag=False,
        job_posting_url=None,
        job_posting_text=None,
        deps=deps,
    )

    assert status == 200
    assert payload["success"] is True
    assert payload["session_id"] == "sess-new"
    assert payload["reused_session"] is False
    assert payload["source_docx_sha256"] == expected_hash
    assert isinstance(store.last_metadata, dict)
    assert store.last_metadata.get("source_docx_sha256") == expected_hash
