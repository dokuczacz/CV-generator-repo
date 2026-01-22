from __future__ import annotations

import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCX = ROOT / "samples" / "Lebenslauf_Mariusz_Horodecki_CH.docx"

BASE_URL = os.environ.get("CV_LOCAL_FUNCTIONS_URL", "http://127.0.0.1:7071/api").rstrip("/")


def _http_json(method: str, url: str, payload: dict | None = None) -> tuple[int, dict, dict | str]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                return resp.status, dict(resp.headers), json.loads(text)
            except Exception:
                return resp.status, dict(resp.headers), text
    except urllib.error.HTTPError as e:
        raw = e.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return e.code, dict(e.headers), json.loads(text)
        except Exception:
            return e.code, dict(e.headers), text


def _require(condition: bool, msg: str) -> None:
    if not condition:
        print(f"FAIL: {msg}", file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    print(f"Using Functions base URL: {BASE_URL}")

    # 1) Health
    status, _, body = _http_json("GET", f"{BASE_URL}/health")
    _require(status == 200, f"/health expected 200, got {status}: {body}")
    print("OK: /health")

    # 2) Extract + store
    _require(SAMPLE_DOCX.exists(), f"Missing sample docx: {SAMPLE_DOCX}")
    docx_b64 = base64.b64encode(SAMPLE_DOCX.read_bytes()).decode("ascii")
    status, _, body = _http_json(
        "POST",
        f"{BASE_URL}/extract-and-store-cv",
        {"docx_base64": docx_b64, "language": "en", "extract_photo": True},
    )
    _require(status == 200, f"extract-and-store-cv expected 200, got {status}: {body}")
    _require(isinstance(body, dict) and body.get("success") is True, f"extract-and-store-cv failed: {body}")
    session_id = body.get("session_id")
    _require(isinstance(session_id, str) and session_id, f"missing session_id: {body}")
    print(f"OK: extract-and-store-cv session_id={session_id}")

    # 3) Get session and assert required fields present
    status, _, body = _http_json("POST", f"{BASE_URL}/get-cv-session", {"session_id": session_id})
    _require(status == 200, f"get-cv-session expected 200, got {status}: {body}")
    _require(isinstance(body, dict) and body.get("success") is True, f"get-cv-session failed: {body}")
    cv = body.get("cv_data") or {}
    _require(isinstance(cv, dict), f"cv_data is not a dict: {type(cv)}")

    _require(bool(str(cv.get("full_name", "")).strip()), "full_name should be extracted")
    _require(bool(str(cv.get("email", "")).strip()), "email should be extracted")
    _require(bool(str(cv.get("phone", "")).strip()), "phone should be extracted")
    _require(isinstance(cv.get("work_experience"), list) and len(cv["work_experience"]) >= 1, "work_experience should have >=1 entry")
    _require(isinstance(cv.get("education"), list) and len(cv["education"]) >= 1, "education should have >=1 entry")
    print("OK: get-cv-session required fields present")

    # 3b) Auto-fix common validator constraints so PDF generation can succeed without manual edits.
    # This is a smoke test for the backend pipeline (not the LLM quality).
    def _clamp(s: str, n: int) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        # Keep it simple and deterministic.
        return (s[: max(0, n - 1)]).rstrip() + "…"

    work = cv.get("work_experience") if isinstance(cv.get("work_experience"), list) else []
    fixed_work = []
    for job in work:
        if not isinstance(job, dict):
            continue
        bullets = job.get("bullets") if isinstance(job.get("bullets"), list) else []
        # Be more conservative than the validator to help satisfy the strict 2-page DoD.
        fixed_bullets = [_clamp(str(b or ""), 90) for b in bullets[:3]]
        fixed_job = dict(job)
        fixed_job["bullets"] = fixed_bullets
        fixed_job["employer"] = _clamp(str(fixed_job.get("employer", "")), 60)
        fixed_job["title"] = _clamp(str(fixed_job.get("title", "")), 80)
        fixed_job["location"] = _clamp(str(fixed_job.get("location", "")), 50)
        fixed_job["date_range"] = _clamp(str(fixed_job.get("date_range", "")), 25)
        fixed_work.append(fixed_job)

    # Keep only the most recent entries to reduce the chance of a 3-page spill.
    fixed_work = fixed_work[:4]

    edu = cv.get("education") if isinstance(cv.get("education"), list) else []
    fixed_edu = []
    for e in edu:
        if not isinstance(e, dict):
            continue
        fixed = dict(e)
        fixed["date_range"] = _clamp(str(fixed.get("date_range", "")), 20)
        fixed["institution"] = _clamp(str(fixed.get("institution", "")), 70)
        fixed["title"] = _clamp(str(fixed.get("title", "")), 90)
        details = fixed.get("details") if isinstance(fixed.get("details"), list) else []
        fixed["details"] = [_clamp(str(d or ""), 120) for d in details][:4]
        fixed_edu.append(fixed)

    # Apply in 2 calls to keep update_cv_field simple (whole-array replacement).
    status, _, body = _http_json(
        "POST",
        f"{BASE_URL}/update-cv-field",
        {"session_id": session_id, "field_path": "work_experience", "value": fixed_work},
    )
    _require(status == 200, f"update-cv-field(work_experience) expected 200, got {status}: {body}")
    status, _, body = _http_json(
        "POST",
        f"{BASE_URL}/update-cv-field",
        {"session_id": session_id, "field_path": "education", "value": fixed_edu},
    )
    _require(status == 200, f"update-cv-field(education) expected 200, got {status}: {body}")
    # Clamp profile and optional sections to help satisfy strict 2-page DoD in smoke runs.
    profile = cv.get("profile") or cv.get("summary") or ""
    status, _, body = _http_json(
        "POST",
        f"{BASE_URL}/update-cv-field",
        {"session_id": session_id, "field_path": "profile", "value": _clamp(str(profile), 320)},
    )
    _require(status == 200, f"update-cv-field(profile) expected 200, got {status}: {body}")

    languages = [str(x or "")[:50].rstrip() for x in (cv.get("languages") or [])][:5]
    skills = [str(x or "")[:70].rstrip() for x in (cv.get("it_ai_skills") or [])][:8]
    interests = _clamp(str(cv.get("interests") or ""), 350)

    fixed_further = []
    for fe in (cv.get("further_experience") or [])[:4]:
        if not isinstance(fe, dict):
            continue
        fixed_further.append(
            {
                "date_range": _clamp(str(fe.get("date_range") or ""), 25),
                "organization": _clamp(str(fe.get("organization") or ""), 70),
                "title": _clamp(str(fe.get("title") or ""), 90),
                "bullets": [_clamp(str(b or ""), 80) for b in (fe.get("bullets") or [])][:3],
            }
        )

    for field_path, value in [
        ("languages", languages),
        ("it_ai_skills", skills),
        ("interests", interests),
        ("further_experience", fixed_further),
        ("references", str(cv.get("references") or "")),
    ]:
        status, _, body = _http_json(
            "POST",
            f"{BASE_URL}/update-cv-field",
            {"session_id": session_id, "field_path": field_path, "value": value},
        )
        _require(status == 200, f"update-cv-field({field_path}) expected 200, got {status}: {body}")

    print("OK: auto-fixed constraints (work/edu/profile + optional clamps)")

    # 5) Generate PDF (optional strictness)
    status, _, body = _http_json(
        "POST",
        f"{BASE_URL}/generate-cv-from-session",
        {"session_id": session_id, "language": "en"},
    )
    if status != 200:
        print(f"PDF generation did not return 200 (status={status}). Body:\n{body}", file=sys.stderr)
        return 3
    if not isinstance(body, dict) or not body.get("success"):
        print(f"PDF generation returned unexpected payload:\n{body}", file=sys.stderr)
        return 3
    pdf_b64 = body.get("pdf_base64") or ""
    _require(isinstance(pdf_b64, str) and len(pdf_b64) > 1000, "pdf_base64 missing/too small")
    pdf_bytes = base64.b64decode(pdf_b64)
    _require(pdf_bytes.startswith(b"%PDF"), "output does not look like a PDF")
    out_dir = ROOT / "tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "local_smoke.pdf"
    try:
        out.write_bytes(pdf_bytes)
    except PermissionError:
        # Windows: file may be open in a PDF viewer; write a timestamped artifact instead.
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = out_dir / f"local_smoke_{ts}.pdf"
        out.write_bytes(pdf_bytes)
    print(f"OK: generate-cv-from-session wrote {out} bytes={len(pdf_bytes)}")

    try:
        from PyPDF2 import PdfReader

        pages = len(PdfReader(out).pages)
        print(f"OK: PDF pages={pages}")
    except Exception as e:
        print(f"WARN: could not count pages via PyPDF2: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
