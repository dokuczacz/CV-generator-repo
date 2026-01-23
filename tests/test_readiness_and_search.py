from function_app import _compute_readiness, _cv_session_search_hits


def test_compute_readiness_blocks_generate_until_confirmed():
    cv_data = {
        "full_name": "A B",
        "email": "a@example.com",
        "phone": "+1 555 000 000",
        "work_experience": [{"employer": "ACME", "title": "Role", "date_range": "2020-2021", "bullets": ["Did X"]}],
        "education": [{"institution": "Uni", "title": "MSc", "date_range": "2010-2015"}],
    }

    meta_unconfirmed = {"confirmed_flags": {"contact_confirmed": False, "education_confirmed": False}}
    r1 = _compute_readiness(cv_data, meta_unconfirmed)
    assert r1["can_generate"] is False
    assert "contact_not_confirmed" in r1["missing"]
    assert "education_not_confirmed" in r1["missing"]

    meta_confirmed = {"confirmed_flags": {"contact_confirmed": True, "education_confirmed": True}}
    r2 = _compute_readiness(cv_data, meta_confirmed)
    assert r2["can_generate"] is True
    assert r2["missing"] == []


def test_cv_session_search_hits_returns_bounded_previews():
    session = {
        "cv_data": {"full_name": "A B"},
        "metadata": {
            "docx_prefill_unconfirmed": {
                "full_name": "A B",
                "education": [{"institution": "Uni", "title": "MSc", "date_range": "2010-2015"}],
            },
            "event_log": [{"type": "update", "field_path": "full_name", "preview": "A B"}],
        },
    }

    out = _cv_session_search_hits(session=session, q="uni", limit=10)
    assert out["truncated"] is False
    assert any(h["source"] == "docx_prefill_unconfirmed" for h in out["hits"])
    assert all(len(h["preview"]) <= 240 for h in out["hits"])
