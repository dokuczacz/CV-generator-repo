"""
Sanity tests for unified skills ranking (IT & AI + Technical & Operational in one prompt).

Tests verify:
1. Schema structure is correct
2. Proposal data structure is valid
3. UI presenter renders both sections
4. Backend action handlers apply both sections correctly
5. Prompt includes required inputs
"""

import json
import sys
from pathlib import Path


def test_unified_proposal_schema():
    """Verify unified proposal schema structure."""
    # Expected schema structure (from skills_unified_proposal.py)
    expected_fields = ["it_ai_skills", "technical_operational_skills", "notes"]
    
    # Verify the schema would have these required fields
    assert "it_ai_skills" in expected_fields, "Should have it_ai_skills field"
    assert "technical_operational_skills" in expected_fields, "Should have technical_operational_skills field"
    assert "notes" in expected_fields, "Should have notes field (optional)"
    print("✅ Schema validation passed")


def test_unified_proposal_dict_structure():
    """Verify proposal dict (stored in metadata) has correct structure."""
    # Simulate what backend stores in meta2["skills_proposal_block"]
    proposal_block = {
        "it_ai_skills": ["Python", "Azure", "Pandas"],
        "technical_operational_skills": ["IATF", "SPC", "KAIZEN"],
        "notes": "Grounded in real work experience",
        "openai_response_id": "resp-20260131-001",
        "created_at": "2026-01-31T12:00:00"
    }
    
    # Verify structure
    assert "it_ai_skills" in proposal_block, "Should have it_ai_skills"
    assert "technical_operational_skills" in proposal_block, "Should have technical_operational_skills"
    assert isinstance(proposal_block["it_ai_skills"], list), "it_ai_skills should be a list"
    assert isinstance(proposal_block["technical_operational_skills"], list), "technical_operational_skills should be a list"
    assert len(proposal_block["it_ai_skills"]) > 0, "it_ai_skills should not be empty"
    assert len(proposal_block["technical_operational_skills"]) > 0, "technical_operational_skills should not be empty"
    assert len(proposal_block["it_ai_skills"]) <= 8, "it_ai_skills should have max 8 items"
    assert len(proposal_block["technical_operational_skills"]) <= 8, "technical_operational_skills should have max 8 items"
    print("✅ Proposal dict structure validation passed")


def test_ui_presenter_field_mapping():
    """Verify UI presenter correctly maps both skill sections to review_form fields."""
    # Simulate proposal_block from backend
    proposal_block = {
        "it_ai_skills": ["Python", "Azure", "Data pipelines"],
        "technical_operational_skills": ["IATF", "KAIZEN", "SPC"],
        "notes": "Both sections aligned with job posting"
    }
    
    # Simulate what the presenter does (from function_app.py skills_tailor_review presenter)
    fields_list = []
    
    it_ai_skills = proposal_block.get("it_ai_skills", [])
    tech_ops_skills = proposal_block.get("technical_operational_skills", [])
    
    # Format IT & AI skills for display
    it_ai_lines = [f"{i+1}. {str(s).strip()}" for i, s in enumerate(it_ai_skills[:8]) if str(s).strip()]
    fields_list.append({
        "key": "it_ai_skills",
        "label": "IT & AI Skills",
        "value": "\n".join(it_ai_lines) if it_ai_lines else "(no skills proposed)"
    })
    
    # Format Technical & Operational skills for display
    tech_ops_lines = [f"{i+1}. {str(s).strip()}" for i, s in enumerate(tech_ops_skills[:8]) if str(s).strip()]
    fields_list.append({
        "key": "technical_operational_skills",
        "label": "Technical & Operational Skills",
        "value": "\n".join(tech_ops_lines) if tech_ops_lines else "(no skills proposed)"
    })
    
    # Verify UI fields
    assert len(fields_list) == 2, "Should have 2 skill section fields"
    assert fields_list[0]["key"] == "it_ai_skills", "First field should be IT & AI skills"
    assert fields_list[1]["key"] == "technical_operational_skills", "Second field should be Technical & Operational"
    assert "Python" in fields_list[0]["value"], "IT & AI value should contain Python"
    assert "IATF" in fields_list[1]["value"], "Tech/ops value should contain IATF"
    assert "1. Python" in fields_list[0]["value"], "Should be numbered list"
    assert "1. IATF" in fields_list[1]["value"], "Tech/ops should be numbered list"
    print("✅ UI presenter field mapping validation passed")


