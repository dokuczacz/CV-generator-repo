from __future__ import annotations

from types import MethodType

from src.session_store import CVSessionStore


def test_offload_heavy_metadata_to_blob_keeps_table_summaries() -> None:
    store = object.__new__(CVSessionStore)

    def _fake_offload(self: CVSessionStore, session_id: str, payload: dict) -> str:
        assert session_id == "sid-meta"
        assert "event_log" in payload
        assert "pdf_refs" in payload
        return "cv-artifacts/sid-meta/metadata_heavy_1.json"

    store._offload_metadata_payload_to_blob = MethodType(_fake_offload, store)

    metadata = {
        "wizard_stage": "review_final",
        "event_log": [{"text": "a" * 5000}],
        "job_data_table_history": [{"company_name": "Acme"}] * 5,
        "job_posting_text": "Job text " + ("x" * 2000),
        "pdf_refs": {
            "new": {"created_at": "2026-03-05T20:00:00Z", "size_bytes": 111, "target_language": "de", "download_name": "new.pdf"},
            "old": {"created_at": "2026-03-04T20:00:00Z", "size_bytes": 99, "target_language": "en", "download_name": "old.pdf"},
        },
    }

    out = store._offload_heavy_metadata_to_blob("sid-meta", metadata)

    assert out["wizard_stage"] == "review_final"
    assert out["metadata_blob_ref"] == "cv-artifacts/sid-meta/metadata_heavy_1.json"
    assert set(out["metadata_blob_keys"]) >= {"event_log", "job_data_table_history", "job_posting_text", "pdf_refs"}
    assert out["event_log_count"] == 1
    assert out["job_data_table_history_count"] == 5
    assert out["job_posting_text_length"] > 2000
    assert "job_posting_text" not in out
    assert out["pdf_refs_count"] == 2
    assert len(out["pdf_refs"]) == 2


def test_get_session_with_blob_retrieval_hydrates_metadata_and_cv_data() -> None:
    store = object.__new__(CVSessionStore)

    def _fake_get_session(self: CVSessionStore, session_id: str):
        assert session_id == "sid-hydrate"
        return {
            "session_id": session_id,
            "cv_data": {"__offloaded__": True, "__blob_ref__": "cv-artifacts/sid-hydrate/cv.json"},
            "metadata": {"metadata_blob_ref": "cv-artifacts/sid-hydrate/meta.json", "wizard_stage": "contact"},
        }

    def _fake_retrieve_cv(self: CVSessionStore, blob_ref: str):
        assert blob_ref.endswith("cv.json")
        return {"full_name": "Jane Doe"}

    def _fake_retrieve_meta(self: CVSessionStore, blob_ref: str):
        assert blob_ref.endswith("meta.json")
        return {"event_log": [{"type": "user_message"}], "job_posting_text": "A long posting"}

    store.get_session = MethodType(_fake_get_session, store)
    store._retrieve_cv_data_from_blob = MethodType(_fake_retrieve_cv, store)
    store._retrieve_metadata_payload_from_blob = MethodType(_fake_retrieve_meta, store)

    session = store.get_session_with_blob_retrieval("sid-hydrate")

    assert isinstance(session, dict)
    assert session["cv_data"]["full_name"] == "Jane Doe"
    assert session["metadata"]["wizard_stage"] == "contact"
    assert session["metadata"]["job_posting_text"] == "A long posting"
    assert isinstance(session["metadata"]["event_log"], list)
