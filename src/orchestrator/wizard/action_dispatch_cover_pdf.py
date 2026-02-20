from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CoverPdfActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    cv_enable_cover_letter: bool
    log_info: Callable[..., Any]
    openai_enabled: Callable[[], bool]
    generate_cover_letter_block_via_openai: Callable[..., tuple[bool, dict | None, str | None]]
    friendly_schema_error_message: Callable[[str], str]
    validate_cover_letter_block: Callable[..., tuple[bool, list[str]]]
    build_cover_letter_render_payload: Callable[..., dict]
    render_cover_letter_pdf: Callable[..., bytes]
    upload_pdf_blob_for_session: Callable[..., dict | None]
    compute_cover_letter_download_name: Callable[..., str]
    now_iso: Callable[[], str]
    wizard_get_stage: Callable[[dict], str]
    tool_generate_cv_from_session: Callable[..., tuple[int, dict | bytes, str]]
    session_get: Callable[[str], dict | None]


def handle_cover_pdf_actions(
    *,
    aid: str,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    trace_id: str,
    stage_now: str,
    language: str | None,
    client_context: dict | None,
    deps: CoverPdfActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | tuple[int, dict, str] | None]:
    if aid == "WORK_CONFIRM_STAGE":
        meta2 = deps.wizard_set_stage(meta2, "further_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Work experience confirmed. Moving to technical projects.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    
    if aid == "COVER_LETTER_PREVIEW":
        target_lang = str(meta2.get("target_language") or meta2.get("language") or language or "en").strip().lower()
        allowed_langs = {"en", "de"}
        try:
            deps.log_info(
                "COVER_ACTION aid=%s session=%s stage_before=%s target_lang=%s",
                aid,
                session_id,
                stage_now,
                target_lang,
            )
        except Exception:
            pass
        if not deps.cv_enable_cover_letter:
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cover letter is disabled.", meta_out=meta2, cv_out=cv_data)
        if target_lang not in allowed_langs:
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cover letter is available only for English (EN) or German (DE) for now.", meta_out=meta2, cv_out=cv_data)
        if not deps.openai_enabled():
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="AI is not configured. Cover letter generation is unavailable.", meta_out=meta2, cv_out=cv_data)
    
        ok_cl, cl_block, err_cl = deps.generate_cover_letter_block_via_openai(
            cv_data=cv_data,
            meta=meta2,
            trace_id=trace_id,
            session_id=session_id,
            target_language=target_lang,
        )
        if not ok_cl or not isinstance(cl_block, dict):
            meta2["cover_letter_error"] = str(err_cl)[:400]
            meta2 = deps.wizard_set_stage(meta2, "review_final")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=deps.friendly_schema_error_message(str(err_cl)), meta_out=meta2, cv_out=cv_data)
    
        meta2["cover_letter_block"] = cl_block
        meta2.pop("cover_letter_error", None)
        meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cover letter draft ready.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "COVER_LETTER_BACK":
        meta2 = deps.wizard_set_stage(meta2, "review_final")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Back to PDF generation.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "COVER_LETTER_GENERATE":
        # Always regenerate cover letter from current CV state.
        target_lang = str(meta2.get("target_language") or meta2.get("language") or language or "en").strip().lower()
        allowed_langs = {"en", "de"}
        try:
            deps.log_info(
                "COVER_ACTION aid=%s session=%s stage_before=%s target_lang=%s mode=always_regenerate",
                aid,
                session_id,
                stage_now,
                target_lang,
            )
        except Exception:
            pass
        if target_lang not in allowed_langs:
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Cover letter is available only for English (EN) or German (DE) for now.",
                meta_out=meta2,
                cv_out=cv_data,
            )
        if not deps.cv_enable_cover_letter:
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cover letter is disabled.", meta_out=meta2, cv_out=cv_data)
        if not deps.openai_enabled():
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="AI is not configured. Cover letter generation is unavailable.", meta_out=meta2, cv_out=cv_data)
    
        ok_cl, cl_block, err_cl = deps.generate_cover_letter_block_via_openai(
            cv_data=cv_data,
            meta=meta2,
            trace_id=trace_id,
            session_id=session_id,
            target_language=target_lang,
        )
        if not ok_cl or not isinstance(cl_block, dict):
            meta2["cover_letter_error"] = str(err_cl)[:400]
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=deps.friendly_schema_error_message(str(err_cl)), meta_out=meta2, cv_out=cv_data)
        cl = cl_block
        meta2["cover_letter_block"] = cl
    
        ok2, errs2 = deps.validate_cover_letter_block(block=cl, cv_data=cv_data)
        if not ok2:
            meta2["cover_letter_error"] = "Validation failed"
            meta2["cover_letter_error_details"] = errs2[:8]
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Validation failed: " + "; ".join(errs2[:4]), meta_out=meta2, cv_out=cv_data)
    
        try:
            payload = deps.build_cover_letter_render_payload(cv_data=cv_data, meta=meta2, block=cl)
            pdf_bytes = deps.render_cover_letter_pdf(payload, enforce_one_page=True, use_cache=False)
        except Exception as e:
            meta2["cover_letter_error"] = str(e)[:400]
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=str(e)[:400], meta_out=meta2, cv_out=cv_data)
    
        pdf_ref = f"cover_letter_{uuid.uuid4().hex[:10]}"
        blob_ptr = deps.upload_pdf_blob_for_session(session_id=session_id, pdf_ref=pdf_ref, pdf_bytes=pdf_bytes)
        pdf_refs = meta2.get("pdf_refs") if isinstance(meta2.get("pdf_refs"), dict) else {}
        pdf_refs = dict(pdf_refs or {})
        pdf_refs[pdf_ref] = {
            "kind": "cover_letter",
            "container": (blob_ptr or {}).get("container"),
            "blob_name": (blob_ptr or {}).get("blob_name"),
            "download_name": deps.compute_cover_letter_download_name(cv_data=cv_data, meta=meta2),
            "created_at": deps.now_iso(),
        }
        meta2["pdf_refs"] = pdf_refs
        meta2["cover_letter_pdf_ref"] = pdf_ref
        meta2.pop("cover_letter_error", None)
        meta2.pop("cover_letter_error_details", None)
        meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
        try:
            deps.log_info(
                "COVER_ACTION_RESULT aid=%s session=%s stage_after=%s pdf_ref=%s",
                aid,
                session_id,
                deps.wizard_get_stage(meta2),
                pdf_ref,
            )
        except Exception:
            pass
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cover letter PDF generated.", meta_out=meta2, cv_out=cv_data, pdf_bytes=pdf_bytes)
    
    if aid == "DOWNLOAD_PDF":
        # Download previously generated PDF (no regeneration)
        status, payload, content_type = deps.tool_generate_cv_from_session(
            session_id=session_id,
            language=language,
            client_context=client_context,
            session=store.get_session_with_blob_retrieval(session_id) or {"cv_data": cv_data, "metadata": meta2},
        )
        
        if (
            status == 200
            and content_type == "application/pdf"
            and isinstance(payload, dict)
            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
        ):
            pdf_bytes = bytes(payload["pdf_bytes"])
            return True, cv_data, meta2, (200, {"success": True, "pdf_bytes": pdf_bytes, "trace_id": trace_id}, "application/pdf")
        else:
            # PDF not available - fallback to error response
            err_msg = "PDF not yet generated or unavailable"
            if isinstance(payload, dict) and payload.get("error"):
                err_msg = str(payload.get("error"))[:400]
            meta2 = deps.wizard_set_stage(meta2, "review_final")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=err_msg, meta_out=meta2, cv_out=cv_data)
    
    if aid == "REQUEST_GENERATE_PDF":
        # Generate on first click (avoid the "clicked but nothing happened" UX).
    
        def _try_generate(*, force_regen: bool) -> tuple[int, dict | bytes, str]:
            cc = client_context if isinstance(client_context, dict) else {}
            if force_regen:
                cc = dict(cc or {})
                cc["force_pdf_regen"] = True
            return deps.tool_generate_cv_from_session(
                session_id=session_id,
                language=language,
                client_context=cc,
                session=deps.session_get(session_id) or {"cv_data": cv_data, "metadata": meta2},
            )
    
        pdf_bytes = None
        status, payload, content_type = _try_generate(force_regen=False)
        if (
            status == 200
            and content_type == "application/pdf"
            and isinstance(payload, dict)
            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
        ):
            pdf_bytes = bytes(payload["pdf_bytes"])
        else:
            # If we hit the execution latch but couldn't download cached bytes, force a regeneration.
            status, payload, content_type = _try_generate(force_regen=True)
            if (
                status == 200
                and content_type == "application/pdf"
                and isinstance(payload, dict)
                and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
            ):
                pdf_bytes = bytes(payload["pdf_bytes"])
            else:
                # Keep the wizard on the final step and return an actionable error.
                err = None
                if isinstance(payload, dict):
                    err = payload.get("error") or payload.get("details")
                    v = payload.get("validation") if isinstance(payload.get("validation"), dict) else None
                    if v and isinstance(v.get("errors"), list) and v.get("errors"):
                        # Show top errors (field + suggestion) to make the next action obvious.
                        parts = []
                        for e in v.get("errors", [])[:3]:
                            if not isinstance(e, dict):
                                continue
                            field = str(e.get("field") or "").strip()
                            msg = str(e.get("message") or "").strip()
                            sug = str(e.get("suggestion") or "").strip()
                            line = msg or field or "validation_error"
                            if field and field not in line:
                                line = f"{field}: {line}"
                            if sug:
                                line = f"{line} | suggestion: {sug}"
                            parts.append(line)
                        if parts:
                            err = (err or "Validation failed") + "\n" + "\n".join(parts)
                    pm = payload.get("pdf_metadata") if isinstance(payload.get("pdf_metadata"), dict) else None
                    if pm and pm.get("download_error"):
                        err = f"{err or 'PDF generation failed'} (download_error={pm.get('download_error')})"
                meta_after = deps.session_get(session_id) or {}
                meta_after = meta_after.get("metadata") if isinstance(meta_after.get("metadata"), dict) else meta2
                meta2_final = deps.wizard_set_stage(meta_after, "review_final")
                cv_data, meta2_final = deps.persist(cv_data, meta2_final)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=str(err or "PDF generation failed")[:400],
                    meta_out=meta2_final,
                    cv_out=cv_data,
                )
    
        # IMPORTANT: _tool_generate_cv_from_session persists pdf_refs/pdf_generated.
        # Reload latest metadata and only adjust wizard_stage, to avoid overwriting new PDF metadata with stale meta2.
        if pdf_bytes is None:
            # PDF generation failed - shouldn't reach here (should return error above), but safety check.
            meta2 = deps.wizard_set_stage(meta2, "review_final")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="PDF generation did not return valid bytes.",
                meta_out=meta2,
                cv_out=cv_data,
            )
        
        sess_after = deps.session_get(session_id) or {}
        meta_after = sess_after.get("metadata") if isinstance(sess_after.get("metadata"), dict) else meta2
        cv_after = sess_after.get("cv_data") if isinstance(sess_after.get("cv_data"), dict) else cv_data
        
        # Move to cover letter stage if enabled, else stay on review_final.
        cover_enabled = deps.cv_enable_cover_letter
        
        next_stage = "cover_letter_review" if (cover_enabled and deps.openai_enabled()) else "review_final"
        meta_after = deps.wizard_set_stage(dict(meta_after or {}), next_stage)
        cv_data, meta2 = deps.persist(dict(cv_after or {}), meta_after)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="PDF generated.", meta_out=meta2, cv_out=cv_data, pdf_bytes=pdf_bytes)
    
    
    return False, cv_data, meta2, None

