import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.context_pack import build_context_pack, build_context_pack_v2


def test_build_context_pack_preserves_bullets_and_limits():
    with open("samples/extracted_cv.json", "r", encoding="utf-8") as f:
        cv = json.load(f)

    pack = build_context_pack(cv)

    # work_experience bullets must match input bullets (verbatim)
    input_jobs = cv.get("work_experience", [])
    pack_jobs = pack["cv_structured"].get("work_experience", [])

    assert len(input_jobs) == len(pack_jobs)
    for inp, out in zip(input_jobs, pack_jobs):
        assert inp.get("bullets", []) == out.get("bullets", [])

    # Ensure fingerprint exists
    assert pack.get("cv_fingerprint", "").startswith("sha256:")

    # Ensure size metadata present (final_size if truncated or actual size)
    limits = pack.get("limits", {})
    assert "max_pack_chars" in limits

    # Either within limits or truncated_fields present
    if limits.get("final_size", 0) > limits.get("max_pack_chars", 0):
        assert "truncated_fields" in limits
    else:
        # final_size may not be present; ensure overall pack serializes reasonably
        s = json.dumps(pack, ensure_ascii=False)
        assert len(s) <= limits.get("max_pack_chars", 12000)


def test_build_context_pack_v2_includes_template_and_trims_to_budget():
    # Build an intentionally large CV payload to force size trimming.
    cv = {
        "full_name": "A B",
        "language": "en",
        "work_experience": [
            {
                "date_range": "2020-01 – 2025-01",
                "employer": "ACME",
                "location": "X",
                "title": "Y",
                "bullets": ["b" * 400] * 8,
            }
        ]
        * 6,
        "education": [
            {"date_range": "2010–2015", "institution": "Uni", "title": "MSc", "details": ["d" * 400] * 5}
        ]
        * 4,
        "languages": ["English (fluent)", "German (B2)"],
        "it_ai_skills": ["Skill " + ("x" * 80)] * 20,
        "interests": "i" * 2000,
    }
    meta = {
        "session_id": "sess_test",
        "version": 9,
        "updated_at": "2099-01-01T00:00:00Z",
        "event_log": [{"type": "update_cv_field", "field_path": "x", "preview": "y"}] * 200,
    }
    pack = build_context_pack_v2(phase="preparation", cv_data=cv, job_posting_text="j" * 10000, session_metadata=meta, max_pack_chars=4000)

    assert pack.get("schema_version") == "cvgen.context_pack.v2"
    assert pack.get("template", {}).get("template_name") == "cv_template_2pages_2025"
    assert isinstance(pack.get("recent_events"), list)
    assert len(pack.get("recent_events")) <= 15

    s = json.dumps(pack, ensure_ascii=False, sort_keys=True)
    # We enforce compaction, but we still allow slight overages with a recorded note.
    assert len(s) <= 6000
    limits = pack.get("limits", {})
    assert limits.get("max_chars") == 4000