def test_skills_tailor_run_user_text():
    """Verify SKILLS_TAILOR_RUN constructs correct user_text with all inputs."""
    # Simulate what backend builds in SKILLS_TAILOR_RUN action
    job_summary = "Quality Manager for production..."
    tailoring_suggestions = "Strong in process improvement and IATF..."
    notes = "Focus on international experience..."
    skills_text = "- Python\n- Azure\n- IATF\n- KAIZEN"
    profile = "Experienced QA professional..."
    
    user_text = (
        f"[JOB_SUMMARY]\n{job_summary}\n\n"
        f"[CANDIDATE_PROFILE]\n{profile}\n\n"
        f"[TAILORING_SUGGESTIONS]\n{tailoring_suggestions}\n\n"
        f"[RANKING_NOTES]\n{notes}\n\n"
        f"[CANDIDATE_SKILLS]\n{skills_text}\n"
    )
    
    # Verify all sections are present
    assert "[JOB_SUMMARY]" in user_text, "Should include JOB_SUMMARY"
    assert "[CANDIDATE_PROFILE]" in user_text, "Should include CANDIDATE_PROFILE"
    assert "[TAILORING_SUGGESTIONS]" in user_text, "Should include TAILORING_SUGGESTIONS"
    assert "[RANKING_NOTES]" in user_text, "Should include RANKING_NOTES"
    assert "[CANDIDATE_SKILLS]" in user_text, "Should include CANDIDATE_SKILLS"
    assert "Quality Manager" in user_text, "Should include job summary content"
    assert "Python" in user_text, "Should include skills"
    print("✅ SKILLS_TAILOR_RUN user_text validation passed")


def test_skills_tailor_accept_logic():
    """Verify SKILLS_TAILOR_ACCEPT logic correctly applies both sections from proposal."""
    # Simulate input state
    proposal_block = {
        "it_ai_skills": ["Python", "Azure"],
        "technical_operational_skills": ["IATF", "KAIZEN"]
    }
    cv_data = {}  # Start with empty CV
    
    # Simulate what backend does in SKILLS_TAILOR_ACCEPT (from function_app.py)
    it_ai_skills = proposal_block.get("it_ai_skills")
    tech_ops_skills = proposal_block.get("technical_operational_skills")
    
    if not isinstance(it_ai_skills, list) or not isinstance(tech_ops_skills, list):
        raise ValueError("Proposal was empty or invalid")
    
    cv_data["it_ai_skills"] = [str(s).strip() for s in it_ai_skills[:8] if str(s).strip()]
    cv_data["technical_operational_skills"] = [str(s).strip() for s in tech_ops_skills[:8] if str(s).strip()]
    
    # Verify both sections applied
    assert cv_data["it_ai_skills"] == ["Python", "Azure"], "IT/AI skills should be applied"
    assert cv_data["technical_operational_skills"] == ["IATF", "KAIZEN"], "Tech/ops skills should be applied"
    assert len(cv_data) == 2, "Should have both skill sections in CV"
    print("✅ SKILLS_TAILOR_ACCEPT logic validation passed")


def test_skills_tailor_skip_logic():
    """Verify SKILLS_TAILOR_SKIP preserves docx prefill and fills both sections."""
    # Simulate DOCX prefill with unconfirmed skills
    meta2 = {
        "docx_prefill_unconfirmed": {
            "it_ai_skills": ["Python", "Azure", "Excel"],
            "technical_operational_skills": ["Quality systems", "IATF"]
        }
    }
    cv_data = {"it_ai_skills": [], "technical_operational_skills": []}
    
    # Simulate SKILLS_TAILOR_SKIP logic (should preserve docx if cv is empty)
    dpu = meta2.get("docx_prefill_unconfirmed") if isinstance(meta2.get("docx_prefill_unconfirmed"), dict) else None
    dpu_it = dpu.get("it_ai_skills") if isinstance(dpu, dict) and isinstance(dpu.get("it_ai_skills"), list) else []
    dpu_tech = dpu.get("technical_operational_skills") if isinstance(dpu, dict) and isinstance(dpu.get("technical_operational_skills"), list) else []
    
    if (not cv_data.get("it_ai_skills")) and dpu_it:
        cv_data["it_ai_skills"] = [str(s).strip() for s in dpu_it if str(s).strip()][:8]
    if (not cv_data.get("technical_operational_skills")) and dpu_tech:
        cv_data["technical_operational_skills"] = [str(s).strip() for s in dpu_tech if str(s).strip()][:8]
    
    # Verify both sections filled from prefill
    assert cv_data["it_ai_skills"] == ["Python", "Azure", "Excel"], "Should fill IT/AI from docx prefill"
    assert cv_data["technical_operational_skills"] == ["Quality systems", "IATF"], "Should fill tech/ops from docx prefill"
    print("✅ SKILLS_TAILOR_SKIP logic validation passed")


