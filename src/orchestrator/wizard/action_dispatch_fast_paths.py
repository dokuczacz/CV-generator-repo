from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FastPathsActionDeps:
    reset_metadata_for_new_version: Callable[[dict], dict]
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    fetch_text_from_url: Callable[[str], tuple[bool, str, str | None]]
    now_iso: Callable[[], str]
    looks_like_job_posting_text: Callable[[str], tuple[bool, str]]
    compute_readiness: Callable[[dict, dict], dict]
    sha256_text: Callable[[str], str]
    download_json_blob: Callable[..., dict | None]
    openai_enabled: Callable[[], bool]
    openai_json_schema_call: Callable[..., tuple[bool, dict | None, str | None]]
    build_ai_system_prompt: Callable[..., str]
    get_job_reference_response_format: Callable[[], dict]
    parse_job_reference: Callable[[dict], Any]
    format_job_reference_for_display: Callable[[dict], str]
    escape_user_input_for_prompt: Callable[[str], str]
    sanitize_for_prompt: Callable[[str], str]
    get_work_experience_bullets_proposal_response_format: Callable[[], dict]
    parse_work_experience_bullets_proposal: Callable[[dict], Any]
    extract_e0_corpus_from_labeled_blocks: Callable[[str, list[str]], Any]
    find_work_e0_violations: Callable[..., list[str]]
    build_work_bullet_violation_payload: Callable[..., dict]
    select_roles_by_violation_indices: Callable[..., list[dict]]
    overwrite_work_experience_from_proposal_roles: Callable[..., dict]
    backfill_missing_work_locations: Callable[..., dict]
    find_work_bullet_hard_limit_violations: Callable[..., list[str]]
    collect_raw_docx_skills_context: Callable[..., list[str]]
    get_skills_unified_proposal_response_format: Callable[[], dict]
    parse_skills_unified_proposal: Callable[[dict], Any]
    tool_generate_cv_from_session: Callable[..., tuple[int, dict | bytes, str]]
    get_session_with_blob_retrieval: Callable[[str], dict | None]
    get_session: Callable[[str], dict | None]
    work_experience_hard_limit_chars: int
    log_warning: Callable[..., Any]


