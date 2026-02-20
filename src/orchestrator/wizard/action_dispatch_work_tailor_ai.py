from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class WorkTailorAIActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    openai_enabled: Callable[[], bool]
    append_event: Callable[[str, dict], Any]
    sha256_text: Callable[[str], str]
    now_iso: Callable[[], str]
    format_job_reference_for_display: Callable[[dict], str]
    escape_user_input_for_prompt: Callable[[str], str]
    openai_json_schema_call: Callable[..., tuple[bool, dict | None, str | None]]
    build_ai_system_prompt: Callable[..., str]
    get_job_reference_response_format: Callable[[], dict]
    parse_job_reference: Callable[[dict], Any]
    sanitize_for_prompt: Callable[[str], str]
    log_info: Callable[..., Any]
    log_warning: Callable[..., Any]
    get_work_experience_bullets_proposal_response_format: Callable[[], dict]
    parse_work_experience_bullets_proposal: Callable[[dict], Any]
    work_experience_hard_limit_chars: int
    extract_e0_corpus_from_labeled_blocks: Callable[[str, list[str]], Any]
    find_work_e0_violations: Callable[..., list[str]]
    friendly_schema_error_message: Callable[[str], str]
    normalize_work_role_from_proposal: Callable[[dict], dict]
    overwrite_work_experience_from_proposal_roles: Callable[..., dict]
    backfill_missing_work_locations: Callable[..., dict]
    find_work_bullet_hard_limit_violations: Callable[..., list[str]]
    build_work_bullet_violation_payload: Callable[..., dict]
    select_roles_by_violation_indices: Callable[..., list[dict]]
    snapshot_session: Callable[..., Any]