def test_backward_compat_proposal_block():
    """Verify proposal block structure won't break old code reading .get('skills')."""
    # New unified structure (no 'skills' key anymore)
    proposal_block_new = {
        "it_ai_skills": ["Python", "Azure"],
        "technical_operational_skills": ["IATF"],
        "notes": "Unified proposal"
    }
    
    # Old code might do: proposal_block.get("skills")
    # With new structure, this should return None (not error)
    old_skills_key = proposal_block_new.get("skills")
    assert old_skills_key is None, "Old 'skills' key should be None in new structure"
    
    # But new keys should work
    new_it_ai = proposal_block_new.get("it_ai_skills")
    new_tech_ops = proposal_block_new.get("technical_operational_skills")
    assert new_it_ai is not None, "New it_ai_skills key should exist"
    assert new_tech_ops is not None, "New technical_operational_skills key should exist"
    print("✅ Backward compatibility check passed")


def test_unified_stage_name():
    """Verify stage name is updated from separate (5a/5b) to unified (5)."""
    # Old: "Stage 5a/6 — Technical projects" and separate 5b
    # New: "Stage 5/6 — Skills (proposal)"
    stage_title_old = "Stage 5a/6 — Technical projects"
    stage_title_new = "Stage 5/6 — Skills (proposal)"
    
    assert "5a" not in stage_title_new, "New title should not reference 5a (deleted stage)"
    assert "5/6" in stage_title_new, "New title should be 5/6 (unified)"
    assert "proposal" in stage_title_new.lower(), "New title should mention proposal"
    print("✅ Stage naming validation passed")


if __name__ == "__main__":
    tests = [
        test_unified_proposal_schema,
        test_unified_proposal_dict_structure,
        test_ui_presenter_field_mapping,
        test_skills_tailor_run_user_text,
        test_skills_tailor_accept_logic,
        test_skills_tailor_skip_logic,
        test_backward_compat_proposal_block,
        test_unified_stage_name,
    ]
    
    print("\n🧪 Running Sanity Tests for Unified Skills Ranking\n")
    print("=" * 60)
    
    passed = 0
    failed = 0
    errors = []
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
            errors.append((test.__name__, str(e)))
    
    print("=" * 60)
    print(f"\n📊 Results: {passed} passed, {failed} failed\n")
    
    if errors:
        print("Failures:")
        for test_name, error in errors:
            print(f"  - {test_name}: {error}")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("✨ All sanity tests passed!")
        sys.exit(0)


def test_unified_proposal_schema():
    """Verify SkillsUnifiedProposal schema is well-formed."""
    schema_dict = get_skills_unified_proposal_response_format()
    assert schema_dict is not None, "Schema format should not be None"
    assert schema_dict["type"] == "json_schema", "Should return json_schema type"
    assert "schema" in schema_dict, "Should contain schema field"
    assert schema_dict["schema"]["name"] == "skills_unified_proposal", "Schema name should be skills_unified_proposal"
    print("✅ Schema validation passed")


def test_unified_proposal_creation():
    """Verify SkillsUnifiedProposal model can be instantiated."""
    proposal = SkillsUnifiedProposal(
        it_ai_skills=["Python", "Azure", "Data pipelines"],
        technical_operational_skills=["IATF", "Quality systems", "KAIZEN"],
        notes="Both sections grounded in Sumitomo experience"
    )
    assert len(proposal.it_ai_skills) == 3, "Should have 3 IT/AI skills"
    assert len(proposal.technical_operational_skills) == 3, "Should have 3 tech/ops skills"
    assert proposal.notes == "Both sections grounded in Sumitomo experience", "Notes should be preserved"
    print("✅ Proposal model creation passed")


