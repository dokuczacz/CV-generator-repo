from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from src.blob_store import BlobPointer, CVBlobStore
from src.normalize import normalize_cv_data
from src.render import count_pdf_pages, render_pdf
from src.schema_validator import validate_canonical_schema
from src.validator import validate_cv


@dataclass(frozen=True)
class CvPdfToolDeps:
    cv_pdf_always_regenerate: bool
    cv_execution_latch: bool
    sha256_text: Callable[[str], str]
    get_session_store: Callable[[], Any]
    compute_readiness: Callable[[dict, dict], dict]
    openai_enabled: Callable[[], bool]
    run_bulk_translation: Callable[..., tuple[dict, dict, bool, str | None]]
    backfill_missing_work_locations: Callable[..., dict]
    drop_one_work_bullet_bottom_up: Callable[..., tuple[dict, str | None]]
    serialize_validation_result: Callable[[Any], dict]
    upload_pdf_blob_for_session: Callable[..., dict[str, str] | None]
    compute_pdf_download_name: Callable[..., str]
    shrink_metadata_for_table: Callable[[dict], dict]
    now_iso: Callable[[], str]


def tool_generate_cv_from_session(
    *,
    session_id: str,
    language: str | None,
    client_context: dict | None,
    session: dict,
    deps: CvPdfToolDeps,
) -> tuple[int, dict | bytes, str]:
    _sha256_text = deps.sha256_text
    _get_session_store = deps.get_session_store
    _compute_readiness = deps.compute_readiness
    _openai_enabled = deps.openai_enabled
    _run_bulk_translation = deps.run_bulk_translation
    _backfill_missing_work_locations = deps.backfill_missing_work_locations
    _drop_one_work_bullet_bottom_up = deps.drop_one_work_bullet_bottom_up
    _serialize_validation_result = deps.serialize_validation_result
    _upload_pdf_blob_for_session = deps.upload_pdf_blob_for_session
    _compute_pdf_download_name = deps.compute_pdf_download_name
    _shrink_metadata_for_table = deps.shrink_metadata_for_table
    _now_iso = deps.now_iso
    def _shrink_cv_for_pdf(*, cv_in: dict, level: int) -> tuple[dict, dict]:
        """
        Deterministic shrink-to-fit for PDF generation only.
        Does NOT mutate the stored session cv_data; it only affects the rendered snapshot.

        Levels (increasing aggressiveness, bounded):
          1) Reduce bullet COUNT outliers to match others (bottom-up)
          2+) Reduce bullet COUNT further (bottom-up)
          5+) Cap auxiliary lists (skills/languages/projects)
          7+) Cap oldest entries (roles/projects/education)
        """
        cv = dict(cv_in or {})
        def _cap_list(items: list, *, max_items: int) -> list:
            out: list[str] = []
            for it in (items or [])[: max(0, int(max_items))]:
                s = str(it or "").strip()
                if not s:
                    continue
                out.append(s)
            return out

        summary: dict = {"level": int(level), "changes": []}

        # Work experience: reduce bullet COUNT (never shorten bullet text).
        if isinstance(cv.get("work_experience"), list):
            work = list(cv.get("work_experience") or [])

            # Determine baseline target (n):
            # Example: 4,4,5 -> target=4 (reduce outlier only).
            counts: list[int] = []
            for i, role in enumerate(work):
                if not isinstance(role, dict):
                    continue
                bullets = role.get("bullets")
                if not isinstance(bullets, list):
                    bullets = role.get("responsibilities") if isinstance(role.get("responsibilities"), list) else []
                counts.append(len(bullets or []))

            unique = sorted({c for c in counts if c > 0}, reverse=True)
            base_target = unique[1] if len(unique) >= 2 else (unique[0] if unique else 0)
            # Level 1: target=base_target, Level 2: target=base_target-1, ...
            # If base_target is 0 (no bullets), do nothing.
            if base_target > 0 and level >= 1:
                target = max(1, int(base_target) - (int(level) - 1))

                # Apply bottom-up: reduce last roles first, then move upward.
                for i in range(len(work) - 1, -1, -1):
                    role = work[i]
                    if not isinstance(role, dict):
                        continue
                    bullets = role.get("bullets")
                    if not isinstance(bullets, list):
                        bullets = role.get("responsibilities") if isinstance(role.get("responsibilities"), list) else []
                    if not isinstance(bullets, list) or len(bullets) <= target:
                        continue
                    role2 = dict(role)
                    role2["bullets"] = list(bullets[:target])
                    if "responsibilities" in role2 and isinstance(role2.get("responsibilities"), list):
                        role2["responsibilities"] = list(role2["bullets"])
                    work[i] = role2
                    summary["changes"].append(f"work_bullets_cap[{i}]={target}")
            cv["work_experience"] = work

            # Very aggressive: cap oldest roles (keep most recent first).
            if level >= 7:
                max_roles = 4
                if isinstance(cv.get("work_experience"), list) and len(cv.get("work_experience") or []) > max_roles:
                    cv["work_experience"] = list(cv.get("work_experience") or [])[:max_roles]
                    summary["changes"].append("work_roles_cap")

        # Cap auxiliary lists only after we've tried bullet reductions.
        if level >= 5:
            if isinstance(cv.get("languages"), list):
                before_n = len(cv.get("languages") or [])
                cv["languages"] = _cap_list(cv.get("languages") or [], max_items=6)
                if len(cv["languages"]) != before_n:
                    summary["changes"].append("languages_cap")

            if isinstance(cv.get("it_ai_skills"), list):
                before_n = len(cv.get("it_ai_skills") or [])
                cv["it_ai_skills"] = _cap_list(cv.get("it_ai_skills") or [], max_items=10)
                if len(cv["it_ai_skills"]) != before_n:
                    summary["changes"].append("skills_cap")

        # Further experience: cap entries and bullet COUNT (never shorten text).
        if isinstance(cv.get("further_experience"), list):
            further = list(cv.get("further_experience") or [])
            max_projects = 5 if level < 7 else 4
            max_proj_bullets = 3 if level < 7 else 2
            trimmed: list[dict] = []
            for p in further[:max_projects]:
                if not isinstance(p, dict):
                    continue
                p2 = dict(p)
                bullets = p2.get("bullets")
                if isinstance(bullets, list):
                    p2["bullets"] = list(bullets[:max_proj_bullets])
                trimmed.append(p2)
            if len(trimmed) != len(further):
                summary["changes"].append("further_cap")
            cv["further_experience"] = trimmed

        # Education: cap only at very aggressive level (keep most recent order).
        if level >= 7 and isinstance(cv.get("education"), list):
            edu = [e for e in (cv.get("education") or []) if isinstance(e, dict)]
            if len(edu) > 2:
                cv["education"] = edu[:2]
                summary["changes"].append("education_cap")

        return cv, summary

    meta = session.get("metadata") or {}
    cv_data = session.get("cv_data") or {}
    lang = language or (meta.get("language") if isinstance(meta, dict) else None) or "en"

    store = None

    # Cache-busting signature for the actual render snapshot (independent of job_sig).
    # Used by the execution latch to avoid serving a stale cached PDF after CV edits/template updates.
    try:
        cv_sig = _sha256_text(json.dumps(normalize_cv_data(dict(cv_data or {})), ensure_ascii=False, sort_keys=True))
    except Exception:
        cv_sig = ""

    force_regen = bool((client_context or {}).get("force_pdf_regen")) or deps.cv_pdf_always_regenerate

    # Wave 0.1: Execution Latch (Idempotency Check)
    # Check if PDF already exists to prevent duplicate generation
    if (not force_regen) and deps.cv_execution_latch:
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
                current_job_sig = str(meta.get("current_job_sig") or "").strip()
                latest_job_sig = str(latest_info.get("job_sig") or "") if isinstance(latest_info, dict) else ""
                latest_cv_sig = str(latest_info.get("cv_sig") or "") if isinstance(latest_info, dict) else ""
                current_lang = str(meta.get("target_language") or meta.get("language") or lang).strip().lower()
                latest_lang = str(latest_info.get("target_language") or "").strip().lower() if isinstance(latest_info, dict) else ""
                if current_job_sig and latest_job_sig and current_job_sig != latest_job_sig:
                    logging.info(
                        "Execution latch: skipping cached PDF due to job_sig mismatch session_id=%s current_job_sig=%s cached_job_sig=%s",
                        session_id,
                        current_job_sig[:12],
                        latest_job_sig[:12],
                    )
                elif current_lang and latest_lang and current_lang != latest_lang:
                    logging.info(
                        "Execution latch: skipping cached PDF due to language mismatch session_id=%s current_lang=%s cached_lang=%s",
                        session_id,
                        current_lang,
                        latest_lang,
                    )
                elif current_lang and not latest_lang:
                    logging.info(
                        "Execution latch: skipping cached PDF due to missing cached language session_id=%s current_lang=%s",
                        session_id,
                        current_lang,
                    )
                elif cv_sig and (not latest_cv_sig or latest_cv_sig != cv_sig):
                    logging.info(
                        "Execution latch: skipping cached PDF due to cv_sig mismatch session_id=%s current_cv_sig=%s cached_cv_sig=%s",
                        session_id,
                        cv_sig[:12],
                        latest_cv_sig[:12] if latest_cv_sig else "(missing)",
                    )
                else:
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

    # Ensure store exists for persistence later (pdf_refs, flags).
    if store is None:
        store = _get_session_store()

    target_lang = str(meta.get("target_language") or meta.get("language") or lang).strip().lower()
    source_lang = str(meta.get("source_language") or cv_data.get("language") or "en").strip().lower()
    explicit_target_lang_selected = bool(meta.get("target_language"))
    needs_bulk_translation = (
        (source_lang != target_lang or explicit_target_lang_selected)
        and str(meta.get("bulk_translated_to") or "") != target_lang
    )
    if needs_bulk_translation:
        if not _openai_enabled():
            return 400, {
                "error": "bulk_translation_required",
                "message": "Target language requires bulk translation, but AI is not configured.",
                "target_language": target_lang,
            }, "application/json"
        cv_data, meta, ok_bt, err_bt = _run_bulk_translation(
            cv_data=cv_data,
            meta=meta if isinstance(meta, dict) else {},
            trace_id=str(uuid.uuid4().hex),
            session_id=session_id,
            target_language=target_lang,
        )
        run_summary["bulk_translation"] = {
            "target_language": target_lang,
            "ok": bool(ok_bt),
        }
        if not ok_bt:
            return 400, {
                "error": "bulk_translation_failed",
                "message": "Bulk translation failed; please retry.",
                "details": str(err_bt)[:400],
            }, "application/json"

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

    cv_data = _backfill_missing_work_locations(
        cv_data=cv_data,
        previous_work=None,
        meta=meta if isinstance(meta, dict) else {},
    )

    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    if not is_valid:
        return 400, {"error": "CV data validation failed", "validation_errors": errors, "run_summary": run_summary}, "application/json"

    cv_data = normalize_cv_data(cv_data)

    # Iterative shrink-to-fit: prefer keeping content; drop exactly 1 bullet at a time (bottom-up).
    # Important: validate_cv's layout height estimate can be conservative; if errors are layout-only,
    # try rendering anyway and stop at the first snapshot that renders as exactly 2 pages.
    layout_fields = {"_total_pages", "_page1_overflow", "_page2_overflow"}
    max_steps = 40
    last_validation = None
    shrink_changes: list[str] = []
    pdf_bytes: bytes | None = None
    cv_try = cv_data

    for step in range(0, max_steps + 1):
        validation_result = validate_cv(cv_try)
        last_validation = validation_result

        hard_errors = []
        if isinstance(validation_result.errors, list):
            for e in validation_result.errors:
                try:
                    field = str(getattr(e, "field", "") or "")
                except Exception:
                    field = ""
                if field and field in layout_fields:
                    continue
                # Treat unknown/malformed errors as hard.
                hard_errors.append(e)

        run_summary["shrink_level"] = step
        run_summary["shrink_changes"] = shrink_changes[:60]

        if not hard_errors:
            try:
                logging.info("=== PDF GENERATION START === session_id=%s shrink_step=%s", session_id, step)
                pdf_bytes = render_pdf(cv_try, enforce_two_pages=True)
                cv_data = cv_try  # render snapshot used for download name + metadata
                break
            except Exception as e:
                # If renderer still violates DoD (pages != 2), shrink once and retry.
                run_summary["render_error"] = str(e)[:200]

        # Shrink step: keep >=3 bullets/role if possible, else allow dropping to 2.
        cv_next, change = _drop_one_work_bullet_bottom_up(cv_in=cv_try, min_bullets_per_role=3)
        if not change:
            cv_next, change = _drop_one_work_bullet_bottom_up(cv_in=cv_try, min_bullets_per_role=2)
        if not change:
            # Fallback to legacy shrink to cap auxiliary lists (skills/languages/projects) if work bullets can't shrink.
            cv_next, summary = _shrink_cv_for_pdf(cv_in=cv_try, level=min(8, 1 + step // 5))
            change = ",".join(summary.get("changes") or []) if isinstance(summary, dict) else "legacy_shrink"

        if change:
            shrink_changes.append(change)
        cv_try = cv_next

    if not pdf_bytes:
        if last_validation is None:
            last_validation = validate_cv(cv_data)
        payload = {"error": "Validation failed", "validation": _serialize_validation_result(last_validation), "run_summary": run_summary}
        return 400, payload, "application/json"

    pdf_ref = f"{session_id}-{uuid.uuid4().hex}"
    render_start = time.time()
    try:
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
            "cv_sig": cv_sig,
            "size_bytes": len(pdf_bytes),
            "render_ms": render_ms,
            "pages": pages,
            "validation_passed": bool(readiness.get("can_generate")),
            "download_name": download_name,
            "target_language": str(meta.get("target_language") or meta.get("language") or lang).strip().lower(),
            "job_sig": str(meta.get("current_job_sig") or (client_context or {}).get("job_sig") or ""),
        }
        metadata["pdf_refs"] = pdf_refs
        # Wave 0.2: Set pdf_generated flag (terminal FSM state)
        metadata["pdf_generated"] = True
        metadata.pop("pdf_failed", None)  # Clear any previous failure
        persisted = False
        persist_error = None
        try:
            # Use blob offload method to handle large cv_data automatically
            persisted = bool(store.update_session_with_blob_offload(session_id, cv_data, metadata))
        except Exception as exc:
            persist_error = str(exc)
            logging.warning("Failed to persist pdf metadata for session %s (will retry shrink): %s", session_id, exc)
        if not persisted:
            try:
                metadata2 = _shrink_metadata_for_table(metadata)
                persisted = bool(store.update_session_with_blob_offload(session_id, cv_data, metadata2))
                metadata = metadata2
            except Exception as exc:
                persist_error = str(exc)
                logging.warning("Failed to persist pdf metadata after shrink for session %s: %s", session_id, exc)
        
        # Post-write verification: ensure pdf_generated and pdf_refs are persisted
        if persisted:
            verify_ok, verify_errors = store.verify_pdf_metadata_persisted(session_id, pdf_ref)
            if not verify_ok:
                logging.error(
                    "PDF metadata verification failed for session %s: %s",
                    session_id,
                    "; ".join(verify_errors)
                )
                # Don't fail the request, but log for monitoring
                run_summary["pdf_metadata_verification_errors"] = verify_errors
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