def handle_work_tailor_ai_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    trace_id: str,
    deps: WorkTailorAIActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "WORK_TAILOR_RUN":
        # Generate one tailored block for the whole work experience section (no inventions).
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        work_list = work if isinstance(work, list) else []
        if not work_list:
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="No work experience roles found in your CV. Please check import.",
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        if not deps.openai_enabled():
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="AI tailoring is not configured (missing OPENAI_API_KEY or CV_ENABLE_AI=0). You can still skip tailoring.",
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        # Persist tailoring notes if the UI sent them with the action payload (user clicked Generate without Save).
        payload = user_action_payload or {}
        force_regenerate = bool(payload.get("force_regenerate")) if isinstance(payload, dict) else False
        if isinstance(payload, dict) and "work_tailoring_notes" in payload:
            _notes = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
            meta2["work_tailoring_notes"] = _notes
            try:
                deps.append_event(
                    session_id,
                    {
                        "type": "wizard_notes_saved",
                        "stage": "work_experience",
                        "field": "work_tailoring_notes",
                        "text_len": len(_notes),
                        "text_sha256": deps.sha256_text(_notes),
                        "ts_utc": deps.now_iso(),
                    },
                )
            except Exception:
                pass
    
        job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
        job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
        job_text = str(meta2.get("job_posting_text") or "")
        notes = deps.escape_user_input_for_prompt(str(meta2.get("work_tailoring_notes") or ""))
        feedback = deps.escape_user_input_for_prompt(str(meta2.get("work_tailoring_feedback") or ""))
        target_lang = str(meta2.get("target_language") or cv_data.get("language") or meta2.get("language") or "en").strip().lower()
    
        if user_action_payload and "work_tailoring_feedback" in user_action_payload:
            feedback = deps.escape_user_input_for_prompt(str(user_action_payload.get("work_tailoring_feedback") or ""))
            meta2["work_tailoring_feedback"] = feedback[:2000]
    
        # If we only have raw job text, extract a compact job summary first.
        # This avoids sending large job text snippets to the tailoring call.
        if (not job_summary) and job_text and len(job_text) >= 80:
            jt = job_text[:20000]
            ok_jr, parsed_jr, err_jr = deps.openai_json_schema_call(
                system_prompt=deps.build_ai_system_prompt(stage="job_posting"),
                user_text=jt,
                trace_id=trace_id,
                session_id=session_id,
                response_format=deps.get_job_reference_response_format(),
                max_output_tokens=1200,
                stage="job_posting",
            )
            if ok_jr and isinstance(parsed_jr, dict):
                try:
                    jr = deps.parse_job_reference(parsed_jr)
                    meta2["job_reference"] = jr.dict()
                    meta2["job_reference_status"] = "ok"
                    job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
                    job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
                except Exception as e:
                    meta2["job_reference_error"] = str(e)[:400]
                    meta2["job_reference_status"] = "parse_failed"
            else:
                meta2["job_reference_error"] = str(err_jr)[:400]
                meta2["job_reference_status"] = "call_failed"
    
        # Serialize existing roles for the model.
        role_blocks = []
        for r in work_list[:12]:
            if not isinstance(r, dict):
                continue
            company = deps.sanitize_for_prompt(str(r.get("employer") or r.get("company") or ""))
            title = deps.sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
            date = deps.sanitize_for_prompt(str(r.get("date_range") or ""))
            location = deps.sanitize_for_prompt(str(r.get("location") or r.get("city") or r.get("place") or ""))
            bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
            bullet_lines = "\n".join([f"- {deps.sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:12])
            head = " | ".join([p for p in [title, company, date, location] if p]) or "Role"
            role_blocks.append(f"{head}\n{bullet_lines}")
        roles_text = "\n\n".join(role_blocks)
    
        user_text = (
            f"[JOB_SUMMARY]\n{deps.sanitize_for_prompt(job_summary)}\n\n"
            f"[TAILORING_SUGGESTIONS]\n{notes}\n\n"
            f"[TAILORING_FEEDBACK]\n{feedback}\n\n"
            f"[CURRENT_WORK_EXPERIENCE]\n{roles_text}\n"
        )

        # Guard against accidental repeated runs with identical inputs.
        # This keeps "Regenerate" explicit: change notes/feedback or pass force_regenerate=true.
        try:
            input_fingerprint = deps.sha256_text(
                json.dumps(
                    {
                        "target_lang": target_lang,
                        "job_summary_sig": deps.sha256_text(job_summary),
                        "notes_sig": deps.sha256_text(notes),
                        "feedback_sig": deps.sha256_text(feedback),
                        "roles_sig": deps.sha256_text(roles_text),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            prev_input_fingerprint = str(meta2.get("work_experience_proposal_input_sig") or "")
            has_cached_proposal = isinstance(meta2.get("work_experience_proposal_block"), dict)
            stage_now = str(meta2.get("wizard_stage") or "").strip().lower()
            if (
                not force_regenerate
                and has_cached_proposal
                and prev_input_fingerprint
                and prev_input_fingerprint == input_fingerprint
                and stage_now in ("work_tailor_review", "work_notes_edit", "work_tailor_feedback")
            ):
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=(
                        "Proposal is already up to date for current notes/job context. "
                        "Edit notes/feedback to regenerate, or accept the current proposal."
                    ),
                    meta_out=meta2,
                    cv_out=cv_data,
                )
        except Exception:
            input_fingerprint = ""
    
        # Auto-retry loop: validate bullets before showing to user (max 3 attempts).
        max_attempts = 3
        attempt = 0
        ok = False
        parsed = None
        err = None
        prop = None
        
        # DIAGNOSTIC: Log the target_language that will be used
        deps.log_info(
            "WORK_TAILOR_CONTEXT target_lang=%s session=%s trace=%s",
            repr(target_lang),
            session_id,
            trace_id,
        )
        
        while attempt < max_attempts:
            attempt += 1
            built_prompt = deps.build_ai_system_prompt(stage="work_experience", target_language=target_lang)
            # Log a sample of the built prompt to verify language substitution
            if built_prompt:
                first_500 = built_prompt[:500]
                deps.log_info(
                    "WORK_TAILOR_PROMPT_FIRST_500 attempt=%s prompt_chars=%s first_500_hash=%s",
                    attempt,
                    len(built_prompt),
                    hashlib.sha256(first_500.encode("utf-8", errors="ignore")).hexdigest()[:16],
                )
            
            ok, parsed, err = deps.openai_json_schema_call(
                system_prompt=built_prompt,
                user_text=user_text,
                trace_id=trace_id,
                session_id=session_id,
                response_format=deps.get_work_experience_bullets_proposal_response_format(),
                max_output_tokens=2240,
                stage="work_experience",
            )
            
            if not ok or not isinstance(parsed, dict):
                break  # Schema error, can't retry
            
            try:
                prop = deps.parse_work_experience_bullets_proposal(parsed)
                roles = prop.roles if hasattr(prop, 'roles') else []
                
                # Validate bullet lengths (hard limit).
                validation_errors = []
                # Language-aware limit: German is ~25% longer than English
                base_limit = deps.work_experience_hard_limit_chars
                hard_limit = int(base_limit * 1.25) if target_lang == "de" else base_limit
                
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
                    user_text = (
                        f"[JOB_SUMMARY]\n{deps.sanitize_for_prompt(job_summary)}\n\n"
                        f"[TAILORING_SUGGESTIONS]\n{notes}\n\n"
                        f"[TAILORING_FEEDBACK]\n"
                        f"FIX_VALIDATION: Shorten bullets to fit hard limit (<= {hard_limit} chars). "
                        f"Rewrite ONLY affected bullets. Keep 4-5 bullets per role. Do NOT invent facts.\n"
                        f"E0_POLICY_ERRORS: {'; '.join(validation_errors[:6])}\n\n"
                        f"[CURRENT_WORK_EXPERIENCE]\n{roles_text}\n"
                    )
            except Exception as e:
                err = str(e)
                break  # Parse error, can't retry
        
        if not ok or not isinstance(parsed, dict):
            meta2["work_experience_proposal_error"] = str(err)[:400]
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=deps.friendly_schema_error_message(str(err)),
                meta_out=meta2,
                cv_out=cv_data,
            )
        
        # Validation already done in retry loop above.
        # Store structured roles proposal.
        if not prop or not hasattr(prop, 'roles'):
            meta2["work_experience_proposal_error"] = "Invalid proposal structure"
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="AI tailoring output was invalid.",
                meta_out=meta2,
                cv_out=cv_data,
            )
        
        roles = prop.roles if hasattr(prop, 'roles') else []
        proposal_roles = [{
            "title": r.title if hasattr(r, 'title') else "",
            "company": r.company if hasattr(r, 'company') else "",
            "date_range": r.date_range if hasattr(r, 'date_range') else "",
            "location": r.location if hasattr(r, 'location') else "",
            "bullets": list(r.bullets if hasattr(r, 'bullets') else []),
        } for r in roles[:5]]
        meta2["work_experience_proposal_block"] = {
            "roles": proposal_roles,
            "notes": str(prop.notes or ""),
            "created_at": deps.now_iso(),
        }
        if input_fingerprint:
            meta2["work_experience_proposal_input_sig"] = input_fingerprint
        meta2 = deps.wizard_set_stage(meta2, "work_tailor_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Work experience proposal ready. Please review and accept.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    
    if aid == "WORK_TAILOR_ACCEPT":
        proposal_block = meta2.get("work_experience_proposal_block")
        if not isinstance(proposal_block, dict):
            # If the proposal was already applied (or was invalidated), let the user proceed.
            already_applied = bool(meta2.get("work_experience_tailored") or meta2.get("work_experience_proposal_accepted_at"))
            if already_applied:
                meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text="Work experience already applied. Moving to skills.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )

            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="No proposal to apply. Generate it first (or Skip).",
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        # Extract roles from structured proposal
        roles = proposal_block.get("roles")
        if not isinstance(roles, list):
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Proposal was empty or invalid. Generate again.",
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        included_roles = list(roles or [])
    
        if not included_roles:
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Proposal was empty or invalid. Generate again.",
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        # Deterministic guard: never apply a proposal that violates hard limits.
        # (Backend must not truncate CV content under any circumstances.)
        # Language-aware: German is ~25% longer than English
        target_lang_guard = str(meta2.get("target_language") or cv_data.get("language") or "en").strip().lower()
        hard_limit = 250 if target_lang_guard == "de" else 200
        violations: list[str] = []
        for role_idx, r in enumerate(included_roles[:8]):
            rr = deps.normalize_work_role_from_proposal(r) if isinstance(r, dict) else {"employer": "", "bullets": []}
            if not str(rr.get("employer") or "").strip():
                violations.append(f"Role {role_idx+1}: missing employer")
            bullets = rr.get("bullets") if isinstance(rr.get("bullets"), list) else []
            for bullet_idx, b in enumerate(bullets):
                blen = len(str(b or ""))
                if blen > hard_limit:
                    violations.append(f"Role {role_idx+1}, Bullet {bullet_idx+1}: {blen} chars (hard max: {hard_limit})")
        if violations:
            meta2["work_experience_proposal_error"] = "Proposal violates hard limits"
            meta2 = deps.wizard_set_stage(meta2, "work_tailor_feedback")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=(
                    "Cannot apply this proposal because bullets exceed the hard limit. "
                    "Please click 'Regenerate' (or add feedback to shorten bullets) and try again."
                ),
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        # Apply accepted proposal as replace-all (no preserve of legacy unmatched roles).
        prev_work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        cv_data = deps.overwrite_work_experience_from_proposal_roles(cv_data=cv_data, proposal_roles=included_roles)
        cv_data = deps.backfill_missing_work_locations(cv_data=cv_data, previous_work=prev_work, meta=meta2)
    
        proposal_block["roles"] = included_roles
        meta2["work_experience_tailored"] = True
        meta2["work_experience_proposal_accepted_at"] = deps.now_iso()
    
        # Language-aware validation after applying proposal
        base_limit = deps.work_experience_hard_limit_chars
        hard_limit = int(base_limit * 1.25) if target_lang_guard == "de" else base_limit
        violations_after = deps.find_work_bullet_hard_limit_violations(cv_data=cv_data, hard_limit=hard_limit)
        if violations_after:
            try:
                deps.log_warning(
                    "work_experience hard-limit violations after apply: %s",
                    "; ".join(violations_after[:8]),
                )
            except Exception:
                pass
            # Silent auto-retry: regenerate proposal with hard-limit feedback (MCP-like), then re-apply.
            try:
                retry_attempts = 2
                attempt = 0
                job_summary = deps.format_job_reference_for_display(meta2.get("job_reference")) if isinstance(meta2.get("job_reference"), dict) else ""
                notes = deps.escape_user_input_for_prompt(str(meta2.get("work_tailoring_notes") or ""))
                target_lang = str(meta2.get("target_language") or cv_data.get("language") or meta2.get("language") or "en").strip().lower()
    
                work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
                role_blocks = []
                for r in (work or [])[:12]:
                    if not isinstance(r, dict):
                        continue
                    company = deps.sanitize_for_prompt(str(r.get("employer") or r.get("company") or ""))
                    title = deps.sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
                    date = deps.sanitize_for_prompt(str(r.get("date_range") or ""))
                    location = deps.sanitize_for_prompt(str(r.get("location") or r.get("city") or r.get("place") or ""))
                    bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
                    bullet_lines = "\n".join([f"- {deps.sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:12])
                    head = " | ".join([p for p in [title, company, date, location] if p]) or "Role"
                    role_blocks.append(f"{head}\n{bullet_lines}")
                roles_text = "\n\n".join(role_blocks)
    
                payload = deps.build_work_bullet_violation_payload(
                    roles=work or [],
                    hard_limit=hard_limit,
                    min_reduction_chars=30,
                )
                payload_json = json.dumps(payload, ensure_ascii=True)
                bad_roles = deps.select_roles_by_violation_indices(
                    roles=work or [],
                    violations=payload.get("violations") if isinstance(payload, dict) else [],
                )
                bad_role_blocks = []
                for r in bad_roles:
                    if not isinstance(r, dict):
                        continue
                    company = deps.sanitize_for_prompt(str(r.get("employer") or r.get("company") or ""))
                    title = deps.sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
                    date = deps.sanitize_for_prompt(str(r.get("date_range") or ""))
                    bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
                    bullet_lines = "\n".join([f"- {deps.sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:12])
                    head = " | ".join([p for p in [title, company, date] if p]) or "Role"
                    bad_role_blocks.append(f"{head}\n{bullet_lines}")
                bad_roles_text = "\n\n".join(bad_role_blocks) if bad_role_blocks else roles_text
                user_text = (
                    f"[JOB_SUMMARY]\n{deps.sanitize_for_prompt(job_summary)}\n\n"
                    f"[TAILORING_FEEDBACK]\n"
                    f"MCP_VALIDATION_PAYLOAD: {payload_json} "
                    f"Reduce ONLY flagged bullets by >= 30 chars and to <= {hard_limit} chars, "
                    f"without changing tone/meaning/logic. Keep 4-5 bullets per role. Do NOT invent facts.\n\n"
                    f"[CURRENT_WORK_EXPERIENCE]\n{bad_roles_text}\n"
                )
    
                while attempt < retry_attempts:
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
                        break
                    prop = deps.parse_work_experience_bullets_proposal(parsed_we)
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
                    cv_candidate = deps.overwrite_work_experience_from_proposal_roles(
                        cv_data=cv_data,
                        proposal_roles=proposal_roles,
                    )
                    cv_candidate = deps.backfill_missing_work_locations(cv_data=cv_candidate, previous_work=(cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []), meta=meta2)
                    violations_retry = deps.find_work_bullet_hard_limit_violations(
                        cv_data=cv_candidate,
                        hard_limit=hard_limit,
                    )
                    if not violations_retry:
                        cv_data = cv_candidate
                        meta2["work_experience_tailored"] = True
                        meta2["work_experience_proposal_accepted_at"] = deps.now_iso()
                        meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
                        cv_data, meta2 = deps.persist(cv_data, meta2)
                        # Snapshot: Work experience proposal accepted (retry path)
                        deps.snapshot_session(session_id, cv_data, snapshot_type="work_accepted")
                        return True, cv_data, meta2, deps.wizard_resp(
                            assistant_text="Proposal applied. Moving to skills.",
                            meta_out=meta2,
                            cv_out=cv_data,
                        )
            except Exception:
                pass
            meta2["work_experience_proposal_error"] = "Applied proposal violates hard limits"
            meta2 = deps.wizard_set_stage(meta2, "work_tailor_feedback")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=(
                    "Applied work experience still exceeds the hard limit. "
                    "Please click 'Regenerate' to shorten bullets before continuing."
                ),
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        # Snapshot: Work experience proposal accepted (main path)
        deps.snapshot_session(session_id, cv_data, snapshot_type="work_accepted")
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Proposal applied. Moving to skills.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    
    
    return False, cv_data, meta2, None
