from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from src.blob_store import BlobPointer, CVBlobStore


@dataclass(frozen=True)
class CoverLetterToolDeps:
    cv_enable_cover_letter: bool
    openai_enabled: Callable[[], bool]
    generate_cover_letter_block_via_openai: Callable[..., tuple[bool, dict | None, str]]
    validate_cover_letter_block: Callable[..., tuple[bool, list[str]]]
    build_cover_letter_render_payload: Callable[..., dict]
    render_cover_letter_pdf: Callable[..., bytes]
    upload_pdf_blob_for_session: Callable[..., dict | None]
    compute_cover_letter_download_name: Callable[..., str]
    now_iso: Callable[[], str]
    get_session_store: Callable[[], Any]


def tool_generate_cover_letter_from_session(
    *,
    session_id: str,
    language: str | None,
    session: dict,
    deps: CoverLetterToolDeps,
) -> tuple[int, dict | bytes, str]:
    cv_data = session.get("cv_data") if isinstance(session.get("cv_data"), dict) else {}
    meta = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    meta2 = dict(meta or {})

    target_lang = str(language or meta2.get("target_language") or meta2.get("language") or "en").strip().lower()
    if target_lang not in ("en", "de"):
        return 400, {"error": "cover_letter_lang_unsupported", "details": "Cover letter generation is EN/DE only for now."}, "application/json"
    if not deps.cv_enable_cover_letter:
        return 403, {"error": "cover_letter_disabled"}, "application/json"
    if not deps.openai_enabled():
        return 400, {"error": "ai_disabled_or_missing_key"}, "application/json"

    trace_id = uuid.uuid4().hex
    ok_cl, cl_block, err_cl = deps.generate_cover_letter_block_via_openai(
        cv_data=cv_data,
        meta=meta2,
        trace_id=trace_id,
        session_id=session_id,
        target_language=target_lang,
    )
    if not ok_cl or not isinstance(cl_block, dict):
        return 500, {"error": "cover_letter_generation_failed", "details": str(err_cl)[:400]}, "application/json"

    ok2, errs2 = deps.validate_cover_letter_block(block=cl_block, cv_data=cv_data)
    if not ok2:
        return 400, {"error": "cover_letter_validation_failed", "details": errs2[:8]}, "application/json"

    payload = deps.build_cover_letter_render_payload(cv_data=cv_data, meta=meta2, block=cl_block)
    try:
        pdf_bytes = deps.render_cover_letter_pdf(payload, enforce_one_page=True, use_cache=False)
    except Exception as exc:
        return 500, {"error": "cover_letter_render_failed", "details": str(exc)[:400]}, "application/json"

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
    meta2["cover_letter_block"] = cl_block
    meta2["cover_letter_pdf_ref"] = pdf_ref
    try:
        deps.get_session_store().update_session(session_id, cv_data, meta2)
    except Exception:
        pass

    pdf_metadata = {"pdf_ref": pdf_ref, "download_name": pdf_refs[pdf_ref].get("download_name")}
    return 200, {"pdf_bytes": pdf_bytes, "pdf_metadata": pdf_metadata, "pdf_ref": pdf_ref}, "application/pdf"


def tool_get_pdf_by_ref(*, session_id: str, pdf_ref: str, session: dict) -> tuple[int, dict | bytes, str]:
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
