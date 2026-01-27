"""
Azure Functions app for CV Generator.

Public surface area (intentionally minimal):
  - GET  /api/health
  - POST /api/cv-tool-call-handler

All workflow operations are routed through the tool dispatcher to keep the API surface small and the UI thin.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import azure.functions as func
from openai import OpenAI

# Reduce Azure SDK HTTP noise; keep only warnings/errors.
for _logger_name in (
    "azure",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.data.tables",
    "azure.storage.blob",
):
    try:
        logging.getLogger(_logger_name).setLevel(logging.WARNING)
    except Exception:
        pass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.blob_store import BlobPointer, CVBlobStore
from src.context_pack import build_context_pack_v2, format_context_pack_with_delimiters
from src.docx_photo import extract_first_photo_from_docx_bytes
from src.docx_prefill import prefill_cv_from_docx_bytes
from src.normalize import normalize_cv_data
from src.render import count_pdf_pages, render_html, render_pdf
from src.schema_validator import validate_canonical_schema
from src.session_store import CVSessionStore
from src.structured_response import CVAssistantResponse, get_response_format, parse_structured_response, format_user_message_for_ui
from src.validator import validate_cv
from src.cv_fsm import CVStage, SessionState, ValidationState, resolve_stage, detect_edit_intent


_SESSION_STORE: CVSessionStore | None = None
_CLEANUP_EXPIRED_RAN = False


def _get_session_store() -> CVSessionStore:
    global _SESSION_STORE
    if _SESSION_STORE is None:
        _SESSION_STORE = CVSessionStore()
    return _SESSION_STORE


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _update_section_hashes_in_metadata(session_id: str, cv_data: dict) -> None:
    """Update section_hashes in session metadata after CV changes.
    
    Stores current hashes and preserves previous hashes for delta detection.
    Call this after any update_cv_field operation.
    """
    from src.context_pack import compute_cv_section_hashes
    
    store = _get_session_store()
    session = store.get_session(session_id)
    if not session:
        logging.warning(f"Cannot update hashes: session {session_id} not found")
        return
    
    metadata = session.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    
    metadata = dict(metadata)
    
    # Compute new hashes
    new_hashes = compute_cv_section_hashes(cv_data)
    
    # Preserve previous hashes for delta detection
    prev_hashes = metadata.get("section_hashes")
    if prev_hashes:
        metadata["section_hashes_prev"] = prev_hashes
    
    metadata["section_hashes"] = new_hashes
    metadata["section_hashes_updated_at"] = _now_iso()
    
    # Update metadata only (cv_data already updated by caller)
    store.update_session(session_id, cv_data, metadata)
    logging.debug(f"Updated section hashes for session {session_id}")


def _get_openai_prompt_id() -> str | None:
    prompt_id = (os.environ.get("OPENAI_PROMPT_ID") or "").strip() or None
    if prompt_id:
        return prompt_id
    # Local dev fallback: read from local.settings.json if available (Azure Functions loads it into env
    # when using `func start`, but IDE/debug setups sometimes don't).
    try:
        settings_path = Path(__file__).parent / "local.settings.json"
        if settings_path.exists():
            doc = json.loads(settings_path.read_text(encoding="utf-8"))
            values = doc.get("Values") if isinstance(doc, dict) else None
            if isinstance(values, dict):
                prompt_id = (values.get("OPENAI_PROMPT_ID") or "").strip() or None
                if prompt_id:
                    return prompt_id
    except Exception:
        pass
    return None


def _require_openai_prompt_id() -> bool:
    return str(os.environ.get("REQUIRE_OPENAI_PROMPT_ID", "0")).strip() == "1"


def _json_response(payload: dict, *, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        mimetype="application/json; charset=utf-8",
        status_code=status_code,
    )


def _serialize_validation_result(validation_result) -> dict:
    """Convert ValidationResult to JSON-safe dict."""
    return {
        "is_valid": validation_result.is_valid,
        "errors": [asdict(err) for err in validation_result.errors],
        "warnings": validation_result.warnings,
        "estimated_pages": validation_result.estimated_pages,
        "estimated_height_mm": validation_result.estimated_height_mm,
        "details": validation_result.details,
    }


def _compute_required_present(cv_data: dict) -> dict:
    return {
        "full_name": bool(cv_data.get("full_name", "").strip()) if isinstance(cv_data.get("full_name"), str) else False,
        "email": bool(cv_data.get("email", "").strip()) if isinstance(cv_data.get("email"), str) else False,
        "phone": bool(cv_data.get("phone", "").strip()) if isinstance(cv_data.get("phone"), str) else False,
        "work_experience": bool(cv_data.get("work_experience")) and isinstance(cv_data.get("work_experience"), list),
        "education": bool(cv_data.get("education")) and isinstance(cv_data.get("education"), list),
    }


def _compute_readiness(cv_data: dict, metadata: dict) -> dict:
    required_present = _compute_required_present(cv_data)
    strict_template = str(os.environ.get("CV_GENERATION_STRICT_TEMPLATE", "0")).strip() == "1"
    if strict_template:
        required_present = dict(required_present)
        required_present.update(
            {
                "address_lines": isinstance(cv_data.get("address_lines"), list) and len(cv_data.get("address_lines") or []) > 0,
                "profile": isinstance(cv_data.get("profile"), str) and bool(cv_data.get("profile", "").strip()),
                "languages": isinstance(cv_data.get("languages"), list) and len(cv_data.get("languages") or []) > 0,
                "it_ai_skills": isinstance(cv_data.get("it_ai_skills"), list) and len(cv_data.get("it_ai_skills") or []) > 0,
            }
        )
    confirmed_flags = (metadata or {}).get("confirmed_flags") or {}
    contact_ok = bool(confirmed_flags.get("contact_confirmed"))
    education_ok = bool(confirmed_flags.get("education_confirmed"))
    missing: list[str] = []
    for k, v in required_present.items():
        if not v:
            missing.append(k)
    if not contact_ok:
        missing.append("contact_not_confirmed")
    if not education_ok:
        missing.append("education_not_confirmed")
    can_generate = all(required_present.values()) and contact_ok and education_ok
    return {
        "can_generate": can_generate,
        "required_present": required_present,
        "strict_template": strict_template,
        "confirmed_flags": {
            "contact_confirmed": contact_ok,
            "education_confirmed": education_ok,
            "confirmed_at": confirmed_flags.get("confirmed_at"),
        },
        "missing": missing,
    }


def _merge_docx_prefill_into_cv_data_if_needed(*, cv_data: dict, docx_prefill: dict, meta: dict) -> tuple[dict, dict, int]:
    """
    When a session was created from DOCX, we keep an unconfirmed prefill snapshot in metadata.
    After user confirmation, we can safely copy missing fields into canonical cv_data to unblock
    validation + PDF generation.
    Returns: (new_cv_data, new_meta, applied_fields_count)
    """
    if not isinstance(cv_data, dict) or not isinstance(docx_prefill, dict) or not isinstance(meta, dict):
        return cv_data, meta, 0

    def _is_empty(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str):
            return not v.strip()
        if isinstance(v, (list, tuple, dict)):
            return len(v) == 0
        return False

    # Only copy a conservative allowlist of fields we actually store in canonical CV schema.
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

    applied = 0
    new_cv = dict(cv_data)
    for k in allow_fields:
        if k not in docx_prefill:
            continue
        if k in new_cv and not _is_empty(new_cv.get(k)):
            continue
        v = docx_prefill.get(k)
        # Do not write obviously wrong types.
        if k in ("address_lines", "work_experience", "education", "further_experience", "languages", "it_ai_skills") and not isinstance(v, list):
            continue
        if k in ("full_name", "email", "phone", "profile", "interests", "references") and not isinstance(v, str):
            continue
        new_cv[k] = v
        applied += 1

    new_meta = dict(meta)
    # Once we copied prefill into canonical cv_data, the unconfirmed snapshot is no longer needed.
    if applied > 0:
        new_meta["docx_prefill_unconfirmed"] = None
    return new_cv, new_meta, applied


def _wants_generate_from_message(message: str) -> bool:
    """
    Heuristic intent detection (keep narrow; avoid false positives from pasted job ads).
    Only examines first 3 lines.
    """
    intent_header = "\n".join((message or "").splitlines()[:3]).lower()
    patterns = [
        r"\bgenerate\b",
        r"\bgo ahead\b",
        r"\bproceed\b",
        r"\bfinal\b",
        r"\bpdf\b",
        r"\bproduce (a )?(cv|resume|pdf)\b",
        r"\bcreate (a )?(cv|resume|pdf)\b",
        r"\bmake (a )?(cv|resume|pdf)\b",
        r"\bprovide me (a )?(cv|resume)\b",
    ]
    return any(re.search(p, intent_header) for p in patterns)


def _intent_scores(message: str) -> dict[str, int]:
    """
    Deterministic, weighted intent scoring.
    Keep it narrow and only inspect first 3 lines to avoid job-posting false positives.
    """
    header = "\n".join((message or "").splitlines()[:3]).lower()
    scores = {"generate": 0, "review": 0}

    # Generation signals (strong)
    if re.search(r"\b(pdf|final)\b", header):
        scores["generate"] += 3
    if re.search(r"\b(go ahead|proceed)\b", header):
        scores["generate"] += 2
    if re.search(r"\b(generate|create|produce|make)\b", header) and re.search(r"\b(pdf|cv|resume)\b", header):
        scores["generate"] += 3

    # Review / tailoring signals (weak-to-medium)
    if re.search(r"\b(tailor|adapt|prepare|update|improve|rewrite|review)\b", header):
        scores["review"] += 2
    if re.search(r"\b(job|offer|vacancy|position)\b", header):
        scores["review"] += 1

    return scores


def _select_stage(message: str) -> tuple[str, dict]:
    """
    Choose stage deterministically based on weighted intent.
    """
    scores = _intent_scores(message)
    gen = int(scores.get("generate", 0))
    rev = int(scores.get("review", 0))
    # Generate only on strong signals; otherwise stay in review.
    stage = "generate_pdf" if gen >= 3 and gen >= rev else "review_session"
    return stage, {"scores": scores, "selected": stage}


def _user_confirm_yes(message: str) -> bool:
    t = (message or "").strip().lower()
    # Accept both exact confirmations and common variants like "yes, ..." / "ok ...".
    if t in ("yes", "y", "ok", "okay", "tak", "jasne", "sure", "confirm", "confirmed"):
        return True
    return bool(re.match(r"^(yes|y|ok|okay|tak|jasne|sure|confirm|confirmed)\b", t))


def _user_confirm_no(message: str) -> bool:
    t = (message or "").strip().lower()
    if t in ("no", "n", "nie", "nope"):
        return True
    return bool(re.match(r"^(no|n|nie|nope)\b", t))


def _is_import_prefill_intent(message: str) -> bool:
    t = (message or "").lower()
    return any(x in t for x in ("import prefill", "use prefill", "copy prefill", "zaimportuj", "przenieś", "importuj", "użyj prefill"))


def _is_generate_pdf_intent(message: str) -> bool:
    t = (message or "").lower()
    return any(x in t for x in ("generate pdf", "generate the pdf", "final pdf", "create pdf", "pdf now", "generuj pdf", "wygeneruj pdf"))


def _get_pending_confirmation(meta: dict) -> dict | None:
    pc = meta.get("pending_confirmation") if isinstance(meta, dict) else None
    return pc if isinstance(pc, dict) else None


def _set_pending_confirmation(meta: dict, *, kind: str) -> dict:
    out = dict(meta or {})
    out["pending_confirmation"] = {"kind": kind, "created_at": _now_iso()}
    return out


def _clear_pending_confirmation(meta: dict) -> dict:
    out = dict(meta or {})
    out["pending_confirmation"] = None
    return out


def _get_turns_in_review(meta: dict) -> int:
    """Get the count of turns spent in REVIEW stage (used for auto-advance logic)."""
    try:
        return int(meta.get("turns_in_review", 0))
    except (ValueError, TypeError):
        return 0


def _increment_turns_in_review(meta: dict) -> dict:
    """Increment turn counter when staying in REVIEW stage."""
    out = dict(meta or {})
    current = _get_turns_in_review(out)
    out["turns_in_review"] = current + 1
    return out


def _reset_turns_in_review(meta: dict) -> dict:
    """Reset turn counter when leaving REVIEW stage."""
    out = dict(meta or {})
    out["turns_in_review"] = 0
    return out


def _estimate_pages_ok(cv_data: dict) -> bool:
    try:
        cv_norm = normalize_cv_data(cv_data or {})
        result = validate_cv(cv_norm)
        est = getattr(result, "estimated_pages", None)
        if isinstance(est, (int, float)):
            return est <= 2
    except Exception:
        pass
    return True


def _get_stage_from_metadata(meta: dict) -> CVStage:
    stage = None
    if isinstance(meta, dict):
        stage = meta.get("stage")
    try:
        return CVStage(str(stage or CVStage.INGEST.value))
    except Exception:
        return CVStage.INGEST


def _set_stage_in_metadata(meta: dict, stage: CVStage) -> dict:
    out = dict(meta or {})
    out["stage"] = stage.value
    out["stage_updated_at"] = _now_iso()
    return out


def _is_debug_export_enabled() -> bool:
    return str(os.environ.get("CV_ENABLE_DEBUG_EXPORT", "0")).strip() == "1"


def _redact_debug_value(value: Any) -> Any:
    """
    Ensure exported diagnostics do not contain large payloads or sensitive content.
    This is best-effort and should stay conservative.
    """
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        # Redact base64-like content and very large strings.
        if len(value) > 2000:
            return f"<str:{len(value)}>"
        if "base64" in value.lower() and len(value) > 256:
            return f"<base64_str:{len(value)}>"
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, list):
        # Keep only a small head; redact nested values.
        head = value[:10]
        return [_redact_debug_value(v) for v in head] + (["<…>"] if len(value) > 10 else [])
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            ks = str(k)
            # Common large fields
            if ks in ("docx_base64", "pdf_base64", "cv_data_json", "metadata_json"):
                out[ks] = "<redacted>"
                continue
            out[ks] = _redact_debug_value(v)
        return out
    return f"<{type(value).__name__}>"


def _shrink_metadata_for_table(metadata: dict) -> dict:
    """
    Azure Table Storage property size limit is 64KB. Keep metadata_json well below that.
    We only trim fields that are non-critical for correctness (event_log verbosity).
    """
    if not isinstance(metadata, dict):
        return {}

    meta = dict(metadata)

    # Job posting text can easily exceed Azure Table Storage limits when combined with event logs.
    # Keep a snippet for debugging, but avoid persistence failures.
    jpt = meta.get("job_posting_text")
    if isinstance(jpt, str) and len(jpt) > 2000:
        meta["job_posting_text"] = jpt[:2000]

    # DOCX prefill snapshot can also be large; keep it bounded.
    dpu = meta.get("docx_prefill_unconfirmed")
    if isinstance(dpu, dict):
        dpu2 = dict(dpu)
        for k, v in list(dpu2.items()):
            if isinstance(v, str) and len(v) > 2000:
                dpu2[k] = v[:2000]
            if isinstance(v, list) and len(v) > 50:
                dpu2[k] = v[:50]
        meta["docx_prefill_unconfirmed"] = dpu2

    event_log = meta.get("event_log")
    if isinstance(event_log, list):
        trimmed: list[dict] = []
        for e in event_log[-10:]:
            if not isinstance(e, dict):
                continue
            e2 = dict(e)
            # Bound long texts
            if isinstance(e2.get("text"), str) and len(e2["text"]) > 800:
                e2["text"] = e2["text"][:800]
            if isinstance(e2.get("assistant_text"), str) and len(e2["assistant_text"]) > 800:
                e2["assistant_text"] = e2["assistant_text"][:800]
            trimmed.append(e2)
        meta["event_log"] = trimmed
    return meta


_FILENAME_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename_part(value: str, *, max_len: int = 48) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    v = v.translate(
        str.maketrans(
            {
                # Polish
                "ą": "a",
                "ć": "c",
                "ę": "e",
                "ł": "l",
                "ń": "n",
                "ó": "o",
                "ś": "s",
                "ż": "z",
                "ź": "z",
                "Ą": "A",
                "Ć": "C",
                "Ę": "E",
                "Ł": "L",
                "Ń": "N",
                "Ó": "O",
                "Ś": "S",
                "Ż": "Z",
                "Ź": "Z",
                # German
                "ä": "a",
                "ö": "o",
                "ü": "u",
                "ß": "ss",
                "Ä": "A",
                "Ö": "O",
                "Ü": "U",
            }
        )
    )
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode("ascii")
    v = _FILENAME_FORBIDDEN_RE.sub(" ", v)
    v = re.sub(r"\\s+", " ", v).strip().replace(" ", "_")
    v = re.sub(r"_+", "_", v).strip("._-")
    if len(v) > max_len:
        v = v[:max_len].rstrip("._-")
    return v


def _extract_job_title_from_metadata(meta: dict) -> str:
    if not isinstance(meta, dict):
        return ""
    for k in ("job_title", "target_job_title", "role_title", "position_title"):
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    jpt = meta.get("job_posting_text")
    if isinstance(jpt, str) and jpt.strip():
        for line in jpt.splitlines():
            line = line.strip()
            if not line:
                continue
            for sep in (" | ", " — ", " – ", " - ", " @ ", " at "):
                if sep in line:
                    line = line.split(sep, 1)[0].strip()
                    break
            return line
    return ""


def _compute_pdf_download_name(*, cv_data: dict, meta: dict) -> str:
    full_name = ""
    if isinstance(cv_data, dict):
        v = cv_data.get("full_name")
        if isinstance(v, str):
            full_name = v.strip()
    job_title = _extract_job_title_from_metadata(meta)

    name_part = _sanitize_filename_part(full_name, max_len=40) or "Candidate"
    job_part = _sanitize_filename_part(job_title, max_len=40)
    if job_part:
        return f"CV_{name_part}_{job_part}.pdf"
    return f"CV_{name_part}.pdf"


def _build_session_debug_snapshot(session: dict) -> dict:
    cv_data = session.get("cv_data") or {}
    meta = session.get("metadata") or {}
    readiness = _compute_readiness(cv_data if isinstance(cv_data, dict) else {}, meta if isinstance(meta, dict) else {})
    confirmed_flags = (meta.get("confirmed_flags") or {}) if isinstance(meta, dict) else {}
    docx_prefill = meta.get("docx_prefill_unconfirmed") if isinstance(meta, dict) else None

    def _count_list(obj: Any) -> int:
        return len(obj) if isinstance(obj, list) else 0

    pdf_refs = meta.get("pdf_refs") if isinstance(meta, dict) else None
    pdf_ref_count = len(pdf_refs) if isinstance(pdf_refs, dict) else 0
    pdf_ref_keys = list(pdf_refs.keys())[:10] if isinstance(pdf_refs, dict) else []

    events = meta.get("event_log") if isinstance(meta, dict) else None
    event_tail: list[dict] = []
    if isinstance(events, list):
        for e in events[-20:]:
            if not isinstance(e, dict):
                continue
            rs = e.get("run_summary") if isinstance(e.get("run_summary"), dict) else {}
            steps = rs.get("steps") if isinstance(rs.get("steps"), list) else []
            tool_steps = [s for s in steps if isinstance(s, dict) and s.get("step") == "tool"]
            event_tail.append(
                {
                    "ts": e.get("ts"),
                    "type": e.get("type"),
                    "stage": e.get("stage"),
                    "trace_id": e.get("trace_id"),
                    "text_preview": (str(e.get("text") or "")[:180] if e.get("type") in ("user_message", "assistant_message") else None),
                    "run": {
                        "model_calls": rs.get("model_calls"),
                        "tool_steps": len(tool_steps),
                        "tools": [str(s.get("tool")) for s in tool_steps][:10],
                    },
                }
            )

    snapshot = {
        "readiness": readiness,
        "cv_counts": {
            "work_experience": _count_list(cv_data.get("work_experience") if isinstance(cv_data, dict) else None),
            "education": _count_list(cv_data.get("education") if isinstance(cv_data, dict) else None),
            "languages": _count_list(cv_data.get("languages") if isinstance(cv_data, dict) else None),
            "it_ai_skills": _count_list(cv_data.get("it_ai_skills") if isinstance(cv_data, dict) else None),
        },
        "confirmed_flags": confirmed_flags,
        "docx_prefill_unconfirmed_present": isinstance(docx_prefill, dict),
        "docx_prefill_counts": {
            "work_experience": _count_list(docx_prefill.get("work_experience") if isinstance(docx_prefill, dict) else None),
            "education": _count_list(docx_prefill.get("education") if isinstance(docx_prefill, dict) else None),
            "languages": _count_list(docx_prefill.get("languages") if isinstance(docx_prefill, dict) else None),
            "it_ai_skills": _count_list(docx_prefill.get("it_ai_skills") if isinstance(docx_prefill, dict) else None),
        },
        "pdf_refs": {
            "count": pdf_ref_count,
            "keys_head": pdf_ref_keys,
        },
        "event_tail": event_tail,
    }
    return _redact_debug_value(snapshot)


def _export_session_debug_files(*, session_id: str, session: dict, include_logs: bool, minutes: int) -> dict:
    out_dir = Path("tmp") / "exports" / f"session_debug_{session_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _build_session_debug_snapshot(session)
    (out_dir / "session_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    exported: dict[str, Any] = {"out_dir": str(out_dir), "files": ["session_snapshot.json"]}
    if not include_logs:
        return exported

    cutoff = datetime.utcnow().timestamp() - max(1, int(minutes)) * 60
    sid = session_id

    def _filter_log(path: Path) -> int:
        if not path.exists():
            return 0
        kept: list[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if sid not in line:
                continue
            # Try to filter by timestamp prefix [YYYY-MM-DDTHH:MM:SS...]
            m = re.search(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
            if m:
                try:
                    ts = datetime.fromisoformat(m.group(1)).timestamp()
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            kept.append(line)
        if not kept:
            return 0
        outp = out_dir / f"{path.name}.sid.log"
        outp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        exported["files"].append(outp.name)
        return len(kept)

    # Only consider the latest func + azurite logs (fast, local dev).
    logs_dir = Path("tmp") / "logs"
    func_latest = None
    az_latest = None
    if logs_dir.exists():
        func_logs = sorted(logs_dir.glob("func_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        az_logs = sorted(logs_dir.glob("azurite_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        func_latest = func_logs[0] if func_logs else None
        az_latest = az_logs[0] if az_logs else None

    exported["log_matches"] = {}
    if func_latest:
        exported["log_matches"]["func"] = {"file": str(func_latest), "lines": _filter_log(func_latest)}
    if az_latest:
        exported["log_matches"]["azurite"] = {"file": str(az_latest), "lines": _filter_log(az_latest)}
    return exported


def _responses_max_output_tokens(stage: str) -> int:
    # Increased limits to give model space to complete thoughts and avoid premature truncation.
    # Target: finish in 1-2 turns instead of 3-4.
    if stage == "draft_proposal":
        return 1800
    if stage == "fix_validation":
        return 1400
    if stage == "generate_pdf":
        return 1500  # was 1200: space for confirmation message
    if stage == "review_session":
        return 2500  # was 1800: space for concrete proposals without cutting off
    if stage == "apply_edits":
        return 2000  # was 1200 (inherited from default): space for batch edits + status
    return 1200


def _context_pack_mode() -> str:
    mode = str(os.environ.get("CV_CONTEXT_PACK_MODE", "")).strip().lower()
    if mode in ("mini", "full"):
        return mode
    return "mini"


def _stage_prompt(stage: str) -> str:
    # Ultra-compact stage hint to anchor the model without bloating tokens.
    # Key change: CONFIRM stage (apply_edits) now auto-enabled after 3 turns → assistant applies edits without approval.
    if stage == "review_session":
        return "Stage=review_session. Goal: review session data, propose concise edits, no PDF. Keep answers short. [Note: sections marked 'unchanged' contain only summary; 'changed' sections have full data]. [After 3 turns, system auto-enables editing without explicit approval]"
    if stage == "apply_edits":
        return "Stage=apply_edits. FIRST ACTION: call update_cv_field(edits=[...]) with ALL proposed changes in ONE batch. Then respond with 1-line confirmation. NO questions, NO waiting for approval. System auto-advanced to this stage; commit your best proposals immediately. [Note: sections marked 'unchanged' contain only summary; 'changed' sections have full data]"
    if stage == "generate_pdf":
        return "Stage=generate_pdf. Goal: user approved; generate once if readiness allows. Keep answers short."
    if stage == "fix_validation":
        return "Stage=fix_validation. Goal: fix validation errors in one pass, then generate once. Keep answers short."
    return "Stage=bootstrap. Goal: gather missing inputs; keep answers short."


def _looks_truncated(text: str) -> bool:
    t = (text or "").rstrip()
    if not t:
        return False
    return not any(t.endswith(x) for x in (".", "!", "?", "…"))


def _should_log_prompt_debug() -> bool:
    return str(os.environ.get("CV_DEBUG_PROMPT_LOG", "")).strip() == "1"


def _describe_responses_input(items: list[Any]) -> list[dict]:
    described: list[dict] = []
    for it in items:
        if isinstance(it, dict) and "role" in it:
            role = str(it.get("role") or "")
            content = it.get("content")
            if isinstance(content, str):
                described.append({"kind": "message", "role": role, "content_len": len(content)})
            else:
                described.append({"kind": "message", "role": role, "content_type": type(content).__name__})
            continue

        t = getattr(it, "type", None)
        described.append({"kind": "output_item", "type": str(t or type(it).__name__)})
    return described


def _tool_schemas_for_responses(*, allow_persist: bool, stage: str = "review_session") -> list[dict]:
    # Provide explicit tool schemas (even with dashboard prompt) to ensure tool calling works.
    tools: list[dict] = [
        {"type": "web_search"},
        {
            "type": "function",
            "name": "get_cv_session",
            "strict": False,
            "description": "Retrieves CV data from an existing session for preview or confirmation.",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        },
    ]

    if allow_persist:
        tools.append(
            {
                "type": "function",
                "name": "update_cv_field",
                "strict": False,
                "description": "Updates CV session fields (single update, batch edits[], one-section cv_patch, and/or confirmation flags).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "field_path": {"type": "string"},
                        "value": {},
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"field_path": {"type": "string"}, "value": {}},
                                "required": ["field_path", "value"],
                                "additionalProperties": False,
                            },
                        },
                        "cv_patch": {"type": "object", "additionalProperties": True},
                        "confirm": {
                            "type": "object",
                            "properties": {
                                "contact_confirmed": {"type": "boolean"},
                                "education_confirmed": {"type": "boolean"},
                            },
                            "additionalProperties": False,
                        },
                        "client_context": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            }
        )

    tools.extend(
        [
            {
                "type": "function",
                "name": "validate_cv",
                "strict": False,
                "description": "Runs deterministic schema + DoD validation checks for the current session (no PDF render).",
                "parameters": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "cv_session_search",
                "strict": False,
                "description": "Search session data (cv_data + docx_prefill_unconfirmed + recent events) and return bounded previews.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "q": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "generate_context_pack_v2",
                "strict": False,
                "description": "Build ContextPackV2 for the given session and phase.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "phase": {"type": "string", "enum": ["preparation", "confirmation", "execution"]},
                        "job_posting_text": {"type": "string"},
                        "max_pack_chars": {"type": "integer"},
                    },
                    "required": ["session_id", "phase"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "preview_html",
                "strict": False,
                "description": "Render debug HTML from current session.",
                "parameters": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}, "inline_css": {"type": "boolean"}},
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            },
        ]
    )

    # Only allow PDF generation/fetch tools in execution-capable stages.
    if stage in ("generate_pdf", "fix_validation"):
        tools.append(
            {
                "type": "function",
                "name": "generate_cv_from_session",
                "strict": False,
                "description": "Generate and persist PDF for the current session (execution stage only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "language": {"type": "string"},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            }
        )
        tools.append(
            {
                "type": "function",
                "name": "get_pdf_by_ref",
                "strict": False,
                "description": "Fetch previously generated PDF by reference (execution stage only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "pdf_ref": {"type": "string"},
                    },
                    "required": ["session_id", "pdf_ref"],
                    "additionalProperties": False,
                },
            }
        )
    return tools


def _sanitize_tool_output_for_model(tool_name: str, payload: Any) -> str:
    try:
        if tool_name == "generate_cv_from_session":
            if isinstance(payload, dict):
                return json.dumps(
                    {
                        "ok": payload.get("success") is True and bool(payload.get("pdf_ref")),
                        "success": payload.get("success"),
                        "error": payload.get("error"),
                        "pdf_ref": payload.get("pdf_ref"),
                        "pdf_sha256": payload.get("pdf_sha256"),
                        "pdf_size_bytes": payload.get("pdf_size_bytes"),
                        "render_ms": payload.get("render_ms"),
                        "validation_passed": payload.get("validation_passed"),
                        "pdf_pages": payload.get("pdf_pages"),
                    },
                    ensure_ascii=False,
                )
        if tool_name == "get_pdf_by_ref":
            if isinstance(payload, dict):
                return json.dumps(
                    {
                        "ok": payload.get("success") is True and bool(payload.get("pdf_ref")),
                        "success": payload.get("success"),
                        "error": payload.get("error"),
                        "pdf_ref": payload.get("pdf_ref"),
                        "pdf_size_bytes": payload.get("pdf_size_bytes"),
                    },
                    ensure_ascii=False,
                )
        if isinstance(payload, dict):
            out = dict(payload)
            for k in ("pdf_base64", "docx_base64", "photo_data_uri"):
                out.pop(k, None)
            return json.dumps(out, ensure_ascii=False)
        return json.dumps({"ok": True, "value": str(payload)[:2000]}, ensure_ascii=False)
    except Exception:
        return json.dumps({"ok": False, "error": "sanitize_failed"}, ensure_ascii=False)


def _run_responses_tool_loop(
    *,
    user_message: str,
    session_id: str,
    stage: str,
    job_posting_text: str | None,
    trace_id: str,
    max_turns: int,
) -> tuple[str, list[dict], dict, str | None, bytes | None]:
    """
    Backend-owned, stateless Responses tool-loop.
    Returns: (assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes)
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt_id = _get_openai_prompt_id()
    model_override = (os.environ.get("OPENAI_MODEL") or "").strip() or None
    # Tool-loop requires persisted response items for follow-up calls; default ON.
    store_flag = str(os.environ.get("OPENAI_STORE", "1")).strip() == "1"

    run_summary: dict = {"trace_id": trace_id, "timestamps": {}, "steps": [], "max_turns": max_turns, "model_calls": 0}
    turn_trace: list[dict] = []
    pdf_bytes: bytes | None = None
    last_response_id: str | None = None
    schema_repair_attempted = False

    def _openai_trace_enabled() -> bool:
        return str(os.environ.get("CV_OPENAI_TRACE", "0")).strip() == "1"

    def _openai_trace_dir() -> str:
        return str(os.environ.get("CV_OPENAI_TRACE_DIR") or "tmp/openai_trace").strip()

    def _sha256_text(s: str) -> str:
        try:
            return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()
        except Exception:
            return ""

    def _summarize_req_for_trace(req_obj: dict) -> dict:
        try:
            input_items = req_obj.get("input") or []
            summarized_inputs: list[dict] = []
            for item in input_items:
                if not isinstance(item, dict):
                    summarized_inputs.append({"item_type": type(item).__name__})
                    continue
                role = item.get("role")
                content = item.get("content", "")
                if isinstance(content, str):
                    summarized_inputs.append(
                        {
                            "role": role,
                            "content_len": len(content),
                            "content_sha256": _sha256_text(content),
                        }
                    )
                else:
                    summarized_inputs.append({"role": role, "content_type": type(content).__name__})

            tools = req_obj.get("tools") or []
            tool_names: list[str] = []
            for t in tools:
                if isinstance(t, dict) and t.get("name"):
                    tool_names.append(str(t.get("name")))

            prompt_obj = req_obj.get("prompt")
            prompt_id_local = prompt_obj.get("id") if isinstance(prompt_obj, dict) else None
            return {
                "has_prompt": bool(prompt_obj),
                "prompt_id": prompt_id_local,
                "has_instructions": bool(req_obj.get("instructions")),
                "model": req_obj.get("model"),
                "store": req_obj.get("store"),
                "max_output_tokens": req_obj.get("max_output_tokens"),
                "truncation": req_obj.get("truncation"),
                "tools_count": len(tools),
                "tool_names": tool_names[:40],
                "input_items": summarized_inputs,
            }
        except Exception:
            return {"error": "summarize_failed"}

    def _append_openai_trace_record(record: dict) -> None:
        if not _openai_trace_enabled():
            return
        try:
            trace_dir = _openai_trace_dir()
            os.makedirs(trace_dir, exist_ok=True)
            index_path = os.path.join(trace_dir, "openai_trace.jsonl")
            with open(index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _responses_create_with_trace(*, req_obj: dict, call_seq: int) -> Any:
        started_at = time.time()
        resp_obj = client.responses.create(**req_obj)

        response_id = getattr(resp_obj, "id", None)
        out_text_local = getattr(resp_obj, "output_text", "") or ""
        output_items = getattr(resp_obj, "output", None) or []
        tool_calls_local = [item for item in output_items if getattr(item, "type", None) == "function_call"]

        _append_openai_trace_record(
            {
                "ts_utc": _now_iso(),
                "trace_id": trace_id,
                "session_id": session_id,
                "stage": stage,
                "phase": phase,
                "call_seq": call_seq,
                "duration_ms": int((time.time() - started_at) * 1000),
                "request": _summarize_req_for_trace(req_obj),
                "response": {
                    "id": response_id,
                    "output_text_len": len(out_text_local),
                    "tool_calls_count": len(tool_calls_local),
                },
            }
        )
        if _openai_trace_enabled() and response_id:
            logging.info(
                "openai_response_id=%s trace_id=%s stage=%s call_seq=%s",
                str(response_id),
                trace_id,
                stage,
                str(call_seq),
            )
        return resp_obj

    store = _get_session_store()
    session = store.get_session(session_id)
    if not session:
        logging.warning(
            "Session missing before OpenAI call trace_id=%s session_id=%s",
            trace_id,
            session_id,
        )
        return (
            "Your session is no longer available. Please re-upload your CV DOCX to start a new session.",
            [],
            run_summary,
            None,
            None,
        )

    # Build capsule once per turn (phase depends on stage).
    phase = "execution" if stage == "generate_pdf" else "preparation"
    if _require_openai_prompt_id() and not prompt_id:
        return (
            "Backend configuration error: OPENAI_PROMPT_ID is required but not set. "
            "Set OPENAI_PROMPT_ID in local.settings.json (Values) or your environment.",
            [],
            run_summary,
            None,
            None,
        )
    call_seq = 0

    for turn_idx in range(1, max_turns + 1):
        run_summary["timestamps"][f"turn_{turn_idx}_start"] = time.time()
        # Refresh session for each turn (tools mutate it).
        session = store.get_session(session_id) or {}
        cv_data = session.get("cv_data") or {}
        readiness = _compute_readiness(cv_data, session.get("metadata") or {})

        # Build context pack text for the model.
        pack_mode = _context_pack_mode()
        pack = build_context_pack_v2(
            phase=phase,
            cv_data=cv_data,
            job_posting_text=job_posting_text,
            session_metadata=(session.get("metadata") or {}) if isinstance(session.get("metadata"), dict) else {},
            pack_mode=pack_mode,
            max_pack_chars=6000 if pack_mode == "mini" else 12000,
        )
        capsule_text = format_context_pack_with_delimiters(pack)

        # Compose user content (bounded, explicit markers).
        user_content = (
            f"{user_message}\n\n"
            f"[SESSION_ID]\n{session_id}\n\n"
            f"[CONTEXT_PACK_V2]\n{capsule_text}\n"
            f"\n[STAGE]\n{stage}\n"
            f"[PHASE]\n{phase}\n"
        )
        input_list = [
            {"role": "developer", "content": _stage_prompt(stage)},
            {"role": "user", "content": user_content},
        ]

        allow_persist = stage in ("apply_edits", "fix_validation")
        req: dict = {
            "input": input_list,
            # In PREPARE/REVIEW/CONFIRM we do not allow persistence via model tools (backend-owned state).
            "tools": _tool_schemas_for_responses(allow_persist=allow_persist, stage=stage),
            "store": store_flag,
            "truncation": "disabled",
            "max_output_tokens": _responses_max_output_tokens(stage),
            "metadata": {
                "app": "cv-generator-backend",
                "workflow": "backend_orchestrator_v1",
                "trace_id": trace_id,
                "stage": stage,
                "turn": str(turn_idx),
            },
        }
        try:
            tool_names_logged = [t.get("name") for t in (req.get("tools") or []) if isinstance(t, dict) and t.get("name")]
            logging.info(
                "trace_id=%s stage=%s turn=%s allow_persist=%s tools=%s pack_mode=%s pack_chars=%s max_tokens=%s store=%s",
                trace_id,
                stage,
                turn_idx,
                allow_persist,
                tool_names_logged,
                pack_mode,
                len(capsule_text),
                req.get("max_output_tokens"),
                str(store_flag),
            )
        except Exception:
            pass
        if prompt_id:
            req["prompt"] = {"id": prompt_id, "variables": {"stage": stage, "phase": phase}}
        else:
            req["instructions"] = "You are a CV assistant operating in a stateless API. Use tools to persist edits."
            # Only set model in legacy mode (no dashboard prompt).
            if model_override:
                req["model"] = model_override

        # Model call
        if _should_log_prompt_debug():
            try:
                logging.info(
                    "responses.create request trace_id=%s stage=%s phase=%s prompt_id=%s model=%s store=%s input=%s",
                    trace_id,
                    stage,
                    phase,
                    prompt_id or "",
                    req.get("model") or "",
                    str(req.get("store")),
                    json.dumps(_describe_responses_input(req.get("input") or []), ensure_ascii=False),
                )
            except Exception:
                pass
        call_seq += 1
        resp = _responses_create_with_trace(req_obj=req, call_seq=call_seq)
        last_response_id = getattr(resp, "id", None) or last_response_id
        if _should_log_prompt_debug():
            try:
                logging.info("responses.create response trace_id=%s stage=%s response_id=%s", trace_id, stage, last_response_id or "")
            except Exception:
                pass
        
        # Parse structured output and format for UI
        out_text = getattr(resp, "output_text", "") or ""
        try:
            # If output_text contains structured JSON, parse and format it
            if out_text.strip().startswith("{"):
                parsed_resp = parse_structured_response(out_text)
                if parsed_resp:
                    formatted = format_user_message_for_ui(parsed_resp)
                    out_text = formatted.get("text", out_text) or out_text
                    # Store parsed response for context
                    if formatted.get("sections"):
                        context.append({"role": "user", "content": json.dumps(formatted.get("sections", {}))})
        except Exception as e:
            logging.debug(f"Failed to parse structured output: {e}; using raw text")
            pass

        # Collect tool calls
        tool_calls = [item for item in (getattr(resp, "output", None) or []) if getattr(item, "type", None) == "function_call"]
        tool_names: list[str] = []
        if tool_calls:
            try:
                logging.info(
                    "trace_id=%s stage=%s turn=%s call_seq=%s tool_calls=%s",
                    trace_id,
                    stage,
                    turn_idx,
                    call_seq,
                    [getattr(call, "name", None) or getattr(getattr(call, "function", None), "name", None) for call in tool_calls],
                )
            except Exception:
                pass
        for call in tool_calls:
            name = getattr(call, "name", None) or getattr(getattr(call, "function", None), "name", None)
            args_raw = getattr(call, "arguments", None) or getattr(getattr(call, "function", None), "arguments", None) or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw or {})
            except Exception:
                args = {}
            tool_names.append(str(name))

            tool_start = time.time()
            tool_payload: Any = {}
            tool_output_for_model = "{}"
            try:
                if name in ("generate_cv_from_session", "get_pdf_by_ref") and stage not in ("generate_pdf", "fix_validation"):
                    tool_payload = {"error": "pdf_tool_not_allowed_in_stage", "stage": stage}
                elif name == "get_cv_session":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {
                            "success": True,
                            "session_id": sid,
                            "readiness": _compute_readiness(cv, s.get("metadata") or {}),
                            "cv_data": cv,
                            "metadata": s.get("metadata"),
                        }
                elif name == "update_cv_field":
                    sid = args.get("session_id") or session_id
                    # Reuse the same update logic as dispatcher by calling CVSessionStore.update_field and metadata confirm update.
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        # Confirmation flags
                        confirm_flags = args.get("confirm")
                        if isinstance(confirm_flags, dict) and confirm_flags:
                            meta = s.get("metadata") or {}
                            if isinstance(meta, dict):
                                meta = dict(meta)
                                cf = meta.get("confirmed_flags") or {}
                                if not isinstance(cf, dict):
                                    cf = {}
                                cf = dict(cf)
                                for k in ("contact_confirmed", "education_confirmed"):
                                    if k in confirm_flags:
                                        cf[k] = bool(confirm_flags.get(k))
                                if cf.get("contact_confirmed") and cf.get("education_confirmed") and not cf.get("confirmed_at"):
                                    cf["confirmed_at"] = _now_iso()
                                meta["confirmed_flags"] = cf
                                store.update_session(str(sid), (s.get("cv_data") or {}), meta)
                        client_context = args.get("client_context")
                        edits = args.get("edits")
                        field_path = args.get("field_path")
                        value = args.get("value")
                        cv_patch = args.get("cv_patch")
                        applied = 0
                        if isinstance(edits, list):
                            for e in edits:
                                fp = e.get("field_path")
                                if not fp:
                                    continue
                                store.update_field(str(sid), fp, e.get("value"), client_context=client_context if isinstance(client_context, dict) else None)
                                applied += 1
                        if field_path:
                            store.update_field(str(sid), str(field_path), value, client_context=client_context if isinstance(client_context, dict) else None)
                            applied += 1
                        if isinstance(cv_patch, dict):
                            for k, v in cv_patch.items():
                                store.update_field(str(sid), str(k), v, client_context=client_context if isinstance(client_context, dict) else None)
                                applied += 1
                        tool_payload = {"success": True, "session_id": sid, "edits_applied": applied}
                elif name == "validate_cv":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {
                            "success": True,
                            "session_id": sid,
                            **_validate_cv_data_for_tool(cv),
                            "readiness": _compute_readiness(cv, s.get("metadata") or {}),
                        }
                elif name == "cv_session_search":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        q = str(args.get("q") or "")
                        limit = int(args.get("limit") or 20)
                        result = _cv_session_search_hits(session=s, q=q, limit=limit)
                        tool_payload = {"success": True, "session_id": sid, "hits": result["hits"], "truncated": result["truncated"]}
                elif name == "generate_context_pack_v2":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, pack2 = _tool_generate_context_pack_v2(
                            session_id=str(sid),
                            phase=str(args.get("phase") or "preparation"),
                            job_posting_text=str(args.get("job_posting_text") or "") or None,
                            max_pack_chars=int(args.get("max_pack_chars") or 12000),
                            session=s,
                        )
                        tool_payload = pack2 if status == 200 else {"error": pack2.get("error") if isinstance(pack2, dict) else "pack_failed"}
                elif name == "preview_html":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {"success": True, "session_id": sid, **_render_html_for_tool(cv, inline_css=bool(args.get("inline_css", True)))}
                elif name == "generate_cv_from_session":
                    sid = args.get("session_id") or session_id
                    logging.info(f"=== TOOL: generate_cv_from_session (v1) === session_id={sid} trace_id={trace_id}")
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                        logging.warning(f"=== TOOL: generate_cv_from_session (v1) FAILED === session not found")
                    else:
                        status, payload, content_type = _tool_generate_cv_from_session(
                            session_id=str(sid),
                            language=str(args.get("language") or "").strip() or None,
                            client_context=None,
                            session=s,
                        )
                        if (
                            content_type == "application/pdf"
                            and isinstance(payload, dict)
                            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
                            and status == 200
                        ):
                            pdf_bytes = bytes(payload["pdf_bytes"])
                            pdf_meta = payload.get("pdf_metadata") or {}
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_meta.get("pdf_ref"),
                                "pdf_sha256": pdf_meta.get("sha256"),
                                "pdf_size_bytes": pdf_meta.get("pdf_size_bytes"),
                                "render_ms": pdf_meta.get("render_ms"),
                                "validation_passed": pdf_meta.get("validation_passed"),
                                "pdf_pages": pdf_meta.get("pages"),
                            }
                            logging.info(
                                "=== TOOL: generate_cv_from_session (v1) SUCCESS === pdf_size=%d bytes pdf_ref=%s",
                                len(pdf_bytes),
                                pdf_meta.get("pdf_ref"),
                            )
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "generate_failed"}
                            logging.warning(f"=== TOOL: generate_cv_from_session (v1) FAILED === status={status} payload={tool_payload}")
                elif name == "get_pdf_by_ref":
                    sid = args.get("session_id") or session_id
                    pdf_ref = str(args.get("pdf_ref") or "").strip()
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, payload, content_type = _tool_get_pdf_by_ref(
                            session_id=str(sid),
                            pdf_ref=pdf_ref,
                            session=s,
                        )
                        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)) and status == 200:
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_ref,
                                "pdf_size_bytes": len(payload),
                            }
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "pdf_fetch_failed"}
                else:
                    tool_payload = {"error": f"Unknown tool: {name}"}

                tool_output_for_model = _sanitize_tool_output_for_model(str(name), tool_payload)
            except Exception as e:
                tool_payload = {"error": f"tool_exec_failed: {e}"}
                tool_output_for_model = _sanitize_tool_output_for_model(str(name), tool_payload)
            tool_end = time.time()
            run_summary["steps"].append(
                {
                    "step": "tool",
                    "tool": str(name),
                    "duration_ms": int((tool_end - tool_start) * 1000),
                    "ok": isinstance(tool_payload, dict) and not tool_payload.get("error"),
                }
            )

            # Feed tool output back to the model in a follow-up call (stateless continuation).
            # We append the function result as an assistant tool message.
            try:
                call_seq += 1
                resp = _responses_create_with_trace(
                    req_obj={
                        **req,
                        "input": input_list
                        + [
                            {"type": "function_call_output", "call_id": getattr(call, "call_id", None) or getattr(call, "id", ""), "output": tool_output_for_model}
                        ],
                        "tools": _tool_schemas_for_responses(allow_persist=False, stage=stage),
                    },
                    call_seq=call_seq,
                )
                last_response_id = getattr(resp, "id", None) or last_response_id
                out_text = getattr(resp, "output_text", "") or out_text
            except Exception:
                # If follow-up fails, continue; we still return what we have.
                pass

        turn_trace.append(
            {
                "turn": turn_idx,
                "stage": stage,
                "phase": phase,
                "tools_called": tool_names,
                "tool_calls_count": len(tool_names),
                "readiness": readiness,
                "assistant_text_chars": len(out_text),
            }
        )
        run_summary["timestamps"][f"turn_{turn_idx}_end"] = time.time()

        # Stop criteria: no tool calls and we have a non-empty assistant response.
        if not tool_calls and out_text.strip():
            # If output looks truncated near cap, do one continuation (no tools).
            if _looks_truncated(out_text):
                try:
                    call_seq += 1
                    cont = _responses_create_with_trace(
                        req_obj={
                            **req,
                            "input": input_list + [{"role": "user", "content": "Continue from where you stopped. Do not repeat."}],
                            "tools": [],
                            "max_output_tokens": min(1024, _responses_max_output_tokens(stage)),
                        },
                        call_seq=call_seq,
                    )
                    cont_text = getattr(cont, "output_text", "") or ""
                    if cont_text:
                        out_text = f"{out_text.rstrip()}\n\n{cont_text.lstrip()}"
                        last_response_id = getattr(cont, "id", None) or last_response_id
                except Exception:
                    pass
            return out_text, turn_trace, run_summary, last_response_id, pdf_bytes

        # If PDF was generated, stop.
        if pdf_bytes:
            return out_text or "PDF generated.", turn_trace, run_summary, last_response_id, pdf_bytes

    # Max turns reached; return last output.
    return out_text or "I need one more message to continue.", turn_trace, run_summary, last_response_id, pdf_bytes


