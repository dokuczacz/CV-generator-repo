"""
Wave 0.1: Execution Latch (Idempotency) Tests

Tests that PDF generation is idempotent and prevents duplicate generation.
"""

import os
import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import datetime
import json

from src.normalize import normalize_cv_data


def _cv_sig(cv_data: dict) -> str:
    import function_app

    return function_app._sha256_text(json.dumps(normalize_cv_data(dict(cv_data or {})), ensure_ascii=False, sort_keys=True))


def test_latch_prevents_duplicate_pdf_generation():
    """Test that existing PDF prevents re-generation when latch is enabled."""

    # Mock session with existing PDF
    mock_session = {
        "session_id": "test-session-123",
        "cv_data": {
            "full_name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
            "work_experience": [{"employer": "Acme"}],
            "education": [{"institution": "MIT"}],
        },
        "metadata": {
            "language": "en",
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
            "pdf_refs": {
                "test-session-123-abc123": {
                    "container": "cv-pdfs",
                    "blob_name": "test-session-123/test-session-123-abc123.pdf",
                    "created_at": "2026-01-27T10:00:00",
                    "sha256": "abc123hash",
                    "cv_sig": "",
                    "target_language": "en",
                    "size_bytes": 145000,
                    "render_ms": 342,
                    "pages": 2,
                    "validation_passed": True,
                    "download_name": "John_Doe_CV.pdf",
                }
            },
        },
    }
    mock_session["metadata"]["pdf_refs"]["test-session-123-abc123"]["cv_sig"] = _cv_sig(mock_session["cv_data"])

    # Import the function
    from function_app import _tool_generate_cv_from_session

    # Call with latch enabled (default)
    with patch.dict(os.environ, {"CV_EXECUTION_LATCH": "1"}):
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id="test-session-123",
            language="en",
            client_context=None,
            session=mock_session,
        )

    # Should return existing PDF metadata, not generate new one
    assert status == 200
    assert content_type == "application/json"
    assert isinstance(payload, dict)
    assert payload.get("pdf_metadata", {}).get("from_cache") is True
    assert payload.get("pdf_metadata", {}).get("pdf_ref") == "test-session-123-abc123"
    assert payload.get("run_summary", {}).get("latch_engaged") is True


def test_latch_allows_first_pdf_generation():
    """Test that latch allows generation when no PDF exists."""

    # Mock session WITHOUT existing PDF
    mock_session = {
        "session_id": "test-session-456",
        "cv_data": {
            "full_name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "+9876543210",
            "profile": "Test profile",
            "work_experience": [{
                "employer": "Beta Corp",
                "position": "Engineer",
                "start_date": "2020-01",
                "end_date": "2025-01",
                "responsibilities": ["Task 1", "Task 2"]
            }],
            "education": [{
                "institution": "Stanford",
                "title": "BSc Computer Science",
                "start_date": "2016",
                "end_date": "2020"
            }],
            "languages": [{"language": "English", "proficiency": "Native"}],
            "it_ai_skills": ["Python", "JavaScript"],
        },
        "metadata": {
            "language": "en",
            "pdf_refs": {},  # No existing PDFs
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
        },
    }

    from function_app import _tool_generate_cv_from_session

    # Mock the PDF rendering and blob upload
    with patch("src.orchestrator.tools.cv_pdf_tools.render_pdf") as mock_render, \
         patch("function_app._upload_pdf_blob_for_session") as mock_upload, \
         patch("function_app._get_session_store") as mock_store, \
         patch("function_app._compute_readiness") as mock_ready, \
         patch("src.orchestrator.tools.cv_pdf_tools.validate_canonical_schema") as mock_schema, \
         patch("src.orchestrator.tools.cv_pdf_tools.validate_cv") as mock_validate, \
         patch("src.orchestrator.tools.cv_pdf_tools.count_pdf_pages") as mock_count_pages, \
         patch.dict(os.environ, {"CV_EXECUTION_LATCH": "1", "CV_GENERATION_STRICT_TEMPLATE": "0"}):

        mock_render.return_value = b"%PDF-1.4 fake pdf bytes"
        mock_upload.return_value = {
            "container": "cv-pdfs",
            "blob_name": "test-session-456/new-pdf-ref.pdf",
        }
        mock_ready.return_value = {
            "can_generate": True,
            "required_present": {
                "full_name": True,
                "email": True,
                "phone": True,
                "work_experience": True,
                "education": True,
            },
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
        }
        mock_schema.return_value = (True, [])
        mock_validate.return_value = SimpleNamespace(is_valid=True, errors=[])
        mock_count_pages.return_value = 2

        mock_store_instance = Mock()
        mock_store_instance.update_session.return_value = True
        mock_store_instance.get_session_with_blob_retrieval.return_value = {
            "cv_data": dict(mock_session.get("cv_data") or {}),
            "metadata": dict(mock_session.get("metadata") or {}),
        }
        mock_store_instance.update_session_with_blob_offload.return_value = True
        mock_store_instance.verify_pdf_metadata_persisted.return_value = (True, [])
        mock_store.return_value = mock_store_instance

        status, payload, content_type = _tool_generate_cv_from_session(
            session_id="test-session-456",
            language="en",
            client_context=None,
            session=mock_session,
        )

    # Should generate new PDF (latch not engaged)
    if status != 200:
        print(f"ERROR: Status={status}, Payload={payload}")
    assert status == 200
    # When PDF is generated, content_type should be application/pdf
    assert content_type == "application/pdf"
    mock_render.assert_called_once()


