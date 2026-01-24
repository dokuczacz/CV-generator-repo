"""
Azure Functions app for CV Generator
Converts Flask endpoints to Azure HTTP triggers
"""

import azure.functions as func
import logging
import json
import base64
import io
from pathlib import Path
from dataclasses import asdict
import sys
from datetime import datetime
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.render import render_pdf, render_html
from src.validator import validate_cv
from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes, extract_first_photo_from_docx_bytes
from src.blob_store import CVBlobStore, BlobPointer
from src.docx_prefill import prefill_cv_from_docx_bytes
from src.normalize import normalize_cv_data
from src.schema_validator import (
    detect_schema_mismatch, 
    validate_canonical_schema,
    build_schema_error_response,
    log_schema_debug_info
)
from typing import Any
from src.session_store import CVSessionStore


def _now_iso():
    return datetime.utcnow().isoformat()


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
    missing = []
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

    hits: list = []

    def _add_hit(source: str, field_path: str, value: Any):
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

    # Contact
    for fp in ["full_name", "email", "phone"]:
        if fp in docx_prefill:
            _add_hit("docx_prefill_unconfirmed", fp, docx_prefill[fp])
        if fp in cv_data:
            _add_hit("cv_data", fp, cv_data.get(fp))

    def _walk_list(lst, base, source):
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


def _serialize_validation_result(validation_result):
    """Convert ValidationResult to JSON-safe dict."""
    return {
        "is_valid": validation_result.is_valid,
        "errors": [asdict(err) for err in validation_result.errors],
        "warnings": validation_result.warnings,
        "estimated_pages": validation_result.estimated_pages,
        "estimated_height_mm": validation_result.estimated_height_mm,
        "details": validation_result.details,
    }


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


def _tool_generate_context_pack_v2(*, session_id: str, phase: str, job_posting_text: str | None, max_pack_chars: int) -> tuple[int, dict]:
    if phase not in ["preparation", "confirmation", "execution"]:
        return 400, {"error": "Invalid phase. Must be 'preparation', 'confirmation', or 'execution'"}

    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        return 500, {"error": "Failed to retrieve session", "details": str(e)}

    if not session:
        return 404, {"error": "Session not found or expired"}

    cv_data = session.get("cv_data") or {}
    metadata = session.get("metadata") or {}
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        metadata["session_id"] = session_id

    from src.context_pack import build_context_pack_v2

    pack = build_context_pack_v2(
        phase=phase,
        cv_data=cv_data,
        job_posting_text=job_posting_text,
        session_metadata=metadata,
        max_pack_chars=max_pack_chars,
    )
    return 200, pack