def _run_responses_tool_loop_v2(
    *,
    user_message: str,
    session_id: str,
    stage: str,
    job_posting_text: str | None,
    trace_id: str,
    max_model_calls: int,
    execution_mode: bool = False,
) -> tuple[str, list[dict], dict, str | None, bytes | None]:
    """
    Backend-owned, stateless Responses tool-loop.

    Design goals:
    - One backend HTTP request can include multiple model calls + tool calls (hard cap <= 5 model calls).
    - Session persistence is deterministic via tools; the model never "assumes" updates without calling tools.

    Wave 0.3: execution_mode=True enforces single-call execution contract for generate_pdf stage.

    Returns: (assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes)
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt_id = _get_openai_prompt_id()
    model_override = (os.environ.get("OPENAI_MODEL") or "").strip() or None
    # Tool-loop requires persisted response items for follow-up calls; default ON.
    store_flag = str(os.environ.get("OPENAI_STORE", "1")).strip() == "1"
    # Structured outputs: when enabled, model returns JSON with tool calls embedded (experimental)
    use_structured_output = str(os.environ.get("USE_STRUCTURED_OUTPUT", "0")).strip() == "1"

    # Wave 0.3: Single-call execution contract
    # Override max_model_calls in execution mode to enforce exactly 1 OpenAI call
    if execution_mode and os.environ.get("CV_SINGLE_CALL_EXECUTION", "1").strip() == "1":
        max_model_calls = 1
        logging.info(f"Execution mode: limiting to 1 OpenAI call (trace_id={trace_id})")

    run_summary: dict = {"trace_id": trace_id, "steps": [], "max_model_calls": max_model_calls, "model_calls": 0, "execution_mode": execution_mode}
    turn_trace: list[dict] = []
    pdf_bytes: bytes | None = None
    last_response_id: str | None = None

    store = _get_session_store()
    session = store.get_session(session_id)
    if not session:
        logging.warning(
            "Session missing before OpenAI call trace_id=%s session_id=%s",
            trace_id,
            session_id,
        )
        return (
            "Your session is no longer available. Please re-upload your CV DOCX to start a new session.",
            [],
            run_summary,
            None,
            None,
        )

    phase = "execution" if stage == "generate_pdf" else "preparation"
    if _require_openai_prompt_id() and not prompt_id:
        return (
            "Backend configuration error: OPENAI_PROMPT_ID is required but not set. "
            "Set OPENAI_PROMPT_ID in local.settings.json (Values) or your environment.",
            [],
            run_summary,
            None,
            None,
        )

    def _openai_trace_enabled() -> bool:
        return str(os.environ.get("CV_OPENAI_TRACE", "0")).strip() == "1"

    def _openai_trace_dir() -> str:
        return str(os.environ.get("CV_OPENAI_TRACE_DIR") or "tmp/openai_trace").strip()

    def _sha256_text(s: str) -> str:
        try:
            return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()
        except Exception:
            return ""

    def _summarize_req_for_trace(req_obj: dict) -> dict:
        try:
            input_items = req_obj.get("input") or []
            summarized_inputs: list[dict] = []
            for item in input_items:
                if not isinstance(item, dict):
                    summarized_inputs.append({"item_type": type(item).__name__})
                    continue
                role = item.get("role") or item.get("type")
                content = item.get("content", "")
                if isinstance(content, str):
                    summarized_inputs.append(
                        {
                            "role": role,
                            "content_len": len(content),
                            "content_sha256": _sha256_text(content),
                        }
                    )
                else:
                    summarized_inputs.append({"role": role, "content_type": type(content).__name__})

            tools = req_obj.get("tools") or []
            tool_names: list[str] = []
            for t in tools:
                if isinstance(t, dict) and t.get("name"):
                    tool_names.append(str(t.get("name")))

            prompt_obj = req_obj.get("prompt")
            prompt_id_local = prompt_obj.get("id") if isinstance(prompt_obj, dict) else None
            return {
                "has_prompt": bool(prompt_obj),
                "prompt_id": prompt_id_local,
                "has_instructions": bool(req_obj.get("instructions")),
                "model": req_obj.get("model"),
                "store": req_obj.get("store"),
                "max_output_tokens": req_obj.get("max_output_tokens"),
                "truncation": req_obj.get("truncation"),
                "tools_count": len(tools),
                "tool_names": tool_names[:40],
                "input_items": summarized_inputs,
                "response_format": "present" if bool(req_obj.get("response_format")) else None,
            }
        except Exception:
            return {"error": "summarize_failed"}

    def _append_openai_trace_record(record: dict) -> None:
        if not _openai_trace_enabled():
            return
        try:
            trace_dir = _openai_trace_dir()
            os.makedirs(trace_dir, exist_ok=True)
            index_path = os.path.join(trace_dir, "openai_trace.jsonl")
            with open(index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _responses_create_with_trace(*, req_obj: dict, call_seq: int) -> Any:
        started_at = time.time()
        resp_obj = client.responses.create(**req_obj)

        response_id = getattr(resp_obj, "id", None)
        out_text_local = getattr(resp_obj, "output_text", "") or ""
        output_items = getattr(resp_obj, "output", None) or []
        tool_calls_local = [item for item in output_items if getattr(item, "type", None) == "function_call"]

        _append_openai_trace_record(
            {
                "ts_utc": _now_iso(),
                "trace_id": trace_id,
                "session_id": session_id,
                "stage": stage,
                "phase": phase,
                "call_seq": call_seq,
                "duration_ms": int((time.time() - started_at) * 1000),
                "request": _summarize_req_for_trace(req_obj),
                "response": {
                    "id": response_id,
                    "output_text_len": len(out_text_local),
                    "tool_calls_count": len(tool_calls_local),
                },
            }
        )
        if _openai_trace_enabled() and response_id:
            logging.info(
                "openai_response_id=%s trace_id=%s stage=%s call_seq=%s",
                str(response_id),
                trace_id,
                stage,
                str(call_seq),
            )
        return resp_obj

    call_seq = 0
    cv_data = session.get("cv_data") or {}
    meta = session.get("metadata") or {}
    readiness = _compute_readiness(cv_data, meta if isinstance(meta, dict) else {})

    pack = build_context_pack_v2(
        phase=phase,
        cv_data=cv_data,
        job_posting_text=job_posting_text,
        session_metadata=meta if isinstance(meta, dict) else {},
        pack_mode=_context_pack_mode(),
        max_pack_chars=8000 if _context_pack_mode() == "mini" else 12000,
    )
    capsule_text = format_context_pack_with_delimiters(pack)

    out_lang = str(meta.get("language") or "").strip() if isinstance(meta, dict) else ""
    readiness_mini = {
        "can_generate": readiness.get("can_generate") if isinstance(readiness, dict) else None,
        "missing": readiness.get("missing") if isinstance(readiness, dict) else None,
        "required_present": readiness.get("required_present") if isinstance(readiness, dict) else None,
    }
    if isinstance(meta, dict) and meta.get("pending_confirmation"):
        readiness_mini["pending_confirmation"] = meta.get("pending_confirmation")

    user_content = (
        f"{user_message}\n\n"
        f"[OUTPUT_LANGUAGE]\n{out_lang}\n\n"
        f"[SESSION_ID]\n{session_id}\n\n"
        f"[READINESS]\n{json.dumps(readiness_mini, ensure_ascii=False)}\n\n"
        f"[CONTEXT_PACK_V2]\n{capsule_text}\n"
        f"\n[STAGE]\n{stage}\n"
        f"[PHASE]\n{phase}\n"
    )

    # Tool permissions are stage-based.
    # - "apply_edits" and "fix_validation" may persist canonical CV changes.
    # - Other stages are read-only.
    allow_persist = stage in ("apply_edits", "fix_validation")
    tools = _tool_schemas_for_responses(allow_persist=allow_persist, stage=stage)
    try:
        tool_names_logged = [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]
        logging.info(
            "trace_id=%s stage=%s phase=%s allow_persist=%s tools=%s store=%s max_tokens=%s",
            trace_id,
            stage,
            phase,
            allow_persist,
            tool_names_logged,
            str(store_flag),
            str(_responses_max_output_tokens(stage)),
        )
    except Exception:
        pass
    req_base: dict = {
        "store": store_flag,
        "truncation": "disabled",
        "max_output_tokens": _responses_max_output_tokens(stage),
        "metadata": {
            "app": "cv-generator-backend",
            "workflow": "backend_orchestrator_v2",
            "trace_id": trace_id,
            "stage": stage,
        },
    }

    # Conditional: structured output (JSON parsing enabled) OR traditional tool calling
    # Note: When using dashboard prompt with structured output, response_format is NOT sent;
    # it's already configured in the dashboard prompt itself.
    if not use_structured_output:
        req_base["tools"] = tools
    if prompt_id:
        req_base["prompt"] = {"id": prompt_id, "variables": {"stage": stage, "phase": phase}}
        # Do not set model when using a dashboard prompt; prompt config owns the model.
    else:
        req_base["instructions"] = "You are a CV assistant operating in a stateless API. Use tools to persist edits."
        # Legacy mode (no dashboard prompt) requires explicit model.
        req_base["model"] = model_override or "gpt-5-mini"

    # Context is stateful within this single HTTP request.
    # Always include a compact stage hint to anchor the model (even with dashboard prompt).
    context: list[Any] = [
        {"role": "developer", "content": _stage_prompt(stage)},
        {"role": "user", "content": user_content},
    ]

    out_text = ""
    for model_call_idx in range(1, max_model_calls + 1):
        model_start = time.time()
        try:
            if _should_log_prompt_debug():
                try:
                    model_for_log = req_base.get("model") or ""
                    logging.info(
                        "responses.create request trace_id=%s stage=%s phase=%s prompt_id=%s model=%s store=%s call_idx=%s context=%s",
                        trace_id,
                        stage,
                        phase,
                        prompt_id or "",
                        model_for_log,
                        str(store_flag),
                        str(model_call_idx),
                        json.dumps(_describe_responses_input(context), ensure_ascii=False),
                    )
                except Exception:
                    pass
            call_context = list(context)
            call_seq += 1
            resp = _responses_create_with_trace(req_obj={**req_base, "input": call_context}, call_seq=call_seq)
        except Exception as e:
            model_end = time.time()
            err = str(e)
            run_summary["steps"].append(
                {
                    "step": "model_call_error",
                    "index": model_call_idx,
                    "duration_ms": int((model_end - model_start) * 1000),
                    "error": err[:800],
                }
            )
            return (
                f"Backend error while calling the model. Please retry. If it persists, check OPENAI_API_KEY / OPENAI_PROMPT_ID.\n\nError: {err}",
                turn_trace,
                run_summary,
                last_response_id,
                pdf_bytes,
            )
        model_end = time.time()

        run_summary["model_calls"] += 1
        model_elapsed_ms = int((model_end - model_start) * 1000)
        last_response_id = getattr(resp, "id", None) or last_response_id
        
        logging.info(f"Model call {model_call_idx} completed in {model_elapsed_ms}ms (trace_id={trace_id})")
        
        if _should_log_prompt_debug():
            try:
                logging.info(
                    "responses.create response trace_id=%s stage=%s call_idx=%s response_id=%s duration_ms=%s",
                    trace_id,
                    stage,
                    str(model_call_idx),
                    last_response_id or "",
                    model_elapsed_ms,
                )
            except Exception:
                pass

        # Parse structured response (if enabled)
        structured_resp: CVAssistantResponse | None = None
        raw_output_text = ""
        schema_repair_attempted = False

        def _parse_structured_output(text: str) -> CVAssistantResponse | None:
            if not text:
                return None
            # Try direct parse
            try:
                return parse_structured_response(text)
            except Exception:
                pass
            # Try trimming to the outermost JSON object (handles trailing prose)
            try:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    candidate = text[start : end + 1]
                    return parse_structured_response(candidate)
            except Exception:
                pass
            return None

        if use_structured_output:
            raw_output_text = getattr(resp, "output_text", "")
            while raw_output_text:
                structured_resp = _parse_structured_output(raw_output_text)
                if structured_resp:
                    break
                logging.warning(
                    "Failed to parse structured response trace_id=%s stage=%s call_idx=%s error=%s",
                    trace_id,
                    stage,
                    model_call_idx,
                    "parse_failed",
                )
                if not schema_repair_attempted:
                    schema_repair_attempted = True
                    repair_resp = _schema_repair_response(
                        client=client,
                        req_base=req_base,
                        base_context=call_context,
                        trace_id=trace_id,
                        stage=stage,
                        model_call_idx=model_call_idx,
                    )
                    if repair_resp:
                        resp = repair_resp
                        run_summary["model_calls"] += 1
                        last_response_id = getattr(resp, "id", None) or last_response_id
                        raw_output_text = getattr(resp, "output_text", "")
                        continue
                    logging.warning(
                        "Schema repair attempt unable to generate a new response trace_id=%s call_idx=%s",
                        trace_id,
                        model_call_idx,
                    )
                raw_output_text = getattr(resp, "output_text", "") or raw_output_text
                break
            if structured_resp:
                # Extract user-facing message
                formatted = format_user_message_for_ui(structured_resp)
                # Convert dict format back to text for backward compatibility (cleaner formatting)
                parts = []
                
                # Main text first
                main_text = formatted.get("text", "").strip()
                if main_text:
                    parts.append(main_text)
                
                # Sections as formatted blocks
                sections = formatted.get("sections") or []
                if sections:
                    for s in sections:
                        section_text = f"### {s['title']}\n{s['content']}"
                        parts.append(section_text)
                
                # Questions as numbered list
                questions = formatted.get("questions") or []
                if questions:
                    q_lines = ["**Please confirm:**"]
                    for idx, q in enumerate(questions, 1):
                        q_lines.append(f"{idx}. {q['question']}")
                        if q.get("options"):
                            for opt in q["options"]:
                                q_lines.append(f"   - {opt}")
                    parts.append("\n".join(q_lines))
                
                out_text = "\n\n".join(parts)
                
                # Log metadata
                if _should_log_prompt_debug():
                    logging.info(
                        "Structured response trace_id=%s response_type=%s confidence=%s validation_status=%s",
                        trace_id,
                        structured_resp.response_type.value,
                        structured_resp.metadata.confidence.value,
                        json.dumps({
                            "schema_valid": structured_resp.metadata.validation_status.schema_valid,
                            "page_count_ok": structured_resp.metadata.validation_status.page_count_ok,
                            "required_fields_present": structured_resp.metadata.validation_status.required_fields_present,
                            "issues": structured_resp.metadata.validation_status.issues
                        })
                    )
                # out_text is already set by formatting above; do not overwrite
        else:
            # Traditional mode: just use raw output text
            out_text = getattr(resp, "output_text", "") or out_text

        outputs = getattr(resp, "output", None) or []
        for item in outputs:
            context.append(item)

        # Handle tool calls from structured response or traditional tool calling
        tool_calls = []
        if use_structured_output and structured_resp and structured_resp.system_actions.tool_calls:
            # Structured response mode: tool calls are embedded in JSON
            for tc in structured_resp.system_actions.tool_calls:
                tool_calls.append({
                    "name": tc.tool_name.value,
                    "arguments": tc.parameters,
                    "reason": tc.reason,
                    "structured": True
                })
            # Check if confirmation is required before executing
            if structured_resp.system_actions.confirmation_required and not tool_calls:
                # Model wants user confirmation before proceeding
                break
        else:
            # Traditional tool calling mode
            tool_calls = [item for item in outputs if getattr(item, "type", None) == "function_call"]

        if len(tool_calls) > 4:
            logging.warning(
                "Trace %s stage %s returned %d tool_calls (max 4); truncating to 4",
                trace_id,
                stage,
                len(tool_calls),
            )
            tool_calls = tool_calls[:4]

        run_summary["steps"].append(
            {
                "step": "model_call",
                "index": model_call_idx,
                "duration_ms": int((model_end - model_start) * 1000),
                "tool_calls": len(tool_calls),
            }
        )

        if not tool_calls:
            break

        tool_names: list[str] = []
        for call in tool_calls:
            # Handle both structured and traditional tool calls
            if isinstance(call, dict) and call.get("structured"):
                name = call["name"]
                args = call["arguments"]
            else:
                name = getattr(call, "name", None) or getattr(getattr(call, "function", None), "name", None)
                args_raw = getattr(call, "arguments", None) or getattr(getattr(call, "function", None), "arguments", None) or "{}"
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw or {})
                except Exception:
                    args = {}
            tool_names.append(str(name))

            tool_start = time.time()
            tool_payload: Any = {}
            try:
                if name in ("generate_cv_from_session", "get_pdf_by_ref") and stage not in ("generate_pdf", "fix_validation"):
                    tool_payload = {"error": "pdf_tool_not_allowed_in_stage", "stage": stage}
                elif name == "get_cv_session":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {
                            "success": True,
                            "session_id": sid,
                            "readiness": _compute_readiness(cv, s.get("metadata") or {}),
                            "cv_data": cv,
                            "metadata": s.get("metadata"),
                        }
                elif name == "update_cv_field":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        confirm_flags = args.get("confirm")
                        confirm_applied = 0
                        if isinstance(confirm_flags, dict) and confirm_flags:
                            meta2 = s.get("metadata") or {}
                            if isinstance(meta2, dict):
                                meta2 = dict(meta2)
                                cf = meta2.get("confirmed_flags") or {}
                                if not isinstance(cf, dict):
                                    cf = {}
                                cf = dict(cf)
                                for k in ("contact_confirmed", "education_confirmed"):
                                    if k in confirm_flags:
                                        cf[k] = bool(confirm_flags.get(k))
                                if cf.get("contact_confirmed") and cf.get("education_confirmed") and not cf.get("confirmed_at"):
                                    cf["confirmed_at"] = _now_iso()
                                meta2["confirmed_flags"] = cf
                                store.update_session(str(sid), (s.get("cv_data") or {}), meta2)
                                confirm_applied = 1

                        edits = args.get("edits")
                        field_path = args.get("field_path")
                        value = args.get("value")
                        cv_patch = args.get("cv_patch")
                        applied = 0
                        if isinstance(edits, list):
                            for e in edits:
                                fp = e.get("field_path")
                                if not fp:
                                    continue
                                store.update_field(str(sid), fp, e.get("value"))
                                applied += 1
                        if isinstance(cv_patch, dict) and cv_patch:
                            for fp, v in cv_patch.items():
                                store.update_field(str(sid), str(fp), v)
                                applied += 1
                        if field_path:
                            store.update_field(str(sid), str(field_path), value)
                            applied += 1

                        total_applied = applied + confirm_applied
                        if total_applied == 0:
                            tool_payload = {
                                "error": "no_op",
                                "message": "No updates were applied. Provide at least one of: field_path+value, edits[], cv_patch, or confirm{}.",
                            }
                        else:
                            s2 = store.get_session(str(sid)) or s
                            cv2 = s2.get("cv_data") or {}
                            meta3 = s2.get("metadata") or {}
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "edits_applied": applied,
                                "confirm_applied": bool(confirm_applied),
                                "readiness": _compute_readiness(cv2, meta3 if isinstance(meta3, dict) else {}),
                            }
                elif name == "validate_cv":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        out = _validate_cv_data_for_tool(cv)
                        tool_payload = {"success": True, "session_id": sid, **out, "readiness": _compute_readiness(cv, s.get("metadata") or {})}
                elif name == "cv_session_search":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        q = str(args.get("q") or "")
                        try:
                            limit = int(args.get("limit") or 20)
                        except Exception:
                            limit = 20
                        limit = max(1, min(limit, 50))
                        tool_payload = {"success": True, "session_id": sid, **_cv_session_search_hits(session=s, q=q, limit=limit)}
                elif name == "generate_context_pack_v2":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, pack2 = _tool_generate_context_pack_v2(
                            session_id=str(sid),
                            phase=str(args.get("phase") or "preparation"),
                            job_posting_text=str(args.get("job_posting_text") or "") or None,
                            max_pack_chars=int(args.get("max_pack_chars") or 12000),
                            session=s,
                        )
                        tool_payload = pack2 if status == 200 else {"error": pack2.get("error") if isinstance(pack2, dict) else "pack_failed"}
                elif name == "preview_html":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {"success": True, "session_id": sid, **_render_html_for_tool(cv, inline_css=bool(args.get("inline_css", True)))}
                elif name == "generate_cv_from_session":
                    sid = args.get("session_id") or session_id
                    logging.info(f"=== TOOL: generate_cv_from_session (v2) === session_id={sid} trace_id={trace_id}")
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                        logging.warning(f"=== TOOL: generate_cv_from_session (v2) FAILED === session not found")
                    else:
                        status, payload, content_type = _tool_generate_cv_from_session(
                            session_id=str(sid),
                            language=str(args.get("language") or "").strip() or None,
                            client_context=None,
                            session=s,
                        )
                        if (
                            content_type == "application/pdf"
                            and isinstance(payload, dict)
                            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
                            and status == 200
                        ):
                            pdf_bytes = bytes(payload["pdf_bytes"])
                            pdf_meta = payload.get("pdf_metadata") or {}
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_meta.get("pdf_ref"),
                                "pdf_sha256": pdf_meta.get("sha256"),
                                "pdf_size_bytes": pdf_meta.get("pdf_size_bytes"),
                                "render_ms": pdf_meta.get("render_ms"),
                                "validation_passed": pdf_meta.get("validation_passed"),
                                "pdf_pages": pdf_meta.get("pages"),
                            }
                            logging.info(
                                "=== TOOL: generate_cv_from_session (v2) SUCCESS === pdf_size=%d bytes pdf_ref=%s",
                                len(pdf_bytes),
                                pdf_meta.get("pdf_ref"),
                            )
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "generate_failed"}
                            logging.warning(f"=== TOOL: generate_cv_from_session (v2) FAILED === status={status} payload={tool_payload}")
                elif name == "get_pdf_by_ref":
                    sid = args.get("session_id") or session_id
                    pdf_ref = str(args.get("pdf_ref") or "").strip()
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, payload, content_type = _tool_get_pdf_by_ref(
                            session_id=str(sid),
                            pdf_ref=pdf_ref,
                            session=s,
                        )
                        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)) and status == 200:
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_ref,
                                "pdf_size_bytes": len(payload),
                            }
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "pdf_fetch_failed"}
                else:
                    tool_payload = {"error": f"Unknown tool: {name}"}
            except Exception as e:
                tool_payload = {"error": f"tool_exec_failed: {e}"}

            tool_end = time.time()
            run_summary["steps"].append(
                {
                    "step": "tool",
                    "tool": str(name),
                    "duration_ms": int((tool_end - tool_start) * 1000),
                    "ok": isinstance(tool_payload, dict) and not tool_payload.get("error"),
                }
            )

            tool_output_for_model = _sanitize_tool_output_for_model(str(name), tool_payload)
            call_id = getattr(call, "call_id", None) or getattr(call, "id", None) or ""
            context.append({"type": "function_call_output", "call_id": call_id, "output": tool_output_for_model})

        turn_trace.append(
            {
                "turn": model_call_idx,
                "stage": stage,
                "phase": phase,
                "tools_called": tool_names,
                "tool_calls_count": len(tool_names),
                "readiness": readiness,
                "assistant_text_chars": len(out_text),
            }
        )

        # Wave 0.3: Fire-and-forget in execution mode
        # After generate_cv_from_session executes, terminate loop immediately
        if execution_mode and "generate_cv_from_session" in tool_names:
            logging.info(f"Execution mode: generate_cv_from_session executed, terminating loop (fire-and-forget)")
            # Return immediately with PDF if generated
            if pdf_bytes:
                return out_text or "PDF generated.", turn_trace, run_summary, last_response_id, pdf_bytes
            # Otherwise return with tool result
            return out_text or "PDF generation attempted.", turn_trace, run_summary, last_response_id, pdf_bytes

    # If output looks truncated near cap, do one continuation (no tools).
    if out_text and _looks_truncated(out_text):
        try:
            call_seq += 1
            cont = _responses_create_with_trace(
                req_obj={
                    **req_base,
                    "input": context + [{"role": "user", "content": "Continue from where you stopped. Do not repeat."}],
                    "tools": [],
                    "max_output_tokens": min(1024, _responses_max_output_tokens(stage)),
                },
                call_seq=call_seq,
            )
            cont_text = getattr(cont, "output_text", "") or ""
            if cont_text:
                out_text = f"{out_text.rstrip()}\n\n{cont_text.lstrip()}"
                last_response_id = getattr(cont, "id", None) or last_response_id
        except Exception:
            pass

    return out_text or "Done.", turn_trace, run_summary, last_response_id, pdf_bytes


def _schema_repair_response(
    *,
    client: OpenAI,
    req_base: dict,
    base_context: list[Any],
    trace_id: str,
    stage: str,
    model_call_idx: int,
) -> Any | None:
    """
    Attempt to regenerate a structured response after a schema parse failure.
    """
    repair_context = list(base_context)
    repair_context.append(
        {
            "role": "developer",
            "content": (
                "Your previous response did not match the required JSON schema. "
                "Please try again and return only valid JSON that strictly conforms to the schema."
            ),
        }
    )
    logging.warning(
        "Schema repair attempt trace_id=%s stage=%s call_idx=%s",
        trace_id,
        stage,
        model_call_idx,
    )
    try:
        resp_obj = client.responses.create(**{**req_base, "input": repair_context})
        if str(os.environ.get("CV_OPENAI_TRACE", "0")).strip() == "1":
            try:
                trace_dir = str(os.environ.get("CV_OPENAI_TRACE_DIR") or "tmp/openai_trace").strip()
                os.makedirs(trace_dir, exist_ok=True)
                index_path = os.path.join(trace_dir, "openai_trace.jsonl")
                rid = getattr(resp_obj, "id", None)
                with open(index_path, "a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "ts_utc": _now_iso(),
                                "trace_id": trace_id,
                                "session_id": None,
                                "stage": stage,
                                "phase": None,
                                "call_seq": f"schema_repair_{model_call_idx}",
                                "request": {
                                    "has_prompt": bool(req_base.get("prompt")),
                                    "prompt_id": (req_base.get("prompt") or {}).get("id") if isinstance(req_base.get("prompt"), dict) else None,
                                    "has_instructions": bool(req_base.get("instructions")),
                                    "model": req_base.get("model"),
                                    "store": req_base.get("store"),
                                    "max_output_tokens": req_base.get("max_output_tokens"),
                                    "tools_count": len(req_base.get("tools") or []),
                                    "response_format": "present" if bool(req_base.get("response_format")) else None,
                                },
                                "response": {"id": rid, "output_text_len": len(getattr(resp_obj, "output_text", "") or "")},
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                if rid:
                    logging.info("openai_response_id=%s trace_id=%s stage=%s call_seq=%s", str(rid), trace_id, stage, f"schema_repair_{model_call_idx}")
            except Exception:
                pass
        return resp_obj
    except Exception as exc:
        logging.warning(
            "Schema repair API call failed trace_id=%s stage=%s call_idx=%s error=%s",
            trace_id,
            stage,
            model_call_idx,
            exc,
        )
        return None


def _tool_process_cv_orchestrated(params: dict) -> tuple[int, dict]:
    """
    Backend-owned orchestration entrypoint (thin UI client).
    """
    trace_id = str(params.get("trace_id") or uuid.uuid4())
    message = str(params.get("message") or "").strip()
    docx_base64 = str(params.get("docx_base64") or "")
    session_id = str(params.get("session_id") or "").strip()
    job_posting_text = (str(params.get("job_posting_text") or "").strip() or None)
    job_posting_url = (str(params.get("job_posting_url") or "").strip() or None)
    language = str(params.get("language") or "en").strip() or "en"
    client_context = params.get("client_context") if isinstance(params.get("client_context"), dict) else None

    if not message:
        return 400, {"success": False, "error": "message is required", "trace_id": trace_id}

    # Contract stage selection is backend-owned. We keep the old scoring only for UI/prompt hints.
    stage_debug = {}
    wants_generate = False

    if (job_posting_url and not job_posting_text) and not wants_generate:
        return 200, {
            "success": True,
            "trace_id": trace_id,
            "session_id": session_id or None,
            "assistant_text": "I could not fetch the job posting text. Please paste the full job description (responsibilities + requirements + title/company).",
            "run_summary": {"trace_id": trace_id, "steps": [{"step": "ask_for_job_text"}]},
            "turn_trace": [],
        }

    # Ensure session exists if docx provided.
    if not session_id and docx_base64:
        status, created = _tool_extract_and_store_cv(
            docx_base64=docx_base64,
            language=language,
            extract_photo_flag=bool(params.get("extract_photo", True)),
            job_posting_url=job_posting_url,
            job_posting_text=job_posting_text,
        )
        if status != 200:
            return status, {"success": False, "trace_id": trace_id, "error": created.get("error") if isinstance(created, dict) else "extract_failed"}
        session_id = str(created.get("session_id") or "")

    if not session_id:
        return 200, {"success": True, "trace_id": trace_id, "assistant_text": "Please upload your CV DOCX to start.", "run_summary": {"trace_id": trace_id, "steps": [{"step": "ask_for_docx"}]}, "turn_trace": []}

    # Validate session exists
    store = _get_session_store()
    sess = store.get_session(session_id)
    if not sess:
        logging.warning(
            "Session missing before orchestration trace_id=%s session_id=%s",
            trace_id,
            session_id,
        )
        return 200, {"success": True, "trace_id": trace_id, "assistant_text": "Your session is no longer available. Please re-upload your CV DOCX to start a new session.", "session_id": None, "run_summary": {"trace_id": trace_id, "steps": [{"step": "session_missing"}]}, "turn_trace": []}

    # Keep metadata language in sync with user preference (stateless calls).
    if isinstance(sess.get("metadata"), dict) and language:
        meta = dict(sess.get("metadata") or {})
        if meta.get("language") != language:
            meta["language"] = language
            store.update_session(session_id, (sess.get("cv_data") or {}), meta)
            sess = store.get_session(session_id) or sess

    meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else {}
    meta = dict(meta) if isinstance(meta, dict) else {}
    cv_data = sess.get("cv_data") if isinstance(sess.get("cv_data"), dict) else {}
    cv_data = dict(cv_data) if isinstance(cv_data, dict) else {}

    current_stage = _get_stage_from_metadata(meta)
    generate_requested = _wants_generate_from_message(message)
    edit_intent = detect_edit_intent(message)

    # confirmation_required is backend-owned: either we have explicit pending edits, or identity-critical fields not confirmed.
    confirmed_flags = meta.get("confirmed_flags") if isinstance(meta.get("confirmed_flags"), dict) else {}
    pending_patch = meta.get("pending_patch") if isinstance(meta.get("pending_patch"), dict) else None
    docx_prefill_unconfirmed = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else None
    pending_edits = 1 if (pending_patch is not None) else 0
    pending_confirmation = _get_pending_confirmation(meta)
    confirmation_required = bool(pending_confirmation)

    # Validation state is deterministic: schema + validator (includes estimated_pages).
    schema_valid, _schema_errors = validate_canonical_schema(normalize_cv_data(cv_data), strict=True)
    val_result = validate_cv(normalize_cv_data(cv_data))
    validation_passed = bool(schema_valid) and bool(getattr(val_result, "is_valid", False))
    readiness = _compute_readiness(cv_data, meta)
    readiness_ok = bool(readiness.get("can_generate")) and _estimate_pages_ok(cv_data) and pending_edits == 0

    # Ensure a deterministic pending confirmation when DOCX prefill exists but is not committed.
    if isinstance(docx_prefill_unconfirmed, dict) and (not cv_data.get("work_experience") or not cv_data.get("education")):
        if not pending_confirmation:
            logging.info(f"Setting pending_confirmation for import_prefill (DOCX has data, canonical CV empty)")
            meta = _set_pending_confirmation(meta, kind="import_prefill")
            pending_confirmation = _get_pending_confirmation(meta)
            # Persist immediately; stage may not change on this turn, but the confirmation gate must.
            try:
                store.update_session(session_id, cv_data, meta)
                sess = store.get_session(session_id) or sess
                meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else meta
                logging.info(f"Pending confirmation persisted successfully")
            except Exception as e:
                logging.warning(f"Failed to persist pending_confirmation: {e}")
        else:
            logging.info(f"Pending confirmation already set: {pending_confirmation}")
    
    # CRITICAL: Refresh confirmation_required after any pending_confirmation updates
    # (FSM diagnostics must reflect current state, not stale state from line 2175)
    pending_confirmation = _get_pending_confirmation(meta)
    confirmation_required = bool(pending_confirmation)

    user_confirm_yes = _user_confirm_yes(message) or _is_import_prefill_intent(message) or _is_generate_pdf_intent(message)
    user_confirm_no = _user_confirm_no(message)
    
    # Get turn counter for auto-advance logic
    turns_in_review = _get_turns_in_review(meta)
    
    next_stage = resolve_stage(
        current_stage,
        message,
        SessionState(
            confirmation_required=confirmation_required,
            pending_edits=pending_edits,
            generate_requested=generate_requested,
            user_confirm_yes=user_confirm_yes,
            user_confirm_no=user_confirm_no,
            turns_in_review=turns_in_review,
        ),
        ValidationState(
            validation_passed=validation_passed,
            readiness_ok=readiness_ok,
            pdf_generated=bool(meta.get("pdf_generated")),
            pdf_failed=bool(meta.get("pdf_failed")),
        ),
    )
    
    # Handle turn counter: increment if staying in REVIEW, reset if leaving
    if current_stage == CVStage.REVIEW and next_stage == CVStage.REVIEW:
        meta = _increment_turns_in_review(meta)
        turns_in_review = _get_turns_in_review(meta)
        logging.info(f"Staying in REVIEW: turn {turns_in_review} (auto-advance at turn 3)")
    elif next_stage != CVStage.REVIEW:
        if current_stage == CVStage.REVIEW:
            logging.info(f"Exiting REVIEW after {turns_in_review} turns → {next_stage.value}")
        meta = _reset_turns_in_review(meta)

    # Wave 0.2: Clear pdf_generated when re-entering REVIEW after PDF generation
    if next_stage == CVStage.REVIEW and current_stage in (CVStage.EXECUTE, CVStage.DONE):
        meta = dict(meta) if isinstance(meta, dict) else {}
        meta["pdf_generated"] = False
        meta.pop("pdf_failed", None)
        logging.info(f"Cleared pdf_generated flag (edit intent after {current_stage.value})")

    # Extended diagnostics: show why FSM is or isn't progressing
    stage_debug.update({
        "current_stage": current_stage.value,
        "next_stage": next_stage.value,
        "edit_intent": bool(edit_intent),
        "generate_requested": bool(generate_requested),
        "confirmation_required": confirmation_required,
        "user_confirm_yes": user_confirm_yes,
        "user_confirm_no": user_confirm_no,
        "validation_passed": validation_passed,
        "readiness_ok": readiness_ok,
        "pending_edits": pending_edits,
        "turns_in_review": turns_in_review,
    })
    logging.info(f"FSM: {current_stage.value}→{next_stage.value} | confirm_req={confirmation_required} user_yes={user_confirm_yes} turns={turns_in_review} val={validation_passed} ready={readiness_ok}")

    # Persist stage transitions (backend-owned).
    if next_stage != current_stage:
        meta = _set_stage_in_metadata(meta, next_stage)
        store.update_session(session_id, cv_data, meta)
        sess = store.get_session(session_id) or sess
        meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else meta
        cv_data = sess.get("cv_data") if isinstance(sess.get("cv_data"), dict) else cv_data
    else:
        # Stage didn't change; persist turn counter if still in REVIEW
        if next_stage == CVStage.REVIEW:
            try:
                store.update_session(session_id, cv_data, meta)
            except Exception:
                pass

    # Map contract stages to current internal prompt stages:
    stage_map = {
        CVStage.INGEST: "review_session",
        CVStage.PREPARE: "review_session",
        CVStage.REVIEW: "review_session",
        # CONFIRM is where the user explicitly allows persistence; enable tool-capable stage.
        CVStage.CONFIRM: "apply_edits",
        CVStage.EXECUTE: "generate_pdf",
        CVStage.DONE: "review_session",
    }
    stage = stage_map.get(next_stage, "review_session")

    # CONFIRM stage: apply explicitly confirmed action (scoped; no global "yes commits everything").
    # Auto-clear pending_confirmation when entering CONFIRM stage (already confirmed by FSM auto-advance).
    pc = _get_pending_confirmation(meta)
    if next_stage == CVStage.CONFIRM and pc and pc.get("kind") == "import_prefill":
        try:
            sess_conf = store.get_session(session_id) or sess
            meta_conf = sess_conf.get("metadata") if isinstance(sess_conf.get("metadata"), dict) else {}
            meta_conf = dict(meta_conf) if isinstance(meta_conf, dict) else {}
            cv_conf = sess_conf.get("cv_data") if isinstance(sess_conf.get("cv_data"), dict) else {}
            cv_conf = dict(cv_conf) if isinstance(cv_conf, dict) else {}
            docx_prefill = meta_conf.get("docx_prefill_unconfirmed")
            if isinstance(docx_prefill, dict):
                cv_conf, meta_conf, _merged = _merge_docx_prefill_into_cv_data_if_needed(
                    cv_data=cv_conf,
                    docx_prefill=docx_prefill,
                    meta=meta_conf,
                )
            # Mark that this specific confirmation was handled (entering CONFIRM stage is the confirmation).
            meta_conf = _clear_pending_confirmation(meta_conf)
            logging.info(f"Cleared pending_confirmation (kind={pc.get('kind')}) on CONFIRM stage entry")
            store.update_session(session_id, cv_conf, meta_conf)
            sess = store.get_session(session_id) or sess
        except Exception as e:
            logging.error(f"Failed to clear pending_confirmation on CONFIRM entry: {e}")
            pass

    # EXECUTE is the only stage that can generate. Gate it with explicit "generate pdf" confirmation.
    if next_stage == CVStage.EXECUTE:
        if not _is_generate_pdf_intent(message):
            # Force back to REVIEW if user did not explicitly request generation.
            next_stage = CVStage.REVIEW
            meta = _set_stage_in_metadata(meta, next_stage)
            store.update_session(session_id, cv_data, meta)
            stage = "review_session"

    readiness = _compute_readiness(sess.get("cv_data") or {}, sess.get("metadata") or {})

    # If user explicitly requests generation and readiness is satisfied, opt into generate_pdf stage
    # for this turn to enforce single-call execution and expose PDF tools.
    if stage != "generate_pdf" and generate_requested and readiness.get("can_generate"):
        stage = "generate_pdf"

    max_model_calls = int(os.environ.get("CV_MAX_MODEL_CALLS", os.environ.get("CV_MAX_TURNS", "5")) or 5)
    max_model_calls = max(1, min(max_model_calls, 5))

    version_before = sess.get("version")

    # Fast-path: edit intent should not invoke the model; return deterministic response.
    if detect_edit_intent(message):
        run_summary = {
            "stage_debug": stage_debug,
            "steps": [{"step": "edit_intent_short_circuit"}],
            "execution_mode": False,
            "model_calls": 0,
            "max_model_calls": max_model_calls,
        }
        return 200, {
            "success": True,
            "trace_id": trace_id,
            "session_id": session_id,
            "stage": stage,
            "assistant_text": "Edit intent detected. Tell me what to change, and I will update your CV fields.",
            "pdf_base64": "",
            "last_response_id": None,
            "run_summary": run_summary,
            "turn_trace": [],
            "client_context_keys": list(client_context.keys())[:20] if client_context else None,
        }

    # Best-effort: append user event (for semantic debugging).
    try:
        store.append_event(
            session_id,
            {
                "type": "user_message",
                "trace_id": trace_id,
                "stage": stage,
                "text": message[:1500],
                "text_len": len(message or ""),
            },
        )
    except Exception:
        pass

    assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes = _run_responses_tool_loop_v2(
        user_message=message,
        session_id=session_id,
        stage=stage,
        job_posting_text=job_posting_text,
        trace_id=trace_id,
        max_model_calls=max_model_calls,
        execution_mode=(stage == "generate_pdf"),  # Wave 0.3: Enable execution mode for PDF generation
    )

    # Deterministic hard rules and debuggability.
    run_summary.setdefault("stage_debug", {})
    run_summary["stage_debug"].update(stage_debug)
    run_summary["stage_debug"].update({"version_before": version_before})

    def _tool_steps_count(rs: dict) -> int:
        steps = rs.get("steps")
        if not isinstance(steps, list):
            return 0
        return sum(1 for s in steps if isinstance(s, dict) and s.get("step") == "tool")

    sess_after = store.get_session(session_id) or sess
    version_after = sess_after.get("version")
    run_summary["stage_debug"]["version_after"] = version_after
    readiness_after = _compute_readiness(sess_after.get("cv_data") or {}, sess_after.get("metadata") or {})
    run_summary["stage_debug"]["readiness_after"] = readiness_after

    # Hard rule: if generation requested but readiness not met -> never return "Done." and never generate.
    if stage == "generate_pdf" and not readiness_after.get("can_generate"):
        missing = readiness_after.get("missing") or []
        assistant_text = (
            "I can’t generate the PDF yet. The session is not complete.\n\n"
            f"Missing / not confirmed: {', '.join(missing) if missing else 'unknown'}.\n\n"
            "Please fill/confirm those fields, then ask again to generate the PDF."
        )
        pdf_bytes = None

    # Deterministic fallback: if the user asked to generate and we still have no PDF, generate directly
    # once readiness is satisfied. This avoids "Done." responses without a PDF.
    # Wave 0.1: Skip fallback if PDF already exists (latch engaged)
    skip_fallback = False
    if os.environ.get("CV_EXECUTION_LATCH", "1").strip() == "1":
        sess_check = store.get_session(session_id) or {}
        meta_check = sess_check.get("metadata") or {}
        pdf_refs_check = meta_check.get("pdf_refs") if isinstance(meta_check, dict) else {}
        if isinstance(pdf_refs_check, dict) and pdf_refs_check:
            skip_fallback = True
            logging.info(f"Skipping fallback PDF generation: PDF already exists (latch engaged)")

    if stage == "generate_pdf" and not pdf_bytes and not skip_fallback:
        try:
            sess2 = store.get_session(session_id) or {}
            meta2 = sess2.get("metadata") or {}
            cv2 = sess2.get("cv_data") or {}
            readiness2 = _compute_readiness(cv2 if isinstance(cv2, dict) else {}, meta2 if isinstance(meta2, dict) else {})
            if readiness2.get("can_generate"):
                status, payload, content_type = _tool_generate_cv_from_session(
                    session_id=session_id,
                    language=language,
                    client_context=client_context if isinstance(client_context, dict) else None,
                    session=sess2,
                )
                if status == 200 and content_type == "application/pdf" and isinstance(payload, dict) and isinstance(payload.get("pdf_bytes"), (bytes, bytearray)):
                    pdf_bytes = bytes(payload["pdf_bytes"])
                    run_summary.setdefault("steps", []).append({"step": "fallback_pdf_generation", "ok": True})
                else:
                    run_summary.setdefault("steps", []).append({"step": "fallback_pdf_generation", "ok": False, "status": status})
        except Exception as exc:
            run_summary.setdefault("steps", []).append({"step": "fallback_pdf_generation", "ok": False, "error": str(exc)})

    # Hard rule: no-changes-no-generation. If nothing changed in this request and we didn't generate a PDF,
    # return a deterministic next-step instead of "Done.".
    if stage == "generate_pdf" and not pdf_bytes and version_after == version_before and not bool(readiness_after.get("can_generate")):
        assistant_text = (
            "No changes were applied in this request, so I did not generate a PDF.\n\n"
            "Next step: confirm/import the prefilled DOCX data into active cv_data (work experience, education, etc.), "
            "then ask again to generate the PDF."
        )

    # Guardrail: if the model returns a no-op 'Done.' without tools, replace with a deterministic response.
    if (assistant_text or "").strip().lower() in ("done.", "done") and _tool_steps_count(run_summary) == 0:
        assistant_text = (
            "I have your session and the DOCX prefill, but I didn’t apply any changes yet.\n\n"
            f"Current readiness.can_generate = {bool(readiness_after.get('can_generate'))}. "
            f"Missing: {', '.join(readiness_after.get('missing') or []) or 'none'}.\n\n"
            "Tell me: (1) import the DOCX prefill into active cv_data (yes/no), and (2) whether to generate the PDF now."
        )

    # Best-effort: append assistant event (pairs user+assistant in event_log).
    try:
        store.append_event(
            session_id,
            {
                "type": "assistant_message",
                "trace_id": trace_id,
                "stage": stage,
                "text": (assistant_text or "")[:1500],
                "text_len": len(assistant_text or ""),
                "run_summary": {"model_calls": run_summary.get("model_calls"), "steps": run_summary.get("steps")[-10:] if isinstance(run_summary.get("steps"), list) else []},
            },
        )
    except Exception:
        pass

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else ""
    return 200, {
        "success": True,
        "trace_id": trace_id,
        "session_id": session_id,
        "stage": stage,
        "assistant_text": assistant_text,
        "pdf_base64": pdf_base64,
        # Debug-only: useful when OPENAI_STORE=1 and you want to inspect a specific Responses API run.
        "last_response_id": last_response_id,
        "run_summary": run_summary,
        "turn_trace": turn_trace,
        "client_context_keys": list(client_context.keys())[:20] if client_context else None,
    }


def _cv_session_search_hits(*, session: dict, q: str, limit: int) -> dict:
    """Pure helper: build bounded search hits from a session dict (no storage I/O)."""
    q = (q or "").lower().strip()
    limit = max(1, min(int(limit or 20), 50))

    hits: list[dict] = []

    def _add_hit(source: str, field_path: str, value: Any) -> None:
        preview = ""
        if isinstance(value, str):
            preview = value[:240]
        elif isinstance(value, (int, float)):
            preview = str(value)
        elif isinstance(value, list):
            preview = json.dumps(value[:2], ensure_ascii=False)[:240]
        elif isinstance(value, dict):
            preview = json.dumps(value, ensure_ascii=False)[:240]
        if q and q not in preview.lower():
            return
        hits.append({"source": source, "field_path": field_path, "preview": preview})

    meta = session.get("metadata") or {}
    docx_prefill = meta.get("docx_prefill_unconfirmed") or {}
    cv_data = session.get("cv_data") or {}

    for fp in ["full_name", "email", "phone"]:
        if fp in docx_prefill:
            _add_hit("docx_prefill_unconfirmed", fp, docx_prefill[fp])
        if fp in cv_data:
            _add_hit("cv_data", fp, cv_data.get(fp))

    def _walk_list(lst: Any, base: str, source: str) -> None:
        if not isinstance(lst, list):
            return
        for idx, item in enumerate(lst):
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                _add_hit(source, f"{base}[{idx}].{k}", v)

    _walk_list(docx_prefill.get("education"), "docx.education", "docx_prefill_unconfirmed")
    _walk_list(cv_data.get("education"), "education", "cv_data")
    _walk_list(docx_prefill.get("work_experience"), "docx.work_experience", "docx_prefill_unconfirmed")
    _walk_list(cv_data.get("work_experience"), "work_experience", "cv_data")

    events = meta.get("event_log") or []
    if isinstance(events, list):
        for i, e in enumerate(events[-20:]):
            _add_hit("event_log", f"event_log[-{min(20, len(events))}+{i}]", e)

    truncated = False
    if len(hits) > limit:
        hits = hits[:limit]
        truncated = True

    return {"hits": hits, "truncated": truncated}


def _validate_cv_data_for_tool(cv_data: dict) -> dict:
    """Deterministic validation for tool use (no rendering)."""
    cv_data = normalize_cv_data(cv_data or {})
    is_schema_valid, schema_errors = validate_canonical_schema(cv_data, strict=True)
    validation_result = validate_cv(cv_data)
    return {
        "schema_valid": bool(is_schema_valid),
        "schema_errors": schema_errors,
        "validation": _serialize_validation_result(validation_result),
    }


def _render_html_for_tool(cv_data: dict, *, inline_css: bool = True) -> dict:
    """Render HTML for tool use (debug/preview)."""
    cv_data = normalize_cv_data(cv_data or {})
    html_content = render_html(cv_data, inline_css=inline_css)
    return {"html": html_content, "html_length": len(html_content or "")}


def _tool_extract_and_store_cv(*, docx_base64: str, language: str, extract_photo_flag: bool, job_posting_url: str | None, job_posting_text: str | None) -> tuple[int, dict]:
    if not docx_base64:
        return 400, {"error": "docx_base64 is required"}

    try:
        docx_bytes = base64.b64decode(docx_base64)
    except Exception as e:
        return 400, {"error": "Invalid base64 encoding", "details": str(e)}

    # Start-fresh semantics are provided by new session IDs; do not purge global storage.
    # Best-effort: cleanup expired sessions to keep local dev storage tidy (at most once per process).
    global _CLEANUP_EXPIRED_RAN
    store = _get_session_store()
    if not _CLEANUP_EXPIRED_RAN:
        _CLEANUP_EXPIRED_RAN = True
        try:
            deleted = store.cleanup_expired()
            if deleted:
                logging.info(f"Expired sessions cleaned: {deleted}")
        except Exception:
            pass

    extracted_photo = None
    photo_extracted = False
    photo_storage = "none"
    photo_omitted_reason = None
    if extract_photo_flag:
        try:
            extracted_photo = extract_first_photo_from_docx_bytes(docx_bytes)
            photo_extracted = bool(extracted_photo)
            logging.info(f"Photo extraction: {'success' if extracted_photo else 'no photo found'}")
        except Exception as e:
            photo_omitted_reason = f"photo_extraction_failed: {e}"
            logging.warning(f"Photo extraction failed: {e}")

    prefill = prefill_cv_from_docx_bytes(docx_bytes)

    cv_data = {
        "full_name": "",
        "email": "",
        "phone": "",
        "address_lines": [],
        "photo_url": "",
        "profile": "",
        "work_experience": [],
        "education": [],
        "further_experience": [],
        "languages": [],
        "it_ai_skills": [],
        "interests": "",
        "references": "",
    }

    prefill_summary = {
        "has_name": bool(prefill.get("full_name")),
        "has_email": bool(prefill.get("email")),
        "has_phone": bool(prefill.get("phone")),
        "work_experience_count": len(prefill.get("work_experience", []) or []),
        "education_count": len(prefill.get("education", []) or []),
        "languages_count": len(prefill.get("languages", []) or []),
        "it_ai_skills_count": len(prefill.get("it_ai_skills", []) or []),
        "interests_chars": len(str(prefill.get("interests", "") or "")),
    }

    metadata: dict[str, Any] = {
        "language": (language or "en"),
        "created_from": "docx",
        "stage": CVStage.PREPARE.value,
        "stage_updated_at": _now_iso(),
        "prefill_summary": prefill_summary,
        "docx_prefill_unconfirmed": prefill,
        "confirmed_flags": {
            "contact_confirmed": False,
            "education_confirmed": False,
            "confirmed_at": None,
        },
    }
    if job_posting_url:
        metadata["job_posting_url"] = job_posting_url
    if job_posting_text:
        metadata["job_posting_text"] = str(job_posting_text)[:20000]

    try:
        session_id = store.create_session(cv_data, metadata)
        logging.info(f"Session created: {session_id}")
    except Exception as e:
        logging.error(f"Session creation failed: {e}")
        return 500, {"error": "Failed to create session", "details": str(e)}

    if photo_extracted and extracted_photo:
        try:
            blob_store = CVBlobStore()
            ptr = blob_store.upload_photo_bytes(extracted_photo)
            try:
                session = store.get_session(session_id)
                if session:
                    meta2 = session.get("metadata") or {}
                    if isinstance(meta2, dict):
                        meta2 = dict(meta2)
                        meta2["photo_blob"] = {
                            "container": ptr.container,
                            "blob_name": ptr.blob_name,
                            "content_type": ptr.content_type,
                        }
                        store.update_session(session_id, cv_data, meta2)
                        photo_storage = "blob"
            except Exception:
                pass
        except Exception as e:
            logging.warning(f"Photo blob storage failed: {e}")
    elif extract_photo_flag and not photo_extracted:
        photo_omitted_reason = photo_omitted_reason or "no_photo_found_in_docx"

    summary = {
        "has_photo": photo_extracted,
        "fields_populated": [k for k, v in cv_data.items() if v],
        "fields_empty": [k for k, v in cv_data.items() if not v],
    }

    session = store.get_session(session_id)
    return 200, {
        "success": True,
        "session_id": session_id,
        "cv_data_summary": summary,
        "photo_extracted": photo_extracted,
        "photo_storage": photo_storage,
        "photo_omitted_reason": photo_omitted_reason,
        "expires_at": session["expires_at"] if session else None,
    }


def _tool_generate_context_pack_v2(*, session_id: str, phase: str, job_posting_text: str | None, max_pack_chars: int, session: dict) -> tuple[int, dict]:
    if phase not in ["preparation", "confirmation", "execution"]:
        return 400, {"error": "Invalid phase. Must be 'preparation', 'confirmation', or 'execution'"}

    cv_data = session.get("cv_data") or {}
    metadata = session.get("metadata") or {}
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        metadata["session_id"] = session_id

    # Feature flag: use delta mode if enabled
    use_delta = os.environ.get("CV_DELTA_MODE", "1") == "1"
    if use_delta and metadata.get("section_hashes_prev"):
        from src.context_pack import build_context_pack_v2_delta
        pack = build_context_pack_v2_delta(
            phase=phase,
            cv_data=cv_data,
            session_metadata=metadata,
            job_posting_text=job_posting_text,
            max_pack_chars=max_pack_chars,
        )
    else:
        pack = build_context_pack_v2(
            phase=phase,
            cv_data=cv_data,
            job_posting_text=job_posting_text,
            session_metadata=metadata,
            max_pack_chars=max_pack_chars,
        )
    return 200, pack


def _tool_generate_cv_from_session(*, session_id: str, language: str | None, client_context: dict | None, session: dict) -> tuple[int, dict | bytes, str]:
    meta = session.get("metadata") or {}
    cv_data = session.get("cv_data") or {}
    lang = language or (meta.get("language") if isinstance(meta, dict) else None) or "en"

    # Wave 0.1: Execution Latch (Idempotency Check)
    # Check if PDF already exists to prevent duplicate generation
    if os.environ.get("CV_EXECUTION_LATCH", "1").strip() == "1":
        pdf_refs = meta.get("pdf_refs") if isinstance(meta.get("pdf_refs"), dict) else {}
        if pdf_refs:
            # Find most recent PDF
            sorted_refs = sorted(
                pdf_refs.items(),
                key=lambda x: x[1].get("created_at", "") if isinstance(x[1], dict) else "",
                reverse=True
            )
            if sorted_refs:
                latest_ref, latest_info = sorted_refs[0]
                logging.info(
                    f"Execution latch: PDF already exists for session {session_id}, "
                    f"returning existing pdf_ref={latest_ref}"
                )

                pdf_bytes_cached: bytes | None = None
                download_error: str | None = None
                try:
                    container = latest_info.get("container") if isinstance(latest_info, dict) else None
                    blob_name = latest_info.get("blob_name") if isinstance(latest_info, dict) else None
                    if container and blob_name:
                        blob_store = CVBlobStore(container=container)
                        pdf_bytes_cached = blob_store.download_bytes(
                            BlobPointer(container=container, blob_name=blob_name, content_type="application/pdf")
                        )
                    else:
                        download_error = "missing_blob_pointer"
                except Exception as exc:
                    download_error = str(exc)
                    logging.warning(
                        "Execution latch: failed to download cached PDF session_id=%s pdf_ref=%s error=%s",
                        session_id,
                        latest_ref,
                        exc,
                    )

                pdf_metadata = {
                    "pdf_ref": latest_ref,
                    "sha256": latest_info.get("sha256") if isinstance(latest_info, dict) else None,
                    "pdf_size_bytes": latest_info.get("size_bytes") if isinstance(latest_info, dict) else None,
                    "pages": latest_info.get("pages") if isinstance(latest_info, dict) else None,
                    "render_ms": latest_info.get("render_ms") if isinstance(latest_info, dict) else None,
                    "validation_passed": latest_info.get("validation_passed") if isinstance(latest_info, dict) else None,
                    "persisted": True,
                    "download_name": latest_info.get("download_name") if isinstance(latest_info, dict) else None,
                    "from_cache": True,  # Flag for debugging
                    "download_error": download_error,
                }

                # If we successfully fetched cached bytes, return them directly
                if pdf_bytes_cached:
                    return 200, {"pdf_bytes": pdf_bytes_cached, "pdf_metadata": pdf_metadata}, "application/pdf"

                # Fallback: return metadata-only so caller can retry via get_pdf_by_ref
                # Wave 2: Log warning when download_error is set
                if download_error:
                    logging.warning(
                        "Latch fallback: returning metadata-only due to download_error=%s session_id=%s pdf_ref=%s",
                        download_error,
                        session_id,
                        latest_ref,
                    )
                return 200, {
                    "pdf_bytes": None,
                    "pdf_metadata": pdf_metadata,
                    "run_summary": {
                        "stage": "generate_pdf",
                        "latch_engaged": True,
                        "existing_pdf_ref": latest_ref,
                        "download_error": download_error,
                    },
                }, "application/json"

    readiness = _compute_readiness(cv_data, meta if isinstance(meta, dict) else {})
    run_summary = {
        "stage": "generate_pdf",
        "can_generate": readiness.get("can_generate"),
        "required_present": readiness.get("required_present"),
        "confirmed_flags": readiness.get("confirmed_flags"),
    }
    if not readiness.get("can_generate"):
        return (
            400,
            {
                "error": "readiness_not_met",
                "message": "Cannot generate until required fields are present and confirmed.",
                "readiness": readiness,
                "run_summary": run_summary,
            },
            "application/json",
        )

    # Best-effort: record a generation attempt.
    try:
        store = _get_session_store()
        store.append_event(
            session_id,
            {
                "type": "generate_cv_from_session_attempt",
                "language": lang,
                "client_context": client_context if isinstance(client_context, dict) else None,
            },
        )
    except Exception:
        pass

    # Inject photo from Blob at render time.
    try:
        photo_blob = meta.get("photo_blob") if isinstance(meta, dict) else None
        if photo_blob and not cv_data.get("photo_url"):
            ptr = BlobPointer(
                container=photo_blob.get("container", ""),
                blob_name=photo_blob.get("blob_name", ""),
                content_type=photo_blob.get("content_type", "application/octet-stream"),
            )
            if ptr.container and ptr.blob_name:
                data = CVBlobStore(container=ptr.container).download_bytes(ptr)
                b64 = base64.b64encode(data).decode("ascii")
                cv_data = dict(cv_data)
                cv_data["photo_url"] = f"data:{ptr.content_type};base64,{b64}"
    except Exception as e:
        logging.warning(f"Failed to inject photo from blob for session {session_id}: {e}")

    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    if not is_valid:
        return 400, {"error": "CV data validation failed", "validation_errors": errors, "run_summary": run_summary}, "application/json"

    cv_data = normalize_cv_data(cv_data)
    validation_result = validate_cv(cv_data)
    if not validation_result.is_valid:
        return (
            400,
            {"error": "Validation failed", "validation": _serialize_validation_result(validation_result), "run_summary": run_summary},
            "application/json",
        )

    pdf_ref = f"{session_id}-{uuid.uuid4().hex}"
    render_start = time.time()
    try:
        logging.info(f"=== PDF GENERATION START === session_id={session_id}")
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        render_ms = max(1, int((time.time() - render_start) * 1000))
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        pages = count_pdf_pages(pdf_bytes)
        blob_info = _upload_pdf_blob_for_session(session_id=session_id, pdf_ref=pdf_ref, pdf_bytes=pdf_bytes)
        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        metadata = dict(metadata)
        pdf_refs = metadata.get("pdf_refs") if isinstance(metadata.get("pdf_refs"), dict) else {}
        pdf_refs = dict(pdf_refs)
        download_name = _compute_pdf_download_name(cv_data=cv_data, meta=meta)
        pdf_refs[pdf_ref] = {
            "container": blob_info["container"] if blob_info else None,
            "blob_name": blob_info["blob_name"] if blob_info else None,
            "created_at": _now_iso(),
            "sha256": pdf_sha256,
            "size_bytes": len(pdf_bytes),
            "render_ms": render_ms,
            "pages": pages,
            "validation_passed": bool(readiness.get("can_generate")),
            "download_name": download_name,
        }
        metadata["pdf_refs"] = pdf_refs
        # Wave 0.2: Set pdf_generated flag (terminal FSM state)
        metadata["pdf_generated"] = True
        metadata.pop("pdf_failed", None)  # Clear any previous failure
        persisted = False
        persist_error = None
        try:
            persisted = bool(store.update_session(session_id, cv_data, metadata))
        except Exception as exc:
            persist_error = str(exc)
            logging.warning("Failed to persist pdf metadata for session %s (will retry shrink): %s", session_id, exc)
        if not persisted:
            try:
                metadata2 = _shrink_metadata_for_table(metadata)
                persisted = bool(store.update_session(session_id, cv_data, metadata2))
                metadata = metadata2
            except Exception as exc:
                persist_error = str(exc)
                logging.warning("Failed to persist pdf metadata after shrink for session %s: %s", session_id, exc)
        logging.info(
            "=== PDF GENERATION SUCCESS === session_id=%s pdf_ref=%s size=%d bytes render_ms=%d pages=%d",
            session_id,
            pdf_ref,
            len(pdf_bytes),
            render_ms,
            pages,
        )
        
        # Wave 3: Sampled metrics logging (10% sample to avoid spam)
        if hash(session_id) % 10 == 0:
            logging.info(
                "PDF_METRICS_SAMPLE: size_bytes=%d render_ms=%d pages=%d session_id=%s",
                len(pdf_bytes),
                render_ms,
                pages,
                session_id[:8],
            )
        pdf_metadata = {
            "pdf_ref": pdf_ref,
            "sha256": pdf_sha256,
            "pdf_size_bytes": len(pdf_bytes),
            "pages": pages,
            "render_ms": render_ms,
            "validation_passed": bool(readiness.get("can_generate")),
            "persisted": bool(persisted),
            "persist_error": persist_error,
            "download_name": download_name,
        }
        return 200, {"pdf_bytes": pdf_bytes, "pdf_metadata": pdf_metadata}, "application/pdf"
    except Exception as e:
        logging.error(f"=== PDF GENERATION FAILED === session_id={session_id} error={e}")
        # Wave 0.2: Set pdf_failed flag on error
        try:
            store = _get_session_store()
            sess_err = store.get_session(session_id)
            if sess_err:
                meta_err = sess_err.get("metadata") or {}
                meta_err = dict(meta_err) if isinstance(meta_err, dict) else {}
                meta_err["pdf_failed"] = True
                meta_err["pdf_generated"] = False
                store.update_session(session_id, sess_err.get("cv_data") or {}, meta_err)
                logging.info(f"Set pdf_failed=True for session {session_id}")
        except Exception as set_flag_exc:
            logging.warning(f"Failed to set pdf_failed flag for {session_id}: {set_flag_exc}")
        return 500, {"error": "PDF generation failed", "details": str(e), "run_summary": run_summary}, "application/json"


def _upload_pdf_blob_for_session(*, session_id: str, pdf_ref: str, pdf_bytes: bytes) -> dict[str, str] | None:
    container = os.environ.get("STORAGE_CONTAINER_PDFS") or "cv-pdfs"
    blob_name = f"{session_id}/{pdf_ref}.pdf"
    try:
        blob_store = CVBlobStore(container=container)
        pointer = blob_store.upload_bytes(blob_name=blob_name, data=pdf_bytes, content_type="application/pdf")
        return {"container": pointer.container, "blob_name": pointer.blob_name}
    except Exception as exc:
        logging.warning("Failed to upload generated PDF blob session_id=%s error=%s", session_id, exc)
        return None


def _tool_get_pdf_by_ref(*, session_id: str, pdf_ref: str, session: dict) -> tuple[int, dict | bytes, str]:
    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    pdf_refs = metadata.get("pdf_refs") if isinstance(metadata, dict) else None
    if not isinstance(pdf_refs, dict):
        return 404, {"error": "pdf_ref_not_found"}, "application/json"
    info = pdf_refs.get(pdf_ref)
    if not isinstance(info, dict):
        return 404, {"error": "pdf_ref_not_found"}, "application/json"
    container = info.get("container")
    blob_name = info.get("blob_name")
    if not container or not blob_name:
        return 404, {"error": "pdf_blob_pointer_missing"}, "application/json"
    try:
        store = CVBlobStore(container=container)
        data = store.download_bytes(BlobPointer(container=container, blob_name=blob_name, content_type="application/pdf"))
        return 200, data, "application/pdf"
    except FileNotFoundError:
        return 404, {"error": "pdf_blob_missing"}, "application/json"
    except Exception as exc:
        return 500, {"error": "pdf_fetch_failed", "details": str(exc)}, "application/json"


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Health check requested")
    return _json_response({"status": "healthy", "service": "CV Generator API", "version": "1.0"}, status_code=200)


@app.route(route="cv-tool-call-handler", methods=["POST"])
def cv_tool_call_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Single tool dispatcher.

    Request:
      {
        "tool_name": "<tool>",
        "session_id": "<uuid>" (optional for some tools),
        "params": {...}
      }
    """
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON"}, status_code=400)

    tool_name = str(body.get("tool_name") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    params = body.get("params") or {}

    if not tool_name:
        return _json_response({"error": "tool_name is required"}, status_code=400)
    if not isinstance(params, dict):
        return _json_response({"error": "params must be an object"}, status_code=400)

    if tool_name == "cleanup_expired_sessions":
        try:
            store = _get_session_store()
            deleted = store.cleanup_expired()
            return _json_response({"success": True, "tool_name": tool_name, "deleted_count": deleted}, status_code=200)
        except Exception as e:
            return _json_response({"error": "Cleanup failed", "details": str(e)}, status_code=500)

    if tool_name == "extract_and_store_cv":
        docx_base64 = str(params.get("docx_base64") or "")
        language = str(params.get("language") or "en")
        extract_photo_flag = bool(params.get("extract_photo", True))
        job_posting_url = (str(params.get("job_posting_url") or "").strip() or None)
        job_posting_text = (str(params.get("job_posting_text") or "").strip() or None)
        status, payload = _tool_extract_and_store_cv(
            docx_base64=docx_base64,
            language=language,
            extract_photo_flag=extract_photo_flag,
            job_posting_url=job_posting_url,
            job_posting_text=job_posting_text,
        )
        return _json_response(payload, status_code=status)

    if tool_name == "process_cv_orchestrated":
        status, payload = _tool_process_cv_orchestrated(params)
        return _json_response(payload, status_code=status)

    if not session_id:
        return _json_response({"error": "session_id is required"}, status_code=400)

    # Most tools require session lookup; do it once.
    try:
        store = _get_session_store()
        session = store.get_session(session_id)
    except Exception as e:
        return _json_response({"error": "Failed to retrieve session", "details": str(e)}, status_code=500)

    if not session:
        return _json_response({"error": "Session not found or expired"}, status_code=404)

    if tool_name == "get_cv_session":
        client_context = params.get("client_context")
        try:
            store.append_event(
                session_id,
                {"type": "get_cv_session", "client_context": client_context if isinstance(client_context, dict) else None},
            )
        except Exception:
            pass

        cv_data = session.get("cv_data") or {}
        readiness = _compute_readiness(cv_data, session.get("metadata") or {})

        interaction_history: list[dict] = []
        try:
            meta = session.get("metadata") or {}
            events = meta.get("event_log") if isinstance(meta, dict) else None
            if isinstance(events, list):
                for e in events[-80:]:
                    if not isinstance(e, dict):
                        continue
                    if e.get("type") not in ("user_message", "assistant_message"):
                        continue
                    interaction_history.append(
                        {
                            "type": e.get("type"),
                            "at": e.get("at") or e.get("timestamp"),
                            "trace_id": e.get("trace_id"),
                            "stage": e.get("stage"),
                            "text": e.get("text"),
                        }
                    )
        except Exception:
            interaction_history = []
        payload = {
            "success": True,
            "session_id": session_id,
            "cv_data": cv_data,
            "metadata": session.get("metadata"),
            "expires_at": session.get("expires_at"),
            "readiness": readiness,
            "interaction_history": interaction_history,
            "_metadata": {
                "version": session.get("version"),
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
                "content_signature": {
                    "work_exp_count": len(cv_data.get("work_experience", [])) if isinstance(cv_data, dict) else 0,
                    "education_count": len(cv_data.get("education", [])) if isinstance(cv_data, dict) else 0,
                    "profile_length": len(str(cv_data.get("profile", ""))) if isinstance(cv_data, dict) else 0,
                    "skills_count": len(cv_data.get("it_ai_skills", [])) if isinstance(cv_data, dict) else 0,
                },
            },
        }
        return _json_response(payload, status_code=200)

    if tool_name == "update_cv_field":
        try:
            applied = 0
            client_context = params.get("client_context")
            edits = params.get("edits")
            field_path = params.get("field_path")
            value = params.get("value")
            cv_patch = params.get("cv_patch")
            confirm_flags = params.get("confirm")

            is_batch = isinstance(edits, list) and len(edits) > 0
            is_patch = isinstance(cv_patch, dict) and len(cv_patch.keys()) > 0
            if not is_batch and not field_path and not is_patch and not confirm_flags:
                return _json_response({"error": "field_path/value or edits[] or cv_patch or confirm is required"}, status_code=400)

            if isinstance(confirm_flags, dict) and confirm_flags:
                try:
                    meta = session.get("metadata") or {}
                    if isinstance(meta, dict):
                        meta = dict(meta)
                        cf = meta.get("confirmed_flags") or {}
                        if not isinstance(cf, dict):
                            cf = {}
                        cf = dict(cf)
                        for k in ("contact_confirmed", "education_confirmed"):
                            if k in confirm_flags:
                                cf[k] = bool(confirm_flags.get(k))
                        if cf.get("contact_confirmed") and cf.get("education_confirmed") and not cf.get("confirmed_at"):
                            cf["confirmed_at"] = _now_iso()
                        meta["confirmed_flags"] = cf
                        # If the session was created from DOCX, copy unconfirmed prefill into canonical cv_data
                        # once the user confirms. This prevents "confirmed but empty cv_data" cases.
                        cv_data_cur = session.get("cv_data") or {}
                        docx_prefill = meta.get("docx_prefill_unconfirmed")
                        if cf.get("contact_confirmed") or cf.get("education_confirmed"):
                            cv_data_cur, meta, merged = _merge_docx_prefill_into_cv_data_if_needed(
                                cv_data=cv_data_cur,
                                docx_prefill=docx_prefill if isinstance(docx_prefill, dict) else {},
                                meta=meta,
                            )
                            applied += merged
                        store.update_session(session_id, cv_data_cur, meta)
                except Exception:
                    pass

            if is_batch:
                for e in edits:
                    fp = e.get("field_path")
                    if not fp:
                        continue
                    store.update_field(session_id, fp, e.get("value"), client_context=client_context)
                    applied += 1

            if field_path:
                store.update_field(session_id, field_path, value, client_context=client_context)
                applied += 1

            if is_patch:
                for k, v in cv_patch.items():
                    store.update_field(session_id, k, v, client_context=client_context)
                    applied += 1

            # Update section hashes after all field updates
            if applied > 0:
                updated_session = store.get_session(session_id)
                if updated_session:
                    _update_section_hashes_in_metadata(session_id, updated_session.get("cv_data") or {})

            updated_session = store.get_session(session_id)
            if updated_session:
                return _json_response(
                    {
                        "success": True,
                        "session_id": session_id,
                        **({"field_updated": field_path} if (field_path and not is_batch) else {}),
                        **({"edits_applied": applied} if is_batch else {}),
                        "updated_version": updated_session.get("version"),
                        "updated_at": updated_session.get("updated_at"),
                    },
                    status_code=200,
                )
            return _json_response({"success": True, "session_id": session_id, "edits_applied": applied}, status_code=200)
        except Exception as e:
            return _json_response({"error": "Failed to update field", "details": str(e)}, status_code=500)

    if tool_name == "generate_context_pack_v2":
        phase = str(params.get("phase") or "")
        job_posting_text = params.get("job_posting_text")
        try:
            max_pack_chars = int(params.get("max_pack_chars") or 12000)
        except Exception:
            max_pack_chars = 12000
        status, payload = _tool_generate_context_pack_v2(
            session_id=session_id,
            phase=phase,
            job_posting_text=str(job_posting_text) if isinstance(job_posting_text, str) else None,
            max_pack_chars=max_pack_chars,
            session=session,
        )
        return _json_response(payload, status_code=status)

    if tool_name == "cv_session_search":
        q = str(params.get("q") or "")
        try:
            limit = int(params.get("limit", 20))
        except Exception:
            limit = 20
        limit = max(1, min(limit, 50))
        result = _cv_session_search_hits(session=session, q=q, limit=limit)
        return _json_response(
            {
                "success": True,
                "tool_name": tool_name,
                "session_id": session_id,
                "hits": result["hits"],
                "truncated": result["truncated"],
            },
            status_code=200,
        )

    if tool_name == "validate_cv":
        cv_data = session.get("cv_data") or {}
        out = _validate_cv_data_for_tool(cv_data)
        readiness = _compute_readiness(cv_data, session.get("metadata") or {})
        return _json_response(
            {
                "success": True,
                "tool_name": tool_name,
                "session_id": session_id,
                **out,
                "readiness": readiness,
            },
            status_code=200,
        )

    if tool_name == "preview_html":
        inline_css = bool(params.get("inline_css", True))
        cv_data = session.get("cv_data") or {}
        out = _render_html_for_tool(cv_data, inline_css=inline_css)
        return _json_response({"success": True, "tool_name": tool_name, "session_id": session_id, **out}, status_code=200)

    if tool_name == "generate_cv_from_session":
        client_context = params.get("client_context")
        language = str(params.get("language") or "").strip() or None
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id=session_id,
            language=language,
            client_context=client_context if isinstance(client_context, dict) else None,
            session=session,
        )
        if (
            content_type == "application/pdf"
            and isinstance(payload, dict)
            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
        ):
            meta = payload.get("pdf_metadata") if isinstance(payload.get("pdf_metadata"), dict) else {}
            download_name = ""
            if isinstance(meta, dict):
                dn = meta.get("download_name")
                if isinstance(dn, str) and dn.strip():
                    download_name = dn.strip()
            if not download_name:
                download_name = _compute_pdf_download_name(cv_data=session.get("cv_data") or {}, meta=session.get("metadata") or {})
            headers = {"Content-Disposition": f'attachment; filename=\"{download_name}\"'}
            return func.HttpResponse(body=payload["pdf_bytes"], mimetype="application/pdf", status_code=status, headers=headers)
        if isinstance(payload, dict):
            return _json_response(payload, status_code=status)
        return _json_response({"error": "Unexpected payload type"}, status_code=500)

    if tool_name == "export_session_debug":
        if not _is_debug_export_enabled():
            return _json_response({"error": "debug_export_disabled", "hint": "Set CV_ENABLE_DEBUG_EXPORT=1 to enable"}, status_code=403)
        try:
            include_logs = bool(params.get("include_logs", True))
            minutes = int(params.get("minutes", 120) or 120)
            minutes = max(5, min(minutes, 24 * 60))
        except Exception:
            include_logs = True
            minutes = 120
        exported = _export_session_debug_files(session_id=session_id, session=session, include_logs=include_logs, minutes=minutes)
        return _json_response({"success": True, "tool_name": tool_name, "session_id": session_id, **exported}, status_code=200)

    if tool_name == "get_pdf_by_ref":
        pdf_ref = str(params.get("pdf_ref") or "").strip()
        status, payload, content_type = _tool_get_pdf_by_ref(
            session_id=session_id,
            pdf_ref=pdf_ref,
            session=session,
        )
        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)):
            download_name = _compute_pdf_download_name(cv_data=session.get("cv_data") or {}, meta=session.get("metadata") or {})
            try:
                meta = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
                pdf_refs = meta.get("pdf_refs") if isinstance(meta, dict) else None
                if isinstance(pdf_refs, dict):
                    info = pdf_refs.get(pdf_ref)
                    if isinstance(info, dict) and isinstance(info.get("download_name"), str) and info.get("download_name").strip():
                        download_name = str(info.get("download_name")).strip()
            except Exception:
                pass
            headers = {"Content-Disposition": f'attachment; filename=\"{download_name}\"'}
            return func.HttpResponse(body=payload, mimetype="application/pdf", status_code=status, headers=headers)
        if isinstance(payload, dict):
            return _json_response(payload, status_code=status)
        return _json_response({"error": "Unexpected payload type"}, status_code=500)

    return _json_response({"error": "Unknown tool_name", "tool_name": tool_name}, status_code=400)
