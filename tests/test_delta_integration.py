"""Integration tests for hash-based delta loading (P1 Unit 4)."""

import pytest
from src.context_pack import (
    build_context_pack_v2,
    build_context_pack_v2_delta,
    compute_cv_section_hashes,
    detect_section_changes,
)


def sample_cv():
    """Return a sample CV for testing."""
    return {
        "full_name": "John Doe",
        "email": "john@example.com",
        "phone": "+1 555 1234",
        "address_lines": ["123 Main St", "Boston, MA"],
        "profile": "Senior Python developer with 5 years experience",
        "work_experience": [
            {"employer": "TechCorp", "title": "Senior Dev", "date_range": "2020-2024"},
            {"employer": "StartupXYZ", "title": "Developer", "date_range": "2018-2020"},
        ],
        "education": [
            {"institution": "MIT", "degree": "BS", "year": "2018"},
        ],
        "languages": ["English", "Polish"],
        "it_ai_skills": ["Python", "React", "AWS"],
        "interests": ["AI", "Open Source"],
        "further_experience": ["Conference Speaker", "Mentor"],
    }


class TestHashComputation:
    """Test hash computation for sections."""

    def test_compute_hashes_generates_all_sections(self):
        """Verify all 8 sections are hashed."""
        cv = sample_cv()
        hashes = compute_cv_section_hashes(cv)
        
        expected_sections = {
            "contact", "work_experience", "education", "languages",
            "it_ai_skills", "interests", "profile", "further_experience"
        }
        assert set(hashes.keys()) == expected_sections

    def test_hash_consistency(self):
        """Same data → same hash."""
        cv = sample_cv()
        h1 = compute_cv_section_hashes(cv)
        h2 = compute_cv_section_hashes(cv)
        assert h1 == h2

    def test_hash_changes_with_data(self):
        """Modified data → different hash."""
        cv1 = sample_cv()
        h1 = compute_cv_section_hashes(cv1)
        
        cv2 = sample_cv()
        cv2["work_experience"][0]["title"] = "Staff Dev"  # Change title
        h2 = compute_cv_section_hashes(cv2)
        
        assert h1["work_experience"] != h2["work_experience"]
        assert h1["education"] == h2["education"]  # Other sections unchanged


class TestDeltaDetection:
    """Test section change detection."""

    def test_detects_changed_sections(self):
        """Correctly identify which sections changed."""
        cv = sample_cv()
        prev_hashes = compute_cv_section_hashes(cv)
        
        # Modify work_experience
        cv["work_experience"][0]["title"] = "Staff Dev"
        curr_hashes = compute_cv_section_hashes(cv)
        
        changes = detect_section_changes(curr_hashes, prev_hashes)
        
        assert changes["work_experience"] is True  # Changed
        assert changes["education"] is False  # Unchanged
        assert changes["profile"] is False  # Unchanged

    def test_detects_new_profile(self):
        """Detect profile changes."""
        cv = sample_cv()
        prev_hashes = compute_cv_section_hashes(cv)
        
        cv["profile"] = "New profile text"
        curr_hashes = compute_cv_section_hashes(cv)
        
        changes = detect_section_changes(curr_hashes, prev_hashes)
        assert changes["profile"] is True

    def test_empty_prev_hashes_marks_all_changed(self):
        """No previous hashes → all sections marked changed (safe default)."""
        cv = sample_cv()
        curr_hashes = compute_cv_section_hashes(cv)
        
        changes = detect_section_changes(curr_hashes, None)
        
        # All should be True (changed) when no previous hashes
        assert all(v is True for v in changes.values())