def _tool_extract_and_store_cv(*, docx_base64: str, language: str, extract_photo_flag: bool, job_posting_url: str | None, job_posting_text: str | None) -> tuple[int, dict]:
    if not docx_base64:
        return 400, {"error": "docx_base64 is required"}

    try:
        docx_bytes = base64.b64decode(docx_base64)
    except Exception as e:
        return 400, {"error": "Invalid base64 encoding", "details": str(e)}

    # Default: start-fresh semantics to avoid stale merges.
    try:
        store = CVSessionStore()
        deleted_sessions = store.delete_all_sessions()
        blob_store = CVBlobStore()
        deleted_blobs = blob_store.purge_all()
        logging.info(f"Reset requested: deleted_sessions={deleted_sessions}, deleted_blobs={deleted_blobs}")
    except Exception as e:
        logging.warning(f"Purge/reset failed (continuing): {e}")
        store = CVSessionStore()

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

    metadata = {
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


def _tool_generate_cv_from_session(*, session_id: str, language: str | None, client_context: dict | None) -> tuple[int, dict | bytes, str]:
    """
    Returns (status, payload, content_type).
    payload is bytes when content_type is application/pdf.
    """
    if not session_id:
        return 400, {"error": "session_id is required"}, "application/json"

    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        logging.error(f"Session retrieval failed: {e}")
        return 500, {"error": "Failed to retrieve session", "details": str(e)}, "application/json"

    if not session:
        return 404, {"error": "Session not found or expired"}, "application/json"

    cv_data = session["cv_data"]
    meta = session.get("metadata") or {}
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

    try:
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

    # If photo stored in Blob, inject it into cv_data as data URI at render time.
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


@app.route(route="cv-tool-call-handler", methods=["POST"])
def cv_tool_call_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Single tool dispatcher for the UI/agent. Keeps the public surface small while allowing new tools.

    Request:
      {
        "tool_name": "cv_session_search",
        "session_id": "<uuid>",
        "params": {...}
      }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(json.dumps({"error": "Invalid JSON"}), mimetype="application/json", status_code=400)

    tool_name = str(body.get("tool_name") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    params = body.get("params") or {}

    if not tool_name:
        return func.HttpResponse(json.dumps({"error": "tool_name is required"}), mimetype="application/json", status_code=400)
    if not isinstance(params, dict):
        return func.HttpResponse(json.dumps({"error": "params must be an object"}), mimetype="application/json", status_code=400)

    # Admin-ish operation: session_id not required.
    if tool_name == "cleanup_expired_sessions":
        try:
            store = CVSessionStore()
            deleted = store.cleanup_expired()
            return func.HttpResponse(
                json.dumps({"success": True, "tool_name": tool_name, "deleted_count": deleted}),
                mimetype="application/json",
                status_code=200,
            )
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Cleanup failed", "details": str(e)}),
                mimetype="application/json",
                status_code=500,
            )

    # Core tool: session_id not required.
    if tool_name == "extract_and_store_cv":
        language = str(params.get("language") or "en")
        extract_photo_flag = bool(params.get("extract_photo", True))
        job_posting_url = (str(params.get("job_posting_url") or "").strip() or None)
        job_posting_text = (str(params.get("job_posting_text") or "").strip() or None)
        docx_base64 = str(params.get("docx_base64") or "")

        status, payload = _tool_extract_and_store_cv(
            docx_base64=docx_base64,
            language=language,
            extract_photo_flag=extract_photo_flag,
            job_posting_url=job_posting_url,
            job_posting_text=job_posting_text,
        )
        return func.HttpResponse(json.dumps(payload, ensure_ascii=False), mimetype="application/json; charset=utf-8", status_code=status)

    if not session_id:
        return func.HttpResponse(json.dumps({"error": "session_id is required"}), mimetype="application/json", status_code=400)

    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
            mimetype="application/json",
            status_code=500,
        )

    if not session:
        return func.HttpResponse(json.dumps({"error": "Session not found or expired"}), mimetype="application/json", status_code=404)

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
        return func.HttpResponse(json.dumps(payload, ensure_ascii=False), mimetype="application/json; charset=utf-8", status_code=200)

    if tool_name == "cv_session_search":
        q = str(params.get("q") or "")
        try:
            limit = int(params.get("limit", 20))
        except Exception:
            limit = 20
        limit = max(1, min(limit, 50))
        result = _cv_session_search_hits(session=session, q=q, limit=limit)
        return func.HttpResponse(
            json.dumps(
                {
                    "success": True,
                    "tool_name": tool_name,
                    "session_id": session_id,
                    "hits": result["hits"],
                    "truncated": result["truncated"],
                }
            ),
            mimetype="application/json",
            status_code=200,
        )

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
        )
        return func.HttpResponse(json.dumps(payload, ensure_ascii=False), mimetype="application/json; charset=utf-8", status_code=status)

    if tool_name == "update_cv_field":
        # Reuse the same request shape as the old endpoint (but tunneled via params).
        req_body = dict(params)
        req_body["session_id"] = session_id
        try:
            applied = 0
            client_context = req_body.get("client_context")
            edits = req_body.get("edits")
            field_path = req_body.get("field_path")
            value = req_body.get("value")
            cv_patch = req_body.get("cv_patch")
            confirm_flags = req_body.get("confirm")

            is_batch = isinstance(edits, list) and len(edits) > 0
            is_patch = isinstance(cv_patch, dict) and len(cv_patch.keys()) > 0
            if not is_batch and not field_path and not is_patch and not confirm_flags:
                return func.HttpResponse(
                    json.dumps({"error": "field_path/value or edits[] or cv_patch or confirm is required"}),
                    mimetype="application/json",
                    status_code=400,
                )

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
                return func.HttpResponse(
                    json.dumps(
                        {
                            "success": True,
                            "session_id": session_id,
                            **({"field_updated": field_path} if (field_path and not is_batch) else {}),
                            **({"edits_applied": applied} if is_batch else {}),
                            "updated_version": updated_session.get("version"),
                            "updated_at": updated_session.get("updated_at"),
                        },
                        ensure_ascii=False,
                    ),
                    mimetype="application/json; charset=utf-8",
                    status_code=200,
                )
            return func.HttpResponse(json.dumps({"success": True, "session_id": session_id, "edits_applied": applied}, ensure_ascii=False), mimetype="application/json; charset=utf-8", status_code=200)
        except Exception as e:
            return func.HttpResponse(json.dumps({"error": "Failed to update field", "details": str(e)}), mimetype="application/json", status_code=500)

    if tool_name == "generate_cv_from_session":
        # We re-use the existing generate endpoint logic by keeping it in-place for now.
        # This branch mirrors its behavior but returns PDF bytes directly.
        try:
            client_context = params.get("client_context")
        except Exception:
            client_context = None
        language = str(params.get("language") or "").strip() or None
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id=session_id,
            language=language,
            client_context=client_context if isinstance(client_context, dict) else None,
        )
        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)):
            return func.HttpResponse(body=payload, mimetype="application/pdf", status_code=status)
        return func.HttpResponse(json.dumps(payload, ensure_ascii=False), mimetype="application/json; charset=utf-8", status_code=status)

    if tool_name == "validate_cv":
        cv_data = (session or {}).get("cv_data") or {}
        out = _validate_cv_data_for_tool(cv_data)
        readiness = _compute_readiness(cv_data, (session or {}).get("metadata") or {})
        return func.HttpResponse(
            json.dumps(
                {
                    "success": True,
                    "tool_name": tool_name,
                    "session_id": session_id,
                    **out,
                    "readiness": readiness,
                }
            ),
            mimetype="application/json",
            status_code=200,
        )

    if tool_name == "preview_html":
        inline_css = params.get("inline_css", True)
        inline_css = bool(inline_css)
        cv_data = (session or {}).get("cv_data") or {}
        out = _render_html_for_tool(cv_data, inline_css=inline_css)
        return func.HttpResponse(
            json.dumps(
                {
                    "success": True,
                    "tool_name": tool_name,
                    "session_id": session_id,
                    **out,
                }
            ),
            mimetype="application/json",
            status_code=200,
        )

    return func.HttpResponse(
        json.dumps({"error": "Unknown tool_name", "tool_name": tool_name}),
        mimetype="application/json",
        status_code=400,
    )


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    logging.info('Health check requested')
    
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "service": "CV Generator API",
            "version": "1.0"
        }),
        mimetype="application/json",
        status_code=200
    )





