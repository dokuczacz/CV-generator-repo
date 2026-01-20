from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .normalize import normalize_cv_data


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


DEFAULT_MAX_PACK_CHARS = 12000


def build_context_pack(
    cv_data: Dict[str, Any],
    user_message: Optional[str] = None,
    job_posting_text: Optional[str] = None,
    user_preferences: Optional[Dict[str, Any]] = None,
    max_pack_chars: int = DEFAULT_MAX_PACK_CHARS,
) -> Dict[str, Any]:
    """Build a ContextPackV1 from parsed CV JSON and optional job posting.

    Guarantees:
    - Preserve work_experience[*].bullets verbatim (never truncated or removed).
    - Omit empty sections from `cv_structured` (renderer will skip them).
    - Enforce a size cap by removing low-priority sections when necessary.
    - Compute a stable fingerprint from the normalized CV JSON.
    """

    normalized = normalize_cv_data(cv_data)

    # Stable string for fingerprinting: deterministic JSON with sorted keys
    normalized_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    fingerprint = "sha256:" + _sha256_hex(normalized_json)

    # Build structured CV: copy relevant keys, omit empty/None
    keep_keys = [
        "full_name",
        "email",
        "phone",
        "address_lines",
        "nationality",
        "profile",
        "work_experience",
        "education",
        "languages",
        "it_ai_skills",
        "trainings",
        "interests",
        "data_privacy",
        "further_experience",
    ]

    cv_structured: Dict[str, Any] = {}
    for k in keep_keys:
        v = normalized.get(k)
        if v is None:
            continue
        # omit empty lists or empty strings
        if isinstance(v, list) and len(v) == 0:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        cv_structured[k] = v

    # Ensure bullets are preserved and accessible for checks
    # (no-op here; just guarantee key exists)
    for job in cv_structured.get("work_experience", []):
        if "bullets" not in job:
            job["bullets"] = []

    # Job posting snippet bounded
    job_snippet = None
    if job_posting_text:
        job_snippet = job_posting_text[:6000]

    pack: Dict[str, Any] = {
        "schema_version": "cvgen.context_pack.v1",
        "language": normalized.get("language", ""),
        "cv_fingerprint": fingerprint,
        "inputs": {
            "has_docx": False,
        },
        "cv_structured": cv_structured,
        "job_posting": {
            "text_snippet": job_snippet,
            "fingerprint": None,
        },
        "user_preferences": user_preferences or {},
        "limits": {
            "max_pack_chars": max_pack_chars,
            "cv_text_max_chars": 0,
            "job_text_max_chars": 6000,
        },
    }

    if job_snippet:
        pack["job_posting"]["fingerprint"] = "sha256:" + _sha256_hex(job_snippet)

    # Serialize and check size; if over limit, remove low-priority fields
    def _pack_size(p: Dict[str, Any]) -> int:
        return len(json.dumps(p, ensure_ascii=False, sort_keys=True))

    truncated_fields: List[str] = []
    size = _pack_size(pack)
    if size > max_pack_chars:
        # Stepwise drop priorities (never touch work_experience.bullets)
        for field in ["trainings", "interests", "it_ai_skills"]:
            if field in pack["cv_structured"]:
                del pack["cv_structured"][field]
                truncated_fields.append(field)
                size = _pack_size(pack)
                if size <= max_pack_chars:
                    break

    # If still too large, trim education.details entries (but keep education entries)
    if size > max_pack_chars and "education" in pack["cv_structured"]:
        for edu in pack["cv_structured"]["education"]:
            if isinstance(edu.get("details"), list) and edu["details"]:
                edu["details"] = []
                truncated_fields.append("education.details")
                size = _pack_size(pack)
                if size <= max_pack_chars:
                    break

    # Final check: if still too large, mark truncated flag (do not remove bullets)
    if size > max_pack_chars:
        pack.setdefault("limits", {})["truncated_fields"] = truncated_fields
        pack.setdefault("limits", {})["final_size"] = size
        pack.setdefault("limits", {})["note"] = (
            "Pack exceeds max size after safe removals; work_experience bullets preserved."
        )
    else:
        if truncated_fields:
            pack.setdefault("limits", {})["truncated_fields"] = truncated_fields
            pack.setdefault("limits", {})["final_size"] = size

    return pack


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: context_pack.py <cv_json_file>")
        raise SystemExit(2)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        cv = json.load(f)

    p = build_context_pack(cv)
    print(json.dumps(p, ensure_ascii=False, indent=2, sort_keys=True))
