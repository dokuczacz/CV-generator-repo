import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.context_pack import build_context_pack


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