def handle_fast_paths_actions(
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
    deps: FastPathsActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "NEW_VERSION_RESET":
        meta2 = deps.reset_metadata_for_new_version(meta2)
        # Keep language/translation/cache metadata and canonical CV state intact.
        # Bring user back to job stage for a fresh tailoring pass.
        meta2 = deps.wizard_set_stage(meta2, "job_posting")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="New version ready. Translation cache and CV data are kept; tailoring artifacts were reset.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    
    if aid in ("FAST_RUN", "FAST_RUN_TO_PDF"):
        stage_updates: list[dict] = []
        payload = user_action_payload or {}
    
        # Update optional user notes (persisted artifacts)
        try:
            if isinstance(payload, dict) and "work_tailoring_notes" in payload:
                meta2["work_tailoring_notes"] = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
            if isinstance(payload, dict) and "skills_ranking_notes" in payload:
                meta2["skills_ranking_notes"] = str(payload.get("skills_ranking_notes") or "").strip()[:2000]
        except Exception:
            pass
    
        # Ensure we have job text (prefer payload override, fallback to stored metadata)
        job_text = str(payload.get("job_posting_text") or payload.get("job_offer_text") or meta2.get("job_posting_text") or "")[:20000]
        job_url = str(payload.get("job_posting_url") or meta2.get("job_posting_url") or "").strip()
        fetch_status = str(meta2.get("job_fetch_status") or "")
        
        # Only fetch if we don't have text and haven't already successfully fetched
        if (not job_text.strip()) and job_url and fetch_status != "success" and re.match(r"^https?://", job_url, re.IGNORECASE):
            meta2["job_fetch_status"] = "fetching"
            ok, fetched_text, err = deps.fetch_text_from_url(job_url)
            if ok and fetched_text.strip():
                job_text = fetched_text[:20000]
                meta2["job_posting_text"] = job_text
                meta2["job_posting_url"] = job_url
                meta2["job_fetch_status"] = "success"
                meta2["job_fetch_timestamp"] = deps.now_iso()
                stage_updates.append({"step": "fetch_job_url", "ok": True})
            else:
                meta2["job_fetch_status"] = "failed"
                meta2["job_fetch_error"] = str(err)[:400]
                meta2["job_fetch_timestamp"] = deps.now_iso()
                stage_updates.append({"step": "fetch_job_url", "ok": False, "error": str(err)[:200]})
                meta2 = deps.wizard_set_stage(meta2, "job_posting_paste")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text="FAST_RUN: could not fetch job offer URL. Please paste the full job description.",
                    meta_out=meta2,
                    cv_out=cv_data,
                    stage_updates=stage_updates,
                )
    
        if len(job_text.strip()) < 80:
            stage_updates.append({"step": "job_text", "ok": False, "error": "too_short"})
            meta2["job_input_status"] = "invalid"
            meta2["job_input_invalid_reason"] = "too_short"
            meta2["job_posting_invalid_draft"] = str(job_text or "")[:2000]
            meta2["job_posting_text"] = ""
            meta2 = deps.wizard_set_stage(meta2, "job_posting_invalid_input")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="FAST_RUN: input is too short for a job summary. Choose: correct URL, paste proper job text, or continue without summary.",
                meta_out=meta2,
                cv_out=cv_data,
                stage_updates=stage_updates,
            )
    
        ok_job_text, reason_job_text = deps.looks_like_job_posting_text(job_text)
        if not ok_job_text:
            stage_updates.append({"step": "job_text", "ok": False, "error": reason_job_text})
            meta2["job_input_status"] = "invalid"
            meta2["job_input_invalid_reason"] = reason_job_text
            meta2["job_posting_invalid_draft"] = str(job_text or "")[:2000]
            meta2["job_posting_text"] = ""
            meta2 = deps.wizard_set_stage(meta2, "job_posting_invalid_input")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="FAST_RUN: input looks like notes, not a job posting. Choose how to proceed.",
                meta_out=meta2,
                cv_out=cv_data,
                stage_updates=stage_updates,
            )
    
        # Require confirmed base identity before fast mode (avoids silent garbage-in PDF).
        readiness0 = deps.compute_readiness(cv_data, meta2)
        cf0 = readiness0.get("confirmed_flags") if isinstance(readiness0, dict) else {}
        if not (isinstance(cf0, dict) and cf0.get("contact_confirmed") and cf0.get("education_confirmed")):
            stage_updates.append({"step": "confirmed_flags", "ok": False})
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="FAST_RUN: please confirm & lock Contact and Education first (then retry).",
                meta_out=meta2,
                cv_out=cv_data,
                stage_updates=stage_updates,
            )
    
        # Compute job signature and reset job-scoped state if needed.
        job_sig = deps.sha256_text(job_text)
        prev_job_sig = str(meta2.get("current_job_sig") or "")
        meta2["job_posting_text"] = job_text
        if job_url:
            meta2["job_posting_url"] = job_url
    
        # Load base CV snapshot (blob) if available.
        base_sig = str(meta2.get("base_cv_sha256") or "")
        base_cv: dict | None = None
        base_ptr = meta2.get("base_cv") if isinstance(meta2.get("base_cv"), dict) else None
        if isinstance(base_ptr, dict):
            container = str(base_ptr.get("container") or "")
            blob_name = str(base_ptr.get("blob_name") or "")
            if container and blob_name:
                base_obj = deps.download_json_blob(container=container, blob_name=blob_name)
                if isinstance(base_obj, dict) and isinstance(base_obj.get("cv_data"), dict):
                    base_cv = base_obj.get("cv_data")
    
        if job_sig and job_sig != prev_job_sig:
            stage_updates.append({"step": "job_changed", "from": prev_job_sig[:12], "to": job_sig[:12]})
            meta2["current_job_sig"] = job_sig
            meta2["job_changed_at"] = deps.now_iso()
            meta2["pdf_generated"] = False
            # Reset job-scoped artifacts; keep user notes and base snapshot.
            meta2.pop("job_reference", None)
            meta2.pop("job_reference_status", None)
            meta2.pop("job_reference_error", None)
            meta2["job_reference_sig"] = ""
            meta2.pop("work_experience_proposal_block", None)
            meta2.pop("work_experience_proposal_error", None)
            meta2["work_experience_proposal_sig"] = ""
            meta2.pop("skills_proposal_block", None)
            meta2.pop("skills_proposal_error", None)
            meta2["skills_proposal_sig"] = ""
            # Restore canonical CV from base snapshot (fast path keeps user profile stable).
            if isinstance(base_cv, dict) and base_cv:
                cv_data = dict(base_cv)
                stage_updates.append({"step": "restore_base_cv", "ok": True})
            else:
                stage_updates.append({"step": "restore_base_cv", "ok": False, "error": "base_snapshot_missing"})
        else:
            meta2["current_job_sig"] = job_sig
    
        if not deps.openai_enabled():
            stage_updates.append({"step": "ai_enabled", "ok": False})
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="FAST_RUN: AI is not configured (missing OPENAI_API_KEY or CV_ENABLE_AI=0).",
                meta_out=meta2,
                cv_out=cv_data,
                stage_updates=stage_updates,
            )
    
        # 1) Job reference (cacheable per job_sig)
        job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
        if job_ref and str(meta2.get("job_reference_sig") or "") == job_sig:
            stage_updates.append({"step": "job_reference", "mode": "cache", "ok": True})
        else:
            ok_jr, parsed_jr, err_jr = deps.openai_json_schema_call(
                system_prompt=deps.build_ai_system_prompt(stage="job_posting"),
                user_text=job_text,
                trace_id=trace_id,
                session_id=session_id,
                response_format=deps.get_job_reference_response_format(),
                max_output_tokens=1200,
                stage="job_posting",
            )
            if not ok_jr or not isinstance(parsed_jr, dict):
                stage_updates.append({"step": "job_reference", "ok": False, "error": str(err_jr)[:200]})
                meta2["job_reference_error"] = str(err_jr)[:400]
                meta2["job_reference_status"] = "call_failed"
                meta2 = deps.wizard_set_stage(meta2, "job_posting")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text="FAST_RUN: failed to analyze the job offer. Please try again or paste a different job text.",
                    meta_out=meta2,
                    cv_out=cv_data,
                    stage_updates=stage_updates,
                )
            try:
                jr = deps.parse_job_reference(parsed_jr)
                meta2["job_reference"] = jr.dict()
                meta2["job_reference_status"] = "ok"
                meta2["job_reference_sig"] = job_sig
                stage_updates.append({"step": "job_reference", "mode": "ai", "ok": True})
            except Exception as e:
                meta2["job_reference_error"] = str(e)[:400]
                meta2["job_reference_status"] = "parse_failed"
                stage_updates.append({"step": "job_reference", "ok": False, "error": str(e)[:200]})
    
        # 2) Work experience tailoring (cacheable per job_sig + base_sig)
        if (
            isinstance(meta2.get("work_experience_proposal_block"), dict)
            and str(meta2.get("work_experience_proposal_sig") or "") == job_sig
            and str(meta2.get("work_experience_proposal_base_sig") or "") == base_sig
        ):
            stage_updates.append({"step": "work_tailor", "mode": "cache", "ok": True})
        else:
            work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
            work_list = work if isinstance(work, list) else []
            if not work_list:
                stage_updates.append({"step": "work_tailor", "ok": False, "error": "no_work_experience"})
            else:
                job_summary = deps.format_job_reference_for_display(meta2.get("job_reference")) if isinstance(meta2.get("job_reference"), dict) else ""
                notes = deps.escape_user_input_for_prompt(str(meta2.get("work_tailoring_notes") or ""))
                feedback = deps.escape_user_input_for_prompt(str(meta2.get("work_tailoring_feedback") or ""))
                target_lang = str(meta2.get("target_language") or cv_data.get("language") or meta2.get("language") or "en").strip().lower()
    
                role_blocks = []
                for r in work_list[:12]:
                    if not isinstance(r, dict):
                        continue
                    company = deps.sanitize_for_prompt(str(r.get("employer") or r.get("company") or ""))
                    title = deps.sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
                    date = deps.sanitize_for_prompt(str(r.get("date_range") or ""))
                    bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
                    bullet_lines = "\n".join([f"- {deps.sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:12])
                    head = " | ".join([p for p in [title, company, date] if p]) or "Role"
                    role_blocks.append(f"{head}\n{bullet_lines}")
                roles_text = "\n\n".join(role_blocks)
    
                user_text = (
                    f"[JOB_SUMMARY]\n{deps.sanitize_for_prompt(job_summary)}\n\n"
                    f"[TAILORING_SUGGESTIONS]\n{notes}\n\n"
                    f"[TAILORING_FEEDBACK]\n{feedback}\n\n"
                    f"[CURRENT_WORK_EXPERIENCE]\n{roles_text}\n"
                )
    
                # Auto-retry loop: validate bullets before showing to user (max 3 attempts).
                max_attempts = 3
                attempt = 0
                ok_we = False
                parsed_we = None
                err_we = None
                prop = None
                
                while attempt < max_attempts:
                    attempt += 1
                    ok_we, parsed_we, err_we = deps.openai_json_schema_call(
                        system_prompt=deps.build_ai_system_prompt(stage="work_experience", target_language=target_lang),
                        user_text=user_text,
                        trace_id=trace_id,
                        session_id=session_id,
                        response_format=deps.get_work_experience_bullets_proposal_response_format(),
                        max_output_tokens=2240,
                        stage="work_experience",
                    )
                    
                    if not ok_we or not isinstance(parsed_we, dict):
                        break  # Schema error, can't retry
                    
                    try:
                        prop = deps.parse_work_experience_bullets_proposal(parsed_we)
                        roles = prop.roles if hasattr(prop, "roles") else []
                        
                        # Validate bullet lengths (hard limit: 200 chars).
                        validation_errors = []
                        # Language-aware limit: German is ~25% longer than English
                        hard_limit = 250 if target_lang == "de" else 200
                        
                        for role_idx, role in enumerate(roles):
                            bullets = role.bullets if hasattr(role, "bullets") else []
                            for bullet_idx, bullet in enumerate(bullets):
                                blen = len(bullet)
                                if blen > hard_limit:
                                    company = role.company if hasattr(role, "company") else "Unknown"
                                    validation_errors.append(
                                        f"Role {role_idx+1} ({company}), Bullet {bullet_idx+1}: {blen} chars (max: {hard_limit})"
                                    )
    
                        e0_corpus = deps.extract_e0_corpus_from_labeled_blocks(
                            user_text,
                            ["CURRENT_WORK_EXPERIENCE", "TAILORING_SUGGESTIONS", "TAILORING_FEEDBACK"],
                        )
                        validation_errors.extend(
                            deps.find_work_e0_violations(roles=list(roles or []), e0_corpus=e0_corpus)
                        )
                        
                        if not validation_errors:
                            # Valid! Exit retry loop.
                            break
                        
                        # Hard limit exceeded → retry with feedback.
                        if attempt < max_attempts:
                            payload = deps.build_work_bullet_violation_payload(
                                roles=roles,
                                hard_limit=hard_limit,
                                min_reduction_chars=30,
                            )
                            payload_json = json.dumps(payload, ensure_ascii=True)
                            bad_roles = deps.select_roles_by_violation_indices(
                                roles=roles,
                                violations=payload.get("violations") if isinstance(payload, dict) else [],
                            )
                            bad_role_blocks = []
                            for r in bad_roles:
                                if not r:
                                    continue
                                if isinstance(r, dict):
                                    company = deps.sanitize_for_prompt(str(r.get("company") or r.get("employer") or ""))
                                    title = deps.sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
                                    date = deps.sanitize_for_prompt(str(r.get("date_range") or ""))
                                    bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
                                else:
                                    company = deps.sanitize_for_prompt(str(getattr(r, "company", "") or ""))
                                    title = deps.sanitize_for_prompt(str(getattr(r, "title", "") or ""))
                                    date = deps.sanitize_for_prompt(str(getattr(r, "date_range", "") or ""))
                                    bullets = list(getattr(r, "bullets", []) or [])
                                bullet_lines = "\n".join([f"- {deps.sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:12])
                                head = " | ".join([p for p in [title, company, date] if p]) or "Role"
                                bad_role_blocks.append(f"{head}\n{bullet_lines}")
                            bad_roles_text = "\n\n".join(bad_role_blocks) if bad_role_blocks else roles_text
                            user_text = (
                                f"[JOB_SUMMARY]\n{deps.sanitize_for_prompt(job_summary)}\n\n"
                                f"[TAILORING_FEEDBACK]\n"
                                f"MCP_VALIDATION_PAYLOAD: {payload_json} "
                                f"Reduce ONLY flagged bullets by >= 30 chars and to <= {hard_limit} chars, "
                                f"without changing tone/meaning/logic. Keep 4-5 bullets per role. Do NOT invent facts.\n"
                                f"E0_POLICY_ERRORS: {'; '.join(validation_errors[:6])}\n\n"
                                f"[CURRENT_WORK_EXPERIENCE]\n{bad_roles_text}\n"
                            )
                    except Exception as e:
                        err_we = str(e)
                        break  # Parse error, can't retry
                
                if not ok_we or not isinstance(parsed_we, dict):
                    meta2["work_experience_proposal_error"] = str(err_we)[:400]
                    meta2["work_experience_proposal_sig"] = ""
                    stage_updates.append({"step": "work_tailor", "ok": False, "error": str(err_we)[:200]})
                elif prop and hasattr(prop, "roles"):
                    try:
                        roles = prop.roles if hasattr(prop, "roles") else []
                        proposal_roles = [
                            {
                                "title": r.title if hasattr(r, "title") else "",
                                "company": r.company if hasattr(r, "company") else "",
                                "date_range": r.date_range if hasattr(r, "date_range") else "",
                                "location": r.location if hasattr(r, "location") else "",
                                "bullets": list(r.bullets if hasattr(r, "bullets") else []),
                            }
                            for r in (roles or [])[:5]
                        ]
                        meta2["work_experience_proposal_block"] = {
                            "roles": proposal_roles,
                            "notes": str(getattr(prop, "notes", "") or ""),
                            "created_at": deps.now_iso(),
                        }
                        meta2["work_experience_proposal_sig"] = job_sig
                        meta2["work_experience_proposal_base_sig"] = base_sig
                        stage_updates.append({"step": "work_tailor", "mode": "ai", "ok": True})
                    except Exception as e:
                        meta2["work_experience_proposal_error"] = str(e)[:400]
                        meta2["work_experience_proposal_sig"] = ""
                        stage_updates.append({"step": "work_tailor", "ok": False, "error": str(e)[:200]})
    
        # Apply work proposal to cv_data (silent accept)
        try:
            proposal_block = meta2.get("work_experience_proposal_block")
            if isinstance(proposal_block, dict) and isinstance(proposal_block.get("roles"), list):
                roles = list(proposal_block.get("roles") or [])
    
                if not roles:
                    stage_updates.append({"step": "work_apply", "ok": False, "error": "no_proposal"})
                else:
                    prev_work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
                    cv_data = deps.overwrite_work_experience_from_proposal_roles(cv_data=cv_data, proposal_roles=roles)
                    cv_data = deps.backfill_missing_work_locations(cv_data=cv_data, previous_work=prev_work, meta=meta2)
    
                    meta2["work_experience_tailored"] = True
                    meta2["work_experience_proposal_accepted_at"] = deps.now_iso()
                    stage_updates.append({"step": "work_apply", "ok": True})
    
                # Language-aware hard limit for post-apply validation
                base_limit = deps.work_experience_hard_limit_chars
                hard_limit = int(base_limit * 1.25) if target_lang == "de" else base_limit
                violations_after = deps.find_work_bullet_hard_limit_violations(cv_data=cv_data, hard_limit=hard_limit)
                if violations_after:
                    try:
                        deps.log_warning(
                            "work_experience hard-limit violations after apply (fast-run): %s",
                            "; ".join(violations_after[:8]),
                        )
                    except Exception:
                        pass
                    meta2["work_experience_proposal_error"] = "Applied proposal violates hard limits"
                    meta2 = deps.wizard_set_stage(meta2, "work_tailor_feedback")
                    cv_data, meta2 = deps.persist(cv_data, meta2)
                    stage_updates.append({"step": "work_apply", "ok": False, "error": "hard_limit"})
                    return True, cv_data, meta2, deps.wizard_resp(
                        assistant_text=(
                            "FAST_RUN: work experience needs shortening to meet hard limits. "
                            "Please regenerate the proposal with shorter bullets."
                        ),
                        meta_out=meta2,
                        cv_out=cv_data,
                        stage_updates=stage_updates,
                    )
            else:
                stage_updates.append({"step": "work_apply", "ok": False, "error": "no_proposal"})
        except Exception as e:
            stage_updates.append({"step": "work_apply", "ok": False, "error": str(e)[:200]})
    
        # 3) Skills ranking (cacheable per job_sig + base_sig)
        if (
            isinstance(meta2.get("skills_proposal_block"), dict)
            and str(meta2.get("skills_proposal_sig") or "") == job_sig
            and str(meta2.get("skills_proposal_base_sig") or "") == base_sig
        ):
            stage_updates.append({"step": "skills_rank", "mode": "cache", "ok": True})
        else:
            job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
            job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
            tailoring_suggestions = deps.escape_user_input_for_prompt(str(meta2.get("work_tailoring_notes") or ""))
            feedback_once_raw = str(meta2.get("work_tailoring_feedback") or "").strip()
            tailoring_feedback = deps.escape_user_input_for_prompt(feedback_once_raw)
            if feedback_once_raw:
                meta2.pop("work_tailoring_feedback", None)
                meta2["work_tailoring_feedback_consumed_at"] = deps.now_iso()
            raw_docx_skills = deps.collect_raw_docx_skills_context(meta=meta2, max_items=20)
            raw_docx_skills_text = "\n".join([f"- {str(s).strip()}" for s in raw_docx_skills if str(s).strip()])
            target_lang = str(meta2.get("target_language") or cv_data.get("language") or "en").strip().lower()
            work_blocks: list[str] = []
            work_list = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
            for r in (work_list or [])[:8]:
                if not isinstance(r, dict):
                    continue
                company = deps.sanitize_for_prompt(str(r.get("employer") or r.get("company") or ""))
                title = deps.sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
                date = deps.sanitize_for_prompt(str(r.get("date_range") or ""))
                bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
                bullet_lines = "\n".join([f"- {deps.sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:6])
                head = " | ".join([p for p in [title, company, date] if p]) or "Role"
                work_blocks.append(f"{head}\n{bullet_lines}")
            work_text = "\n\n".join(work_blocks)
            user_text = (
                f"[JOB_SUMMARY]\n{job_summary}\n\n"
                f"[TAILORING_SUGGESTIONS]\n{tailoring_suggestions}\n\n"
                f"[TAILORING_FEEDBACK]\n{tailoring_feedback}\n\n"
                f"[WORK_EXPERIENCE_TAILORED]\n{work_text}\n\n"
                f"[RAW_DOCX_SKILLS]\n{raw_docx_skills_text}\n"
            )
    
            ok_sk, parsed_sk, err_sk = deps.openai_json_schema_call(
                system_prompt=deps.build_ai_system_prompt(stage="it_ai_skills", target_language=target_lang),
                user_text=user_text,
                trace_id=trace_id,
                session_id=session_id,
                response_format=deps.get_skills_unified_proposal_response_format(),
                max_output_tokens=1200,
                stage="it_ai_skills",
            )
            if not ok_sk or not isinstance(parsed_sk, dict):
                meta2["skills_proposal_error"] = str(err_sk)[:400]
                meta2["skills_proposal_sig"] = ""
                stage_updates.append({"step": "skills_rank", "ok": False, "error": str(err_sk)[:200]})
            else:
                try:
                    prop = deps.parse_skills_unified_proposal(parsed_sk)
                    it_ai_skills = prop.it_ai_skills if hasattr(prop, "it_ai_skills") else []
                    tech_ops_skills = prop.technical_operational_skills if hasattr(prop, "technical_operational_skills") else []
                    meta2["skills_proposal_block"] = {
                        "it_ai_skills": [str(s).strip() for s in it_ai_skills[:8] if str(s).strip()],
                        "technical_operational_skills": [str(s).strip() for s in tech_ops_skills[:8] if str(s).strip()],
                        "notes": str(getattr(prop, "notes", "") or "")[:500],
                        "created_at": deps.now_iso(),
                    }
                    meta2["skills_proposal_sig"] = job_sig
                    meta2["skills_proposal_base_sig"] = base_sig
                    stage_updates.append({"step": "skills_rank", "mode": "ai", "ok": True})
                except Exception as e:
                    meta2["skills_proposal_error"] = str(e)[:400]
                    meta2["skills_proposal_sig"] = ""
                    stage_updates.append({"step": "skills_rank", "ok": False, "error": str(e)[:200]})
    
        # Apply skills proposal to cv_data (silent accept)
        try:
            proposal_block = meta2.get("skills_proposal_block")
            if isinstance(proposal_block, dict):
                it_ai_skills = proposal_block.get("it_ai_skills")
                tech_ops_skills = proposal_block.get("technical_operational_skills")
                if isinstance(it_ai_skills, list) and isinstance(tech_ops_skills, list):
                    cv2 = dict(cv_data or {})
                    cv2["it_ai_skills"] = [str(s).strip() for s in it_ai_skills[:8] if str(s).strip()]
                    cv2["technical_operational_skills"] = [str(s).strip() for s in tech_ops_skills[:8] if str(s).strip()]
                    cv_data = cv2
                    meta2["it_ai_skills_tailored"] = True
                    meta2["skills_proposal_accepted_at"] = deps.now_iso()
                    stage_updates.append({"step": "skills_apply", "ok": True})
                else:
                    stage_updates.append({"step": "skills_apply", "ok": False, "error": "invalid_proposal"})
            else:
                stage_updates.append({"step": "skills_apply", "ok": False, "error": "no_proposal"})
        except Exception as e:
            stage_updates.append({"step": "skills_apply", "ok": False, "error": str(e)[:200]})
    
        meta2 = deps.wizard_set_stage(meta2, "review_final")
        cv_data, meta2 = deps.persist(cv_data, meta2)
    
        # Always regenerate PDF for fast path.
        readiness_now = deps.compute_readiness(cv_data, meta2)
        if not readiness_now.get("can_generate"):
            stage_updates.append({"step": "readiness", "ok": False, "missing": readiness_now.get("missing")})
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="FAST_RUN: completed tailoring, but readiness is not met for PDF generation.",
                meta_out=meta2,
                cv_out=cv_data,
                stage_updates=stage_updates,
            )
    
        cc = dict(client_context or {})
        cc["force_pdf_regen"] = True
        cc["job_sig"] = job_sig
        cc["fast_path"] = True
        status, payload_pdf, content_type = deps.tool_generate_cv_from_session(
            session_id=session_id,
            language=language,
            client_context=cc,
            session=deps.get_session_with_blob_retrieval(session_id) or {"cv_data": cv_data, "metadata": meta2},
        )
        if status != 200 or content_type != "application/pdf" or not isinstance(payload_pdf, dict):
            stage_updates.append({"step": "pdf_generate", "ok": False, "error": str(payload_pdf.get("error") if isinstance(payload_pdf, dict) else "pdf_failed")})
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="FAST_RUN: PDF generation failed.",
                meta_out=meta2,
                cv_out=cv_data,
                stage_updates=stage_updates,
            )
        pdf_bytes = payload_pdf.get("pdf_bytes")
        pdf_bytes = bytes(pdf_bytes) if isinstance(pdf_bytes, (bytes, bytearray)) else None
        pdf_meta = payload_pdf.get("pdf_metadata") if isinstance(payload_pdf.get("pdf_metadata"), dict) else {}
        stage_updates.append({"step": "pdf_generate", "ok": True, "pdf_ref": pdf_meta.get("pdf_ref")})
    
        # Reload latest metadata for UI badges (pdf_generated flag, pdf_refs, etc.)
        try:
            s3 = deps.get_session(session_id) or {}
            m3 = s3.get("metadata") if isinstance(s3.get("metadata"), dict) else meta2
            c3 = s3.get("cv_data") if isinstance(s3.get("cv_data"), dict) else cv_data
            meta2 = dict(m3 or {})
            cv_data = dict(c3 or {})
        except Exception:
            pass
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="FAST_RUN: job analyzed, CV tailored, skills ranked, PDF generated.",
            meta_out=meta2,
            cv_out=cv_data,
            pdf_bytes=pdf_bytes,
            stage_updates=stage_updates,
        )
    
    
    return False, cv_data, meta2, None
