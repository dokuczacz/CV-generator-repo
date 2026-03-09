from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from src import product_config
from src.combined_cv_proposal import (
    get_combined_cv_proposal_response_format,
    parse_combined_cv_proposal,
)
from src.cv_cl_unified_proposal import (
    get_unified_cv_cl_proposal_response_format,
    parse_unified_cv_cl_proposal,
)
from src.orchestrator.wizard.execution_strategy import resolve_execution_strategy


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
    format_job_reference_for_prompt: Callable[[dict], str] | None = None


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
    WORK_TAILORING_NOTES_MAX_CHARS = 8000

    def _capitalize_first_alpha(text: str) -> str:
        s = str(text or "")
        for i, ch in enumerate(s):
            if ch.isalpha():
                return s[:i] + ch.upper() + s[i + 1 :]
        return s

    def _word_count(text: str) -> int:
        return len([w for w in str(text or "").strip().split() if w])

    def _job_summary_for_prompt(job_ref: dict | None) -> str:
        if not isinstance(job_ref, dict):
            return ""
        formatter = deps.format_job_reference_for_prompt or deps.format_job_reference_for_display
        return formatter(job_ref)

    if aid in ("MOVE_WORK_PROPOSAL_UP", "MOVE_WORK_PROPOSAL_DOWN"):
        payload = user_action_payload or {}
        try:
            position_index = int(payload.get("position_index", -1))
        except Exception:
            position_index = -1

        proposal_block = meta2.get("work_experience_proposal_block")
        roles = proposal_block.get("roles") if isinstance(proposal_block, dict) and isinstance(proposal_block.get("roles"), list) else []
        if not isinstance(proposal_block, dict) or not isinstance(roles, list) or not roles:
            meta2 = deps.wizard_set_stage(meta2, "work_tailor_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="No proposal roles to reorder.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        moved = False
        if aid == "MOVE_WORK_PROPOSAL_UP" and position_index > 0 and position_index < len(roles):
            roles[position_index], roles[position_index - 1] = roles[position_index - 1], roles[position_index]
            moved = True
        if aid == "MOVE_WORK_PROPOSAL_DOWN" and position_index >= 0 and position_index < len(roles) - 1:
            roles[position_index], roles[position_index + 1] = roles[position_index + 1], roles[position_index]
            moved = True

        proposal_block2 = dict(proposal_block)
        proposal_block2["roles"] = roles
        meta2["work_experience_proposal_block"] = proposal_block2
        if moved:
            meta2["work_experience_order_source"] = "proposal_manual_reorder"
            msg = f"Moved proposed role {position_index + 1}."
        else:
            msg = "Cannot move: role is already at the edge or index is invalid."

        meta2 = deps.wizard_set_stage(meta2, "work_tailor_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text=msg,
            meta_out=meta2,
            cv_out=cv_data,
        )

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
            _notes = str(payload.get("work_tailoring_notes") or "").strip()[:WORK_TAILORING_NOTES_MAX_CHARS]
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
        if isinstance(payload, dict):
            _target_language = str(payload.get("target_language") or "").strip().lower()
            if _target_language in ("en", "de"):
                meta2["target_language"] = _target_language
            _positioning_mode = str(payload.get("positioning_mode") or "").strip().lower()
            if _positioning_mode:
                meta2["positioning_mode"] = _positioning_mode[:80]
    
        job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
        job_summary = _job_summary_for_prompt(job_ref)
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
                    job_summary = _job_summary_for_prompt(job_ref)
                except Exception as e:
                    meta2["job_reference_error"] = str(e)[:400]
                    meta2["job_reference_status"] = "parse_failed"
            else:
                meta2["job_reference_error"] = str(err_jr)[:400]
                meta2["job_reference_status"] = "call_failed"

        # Strict mode: job summary must come from parsed job_reference (no fallback synthesis).
        if (not str(job_summary or "").strip()) and job_text:
            meta2["work_experience_proposal_error"] = "job_summary_missing_or_unparsed"
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=(
                    "Job summary is missing or could not be parsed. "
                    "Please re-analyze the job posting before running tailoring."
                ),
                meta_out=meta2,
                cv_out=cv_data,
            )
    
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

        # Execution strategy branch:
        # - separate: classic staged calls
        # - unified: one-call path for combined CV (+ optional cover letter)
        experiment_mode = str(product_config.EXPERIMENT_MODE or "baseline").strip().lower()
        execution_strategy, execution_strategy_source = resolve_execution_strategy(payload=payload, meta=meta2)
        meta2["execution_strategy"] = execution_strategy
        meta2["execution_strategy_source"] = execution_strategy_source

        if execution_strategy == "unified":
            current_it_ai = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
            current_tech = (
                cv_data.get("technical_operational_skills")
                if isinstance(cv_data.get("technical_operational_skills"), list)
                else []
            )
            positioning_mode = deps.sanitize_for_prompt(str(meta2.get("positioning_mode") or "").strip())
            combined_user_text = (
                f"{user_text}\n"
                f"[CURRENT_IT_AI_SKILLS]\n"
                + "\n".join([f"- {deps.sanitize_for_prompt(str(s))}" for s in current_it_ai if str(s).strip()])
                + "\n\n"
                f"[CURRENT_TECHNICAL_OPERATIONAL_SKILLS]\n"
                + "\n".join([f"- {deps.sanitize_for_prompt(str(s))}" for s in current_tech if str(s).strip()])
                + "\n\n"
                + f"[POSITIONING_MODE]\n{positioning_mode}\n"
                + "\n"
            )

            # Keep backward compatibility with existing split experiment mode.
            effective_unified_mode = "variant_split" if experiment_mode == "variant_split" else "variant_unified"
            stage_name = "cv_cl_unified" if effective_unified_mode == "variant_unified" else "cv_combined"
            response_format = (
                get_unified_cv_cl_proposal_response_format()
                if effective_unified_mode == "variant_unified"
                else get_combined_cv_proposal_response_format()
            )
            ok_exp, parsed_exp, err_exp = deps.openai_json_schema_call(
                system_prompt=deps.build_ai_system_prompt(stage=stage_name, target_language=target_lang),
                user_text=combined_user_text,
                trace_id=trace_id,
                session_id=session_id,
                response_format=response_format,
                max_output_tokens=3200 if effective_unified_mode == "variant_split" else 3600,
                stage=stage_name,
            )
            if not ok_exp or not isinstance(parsed_exp, dict):
                meta2["work_experience_proposal_error"] = str(err_exp)[:400]
                meta2 = deps.wizard_set_stage(meta2, "work_experience")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=deps.friendly_schema_error_message(str(err_exp)),
                    meta_out=meta2,
                    cv_out=cv_data,
                )

            try:
                if effective_unified_mode == "variant_unified":
                    unified = parse_unified_cv_cl_proposal(parsed_exp)
                    combined = unified.combined_cv
                    cl = unified.cover_letter
                    cl_block = cl.dict()
                    # Unified UX fix: enforce sentence-case opening start (model may return lowercase).
                    cl_block["opening_paragraph"] = _capitalize_first_alpha(str(cl_block.get("opening_paragraph") or ""))

                    # Unified contract guard: keep cover letter length within agreed range.
                    cl_full_text = " ".join(
                        [
                            str(cl_block.get("opening_paragraph") or ""),
                            " ".join([str(p) for p in (cl_block.get("core_paragraphs") or [])]),
                            str(cl_block.get("closing_paragraph") or ""),
                        ]
                    ).strip()
                    cl_words = _word_count(cl_full_text)
                    if cl_words < 220 or cl_words > 320:
                        raise ValueError(
                            f"Unified cover letter length out of range: {cl_words} words (expected 220-320)."
                        )

                    meta2["cover_letter_block"] = cl_block
                    meta2["alignment_notes"] = str(getattr(unified, "alignment_notes", "") or "")[:2000]
                    meta2["cover_letter_input_sig"] = deps.sha256_text(
                        json.dumps(parsed_exp, ensure_ascii=False, sort_keys=True)
                    )
                else:
                    combined = parse_combined_cv_proposal(parsed_exp)

                roles = list(getattr(combined, "roles", []) or [])
                proposal_roles = [
                    {
                        "title": r.title if hasattr(r, "title") else "",
                        "company": r.company if hasattr(r, "company") else "",
                        "date_range": r.date_range if hasattr(r, "date_range") else "",
                        "location": r.location if hasattr(r, "location") else "",
                        "bullets": list(r.bullets if hasattr(r, "bullets") else []),
                    }
                    for r in roles[:5]
                ]

                meta2["work_experience_proposal_block"] = {
                    "roles": proposal_roles,
                    "notes": str(getattr(combined, "notes", "") or ""),
                    "created_at": deps.now_iso(),
                    "experiment_mode": effective_unified_mode,
                    "execution_strategy": execution_strategy,
                }
                meta2["skills_proposal_block"] = {
                    "it_ai_skills": [str(s).strip() for s in list(getattr(combined, "it_ai_skills", []) or []) if str(s).strip()][:8],
                    "technical_operational_skills": [
                        str(s).strip()
                        for s in list(getattr(combined, "technical_operational_skills", []) or [])
                        if str(s).strip()
                    ][:8],
                    "notes": str(getattr(combined, "notes", "") or "")[:500],
                    "created_at": deps.now_iso(),
                    "experiment_mode": effective_unified_mode,
                    "execution_strategy": execution_strategy,
                }
                meta2["skills_proposal_input_sig"] = deps.sha256_text(
                    json.dumps(parsed_exp, ensure_ascii=False, sort_keys=True)
                )
                meta2 = deps.wizard_set_stage(meta2, "work_tailor_review")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=(
                        "Combined CV proposal ready."
                        if effective_unified_mode == "variant_split"
                        else "Unified CV + Cover Letter proposal ready."
                    ),
                    meta_out=meta2,
                    cv_out=cv_data,
                )
            except Exception as exp_parse_err:
                meta2["work_experience_proposal_error"] = str(exp_parse_err)[:400]
                meta2 = deps.wizard_set_stage(meta2, "work_experience")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=deps.friendly_schema_error_message(str(exp_parse_err)),
                    meta_out=meta2,
                    cv_out=cv_data,
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
                # Reuse existing proposal for identical inputs and move user to review.
                # This avoids a perceived no-op when user clicks "Run" again.
                meta2 = deps.wizard_set_stage(meta2, "work_tailor_review")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=(
                        "Loaded existing work proposal for current notes/job context. "
                        "Use Regenerate (force) or edit notes/feedback to create a new version."
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
        meta2["work_experience_order_source"] = "model_relevance_after_accept"
    
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
                job_summary = _job_summary_for_prompt(meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None)
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