# Removed public endpoints (now available via /api/cv-tool-call-handler):
# - preview-html (tool_name="preview_html")
# - validate-cv (tool_name="validate_cv")


# Public endpoint removed (use /api/cv-tool-call-handler tool_name="generate_context_pack_v2")
def _legacy_generate_context_pack_v2(req: func.HttpRequest) -> func.HttpResponse:
    """
    Build ContextPackV2 (phase-specific) from session data.
    Returns JSON with phase-appropriate context.

    Request:
        {
            "phase": "preparation|confirmation|execution",
            "session_id": "uuid",
            "job_posting_text": "..." (optional, for Phase 1),
            "max_pack_chars": 12000 (optional)
        }

    Response:
        {
            "schema_version": "cvgen.context_pack.v2",
            "phase": "preparation",
            "preparation": {...},  // Phase-specific context
            "session_id": "uuid",
            "cv_fingerprint": "sha256:..."
        }
    """
    logging.info('Generate Context Pack V2 requested')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400,
        )

    phase = req_body.get("phase")
    if phase not in ["preparation", "confirmation", "execution"]:
        return func.HttpResponse(
            json.dumps({"error": "Invalid phase. Must be 'preparation', 'confirmation', or 'execution'"}),
            mimetype="application/json",
            status_code=400,
        )

    session_id = req_body.get("session_id")
    if not session_id:
        return func.HttpResponse(
            json.dumps({"error": "Missing session_id in request"}),
            mimetype="application/json",
            status_code=400,
        )

    job_posting_text = req_body.get("job_posting_text")
    max_pack_chars = req_body.get("max_pack_chars") or 12000

    try:
        # Load session
        store = CVSessionStore()
        session = store.get_session(session_id)
        if not session:
            return func.HttpResponse(
                json.dumps({"error": "Session not found or expired"}),
                mimetype="application/json",
                status_code=404
            )

        cv_data = session.get("cv_data")
        metadata = session.get("metadata") or {}

        # Add session_id to metadata for context pack
        metadata["session_id"] = session_id

        # Build phase-specific context pack
        from src.context_pack import build_context_pack_v2

        pack = build_context_pack_v2(
            phase=phase,
            cv_data=cv_data,
            job_posting_text=job_posting_text,
            session_metadata=metadata,
            max_pack_chars=max_pack_chars,
        )

        # Log pack size
        pack_str = json.dumps(pack, ensure_ascii=False)
        token_estimate = len(pack_str) // 4  # Rough: 1 token ≈ 4 chars
        logging.info(f"Context pack V2 built for phase {phase}: {token_estimate} tokens (~{len(pack_str)} bytes)")

        if token_estimate > 3000:
            logging.warning(f"Context pack exceeds 3K tokens ({token_estimate})")

        return func.HttpResponse(
            json.dumps(pack, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
            status_code=200,
        )
    except Exception as e:
        logging.error(f"Context pack V2 generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Context pack V2 generation failed", "details": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


# ============================================================================
# PHASE 2: SESSION-BASED ENDPOINTS
# ============================================================================

# Public endpoint removed (use /api/cv-tool-call-handler tool_name="extract_and_store_cv")
def _legacy_extract_and_store_cv(req: func.HttpRequest) -> func.HttpResponse:
    """
    Extract CV data from DOCX and store in session
    
    This endpoint:
    1. Receives DOCX file (base64)
    2. Extracts CV data (using GPT or parsing logic - placeholder for now)
    3. Stores in Azure Table Storage
    4. Returns session_id for subsequent operations
    
    Request:
        {
            "docx_base64": "base64-encoded DOCX",
            "language": "en|de|pl",
            "extract_photo": true|false
        }
    
    Response:
        {
            "session_id": "uuid",
            "cv_data_summary": {...},
            "photo_extracted": true|false,
            "expires_at": "ISO timestamp"
        }
    """
    logging.info('Extract and store CV requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    docx_base64 = req_body.get("docx_base64")
    if not docx_base64:
        return func.HttpResponse(
            json.dumps({"error": "docx_base64 is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    language = req_body.get("language", "en")
    extract_photo_flag = req_body.get("extract_photo", True)
    job_posting_url = (req_body.get("job_posting_url") or "").strip() or None
    job_posting_text = (req_body.get("job_posting_text") or "").strip() or None
    
    try:
        docx_bytes = base64.b64decode(docx_base64)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": "Invalid base64 encoding", "details": str(e)}),
            mimetype="application/json",
            status_code=400
        )
    
    # Default: start-fresh semantics to avoid stale merges.
    purge_flag = True
    if purge_flag:
        try:
            store = CVSessionStore()
            deleted_sessions = store.delete_all_sessions()
            blob_store = CVBlobStore()
            deleted_blobs = blob_store.purge_all()
            logging.info(f"Reset requested: deleted_sessions={deleted_sessions}, deleted_blobs={deleted_blobs}")
        except Exception as e:
            logging.warning(f"Purge/reset failed (continuing): {e}")

    # Extract photo if requested (store in Blob; do not store base64 in Table Storage)
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
    
    # Best-effort extraction of basic CV fields from DOCX (no OpenAI call)
    # We now start sessions EMPTY to avoid stale/legacy data sneaking in.
    # The prefill is kept only as metadata for reference; it is not applied to cv_data.
    prefill = prefill_cv_from_docx_bytes(docx_bytes)

    # Minimal empty structure; the agent/user will populate it explicitly.
    cv_data = {
        "full_name": "",
        "email": "",
        "phone": "",
        "address_lines": [],
        "photo_url": "",
        "birth_date": "",
        "nationality": "",
        "profile": "",
        "work_experience": [],
        "education": [],
        "it_ai_skills": [],
        "languages": [],
        "certifications": [],
        "interests": "",
        "further_experience": [],
        "references": "",
        "language": language
    }
    
    # Store in session
    try:
        store = CVSessionStore()
        metadata = {
            "language": language,
            "source_file": "uploaded.docx",
            "extraction_method": "docx_prefill_v1",
            "event_log": [],
            "confirmed_flags": {
                "contact_confirmed": False,
                "education_confirmed": False,
                "confirmed_at": None,
            },
        }
        # Keep a lightweight summary of prefill (for reference only, not applied).
        try:
            metadata["prefill_summary"] = {
                "full_name_present": bool(prefill.get("full_name")),
                "work_count": len(prefill.get("work_experience", []) or []),
                "education_count": len(prefill.get("education", []) or []),
                "languages_count": len(prefill.get("languages", []) or []),
                "skills_count": len(prefill.get("it_ai_skills", []) or []),
                "profile_chars": len(prefill.get("profile", "") or ""),
            }
        except Exception:
            metadata["prefill_summary"] = {"error": "prefill_summary_failed"}

        # Keep a bounded, unconfirmed prefill snapshot for the agent to re-populate
        # the empty canonical schema explicitly (avoids stale auto-merges).
        try:
            def _bounded_list(items, max_items: int):
                if not isinstance(items, list):
                    return []
                return items[:max_items]

            def _bounded_str(s: Any, max_chars: int):
                if not isinstance(s, str):
                    return ""
                s = s.strip()
                return s[:max_chars]

            metadata["docx_prefill_unconfirmed"] = {
                "full_name": _bounded_str(prefill.get("full_name"), 80),
                "email": _bounded_str(prefill.get("email"), 120),
                "phone": _bounded_str(prefill.get("phone"), 60),
                "address_lines": _bounded_list(prefill.get("address_lines") or [], 3),
                "profile": _bounded_str(prefill.get("profile"), 1200),
                "education": _bounded_list(prefill.get("education") or [], 4),
                "work_experience": _bounded_list(prefill.get("work_experience") or [], 6),
                "languages": _bounded_list(prefill.get("languages") or [], 8),
                "it_ai_skills": _bounded_list(prefill.get("it_ai_skills") or [], 15),
                "interests": _bounded_str(prefill.get("interests"), 800),
                "further_experience": _bounded_list(prefill.get("further_experience") or [], 6),
                "notes": "UNCONFIRMED: extracted from uploaded DOCX. Use only as a reference to explicitly populate cv_data via update_cv_field.",
            }
        except Exception:
            metadata["docx_prefill_unconfirmed"] = {"error": "docx_prefill_unconfirmed_failed"}
        if job_posting_url:
            metadata["job_posting_url"] = job_posting_url
        if job_posting_text:
            # Keep bounded to avoid Table Storage bloat; UI already bounds to 20k as well.
            metadata["job_posting_text"] = job_posting_text[:20000]
        session_id = store.create_session(cv_data, metadata)
    except Exception as e:
        logging.error(f"Session creation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to create session", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    # Store extracted photo in Blob (if any) and record a pointer in session metadata
    if extracted_photo and session_id:
        try:
            blob_store = CVBlobStore()
            ext = "jpg" if extracted_photo.mime == "image/jpeg" else "png" if extracted_photo.mime == "image/png" else "bin"
            blob_name = f"sessions/{session_id}/photo.{ext}"
            ptr = blob_store.upload_bytes(blob_name=blob_name, data=extracted_photo.data, content_type=extracted_photo.mime)
            metadata = dict(metadata)
            metadata["photo_blob"] = {"container": ptr.container, "blob_name": ptr.blob_name, "content_type": ptr.content_type}
            store.update_session(session_id, cv_data, metadata)
            photo_storage = "blob"
        except Exception as e:
            photo_storage = "none"
            photo_omitted_reason = f"photo_blob_store_failed: {e}"
            logging.warning(f"Photo blob storage failed: {e}")
    elif extract_photo_flag and not photo_extracted:
        photo_omitted_reason = photo_omitted_reason or "no_photo_found_in_docx"

    # Build summary for response (avoid sending full data back)
    summary = {
        "has_photo": photo_extracted,
        "fields_populated": [k for k, v in cv_data.items() if v],
        "fields_empty": [k for k, v in cv_data.items() if not v]
    }
    
    session = store.get_session(session_id)
    
    return func.HttpResponse(
        json.dumps({
            "success": True,
            "session_id": session_id,
            "cv_data_summary": summary,
            "photo_extracted": photo_extracted,
            "photo_storage": photo_storage,
            "photo_omitted_reason": photo_omitted_reason,
            "expires_at": session["expires_at"]
        }),
        mimetype="application/json",
        status_code=200
    )


# Public endpoint removed (use /api/cv-tool-call-handler tool_name="get_cv_session")
def _legacy_get_cv_session(req: func.HttpRequest) -> func.HttpResponse:
    """
    Retrieve CV data from session
    
    Request (POST):
        {"session_id": "uuid"}
    
    Or GET with query param:
        ?session_id=uuid
    
    Response:
        {
            "cv_data": {...},
            "metadata": {...},
            "session_id": "uuid",
            "expires_at": "ISO timestamp"
        }
    """
    logging.info('Get CV session requested')
    
    if req.method == "GET":
        session_id = req.params.get("session_id")
    else:
        try:
            req_body = req.get_json()
            session_id = req_body.get("session_id")
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON"}),
                mimetype="application/json",
                status_code=400
            )
    
    if not session_id:
        return func.HttpResponse(
            json.dumps({"error": "session_id is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        logging.error(f"Session retrieval failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    if not session:
        return func.HttpResponse(
            json.dumps({"error": "Session not found or expired"}),
            mimetype="application/json",
            status_code=404
        )
    
    # Include version info and content signature for model to verify data freshness
    cv_data = session["cv_data"]
    readiness = _compute_readiness(cv_data, session.get("metadata") or {})
    version_info = {
        "success": True,
        "session_id": session["session_id"],
        "cv_data": cv_data,
        "metadata": session["metadata"],
        "expires_at": session["expires_at"],
        "readiness": readiness,
        # Include metadata about CV content freshness for debugging
        "_metadata": {
            "version": session.get("version"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "content_signature": {
                "work_exp_count": len(cv_data.get("work_experience", [])),
                "education_count": len(cv_data.get("education", [])),
                "profile_length": len(str(cv_data.get("profile", ""))),
                "skills_count": len(cv_data.get("it_ai_skills", []))
            }
        }
    }

    return func.HttpResponse(
        json.dumps(version_info),
        mimetype="application/json",
        status_code=200
    )


# Public endpoint removed (use /api/cv-tool-call-handler tool_name="update_cv_field")
def _legacy_update_cv_field(req: func.HttpRequest) -> func.HttpResponse:
    """
    Update CV session fields (single, batch edits[], or a single-section cv_patch).

    Request:
        {
            "session_id": "uuid",
            "field_path": "...", "value": ...    // single update
            OR
            "edits": [{"field_path": "...", "value": ...}, ...]  // batch
        }
    """
    logging.info('Update CV field(s) requested')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )

    session_id = req_body.get("session_id")
    client_context = req_body.get("client_context")
    edits = req_body.get("edits")
    field_path = req_body.get("field_path")
    value = req_body.get("value")
    cv_patch = req_body.get("cv_patch")
    confirm_flags = req_body.get("confirm")

    if not session_id:
        return func.HttpResponse(
            json.dumps({"error": "session_id is required"}),
            mimetype="application/json",
            status_code=400
        )

    is_batch = isinstance(edits, list) and len(edits) > 0
    is_patch = isinstance(cv_patch, dict) and len(cv_patch.keys()) > 0
    if not is_batch and not field_path and not is_patch:
        return func.HttpResponse(
            json.dumps({"error": "field_path/value or edits[] or cv_patch is required"}),
            mimetype="application/json",
            status_code=400
        )

    def _preview(val: Any) -> str:
        pv = str(val)[:150] if val is not None else "(None)"
        if isinstance(val, list):
            pv = f"[{len(val)} items]"
        elif isinstance(val, dict):
            pv = f"{{dict with {len(val)} keys}}"
        return pv

    try:
        store = CVSessionStore()
        applied = 0
        metadata_after_confirm = None

        # cv_patch path: allow exactly one top-level section to be replaced/merged
        if is_patch:
            allowed_sections = {
                "profile",
                "work_experience",
                "education",
                "languages",
                "it_ai_skills",
                "further_experience",
                "interests",
                "references",
                "contact",
                "address_lines",
                "email",
                "phone",
                "full_name",
                "nationality",
                "birth_date",
                "certifications",
                "trainings",
                "data_privacy",
            }
            if len(cv_patch.keys()) != 1:
                return func.HttpResponse(
                    json.dumps({"error": "cv_patch must contain exactly one top-level section"}),
                    mimetype="application/json",
                    status_code=400,
                )
            key = next(iter(cv_patch.keys()))
            if key not in allowed_sections:
                return func.HttpResponse(
                    json.dumps({"error": f"cv_patch section '{key}' not allowed"}),
                    mimetype="application/json",
                    status_code=400,
                )

            session = store.get_session(session_id)
            if not session:
                return func.HttpResponse(
                    json.dumps({"error": "Session not found"}),
                    mimetype="application/json",
                    status_code=404
                )

            cv_data = session["cv_data"]
            metadata = session.get("metadata") or {}
            cv_data = dict(cv_data)
            cv_data[key] = cv_patch[key]

            # Validate before persisting
            try:
                log_schema_debug_info(cv_data, context="update-cv-field-cv_patch")
                ok, schema_errors = validate_canonical_schema(cv_data, strict=True)
                if not ok:
                    return func.HttpResponse(
                        json.dumps({"error": "Schema validation failed", "validation_errors": schema_errors}),
                        mimetype="application/json",
                        status_code=400
                    )
                validation_result = validate_cv(cv_data)
                if not validation_result.is_valid:
                    return func.HttpResponse(
                        json.dumps({
                            "error": "Validation failed",
                            "validation": _serialize_validation_result(validation_result),
                        }),
                        mimetype="application/json",
                        status_code=400,
                    )
            except Exception as e:
                return func.HttpResponse(
                    json.dumps({"error": "Validation crashed", "details": str(e)}),
                    mimetype="application/json",
                    status_code=500,
                )

            store.update_session(session_id, cv_data, metadata)
            applied = 1
            logging.info(f"[update-cv-field/cv_patch] replaced section {key} (len={_preview(cv_patch[key])})")

        elif is_batch:
            for edit in edits:
                if not isinstance(edit, dict):
                    continue
                fp = edit.get("field_path")
                if not fp:
                    continue
                val = edit.get("value")
                logging.info(f"[update-cv-field/batch] {fp} <= {_preview(val)}")
                if store.update_field(session_id, fp, val):
                    applied += 1
        else:
            logging.info(f"[update-cv-field] {field_path} <= {_preview(value)}")
            if store.update_field(session_id, field_path, value):
                applied = 1

        # Apply confirmation flags (contact/education) if provided.
        if applied > 0 and isinstance(confirm_flags, dict):
            session = store.get_session(session_id)
            if session:
                metadata = session.get("metadata") or {}
                flags = metadata.get("confirmed_flags") or {}
                if confirm_flags.get("contact") is True:
                    flags["contact_confirmed"] = True
                    flags["confirmed_at"] = _now_iso()
                if confirm_flags.get("education") is True:
                    flags["education_confirmed"] = True
                    flags["confirmed_at"] = flags.get("confirmed_at") or _now_iso()
                metadata["confirmed_flags"] = flags
                metadata_after_confirm = metadata
                store.update_session(session_id, session["cv_data"], metadata)

        # Best-effort: also record client context (stage/seq) for stateless continuity.
        if applied > 0 and isinstance(client_context, dict) and client_context:
            store.append_event(
                session_id,
                {
                    "type": "client_context",
                    "client_context": {
                        "stage": client_context.get("stage"),
                        "stage_seq": client_context.get("stage_seq"),
                        "source": client_context.get("source"),
                    },
                },
            )
    except Exception as e:
        logging.error(f"Field update failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to update field", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )

    if applied == 0:
        return func.HttpResponse(
            json.dumps({"error": "Session not found or no edits applied"}),
            mimetype="application/json",
            status_code=404
        )

    # Get updated session to report back version and timestamp
    try:
        store = CVSessionStore()
        updated_session = store.get_session(session_id)
        if updated_session:
            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "session_id": session_id,
                    **({"field_updated": field_path} if not is_batch else {"edits_applied": applied}),
                    "updated_version": updated_session.get("version"),
                    "updated_at": updated_session.get("updated_at")
                }),
                mimetype="application/json",
                status_code=200
            )
    except Exception:
        pass  # Fall through to default response

    return func.HttpResponse(
        json.dumps({
            "success": True,
            "session_id": session_id,
            **({"field_updated": field_path} if not is_batch else {"edits_applied": applied})
        }),
        mimetype="application/json",
        status_code=200
    )


# Public endpoint removed (use /api/cv-tool-call-handler tool_name="generate_cv_from_session")
def _legacy_generate_cv_from_session(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate PDF from session data
    
    Request:
        {
            "session_id": "uuid",
            "language": "en|de|pl" (optional, uses session metadata if not provided)
        }
    
    Response:
        {
            "success": true,
            "pdf_base64": "...",
            "validation": {...}
        }
    """
    logging.info('Generate CV from session requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    session_id = req_body.get("session_id")
    if not session_id:
        return func.HttpResponse(
            json.dumps({"error": "session_id is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        logging.error(f"Session retrieval failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    if not session:
        return func.HttpResponse(
            json.dumps({"error": "Session not found or expired"}),
            mimetype="application/json",
            status_code=404
        )

    # Best-effort: store that the session was accessed (helps with stateless continuity/debugging).
    try:
        if req.method == "POST":
            req_body = req.get_json()
            client_context = req_body.get("client_context")
        else:
            client_context = None
        store.append_event(
            session_id,
            {
                "type": "get_cv_session",
                "client_context": client_context if isinstance(client_context, dict) else None,
            },
        )
    except Exception:
        pass
    
    cv_data = session["cv_data"]
    language = req_body.get("language") or session["metadata"].get("language", "en")
    client_context = req_body.get("client_context")

    readiness = _compute_readiness(cv_data, session.get("metadata") or {})
    run_summary = {
        "stage": "generate_pdf",
        "can_generate": readiness.get("can_generate"),
        "required_present": readiness.get("required_present"),
        "confirmed_flags": readiness.get("confirmed_flags"),
    }
    if not readiness.get("can_generate"):
        return func.HttpResponse(
            json.dumps({
                "error": "readiness_not_met",
                "message": "Cannot generate until required fields are present and confirmed.",
                "readiness": readiness,
                "run_summary": run_summary,
            }),
            mimetype="application/json",
            status_code=400,
        )

    # Best-effort: record a generation attempt in session metadata (helps stateless continuity/debugging).
    try:
        store = CVSessionStore()
        store.append_event(
            session_id,
            {
                "type": "generate_cv_from_session_attempt",
                "language": language,
                "client_context": client_context if isinstance(client_context, dict) else None,
            },
        )
    except Exception:
        pass

    # Log CV data version and content for debugging staleness issues
    session_version = session.get("version", "unknown")
    work_exp_count = len(cv_data.get("work_experience", []))
    profile_preview = (str(cv_data.get("profile", ""))[:100]).replace("\n", " ")
    logging.info(f"[generate-from-session] Using session version={session_version}, work_exp_count={work_exp_count}, profile_preview={profile_preview}")

    # If photo stored in Blob, inject it into cv_data as data URI at render time.
    # (We keep Table Storage session lean; the HTML template expects photo_url.)
    try:
        metadata = session.get("metadata") or {}
        photo_blob = metadata.get("photo_blob") if isinstance(metadata, dict) else None
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
    
    # Schema validation
    log_schema_debug_info(cv_data, context="generate-from-session")
    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    
    if not is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "CV data validation failed",
                "validation_errors": errors,
                "guidance": "Use update-cv-field to fix missing or invalid fields"
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize and validate
    cv_data = normalize_cv_data(cv_data)
    validation_result = validate_cv(cv_data)
    
    if not validation_result.is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "Validation failed",
                "validation": _serialize_validation_result(validation_result)
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Generate PDF
    try:
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        logging.info(f"PDF generated from session {session_id}: {len(pdf_bytes)} bytes")
        
        # Return raw binary PDF, not base64-encoded JSON
        return func.HttpResponse(
            body=pdf_bytes,
            mimetype="application/pdf",
            status_code=200
        )
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "PDF generation failed", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )


# NOTE: Legacy endpoints removed from the public surface.
#
# The staged workflow is supported via:
# - extract-and-store-cv
# - get-cv-session
# - update-cv-field
# - generate-cv-from-session
# - generate-context-pack-v2
# - cv-tool-call-handler (tool dispatcher)
def _legacy_process_cv_orchestrated(req: func.HttpRequest) -> func.HttpResponse:
    """
    Orchestrated CV processing - single endpoint for full workflow
    
    This endpoint handles the complete CV processing pipeline:
    1. Extract CV data from DOCX (or use existing session)
    2. Apply user edits if provided
    3. Validate CV data
    4. Generate PDF
    
    Request:
        {
            "session_id": "uuid" (optional - reuse existing session),
            "docx_base64": "base64" (required if no session_id),
            "language": "en|de|pl" (optional, default: en),
            "edits": [
                {"field_path": "full_name", "value": "John Doe"},
                {"field_path": "work_experience[0].employer", "value": "Acme"}
            ] (optional),
            "extract_photo": true|false (optional, default: true)
        }
    
    Response:
        {
            "success": true,
            "session_id": "uuid",
            "pdf_base64": "...",
            "validation": {...},
            "cv_data_summary": {...}
        }
    """
    logging.info("Legacy endpoint invoked (removed)")
    return func.HttpResponse(
        json.dumps(
            {
                "error": "endpoint_removed",
                "message": "This endpoint was removed. Use the staged workflow endpoints and the tool dispatcher.",
            }
        ),
        mimetype="application/json",
        status_code=410,
    )
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    session_id = req_body.get("session_id")
    docx_base64 = req_body.get("docx_base64")
    language = req_body.get("language", "en")
    edits = req_body.get("edits", [])
    extract_photo_flag = req_body.get("extract_photo", True)
    job_posting_url = (req_body.get("job_posting_url") or "").strip() or None
    job_posting_text = (req_body.get("job_posting_text") or "").strip() or None
    
    store = CVSessionStore()
    
    # Step 1: Get or create session
    if session_id:
        logging.info(f"Using existing session: {session_id}")
        try:
            session = store.get_session(session_id)
            if not session:
                return func.HttpResponse(
                    json.dumps({"error": "Session not found or expired"}),
                    mimetype="application/json",
                    status_code=404
                )
            cv_data = session["cv_data"]
            metadata = session.get("metadata") or {}
            if job_posting_url:
                metadata["job_posting_url"] = job_posting_url
            if job_posting_text:
                metadata["job_posting_text"] = job_posting_text[:20000]
            if job_posting_url or job_posting_text:
                store.update_session(session_id, cv_data, metadata)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
                mimetype="application/json",
                status_code=500
            )
    elif docx_base64:
        logging.info("Creating new session from DOCX")
        try:
            docx_bytes = base64.b64decode(docx_base64)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Invalid base64 encoding", "details": str(e)}),
                mimetype="application/json",
                status_code=400
            )
        
        # Extract photo (store in Blob after session is created)
        extracted_photo = None
        photo_extracted = False
        photo_storage = "none"
        photo_omitted_reason = None
        if extract_photo_flag:
            try:
                extracted_photo = extract_first_photo_from_docx_bytes(docx_bytes)
                photo_extracted = bool(extracted_photo)
            except Exception as e:
                photo_omitted_reason = f"photo_extraction_failed: {e}"
                logging.warning(f"Photo extraction failed: {e}")
        
        # Best-effort extraction of basic CV fields (no OpenAI call)
        prefill = prefill_cv_from_docx_bytes(docx_bytes)

        # Create minimal CV data (agent will populate via edits)
        cv_data = {
            "full_name": prefill.get("full_name", "") or "",
            "email": prefill.get("email", "") or "",
            "phone": prefill.get("phone", "") or "",
            "address_lines": prefill.get("address_lines", []) or [],
            "photo_url": "",
            "birth_date": "",
            "nationality": "",
            "profile": prefill.get("profile", "") or "",
            "work_experience": prefill.get("work_experience", []) or [],
            "education": prefill.get("education", []) or [],
            "it_ai_skills": prefill.get("it_ai_skills", []) or [],
            "languages": prefill.get("languages", []) or [],
            "certifications": [],
            "interests": prefill.get("interests", "") or "",
            "further_experience": prefill.get("further_experience", []) or [],
            "references": "",
            "language": language
        }
        
        try:
            metadata = {
                "language": language,
                "source_file": "uploaded.docx",
                "confirmed_flags": {
                    "contact_confirmed": False,
                    "education_confirmed": False,
                    "confirmed_at": None,
                },
            }
            if job_posting_url:
                metadata["job_posting_url"] = job_posting_url
            if job_posting_text:
                metadata["job_posting_text"] = job_posting_text[:20000]
            session_id = store.create_session(cv_data, metadata)
            logging.info(f"Created session: {session_id}")
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Failed to create session", "details": str(e)}),
                mimetype="application/json",
                status_code=500
            )

        # Store photo in Blob and persist pointer in metadata
        if extracted_photo and session_id:
            try:
                blob_store = CVBlobStore()
                ext = "jpg" if extracted_photo.mime == "image/jpeg" else "png" if extracted_photo.mime == "image/png" else "bin"
                blob_name = f"sessions/{session_id}/photo.{ext}"
                ptr = blob_store.upload_bytes(blob_name=blob_name, data=extracted_photo.data, content_type=extracted_photo.mime)
                metadata = dict(metadata)
                metadata["photo_blob"] = {"container": ptr.container, "blob_name": ptr.blob_name, "content_type": ptr.content_type}
                store.update_session(session_id, cv_data, metadata)
                photo_storage = "blob"
            except Exception as e:
                photo_storage = "none"
                photo_omitted_reason = f"photo_blob_store_failed: {e}"
                logging.warning(f"Photo blob storage failed: {e}")
        elif extract_photo_flag and not photo_extracted:
            photo_omitted_reason = photo_omitted_reason or "no_photo_found_in_docx"
    else:
        return func.HttpResponse(
            json.dumps({"error": "Either session_id or docx_base64 is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    # Step 2: Apply edits if provided
    if edits:
        logging.info(f"Applying {len(edits)} edits to session {session_id}")
        for edit in edits:
            field_path = edit.get("field_path")
            value = edit.get("value")
            if field_path:
                try:
                    store.update_field(session_id, field_path, value)
                except Exception as e:
                    logging.warning(f"Failed to apply edit to {field_path}: {e}")
        
        # Refresh cv_data after edits
        session = store.get_session(session_id)
        cv_data = session["cv_data"]
    
    # Step 3: Validate
    log_schema_debug_info(cv_data, context="orchestrated")
    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    
    if not is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "CV data validation failed",
                "validation_errors": errors,
                "session_id": session_id,
                "guidance": "Provide edits array to populate missing fields"
            }),
            mimetype="application/json",
            status_code=400
        )
    
    cv_data = normalize_cv_data(cv_data)
    validation_result = validate_cv(cv_data)
    
    if not validation_result.is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "Validation failed",
                "validation": _serialize_validation_result(validation_result),
                "session_id": session_id
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Step 4: Generate PDF
    try:
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        logging.info(f"Orchestrated: Generated PDF ({len(pdf_bytes)} bytes) for session {session_id}")
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        
        summary = {
            "has_photo": bool(cv_data.get("photo_url")),
            "work_experience_count": len(cv_data.get("work_experience", [])),
            "education_count": len(cv_data.get("education", [])),
            "languages": cv_data.get("languages", [])
        }
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "session_id": session_id,
                "pdf_base64": pdf_base64,
                "validation": _serialize_validation_result(validation_result),
                "cv_data_summary": summary,
                "readiness": readiness,
                "run_summary": run_summary,
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Orchestrated: PDF generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "PDF generation failed", "details": str(e), "session_id": session_id}),
            mimetype="application/json",
            status_code=500
        )


def _legacy_cv_session_search(req: func.HttpRequest) -> func.HttpResponse:
    """
    Lightweight search over session data (cv_data, docx_prefill_unconfirmed, recent events).
    Returns bounded previews to avoid token bloat.
    """
    logging.info("Legacy endpoint invoked (removed)")
    return func.HttpResponse(
        json.dumps(
            {
                "error": "endpoint_removed",
                "message": "This endpoint was removed. Use the tool dispatcher (cv-tool-call-handler).",
            }
        ),
        mimetype="application/json",
        status_code=410,
    )
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(json.dumps({"error": "Invalid JSON"}), mimetype="application/json", status_code=400)

    session_id = body.get("session_id")
    q = str(body.get("q") or "").lower().strip()
    section = str(body.get("section") or "").lower().strip()
    try:
        limit = int(body.get("limit", 20))
    except Exception:
        limit = 20
    limit = max(1, min(limit, 50))

    if not session_id:
        return func.HttpResponse(json.dumps({"error": "session_id is required"}), mimetype="application/json", status_code=400)

    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": "Failed to retrieve session", "details": str(e)}), mimetype="application/json", status_code=500)

    if not session:
        return func.HttpResponse(json.dumps({"error": "Session not found or expired"}), mimetype="application/json", status_code=404)

    result = _cv_session_search_hits(session=session, q=q, limit=limit)

    return func.HttpResponse(
        json.dumps({
            "success": True,
            "session_id": session_id,
            "hits": result["hits"],
            "truncated": result["truncated"]
        }),
        mimetype="application/json",
        status_code=200
    )


# Removed public endpoint cleanup-expired-sessions.
# Use /api/cv-tool-call-handler with tool_name="cleanup_expired_sessions" instead.
