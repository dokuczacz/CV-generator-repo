from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import azure.functions as func


def handle_health_check(
    *,
    json_response: Callable[..., func.HttpResponse],
    log_info: Callable[[str], None],
) -> func.HttpResponse:
    log_info("Health check requested")
    return json_response({"status": "healthy", "service": "CV Generator API", "version": "1.0"}, status_code=200)


@dataclass(frozen=True)
class EntryPointDeps:
    json_response: Callable[..., func.HttpResponse]
    get_session_store: Callable[[], Any]
    tool_extract_and_store_cv: Callable[..., tuple[int, dict]]
    tool_process_cv_orchestrated: Callable[[dict], tuple[int, dict]]
    compute_readiness: Callable[[dict, dict], dict]
    now_iso: Callable[[], str]
    merge_docx_prefill_into_cv_data_if_needed: Callable[..., tuple[dict, dict, int]]
    update_section_hashes_in_metadata: Callable[[str, dict], None]
    tool_generate_context_pack_v2: Callable[..., tuple[int, dict]]
    cv_session_search_hits: Callable[..., dict]
    validate_cv_data_for_tool: Callable[[dict], dict]
    render_html_for_tool: Callable[..., dict]
    tool_generate_cv_from_session: Callable[..., tuple[int, dict | bytes, str]]
    compute_pdf_download_name: Callable[..., str]
    tool_generate_cover_letter_from_session: Callable[..., tuple[int, dict | bytes, str]]
    compute_cover_letter_download_name: Callable[..., str]
    is_debug_export_enabled: Callable[[], bool]
    export_session_debug_files: Callable[..., dict]
    tool_get_pdf_by_ref: Callable[..., tuple[int, dict | bytes, str]]

def handle_cv_tool_call(req: func.HttpRequest, *, deps: EntryPointDeps) -> func.HttpResponse:
    """
    Single tool dispatcher.

    Request:
      {
        "tool_name": "<tool>",
        "session_id": "<uuid>" (optional for some tools),
        "params": {...}
      }
    """
    _json_response = deps.json_response
    _get_session_store = deps.get_session_store
    _tool_extract_and_store_cv = deps.tool_extract_and_store_cv
    _tool_process_cv_orchestrated = deps.tool_process_cv_orchestrated
    _compute_readiness = deps.compute_readiness
    _now_iso = deps.now_iso
    _merge_docx_prefill_into_cv_data_if_needed = deps.merge_docx_prefill_into_cv_data_if_needed
    _update_section_hashes_in_metadata = deps.update_section_hashes_in_metadata
    _tool_generate_context_pack_v2 = deps.tool_generate_context_pack_v2
    _cv_session_search_hits = deps.cv_session_search_hits
    _validate_cv_data_for_tool = deps.validate_cv_data_for_tool
    _render_html_for_tool = deps.render_html_for_tool
    _tool_generate_cv_from_session = deps.tool_generate_cv_from_session
    _compute_pdf_download_name = deps.compute_pdf_download_name
    _tool_generate_cover_letter_from_session = deps.tool_generate_cover_letter_from_session
    _compute_cover_letter_download_name = deps.compute_cover_letter_download_name
    _is_debug_export_enabled = deps.is_debug_export_enabled
    _export_session_debug_files = deps.export_session_debug_files
    _tool_get_pdf_by_ref = deps.tool_get_pdf_by_ref
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
        getter = getattr(store, "get_session_with_blob_retrieval", None)
        if callable(getter):
            session = getter(session_id)
        else:
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
                                keys_to_merge=[
                                    "full_name",
                                    "email",
                                    "phone",
                                    "address_lines",
                                    "profile",
                                    "work_experience",
                                    "education",
                                    "languages",
                                    "interests",
                                    "references",
                                ],
                                clear_prefill=False,
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

    if tool_name == "generate_cover_letter_from_session":
        language = str(params.get("language") or "").strip() or None
        status, payload, content_type = _tool_generate_cover_letter_from_session(
            session_id=session_id,
            language=language,
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
                download_name = _compute_cover_letter_download_name(cv_data=session.get("cv_data") or {}, meta=session.get("metadata") or {})
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

