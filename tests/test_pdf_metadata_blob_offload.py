#!/usr/bin/env python3
"""
Test: PDF metadata persistence with blob offload for large cv_data

Regression test for PropertyValueTooLarge error in Azure Table Storage.
Tests that large cv_data is automatically offloaded to blob storage.
"""

import pytest
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_store import CVSessionStore
from src.blob_store import CVBlobStore
import os


def test_small_cv_data_stored_in_table():
    """Test that small cv_data is stored directly in Table Storage (normal path)"""
    store = CVSessionStore()
    
    # Create small CV data
    small_cv_data = {
        "full_name": "Test User",
        "email": "test@example.com",
        "work_experience": [
            {
                "employer": "Test Company",
                "role_title": "Developer",
                "bullets": ["Developed features"]
            }
        ]
    }
    
    # Create session
    session_id = store.create_session(small_cv_data, {"test": "small_data"})
    
    # Update with blob offload method (should store in table)
    success = store.update_session_with_blob_offload(
        session_id,
        small_cv_data,
        {"pdf_generated": True}
    )
    
    assert success, "Should successfully store small cv_data"
    
    # Retrieve and verify
    session = store.get_session(session_id)
    assert session is not None
    assert session["cv_data"]["full_name"] == "Test User"
    assert session["metadata"]["pdf_generated"] is True
    
    # Verify cv_data is not offloaded
    assert "__offloaded__" not in session["cv_data"]
    
    # Cleanup
    store.delete_session(session_id)


def test_large_cv_data_offloaded_to_blob():
    """Test that large cv_data is automatically offloaded to blob storage"""
    store = CVSessionStore()
    
    # Create large CV data (exceeding 50KB limit)
    large_cv_data = {
        "full_name": "Test User With Very Long CV",
        "email": "test@example.com",
        "work_experience": []
    }
    
    # Add many work experiences to exceed size limit
    for i in range(100):
        large_cv_data["work_experience"].append({
            "employer": f"Company {i}" + " " * 1000,  # Pad to increase size
            "role_title": f"Role {i}" + " " * 1000,
            "bullets": [
                f"Bullet {j} with lots of text " + ("x" * 500)
                for j in range(10)
            ],
            "description": "Long description " + ("y" * 2000)
        })
    
    # Create session
    session_id = store.create_session({"initial": "data"}, {"test": "large_data"})
    
    # Estimate size (should be > 50KB)
    cv_json = json.dumps(large_cv_data, ensure_ascii=False)
    cv_size = len(cv_json.encode('utf-8'))
    assert cv_size > 50000, f"Test data should be > 50KB, got {cv_size} bytes"
    
    # Update with blob offload method (should offload to blob)
    success = store.update_session_with_blob_offload(
        session_id,
        large_cv_data,
        {"pdf_generated": True},
        max_table_size=50000
    )
    
    assert success, "Should successfully offload large cv_data to blob"
    
    # Retrieve session (should have blob reference in table)
    session_raw = store.get_session(session_id)
    assert session_raw is not None
    assert session_raw["cv_data"].get("__offloaded__") is True, "cv_data should be marked as offloaded"
    assert "__blob_ref__" in session_raw["cv_data"], "Should have blob reference"
    
    # Retrieve with blob retrieval (should restore full cv_data)
    session_full = store.get_session_with_blob_retrieval(session_id)
    assert session_full is not None
    assert session_full["cv_data"]["full_name"] == "Test User With Very Long CV"
    assert len(session_full["cv_data"]["work_experience"]) == 100
    assert session_full["metadata"]["pdf_generated"] is True
    assert "cv_data_blob_ref" in session_full["metadata"], "Metadata should have blob ref tracking"
    
    # Cleanup
    store.delete_session(session_id)
    
    # Cleanup blob (extract blob ref from session)
    blob_ref = session_raw["cv_data"]["__blob_ref__"]
    container = blob_ref.split("/")[0]
    blob_store = CVBlobStore(container=container)
    # Note: blob cleanup would require delete_prefix or similar, skip for now


def test_pdf_metadata_verification_success():
    """Test post-write verification for successful PDF metadata persistence"""
    store = CVSessionStore()
    
    cv_data = {
        "full_name": "Test User",
        "email": "test@example.com"
    }
    
    # Create session
    session_id = store.create_session(cv_data, {})
    
    # Simulate PDF generation metadata
    pdf_ref = f"test_pdf_{session_id[:8]}"
    metadata = {
        "pdf_generated": True,
        "pdf_refs": {
            pdf_ref: {
                "container": "cv-pdfs",
                "blob_name": f"{session_id}/{pdf_ref}.pdf",
                "created_at": "2026-02-14T12:00:00",
                "sha256": "abc123",
                "size_bytes": 12345,
                "pages": 2
            }
        }
    }
    
    # Update session with PDF metadata
    success = store.update_session_with_blob_offload(session_id, cv_data, metadata)
    assert success
    
    # Verify PDF metadata persistence
    verify_ok, errors = store.verify_pdf_metadata_persisted(session_id, pdf_ref)
    
    assert verify_ok, f"Verification should pass, got errors: {errors}"
    assert len(errors) == 0
    
    # Cleanup
    store.delete_session(session_id)


def test_pdf_metadata_verification_failure():
    """Test post-write verification detects missing PDF metadata"""
    store = CVSessionStore()
    
    cv_data = {"full_name": "Test User"}
    
    # Create session without pdf_generated flag
    session_id = store.create_session(cv_data, {"test": "no_pdf"})
    
    # Verify should fail (no pdf_generated flag)
    verify_ok, errors = store.verify_pdf_metadata_persisted(session_id, "nonexistent_pdf")
    
    assert not verify_ok, "Verification should fail when pdf_generated is False"
    assert len(errors) > 0
    assert any("pdf_generated" in err for err in errors)
    
    # Cleanup
    store.delete_session(session_id)


def test_multiple_pdf_generations_with_size_limit():
    """Test that multiple PDF regenerations with pdf_refs growth are handled correctly"""
    store = CVSessionStore()
    
    cv_data = {"full_name": "Test User"}
    session_id = store.create_session(cv_data, {})
    
    # Generate 5 PDFs (more than the 3-reference limit in shrink function)
    for i in range(5):
        pdf_ref = f"pdf_{i}"
        metadata = {
            "pdf_generated": True,
            "pdf_refs": {}
        }
        
        # Retrieve existing pdf_refs
        session = store.get_session(session_id)
        if session and session.get("metadata"):
            metadata["pdf_refs"] = session["metadata"].get("pdf_refs", {})
        
        # Add new PDF ref
        metadata["pdf_refs"][pdf_ref] = {
            "container": "cv-pdfs",
            "blob_name": f"{session_id}/{pdf_ref}.pdf",
            "created_at": f"2026-02-14T12:0{i}:00",
            "sha256": f"hash_{i}",
            "size_bytes": 10000 + i,
            "pages": 2
        }
        
        success = store.update_session_with_blob_offload(session_id, cv_data, metadata)
        assert success, f"Should handle PDF regeneration {i}"
    
    # Verify final state
    final_session = store.get_session(session_id)
    assert final_session is not None
    assert final_session["metadata"]["pdf_generated"] is True
    
    # All 5 refs should be present (shrinking only happens in _shrink_metadata_for_table)
    assert len(final_session["metadata"]["pdf_refs"]) == 5
    
    # Cleanup
    store.delete_session(session_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
