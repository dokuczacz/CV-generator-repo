from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ExtractStoreToolDeps:
    get_session_store: Callable[[], Any]
    cleanup_expired_once: Callable[[Any], None]
    extract_first_photo_from_docx_bytes: Callable[[bytes], bytes | None]
    prefill_cv_from_docx_bytes: Callable[[bytes], dict]
    now_iso: Callable[[], str]
    looks_like_job_posting_text: Callable[[str], tuple[bool, str]]
    fetch_text_from_url: Callable[..., tuple[bool, str, str]]
    blob_store_factory: Callable[[], Any]
    stage_prepare_value: str


def tool_extract_and_store_cv(
    *,
    docx_base64: str,
    language: str,
    extract_photo_flag: bool,
    job_posting_url: str | None,
    job_posting_text: str | None,
    deps: ExtractStoreToolDeps,
) -> tuple[int, dict]:
    if not docx_base64:
        return 400, {"error": "docx_base64 is required"}

    try:
        docx_bytes = base64.b64decode(docx_base64)
    except Exception as e:
        return 400, {"error": "Invalid base64 encoding", "details": str(e)}

    store = deps.get_session_store()
    deps.cleanup_expired_once(store)

    extracted_photo = None
    photo_extracted = False
    photo_storage = "none"
    photo_omitted_reason = None
    if extract_photo_flag:
        try:
            extracted_photo = deps.extract_first_photo_from_docx_bytes(docx_bytes)
            photo_extracted = bool(extracted_photo)
            logging.info("Photo extraction: %s", "success" if extracted_photo else "no photo found")
        except Exception as e:
            photo_omitted_reason = f"photo_extraction_failed: {e}"
            logging.warning("Photo extraction failed: %s", e)

    prefill = deps.prefill_cv_from_docx_bytes(docx_bytes)

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
        "source_language": (language or "en"),
        "target_language": None,
        "created_from": "docx",
        "stage": deps.stage_prepare_value,
        "stage_updated_at": deps.now_iso(),
        "flow_mode": "wizard",
        "wizard_stage": "language_selection",
        "wizard_stage_updated_at": deps.now_iso(),
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
        metadata["job_fetch_status"] = "pending"
    if job_posting_text:
        candidate_text = str(job_posting_text)[:20000]
        ok_text, reason_text = deps.looks_like_job_posting_text(candidate_text)
        if ok_text:
            metadata["job_posting_text"] = candidate_text
            metadata["job_input_status"] = "ok"
            if job_posting_url:
                metadata["job_fetch_status"] = "manual"
        else:
            metadata["job_posting_text"] = ""
            metadata["job_input_status"] = "invalid"
            metadata["job_input_invalid_reason"] = reason_text
            metadata["job_posting_invalid_draft"] = candidate_text[:2000]

    try:
        session_id = store.create_session(cv_data, metadata)
        logging.info("Session created: %s", session_id)
    except Exception as e:
        logging.error("Session creation failed: %s", e)
        return 500, {"error": "Failed to create session", "details": str(e)}

    if job_posting_url and not job_posting_text:
        try:
            url = str(job_posting_url).strip()
            if re.match(r"^https?://", url, re.IGNORECASE):
                logging.info("Starting async job URL fetch: %s", url[:100])
                ok, fetched_text, err = deps.fetch_text_from_url(url, timeout=8.0)
                session = store.get_session(session_id)
                if session:
                    meta_update = session.get("metadata") or {}
                    if ok and fetched_text.strip():
                        candidate_text = fetched_text[:20000]
                        ok_text, reason_text = deps.looks_like_job_posting_text(candidate_text)
                        if ok_text:
                            meta_update["job_posting_text"] = candidate_text
                            meta_update["job_fetch_status"] = "success"
                            meta_update["job_fetch_timestamp"] = deps.now_iso()
                            meta_update["job_input_status"] = "ok"
                            logging.info("Job URL fetch successful: %s chars", len(fetched_text))
                        else:
                            meta_update["job_posting_text"] = ""
                            meta_update["job_fetch_status"] = "failed"
                            meta_update["job_fetch_error"] = f"fetched_text_invalid:{reason_text}"[:400]
                            meta_update["job_fetch_timestamp"] = deps.now_iso()
                            meta_update["job_input_status"] = "invalid"
                            meta_update["job_input_invalid_reason"] = reason_text
                            logging.warning("Job URL fetch text rejected by gate: %s", reason_text)
                    else:
                        meta_update["job_fetch_status"] = "failed"
                        meta_update["job_fetch_error"] = str(err)[:400]
                        meta_update["job_fetch_timestamp"] = deps.now_iso()
                        logging.warning("Job URL fetch failed: %s", err)
                    store.update_session(session_id, session.get("cv_data"), meta_update)
        except Exception as e:
            logging.warning("Async job URL fetch exception: %s", e)

    if photo_extracted and extracted_photo:
        try:
            blob_store = deps.blob_store_factory()
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
            logging.warning("Photo blob storage failed: %s", e)
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
