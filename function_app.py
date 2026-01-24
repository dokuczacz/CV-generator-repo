"""
Azure Functions app for CV Generator.

Public surface area (intentionally minimal):
  - GET  /api/health
  - POST /api/cv-tool-call-handler

All workflow operations are routed through the tool dispatcher to keep the API surface small and the UI thin.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import azure.functions as func

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.blob_store import BlobPointer, CVBlobStore
from src.context_pack import build_context_pack_v2
from src.docx_photo import extract_first_photo_from_docx_bytes
from src.docx_prefill import prefill_cv_from_docx_bytes
from src.normalize import normalize_cv_data
from src.render import render_html, render_pdf
from src.schema_validator import validate_canonical_schema
from src.session_store import CVSessionStore
from src.validator import validate_cv


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


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
        "confirmed_flags": {
            "contact_confirmed": contact_ok,
            "education_confirmed": education_ok,
            "confirmed_at": confirmed_flags.get("confirmed_at"),
        },
        "missing": missing,
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
    # Best-effort: cleanup expired sessions to keep local dev storage tidy.
    store = CVSessionStore()
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
        store = CVSessionStore()
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

    try:
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        logging.info(f"PDF generated from session {session_id}: {len(pdf_bytes)} bytes")
        return 200, pdf_bytes, "application/pdf"
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return 500, {"error": "PDF generation failed", "details": str(e), "run_summary": run_summary}, "application/json"


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
            store = CVSessionStore()
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

    if not session_id:
        return _json_response({"error": "session_id is required"}, status_code=400)

    # Most tools require session lookup; do it once.
    try:
        store = CVSessionStore()
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
        payload = {
            "success": True,
            "session_id": session_id,
            "cv_data": cv_data,
            "metadata": session.get("metadata"),
            "expires_at": session.get("expires_at"),
            "readiness": readiness,
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
                        store.update_session(session_id, (session.get("cv_data") or {}), meta)
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
        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)):
            return func.HttpResponse(body=payload, mimetype="application/pdf", status_code=status)
        if isinstance(payload, dict):
            return _json_response(payload, status_code=status)
        return _json_response({"error": "Unexpected payload type"}, status_code=500)

    return _json_response({"error": "Unknown tool_name", "tool_name": tool_name}, status_code=400)