def test_latch_ignores_cover_letter_refs_when_reusing_cv_pdf() -> None:
    """If newest ref is cover letter, latch should still reuse newest CV ref."""

    mock_session = {
        "session_id": "test-session-cover-priority",
        "cv_data": {
            "full_name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
            "work_experience": [{"employer": "Acme"}],
            "education": [{"institution": "MIT"}],
        },
        "metadata": {
            "language": "en",
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
            "pdf_refs": {
                "cover_letter_newer": {
                    "kind": "cover_letter",
                    "container": "cv-pdfs",
                    "blob_name": "test-session-cover-priority/cover_letter_newer.pdf",
                    "created_at": "2026-01-27T12:00:00",
                    "target_language": "en",
                },
                "cv_ref_older": {
                    "container": "cv-pdfs",
                    "blob_name": "test-session-cover-priority/cv_ref_older.pdf",
                    "created_at": "2026-01-27T10:00:00",
                    "sha256": "cvhash",
                    "cv_sig": "",
                    "target_language": "en",
                    "size_bytes": 145000,
                    "render_ms": 342,
                    "pages": 2,
                    "validation_passed": True,
                    "download_name": "John_Doe_CV.pdf",
                },
            },
        },
    }
    mock_session["metadata"]["pdf_refs"]["cv_ref_older"]["cv_sig"] = _cv_sig(mock_session["cv_data"])

    from function_app import _tool_generate_cv_from_session

    with patch("src.orchestrator.tools.cv_pdf_tools.CVBlobStore.download_bytes") as mock_download, patch.dict(
        os.environ, {"CV_EXECUTION_LATCH": "1"}
    ):
        mock_download.return_value = b"%PDF-1.4 cached cv"
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id="test-session-cover-priority",
            language="en",
            client_context=None,
            session=mock_session,
        )

    assert status == 200
    assert content_type == "application/pdf"
    assert isinstance(payload, dict)
    assert isinstance(payload.get("pdf_bytes"), (bytes, bytearray))


def test_download_only_reuses_cached_pdf_despite_job_sig_mismatch() -> None:
    mock_session = {
        "session_id": "test-session-download-only",
        "cv_data": {
            "full_name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
            "work_experience": [{"employer": "Acme"}],
            "education": [{"institution": "MIT"}],
        },
        "metadata": {
            "language": "en",
            "target_language": "en",
            "current_job_sig": "newjobsig123456",
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
            "pdf_refs": {
                "cv_ref_existing": {
                    "container": "cv-pdfs",
                    "blob_name": "test-session-download-only/cv_ref_existing.pdf",
                    "created_at": "2026-01-27T10:00:00",
                    "job_sig": "oldjobsig654321",
                    "cv_sig": "",
                    "target_language": "en",
                    "size_bytes": 145000,
                    "render_ms": 342,
                    "pages": 2,
                    "validation_passed": True,
                    "download_name": "John_Doe_CV.pdf",
                }
            },
        },
    }
    mock_session["metadata"]["pdf_refs"]["cv_ref_existing"]["cv_sig"] = _cv_sig(mock_session["cv_data"])

    from function_app import _tool_generate_cv_from_session

    with patch("src.orchestrator.tools.cv_pdf_tools.CVBlobStore.download_bytes") as mock_download, patch.dict(
        os.environ, {"CV_EXECUTION_LATCH": "1"}
    ):
        mock_download.return_value = b"%PDF-1.4 cached cv"
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id="test-session-download-only",
            language="en",
            client_context={"pdf_action": "download_only"},
            session=mock_session,
        )

    assert status == 200
    assert content_type == "application/pdf"
    assert isinstance(payload, dict)
    assert isinstance(payload.get("pdf_bytes"), (bytes, bytearray))


