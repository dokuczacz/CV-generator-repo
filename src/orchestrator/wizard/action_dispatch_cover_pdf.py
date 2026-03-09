from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from src import product_config
from src.orchestrator.wizard.execution_strategy import resolve_execution_strategy


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
    sync_job_data_table_history: Callable[..., dict]


def handle_cover_pdf_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    trace_id: str,
    stage_now: str,
    language: str | None,
    client_context: dict | None,
    deps: CoverPdfActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    def _ensure_signoff_full_name(block: dict, cv: dict) -> dict:
        out = dict(block or {})
        full_name = str((cv or {}).get("full_name") or "").strip()
        if not full_name:
            return out
        signoff = str(out.get("signoff") or "").strip()
        if not signoff:
            out["signoff"] = full_name
            return out
        if full_name.casefold() in signoff.casefold():
            return out
        out["signoff"] = f"{signoff}\n{full_name}"
        return out

    def _notes_variant(payload: dict | None, meta: dict) -> str:
        payload_val = str((payload or {}).get("cover_letter_notes_variant") or "").strip().lower()
        meta_val = str(meta.get("cover_letter_notes_variant") or "").strip().lower()
        candidate = payload_val or meta_val or "work_plus_cover"
        if candidate not in {"work_plus_cover", "cover_only"}:
            candidate = "work_plus_cover"
        return candidate

    def _is_unified_mode(payload: dict | None, meta: dict) -> bool:
        experiment_mode = str(product_config.EXPERIMENT_MODE or "baseline").strip().lower()
        execution_strategy, _strategy_source = resolve_execution_strategy(payload=payload, meta=meta)
        return execution_strategy == "unified" or experiment_mode == "variant_unified"

    if aid == "WORK_CONFIRM_STAGE":
        meta2 = deps.wizard_set_stage(meta2, "further_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Work experience confirmed. Moving to technical projects.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    
    if aid == "COVER_LETTER_PREVIEW":
        payload = user_action_payload if isinstance(user_action_payload, dict) else {}
        force_regenerate = bool(payload.get("force_regenerate")) if isinstance(payload, dict) else False
        if isinstance(payload, dict) and "cover_letter_tailoring_notes" in payload:
            meta2["cover_letter_tailoring_notes"] = str(payload.get("cover_letter_tailoring_notes") or "").strip()[:2000]
        notes_variant = _notes_variant(payload, meta2)
        meta2["cover_letter_notes_variant"] = notes_variant
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

        # In unified mode, never regenerate CL via OpenAI from this button.
        unified_mode = _is_unified_mode(payload, meta2)
        execution_strategy, _strategy_source = resolve_execution_strategy(payload=payload, meta=meta2)
        meta2["execution_strategy"] = execution_strategy
        if unified_mode:
            if isinstance(meta2.get("cover_letter_block"), dict):
                meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text="Unified mode: reusing cover letter draft from unified output.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Unified mode: cover letter draft is unavailable. Re-run Work tailoring in unified mode.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        # Inline shortcut: reuse unified cover letter draft generated in work stage.
        experiment_mode = str(product_config.EXPERIMENT_MODE or "baseline").strip().lower()
        if (
            (execution_strategy == "unified" or experiment_mode == "variant_unified")
            and not force_regenerate
            and isinstance(meta2.get("cover_letter_block"), dict)
            and str(meta2.get("cover_letter_input_sig") or "").strip()
        ):
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Loaded cover letter draft from unified experiment output.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        input_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "target_lang": target_lang,
                    "job_sig": str(meta2.get("current_job_sig") or ""),
                    "notes_variant": notes_variant,
                    "feedback": str(meta2.get("cover_letter_feedback") or ""),
                    "work_tailoring_notes": str(meta2.get("work_tailoring_notes") or "") if notes_variant != "cover_only" else "",
                    "cover_letter_tailoring_notes": str(meta2.get("cover_letter_tailoring_notes") or ""),
                    "skills_ranking_notes": str(meta2.get("skills_ranking_notes") or ""),
                    "cv_sig": hashlib.sha256(
                        json.dumps(cv_data or {}, ensure_ascii=False, sort_keys=True).encode("utf-8", errors="ignore")
                    ).hexdigest(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8", errors="ignore")
        ).hexdigest()
        if (
            not force_regenerate
            and isinstance(meta2.get("cover_letter_block"), dict)
            and str(meta2.get("cover_letter_input_sig") or "") == input_fingerprint
        ):
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=(
                    "Loaded existing cover letter draft for unchanged CV/job context. "
                    "Edit context or use force regenerate to create a new draft."
                ),
                meta_out=meta2,
                cv_out=cv_data,
            )
    
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
        meta2["cover_letter_input_sig"] = input_fingerprint
        meta2.pop("cover_letter_error", None)
        meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cover letter draft ready.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "COVER_LETTER_BACK":
        meta2 = deps.wizard_set_stage(meta2, "review_final")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Back to PDF generation.", meta_out=meta2, cv_out=cv_data)

    if aid == "JOB_DATA_TABLE_OPEN":
        latest_cv = cv_data
        latest_meta = meta2
        try:
            sess_latest = deps.session_get(session_id) or {}
            if isinstance(sess_latest.get("cv_data"), dict):
                latest_cv = dict(sess_latest.get("cv_data") or {})
            if isinstance(sess_latest.get("metadata"), dict):
                latest_meta = dict(sess_latest.get("metadata") or {})
        except Exception:
            latest_cv = cv_data
            latest_meta = meta2
        try:
            latest_meta = deps.sync_job_data_table_history(
                session_id=session_id,
                cv_data=latest_cv,
                meta=latest_meta,
            )
        except Exception as exc:
            try:
                deps.log_info("JOB_DATA_TABLE_SYNC_FAILED session=%s err=%s", session_id, str(exc)[:240])
            except Exception:
                pass
        latest_meta = deps.wizard_set_stage(latest_meta, "job_data_table")
        cv_data, meta2 = deps.persist(latest_cv, latest_meta)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Job data table is ready.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "JOB_DATA_TABLE_BACK":
        meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Back to Cover Letter.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "COVER_LETTER_FEEDBACK_EDIT":
        meta2 = deps.wizard_set_stage(meta2, "cover_letter_feedback_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Add feedback and click Improve draft.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "COVER_LETTER_FEEDBACK_APPLY":
        payload = user_action_payload if isinstance(user_action_payload, dict) else {}
        if isinstance(payload, dict) and "cover_letter_tailoring_notes" in payload:
            meta2["cover_letter_tailoring_notes"] = str(payload.get("cover_letter_tailoring_notes") or "").strip()[:2000]
        notes_variant = _notes_variant(payload, meta2)
        meta2["cover_letter_notes_variant"] = notes_variant
        feedback_text = ""
        if isinstance(payload, dict):
            feedback_text = str(payload.get("cover_letter_feedback") or "").strip()
        if not feedback_text:
            feedback_text = str(meta2.get("cover_letter_feedback") or "").strip()

        feedback_text = feedback_text[:2000]
        meta2["cover_letter_feedback"] = feedback_text
        meta2["cover_letter_feedback_applied_at"] = deps.now_iso()

        if _is_unified_mode(payload, meta2):
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Unified mode: draft improvement via separate OpenAI call is disabled.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        capsule_context = {
            "job_reference": meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else {},
            "cover_letter_block": meta2.get("cover_letter_block") if isinstance(meta2.get("cover_letter_block"), dict) else {},
            "work_experience": cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else [],
            "work_tailoring_notes": str(meta2.get("work_tailoring_notes") or "")[:2000] if notes_variant != "cover_only" else "",
            "cover_letter_tailoring_notes": str(meta2.get("cover_letter_tailoring_notes") or "")[:2000],
            "cover_letter_notes_variant": notes_variant,
            "feedback": feedback_text,
        }
        meta2["cover_letter_feedback_capsule"] = capsule_context

        target_lang = str(meta2.get("target_language") or meta2.get("language") or language or "en").strip().lower()
        allowed_langs = {"en", "de"}
        if target_lang not in allowed_langs:
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Cover letter is available only for English (EN) or German (DE) for now.",
                meta_out=meta2,
                cv_out=cv_data,
            )
        if not deps.cv_enable_cover_letter or not deps.openai_enabled():
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="AI is not configured. Cover letter improvement is unavailable.",
                meta_out=meta2,
                cv_out=cv_data,
            )

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
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=deps.friendly_schema_error_message(str(err_cl)),
                meta_out=meta2,
                cv_out=cv_data,
            )

        meta2["cover_letter_block"] = cl_block
        meta2.pop("cover_letter_error", None)
        meta2.pop("cover_letter_error_details", None)
        meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Cover letter draft improved.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    
    if aid == "COVER_LETTER_GENERATE":
        # Always regenerate cover letter from current CV state.
        payload = user_action_payload if isinstance(user_action_payload, dict) else {}
        force_regenerate = bool(payload.get("force_regenerate")) if isinstance(payload, dict) else False
        if isinstance(payload, dict) and "cover_letter_tailoring_notes" in payload:
            meta2["cover_letter_tailoring_notes"] = str(payload.get("cover_letter_tailoring_notes") or "").strip()[:2000]
        notes_variant = _notes_variant(payload, meta2)
        meta2["cover_letter_notes_variant"] = notes_variant
        target_lang = str(meta2.get("target_language") or meta2.get("language") or language or "en").strip().lower()
        allowed_langs = {"en", "de"}
        try:
            deps.log_info(
                "COVER_ACTION aid=%s session=%s stage_before=%s target_lang=%s mode=reuse_or_regenerate",
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

        unified_mode = _is_unified_mode(payload, meta2)

        input_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "target_lang": target_lang,
                    "job_sig": str(meta2.get("current_job_sig") or ""),
                    "notes_variant": notes_variant,
                    "feedback": str(meta2.get("cover_letter_feedback") or ""),
                    "work_tailoring_notes": str(meta2.get("work_tailoring_notes") or "") if notes_variant != "cover_only" else "",
                    "cover_letter_tailoring_notes": str(meta2.get("cover_letter_tailoring_notes") or ""),
                    "skills_ranking_notes": str(meta2.get("skills_ranking_notes") or ""),
                    "cv_sig": hashlib.sha256(
                        json.dumps(cv_data or {}, ensure_ascii=False, sort_keys=True).encode("utf-8", errors="ignore")
                    ).hexdigest(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8", errors="ignore")
        ).hexdigest()

        existing_pdf_ref = str(meta2.get("cover_letter_pdf_ref") or "")
        pdf_refs = meta2.get("pdf_refs") if isinstance(meta2.get("pdf_refs"), dict) else {}
        reuse_existing_pdf_artifact = bool(
            (not force_regenerate)
            and existing_pdf_ref
            and isinstance(pdf_refs.get(existing_pdf_ref), dict)
            and str(meta2.get("cover_letter_pdf_input_sig") or "") == input_fingerprint
        )
    
        if unified_mode:
            if isinstance(meta2.get("cover_letter_block"), dict):
                cl = dict(meta2.get("cover_letter_block") or {})
            else:
                meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text="Unified mode: missing cover letter draft. Re-run Work tailoring in unified mode.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )
        elif reuse_existing_pdf_artifact and isinstance(meta2.get("cover_letter_block"), dict):
            cl = dict(meta2.get("cover_letter_block") or {})
        elif (
            not force_regenerate
            and isinstance(meta2.get("cover_letter_block"), dict)
            and str(meta2.get("cover_letter_input_sig") or "") == input_fingerprint
        ):
            cl = dict(meta2.get("cover_letter_block") or {})
        else:
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
            meta2["cover_letter_input_sig"] = input_fingerprint
        cl = _ensure_signoff_full_name(cl, cv_data)
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
            render_start = time.time()
            pdf_bytes = deps.render_cover_letter_pdf(payload, enforce_one_page=True, use_cache=False)
        except Exception as e:
            meta2["cover_letter_error"] = str(e)[:400]
            meta2 = deps.wizard_set_stage(meta2, "cover_letter_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=str(e)[:400], meta_out=meta2, cv_out=cv_data)
    
        pdf_ref = f"cover_letter_{uuid.uuid4().hex[:10]}"
        render_ms = max(1, int((time.time() - render_start) * 1000))
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        target_lang = str(target_lang or meta2.get("target_language") or meta2.get("language") or "").strip().lower()
        job_sig = str(meta2.get("current_job_sig") or "").strip()
        blob_ptr = deps.upload_pdf_blob_for_session(session_id=session_id, pdf_ref=pdf_ref, pdf_bytes=pdf_bytes)
        pdf_refs = meta2.get("pdf_refs") if isinstance(meta2.get("pdf_refs"), dict) else {}
        pdf_refs = dict(pdf_refs or {})
        pdf_refs[pdf_ref] = {
            "kind": "cover_letter",
            "container": (blob_ptr or {}).get("container"),
            "blob_name": (blob_ptr or {}).get("blob_name"),
            "download_name": deps.compute_cover_letter_download_name(cv_data=cv_data, meta=meta2),
            "created_at": deps.now_iso(),
            "sha256": pdf_sha256,
            "size_bytes": len(pdf_bytes),
            "render_ms": render_ms,
            "target_language": target_lang,
            "job_sig": job_sig,
        }
        meta2["pdf_refs"] = pdf_refs
        meta2["cover_letter_pdf_ref"] = pdf_ref
        meta2["cover_letter_pdf_input_sig"] = input_fingerprint
        meta2.pop("cover_letter_error", None)
        meta2.pop("cover_letter_error_details", None)
        try:
            meta2 = deps.sync_job_data_table_history(
                session_id=session_id,
                cv_data=cv_data,
                meta=meta2,
            )
        except Exception as exc:
            try:
                deps.log_info("COVER_LETTER_HISTORY_SYNC_FAILED session=%s err=%s", session_id, str(exc)[:240])
            except Exception:
                pass
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
        cc_download = dict(client_context) if isinstance(client_context, dict) else {}
        cc_download["pdf_action"] = "download_only"
        status, payload, content_type = deps.tool_generate_cv_from_session(
            session_id=session_id,
            language=language,
            client_context=cc_download,
            session=deps.session_get(session_id) or {"cv_data": cv_data, "metadata": meta2},
        )
        
        if (
            status == 200
            and content_type == "application/pdf"
            and isinstance(payload, dict)
            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
        ):
            pdf_bytes = bytes(payload["pdf_bytes"])
            sess_after = deps.session_get(session_id) or {}
            meta_after = sess_after.get("metadata") if isinstance(sess_after.get("metadata"), dict) else meta2
            cv_after = sess_after.get("cv_data") if isinstance(sess_after.get("cv_data"), dict) else cv_data
            current_stage_after = str(deps.wizard_get_stage(meta_after) or "").strip().lower()
            if current_stage_after == "review_final" and deps.cv_enable_cover_letter and deps.openai_enabled():
                meta_after = deps.wizard_set_stage(dict(meta_after or {}), "cover_letter_review")
            cv_data, meta2 = deps.persist(dict(cv_after or {}), dict(meta_after or {}))
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="PDF is ready. You can download it now.",
                meta_out=meta2,
                cv_out=cv_data,
                pdf_bytes=pdf_bytes,
            )
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
        effective_language = str(meta2.get("target_language") or meta2.get("language") or language or "en").strip().lower() or "en"
        unified_mode = _is_unified_mode(user_action_payload if isinstance(user_action_payload, dict) else None, meta2)
    
        def _try_generate(*, force_regen: bool) -> tuple[int, dict | bytes, str]:
            cc = client_context if isinstance(client_context, dict) else {}
            cc = dict(cc or {})
            cc["pdf_action"] = "generate"
            if force_regen:
                cc["force_pdf_regen"] = True
            return deps.tool_generate_cv_from_session(
                session_id=session_id,
                language=effective_language,
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
        elif not unified_mode:
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
            # Unified mode skips force-regenerate retry; surface the first-attempt error.
            err = None
            if isinstance(payload, dict):
                err = payload.get("error") or payload.get("message") or payload.get("details")
            meta2 = deps.wizard_set_stage(meta2, "review_final")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=str(err or "PDF generation did not return valid bytes.")[:400],
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