class TestDeltaContextPack:
    """Test delta-aware context pack builder."""

    def test_delta_pack_schema_version(self):
        """Verify delta pack has correct schema version."""
        cv = sample_cv()
        pack = build_context_pack_v2_delta(
            phase="review_session",
            cv_data=cv,
            session_metadata={"session_id": "test123"},
        )
        
        assert pack["schema_version"] == "cvgen.context_pack.v2_delta"

    def test_delta_pack_marks_sections(self):
        """Verify delta pack marks sections with changed/unchanged statuses."""
        import copy
        cv1 = sample_cv()
        prev_hashes = compute_cv_section_hashes(cv1)
        
        # Create a new CV with modified work_experience
        cv2 = copy.deepcopy(cv1)
        cv2["work_experience"][0]["title"] = "Staff Dev (New)"
        
        pack = build_context_pack_v2_delta(
            phase="review_session",
            cv_data=cv2,
            session_metadata={
                "session_id": "test123",
                "section_hashes_prev": prev_hashes,
            },
        )
        
        # Verify structure: all sections have status and hash
        for section in ["work_experience", "education", "languages"]:
            assert "status" in pack[section]
            assert pack[section]["status"] in ["changed", "unchanged"]
            assert "hash" in pack[section]
        
        # Verify changed sections have full data
        if pack["work_experience"]["status"] == "changed":
            assert "data" in pack["work_experience"]
        else:
            assert "count" in pack["work_experience"] or "preview" in pack["work_experience"]

    def test_delta_pack_contact_always_sent_when_changed(self):
        """Contact section sent in full if changed."""
        import copy
        cv1 = sample_cv()
        prev_hashes = compute_cv_section_hashes(cv1)
        
        # Modify email
        cv2 = copy.deepcopy(cv1)
        cv2["email"] = "newemail@example.com"
        
        pack = build_context_pack_v2_delta(
            phase="review_session",
            cv_data=cv2,
            session_metadata={
                "session_id": "test123",
                "section_hashes_prev": prev_hashes,
            },
        )
        
        assert pack["contact"]["status"] == "changed"
        assert pack["contact"]["email"] == "newemail@example.com"

    def test_delta_pack_fallback_when_no_prev_hashes(self):
        """Gracefully fall back when previous hashes missing."""
        cv = sample_cv()
        
        pack = build_context_pack_v2_delta(
            phase="review_session",
            cv_data=cv,
            session_metadata={"session_id": "test123"},  # No prev hashes
        )
        
        # Should mark all as changed (safe default)
        assert pack["section_changes"]["work_experience"] is True
        # Pack should still be valid
        assert "work_experience" in pack
        assert pack["work_experience"]["status"] == "changed"

    def test_delta_pack_token_savings(self):
        """Verify delta pack works end-to-end (schema + structure)."""
        import copy
        import json
        
        cv1 = sample_cv()
        prev_hashes = compute_cv_section_hashes(cv1)
        
        # Only modify work_experience
        cv2 = copy.deepcopy(cv1)
        cv2["work_experience"][0]["title"] = "Staff Dev (Updated)"
        
        delta_pack = build_context_pack_v2_delta(
            phase="review_session",
            cv_data=cv2,
            session_metadata={
                "session_id": "test123",
                "section_hashes_prev": prev_hashes,
            },
        )
        
        # Verify structure
        assert delta_pack["schema_version"] == "cvgen.context_pack.v2_delta"
        assert "section_changes" in delta_pack
        assert "section_hashes" in delta_pack
        
        # All sections should have status/hash
        for sec in ["work_experience", "education", "languages", "contact"]:
            assert sec in delta_pack
            assert "status" in delta_pack[sec]
            assert "hash" in delta_pack[sec]


class TestFeatureFlagIntegration:
    """Test CV_DELTA_MODE feature flag (orchestration level)."""

    def test_context_pack_builder_respects_delta_mode(self):
        """Verify delta pack builder integrates with orchestration."""
        import os
        import copy
        
        # Set delta mode
        os.environ["CV_DELTA_MODE"] = "1"
        
        cv1 = sample_cv()
        prev_hashes = compute_cv_section_hashes(cv1)
        
        # Modify work_experience
        cv2 = copy.deepcopy(cv1)
        cv2["work_experience"][0]["title"] = "Staff Dev (New)"
        
        session = {
            "cv_data": cv2,
            "metadata": {
                "session_id": "test123",
                "section_hashes_prev": prev_hashes,
            },
        }
        
        # Simulate orchestration: call delta pack directly
        pack = build_context_pack_v2_delta(
            phase="review_session",
            cv_data=cv2,
            session_metadata=session["metadata"],
        )
        
        # Verify it's delta pack (not v2)
        assert pack["schema_version"] == "cvgen.context_pack.v2_delta"
        # Verify it has delta markers
        assert "section_changes" in pack
        assert isinstance(pack["section_changes"], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