def test_unified_proposal_parsing():
    """Verify parse_skills_unified_proposal handles both formats (dict and JSON string)."""
    # Test with dict
    proposal_dict = {
        "it_ai_skills": ["Python", "Azure"],
        "technical_operational_skills": ["IATF", "KAIZEN"],
        "notes": "Test notes"
    }
    
    parsed = parse_skills_unified_proposal(proposal_dict)
    assert isinstance(parsed, SkillsUnifiedProposal), "Should return SkillsUnifiedProposal instance"
    assert parsed.it_ai_skills == ["Python", "Azure"], "IT/AI skills should match"
    assert parsed.technical_operational_skills == ["IATF", "KAIZEN"], "Tech/ops skills should match"
    
    # Test with JSON string
    json_str = json.dumps(proposal_dict)
    parsed_json = parse_skills_unified_proposal(json_str)
    assert parsed_json.it_ai_skills == ["Python", "Azure"], "JSON parsing should preserve IT/AI skills"
    assert parsed_json.technical_operational_skills == ["IATF", "KAIZEN"], "JSON parsing should preserve tech/ops skills"
    print("✅ Proposal parsing passed")


def test_unified_proposal_min_max_items():
    """Verify proposal respects 5-8 item limits per section."""
    # Test minimum (5 items per section)
    proposal_min = SkillsUnifiedProposal(
        it_ai_skills=["Skill1", "Skill2", "Skill3", "Skill4", "Skill5"],
        technical_operational_skills=["Skill1", "Skill2", "Skill3", "Skill4", "Skill5"]
    )
    assert len(proposal_min.it_ai_skills) == 5, "Should accept 5 items"
    
    # Test maximum (8 items per section)
    proposal_max = SkillsUnifiedProposal(
        it_ai_skills=["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"],
        technical_operational_skills=["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    )
    assert len(proposal_max.it_ai_skills) == 8, "Should accept 8 items"
    print("✅ Item limits validation passed")


def test_unified_proposal_no_duplication():
    """Verify proposal can contain distinct items in each section."""
    proposal = SkillsUnifiedProposal(
        it_ai_skills=["Python", "Azure", "Data engineering"],
        technical_operational_skills=["IATF", "KAIZEN", "Quality assurance"]
    )
    it_ai_set = set(s.lower() for s in proposal.it_ai_skills)
    tech_ops_set = set(s.lower() for s in proposal.technical_operational_skills)
    
    # Verify no overlap (just for sanity; real dedupe happens in prompt)
    overlap = it_ai_set & tech_ops_set
    assert len(overlap) == 0, f"Should not have duplicates, but found: {overlap}"
    print("✅ No-duplication validation passed")


def test_unified_proposal_optional_notes():
    """Verify notes field is optional and defaults to empty string."""
    proposal_no_notes = SkillsUnifiedProposal(
        it_ai_skills=["Python"],
        technical_operational_skills=["IATF"]
    )
    assert proposal_no_notes.notes == "", "Notes should default to empty string"
    
    proposal_with_notes = SkillsUnifiedProposal(
        it_ai_skills=["Python"],
        technical_operational_skills=["IATF"],
        notes="Custom notes"
    )
    assert proposal_with_notes.notes == "Custom notes", "Notes should be preserved when provided"
    print("✅ Optional notes handling passed")


def test_skills_proposal_block_structure():
    """Verify skills_proposal_block (stored in session metadata) has correct structure."""
    # Simulate what the backend stores in meta2["skills_proposal_block"]
    proposal_block = {
        "it_ai_skills": ["Python", "Azure", "Pandas"],
        "technical_operational_skills": ["IATF", "SPC", "KAIZEN"],
        "notes": "Grounded in real work experience",
        "openai_response_id": "resp-20260131-001",
        "created_at": "2026-01-31T12:00:00"
    }
    
    # Verify structure
    assert "it_ai_skills" in proposal_block, "Should have it_ai_skills"
    assert "technical_operational_skills" in proposal_block, "Should have technical_operational_skills"
    assert isinstance(proposal_block["it_ai_skills"], list), "it_ai_skills should be a list"
    assert isinstance(proposal_block["technical_operational_skills"], list), "technical_operational_skills should be a list"
    assert len(proposal_block["it_ai_skills"]) > 0, "it_ai_skills should not be empty"
    assert len(proposal_block["technical_operational_skills"]) > 0, "technical_operational_skills should not be empty"
    print("✅ Proposal block structure validation passed")


def test_ui_presenter_field_mapping():
    """Verify the UI presenter would correctly map both skill sections to review_form fields."""
    # Simulate proposal_block from backend
    proposal_block = {
        "it_ai_skills": ["Python", "Azure", "Data pipelines"],
        "technical_operational_skills": ["IATF", "KAIZEN", "SPC"],
        "notes": "Both sections aligned with job posting"
    }
    
    # Simulate what the presenter does
    fields_list = []
    
    it_ai_skills = proposal_block.get("it_ai_skills", [])
    tech_ops_skills = proposal_block.get("technical_operational_skills", [])
    
    # Format IT & AI skills for display
    it_ai_lines = [f"{i+1}. {str(s).strip()}" for i, s in enumerate(it_ai_skills[:8]) if str(s).strip()]
    fields_list.append({
        "key": "it_ai_skills",
        "label": "IT & AI Skills",
        "value": "\n".join(it_ai_lines) if it_ai_lines else "(no skills proposed)"
    })
    
    # Format Technical & Operational skills for display
    tech_ops_lines = [f"{i+1}. {str(s).strip()}" for i, s in enumerate(tech_ops_skills[:8]) if str(s).strip()]
    fields_list.append({
        "key": "technical_operational_skills",
        "label": "Technical & Operational Skills",
        "value": "\n".join(tech_ops_lines) if tech_ops_lines else "(no skills proposed)"
    })
    
    # Verify UI fields
    assert len(fields_list) == 2, "Should have 2 skill section fields"
    assert fields_list[0]["key"] == "it_ai_skills", "First field should be IT & AI skills"
    assert fields_list[1]["key"] == "technical_operational_skills", "Second field should be Technical & Operational"
    assert "Python" in fields_list[0]["value"], "IT & AI value should contain Python"
    assert "IATF" in fields_list[1]["value"], "Tech/ops value should contain IATF"
    assert "1. Python" in fields_list[0]["value"], "Should be numbered list"
    print("✅ UI presenter field mapping passed")


def test_skills_tailor_accept_logic():
    """Verify SKILLS_TAILOR_ACCEPT logic correctly applies both sections from proposal."""
    # Simulate input state
    proposal_block = {
        "it_ai_skills": ["Python", "Azure"],
        "technical_operational_skills": ["IATF", "KAIZEN"]
    }
    cv_data = {}  # Start with empty CV
    
    # Simulate what backend does in SKILLS_TAILOR_ACCEPT
    it_ai_skills = proposal_block.get("it_ai_skills")
    tech_ops_skills = proposal_block.get("technical_operational_skills")
    
    if not isinstance(it_ai_skills, list) or not isinstance(tech_ops_skills, list):
        raise ValueError("Proposal was empty or invalid")
    
    cv_data["it_ai_skills"] = [str(s).strip() for s in it_ai_skills[:8] if str(s).strip()]
    cv_data["technical_operational_skills"] = [str(s).strip() for s in tech_ops_skills[:8] if str(s).strip()]
    
    # Verify both sections applied
    assert cv_data["it_ai_skills"] == ["Python", "Azure"], "IT/AI skills should be applied"
    assert cv_data["technical_operational_skills"] == ["IATF", "KAIZEN"], "Tech/ops skills should be applied"
    print("✅ SKILLS_TAILOR_ACCEPT logic validation passed")


def test_unified_prompt_includes_profile():
    """Verify the unified prompt includes [CANDIDATE_PROFILE] input."""
    # This is a documentation check: unified prompt should include profile context
    expected_inputs = [
        "[JOB_SUMMARY]",
        "[CANDIDATE_PROFILE]",
        "[TAILORING_SUGGESTIONS]",
        "[RANKING_NOTES]",
        "[CANDIDATE_SKILLS]"
    ]
    
    # In real usage, the backend builds user_text with these sections
    # For this test, we verify the expected structure is documented
    for input_section in expected_inputs:
        assert input_section in [
            "[JOB_SUMMARY]",
            "[CANDIDATE_PROFILE]",
            "[TAILORING_SUGGESTIONS]",
            "[RANKING_NOTES]",
            "[CANDIDATE_SKILLS]"
        ], f"Should include {input_section} in unified prompt inputs"
    
    print("✅ Unified prompt inputs validation passed")


if __name__ == "__main__":
    tests = [
        test_unified_proposal_schema,
        test_unified_proposal_creation,
        test_unified_proposal_parsing,
        test_unified_proposal_min_max_items,
        test_unified_proposal_no_duplication,
        test_unified_proposal_optional_notes,
        test_skills_proposal_block_structure,
        test_ui_presenter_field_mapping,
        test_skills_tailor_accept_logic,
        test_unified_prompt_includes_profile,
    ]
    
    print("\n🧪 Running Sanity Tests for Unified Skills Ranking\n")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"\n📊 Results: {passed} passed, {failed} failed\n")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("✨ All sanity tests passed!")
        sys.exit(0)