def test_latch_disabled_allows_regeneration():
    """Test that disabling latch allows re-generation even with existing PDF."""

    # Mock session with existing PDF
    mock_session = {
        "session_id": "test-session-789",
        "cv_data": {
            "full_name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "+1111111111",
            "profile": "Test profile",
            "work_experience": [{
                "employer": "Gamma Inc",
                "position": "Manager",
                "start_date": "2018-01",
                "end_date": "2025-01",
                "responsibilities": ["Task A", "Task B"]
            }],
            "education": [{
                "institution": "Harvard",
                "title": "MBA",
                "start_date": "2015",
                "end_date": "2017"
            }],
            "languages": [{"language": "English", "proficiency": "Native"}],
            "it_ai_skills": ["Excel", "PowerPoint"],
        },
        "metadata": {
            "language": "en",
            "pdf_refs": {
                "existing-pdf-ref": {
                    "created_at": "2026-01-20T10:00:00",
                    "sha256": "oldhash",
                }
            },
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
        },
    }

    from function_app import _tool_generate_cv_from_session

    # Mock the PDF rendering and blob upload
    with patch("src.orchestrator.tools.cv_pdf_tools.render_pdf") as mock_render, \
         patch("function_app._upload_pdf_blob_for_session") as mock_upload, \
         patch("function_app._get_session_store") as mock_store, \
         patch("function_app._compute_readiness") as mock_ready, \
         patch("src.orchestrator.tools.cv_pdf_tools.validate_canonical_schema") as mock_schema, \
         patch("src.orchestrator.tools.cv_pdf_tools.validate_cv") as mock_validate, \
         patch("src.orchestrator.tools.cv_pdf_tools.count_pdf_pages") as mock_count_pages, \
         patch.dict(os.environ, {"CV_EXECUTION_LATCH": "0", "CV_GENERATION_STRICT_TEMPLATE": "0"}):  # Latch DISABLED

        mock_render.return_value = b"%PDF-1.4 new pdf bytes"
        mock_upload.return_value = {
            "container": "cv-pdfs",
            "blob_name": "test-session-789/new-pdf-ref-2.pdf",
        }
        mock_ready.return_value = {
            "can_generate": True,
            "required_present": {
                "full_name": True,
                "email": True,
                "phone": True,
                "work_experience": True,
                "education": True,
            },
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
        }
        mock_schema.return_value = (True, [])
        mock_validate.return_value = SimpleNamespace(is_valid=True, errors=[])
        mock_count_pages.return_value = 2

        mock_store_instance = Mock()
        mock_store_instance.update_session.return_value = True
        mock_store_instance.get_session_with_blob_retrieval.return_value = {
            "cv_data": dict(mock_session.get("cv_data") or {}),
            "metadata": dict(mock_session.get("metadata") or {}),
        }
        mock_store_instance.update_session_with_blob_offload.return_value = True
        mock_store_instance.verify_pdf_metadata_persisted.return_value = (True, [])
        mock_store.return_value = mock_store_instance

        status, payload, content_type = _tool_generate_cv_from_session(
            session_id="test-session-789",
            language="en",
            client_context=None,
            session=mock_session,
        )

    # Should generate NEW PDF even though one exists (latch disabled)
    assert status == 200
    mock_render.assert_called_once()


def test_latch_returns_latest_pdf_when_multiple():
    """Test that latch returns the most recent PDF when multiple exist."""

    # Mock session with MULTIPLE existing PDFs
    mock_session = {
        "session_id": "test-session-multi",
        "cv_data": {
            "full_name": "Alice Brown",
            "email": "alice@example.com",
            "phone": "+2222222222",
            "work_experience": [{"employer": "Delta Corp"}],
            "education": [{"institution": "Yale"}],
        },
        "metadata": {
            "language": "en",
            "confirmed_flags": {
                "contact_confirmed": True,
                "education_confirmed": True,
            },
            "pdf_refs": {
                "old-pdf-ref": {
                    "created_at": "2026-01-20T10:00:00",
                    "sha256": "oldhash1",
                    "cv_sig": "",
                    "target_language": "en",
                },
                "newer-pdf-ref": {
                    "created_at": "2026-01-25T15:30:00",
                    "sha256": "newhash2",
                    "cv_sig": "",
                    "target_language": "en",
                },
                "latest-pdf-ref": {
                    "created_at": "2026-01-27T12:00:00",  # Most recent
                    "sha256": "latesthash3",
                    "cv_sig": "",
                    "target_language": "en",
                    "pages": 2,
                },
            },
        },
    }
    sig = _cv_sig(mock_session["cv_data"])
    for _k, _v in (mock_session.get("metadata") or {}).get("pdf_refs", {}).items():
        if isinstance(_v, dict):
            _v["cv_sig"] = sig

    from function_app import _tool_generate_cv_from_session

    with patch.dict(os.environ, {"CV_EXECUTION_LATCH": "1"}):
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id="test-session-multi",
            language="en",
            client_context=None,
            session=mock_session,
        )

    # Should return the LATEST pdf_ref
    assert status == 200
    assert payload.get("pdf_metadata", {}).get("pdf_ref") == "latest-pdf-ref"
    assert payload.get("pdf_metadata", {}).get("sha256") == "latesthash3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
