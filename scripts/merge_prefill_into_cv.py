import os
import sys
from typing import Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.session_store import CVSessionStore


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, tuple, dict)):
        return len(v) == 0
    return False


def main() -> None:
    session_id = (os.environ.get("CV_SESSION_ID") or "").strip()
    if not session_id:
        raise SystemExit("Set CV_SESSION_ID env var")

    store = CVSessionStore()
    session = store.get_session(session_id)
    if not session:
        raise SystemExit(f"Session not found: {session_id}")

    cv_data = session.get("cv_data") or {}
    metadata = session.get("metadata") or {}
    prefill = metadata.get("docx_prefill_unconfirmed")

    allow_fields = [
        "full_name",
        "email",
        "phone",
        "address_lines",
        "profile",
        "work_experience",
        "education",
        "further_experience",
        "languages",
        "it_ai_skills",
        "interests",
        "references",
    ]

    new_cv = dict(cv_data)
    applied = 0

    if isinstance(prefill, dict):
        for k in allow_fields:
            if k not in prefill:
                continue
            if k in new_cv and not _is_empty(new_cv.get(k)):
                continue

            v = prefill.get(k)
            if k in (
                "address_lines",
                "work_experience",
                "education",
                "further_experience",
                "languages",
                "it_ai_skills",
            ) and not isinstance(v, list):
                continue
            if k in (
                "full_name",
                "email",
                "phone",
                "profile",
                "interests",
                "references",
            ) and not isinstance(v, str):
                continue

            new_cv[k] = v
            applied += 1

    new_meta = dict(metadata)
    if applied > 0:
        new_meta["docx_prefill_unconfirmed"] = None

    ok = store.update_session(session_id, new_cv, new_meta)
    session2 = store.get_session(session_id) or {}
    cv2 = session2.get("cv_data") or {}

    print(
        {
            "session_id": session_id,
            "merge_applied": applied,
            "update_ok": ok,
            "after": {
                "full_name": cv2.get("full_name"),
                "email_present": bool((cv2.get("email") or "").strip()),
                "phone_present": bool((cv2.get("phone") or "").strip()),
                "work_experience_count": len(cv2.get("work_experience") or []),
                "education_count": len(cv2.get("education") or []),
            },
        }
    )


if __name__ == "__main__":
    main()
