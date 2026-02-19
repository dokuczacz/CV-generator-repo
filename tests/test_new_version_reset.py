from function_app import _reset_metadata_for_new_version


def test_new_version_reset_preserves_translation_cache_fields():
    metadata = {
        "target_language": "de",
        "active_cv_state": "translated",
        "active_cv_state_lang": "de",
        "cv_state_translated_refs": {"de": "blob://translated/de"},
        "bulk_translation_cache": {"en": {"summary": "..."}},
        "bulk_translation_source_hash": "abc123",
        "job_reference": "cached-job-ref",
        "job_reference_status": "ok",
        "job_reference_error": "",
        "job_reference_sig": "sig-job",
        "pdf_generated": True,
        "pdf_refs": ["pdf-1"],
        "latest_pdf_ref": "pdf-1",
        "work_experience_proposal_block": {"roles": []},
        "work_experience_proposal_sig": "sig-work",
        "skills_proposal_block": {"ranked_skills": []},
        "skills_proposal_sig": "sig-skills",
        "pending_confirmation": "WORK_CONFIRM",
        "work_selected_index": 2,
    }

    out = _reset_metadata_for_new_version(metadata)

    assert out.get("target_language") == "de"
    assert out.get("active_cv_state") == "translated"
    assert out.get("active_cv_state_lang") == "de"
    assert out.get("bulk_translation_cache") == {"en": {"summary": "..."}}
    assert out.get("bulk_translation_source_hash") == "abc123"

    assert out.get("pdf_generated") is False
    assert "pdf_refs" not in out
    assert "latest_pdf_ref" not in out
    assert "job_reference" not in out
    assert "job_reference_status" not in out
    assert out.get("job_reference_sig") == ""
    assert "work_experience_proposal_block" not in out
    assert out.get("work_experience_proposal_sig") == ""
    assert "skills_proposal_block" not in out
    assert out.get("skills_proposal_sig") == ""
    assert "pending_confirmation" not in out
    assert "work_selected_index" not in out
    assert isinstance(out.get("new_version_reset_at"), str)
