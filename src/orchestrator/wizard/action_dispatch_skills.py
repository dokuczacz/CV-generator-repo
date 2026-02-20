from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SkillsActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    append_event: Callable[[str, dict], Any]
    sha256_text: Callable[[str], str]
    now_iso: Callable[[], str]
    openai_enabled: Callable[[], bool]
    format_job_reference_for_display: Callable[[dict], str]
    escape_user_input_for_prompt: Callable[[str], str]
    collect_raw_docx_skills_context: Callable[..., list[str]]
    sanitize_for_prompt: Callable[[str], str]
    openai_json_schema_call: Callable[..., tuple[bool, dict | None, str | None]]
    build_ai_system_prompt: Callable[..., str]
    get_skills_unified_proposal_response_format: Callable[[], dict]
    friendly_schema_error_message: Callable[[str], str]
    parse_skills_unified_proposal: Callable[[dict], Any]
    dedupe_strings_case_insensitive: Callable[..., list[str]]
    find_work_bullet_hard_limit_violations: Callable[..., list[str]]
    snapshot_session: Callable[..., Any]


def handle_skills_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    trace_id: str,
    deps: SkillsActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "SKILLS_ADD_NOTES":
        # Persist inline work tailoring context before navigating away.
        payload = user_action_payload or {}
        if "work_tailoring_notes" in payload:
            _w = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
            meta2["work_tailoring_notes"] = _w
        meta2 = deps.wizard_set_stage(meta2, "skills_notes_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Add ranking notes below (optional).", meta_out=meta2, cv_out=cv_data)
    
    if aid == "SKILLS_NOTES_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Review your IT/AI skills below.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "SKILLS_NOTES_SAVE":
        payload = user_action_payload or {}
        _notes = str(payload.get("skills_ranking_notes") or "").strip()[:2000]
        meta2["skills_ranking_notes"] = _notes
        try:
            deps.append_event(
                session_id,
                {
                    "type": "wizard_notes_saved",
                    "stage": "it_ai_skills",
                    "field": "skills_ranking_notes",
                    "text_len": len(_notes),
                    "text_sha256": deps.sha256_text(_notes),
                    "ts_utc": deps.now_iso(),
                },
            )
        except Exception:
            pass
        meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Notes saved.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "SKILLS_TAILOR_SKIP":
        # Persist work tailoring context edits (shown inline in this step).
        payload = user_action_payload or {}
        if "work_tailoring_notes" in payload:
            _w = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
            meta2["work_tailoring_notes"] = _w
            try:
                deps.append_event(
                    session_id,
                    {
                        "type": "wizard_notes_saved",
                        "stage": "it_ai_skills",
                        "field": "work_tailoring_notes",
                        "text_len": len(_w),
                        "text_sha256": deps.sha256_text(_w),
                        "ts_utc": deps.now_iso(),
                    },
                )
            except Exception:
                pass
        # Also persist ranking notes if the UI sent them (e.g., user clicked Generate/Continue without Save).
        if "skills_ranking_notes" in payload:
            meta2["skills_ranking_notes"] = str(payload.get("skills_ranking_notes") or "").strip()[:2000]
    
        # If the user skips ranking, we should still carry forward any skills
        # extracted from the uploaded DOCX into the canonical cv_data used for rendering.
        # Otherwise the PDF template will render empty skills sections.
        cv2 = dict(cv_data or {})
        dpu = meta2.get("docx_prefill_unconfirmed") if isinstance(meta2.get("docx_prefill_unconfirmed"), dict) else None
    
        cv_it = cv2.get("it_ai_skills") if isinstance(cv2.get("it_ai_skills"), list) else []
        cv_tech = cv2.get("technical_operational_skills") if isinstance(cv2.get("technical_operational_skills"), list) else []
    
        dpu_it = dpu.get("it_ai_skills") if isinstance(dpu, dict) and isinstance(dpu.get("it_ai_skills"), list) else []
        dpu_tech = dpu.get("technical_operational_skills") if isinstance(dpu, dict) and isinstance(dpu.get("technical_operational_skills"), list) else []
    
        if (not cv_it) and (not cv_tech):
            # Split docx skills into two buckets to avoid an empty second section.
            combined: list[str] = []
            seen_lower: set[str] = set()
            for s in list(dpu_it) + list(dpu_tech):
                s_str = str(s).strip()
                if s_str and s_str.lower() not in seen_lower:
                    seen_lower.add(s_str.lower())
                    combined.append(s_str)
            if combined:
                # Distribute across both buckets so the template doesn't render an empty second section.
                if len(combined) == 1:
                    cv2["it_ai_skills"] = combined[:1]
                    cv2["technical_operational_skills"] = combined[:1]
                else:
                    mid = max(1, min(8, (len(combined) + 1) // 2))
                    it = list(combined[:mid])
                    tech = list(combined[mid : mid + 8])
                    if not tech and len(it) > 1:
                        tech = [it.pop()]
                    cv2["it_ai_skills"] = it[:8]
                    cv2["technical_operational_skills"] = tech[:8]
        else:
            # Fill missing bucket from docx prefill if needed.
            if (not cv_it) and dpu_it:
                cv2["it_ai_skills"] = [str(s).strip() for s in dpu_it if str(s).strip()][:8]
            if (not cv_tech) and dpu_tech:
                cv2["technical_operational_skills"] = [str(s).strip() for s in dpu_tech if str(s).strip()][:8]
    
        cv_data = cv2
        meta2 = deps.wizard_set_stage(meta2, "review_final")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Skipped skills ranking. Ready to generate PDF.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "SKILLS_TAILOR_RUN":
        # Persist work tailoring context edits (shown inline in this step) before ranking.
        payload = user_action_payload or {}
        if "work_tailoring_notes" in payload:
            _w = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
            meta2["work_tailoring_notes"] = _w
            try:
                deps.append_event(
                    session_id,
                    {
                        "type": "wizard_notes_saved",
                        "stage": "it_ai_skills",
                        "field": "work_tailoring_notes",
                        "text_len": len(_w),
                        "text_sha256": deps.sha256_text(_w),
                        "ts_utc": deps.now_iso(),
                    },
                )
            except Exception:
                pass
        if "skills_ranking_notes" in payload:
            meta2["skills_ranking_notes"] = str(payload.get("skills_ranking_notes") or "").strip()[:2000]
    
        if not deps.openai_enabled():
            meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="AI ranking is not configured.", meta_out=meta2, cv_out=cv_data)
    
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
    
        ok, parsed, err = deps.openai_json_schema_call(
            system_prompt=deps.build_ai_system_prompt(stage="it_ai_skills", target_language=target_lang),
            user_text=user_text,
            trace_id=trace_id,
            session_id=session_id,
            response_format=deps.get_skills_unified_proposal_response_format(),
            max_output_tokens=1680,
            stage="it_ai_skills",
        )
        if not ok or not isinstance(parsed, dict):
            meta2["skills_proposal_error"] = str(err)[:400]
            meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=deps.friendly_schema_error_message(str(err)), meta_out=meta2, cv_out=cv_data)
        
        try:
            prop = deps.parse_skills_unified_proposal(parsed)
            it_ai_skills = prop.it_ai_skills if hasattr(prop, 'it_ai_skills') else []
            tech_ops_skills = prop.technical_operational_skills if hasattr(prop, 'technical_operational_skills') else []
            meta2["skills_proposal_block"] = {
                "it_ai_skills": deps.dedupe_strings_case_insensitive(list(it_ai_skills), max_items=8),
                "technical_operational_skills": deps.dedupe_strings_case_insensitive(list(tech_ops_skills), max_items=8),
                "notes": str(prop.notes or "")[:500],
                "openai_response_id": str(parsed.get("_openai_response_id") or "")[:120],
                "created_at": deps.now_iso(),
            }
            meta2 = deps.wizard_set_stage(meta2, "skills_tailor_review")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Skills ranking ready.", meta_out=meta2, cv_out=cv_data)
        except Exception as e:
            meta2["skills_proposal_error"] = str(e)[:400]
            meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=deps.friendly_schema_error_message(str(e)), meta_out=meta2, cv_out=cv_data)
    
    if aid == "SKILLS_TAILOR_ACCEPT":
        # Persist work tailoring context edits (shown inline in this step).
        payload = user_action_payload or {}
        if "work_tailoring_notes" in payload:
            _w = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
            meta2["work_tailoring_notes"] = _w
            try:
                deps.append_event(
                    session_id,
                    {
                        "type": "wizard_notes_saved",
                        "stage": "it_ai_skills",
                        "field": "work_tailoring_notes",
                        "text_len": len(_w),
                        "text_sha256": deps.sha256_text(_w),
                        "ts_utc": deps.now_iso(),
                    },
                )
            except Exception:
                pass
    
        proposal_block = meta2.get("skills_proposal_block")
        if not isinstance(proposal_block, dict):
            meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="No proposal to apply.", meta_out=meta2, cv_out=cv_data)
    
        # Apply both skill sections directly from the unified proposal
        it_ai_skills = proposal_block.get("it_ai_skills")
        tech_ops_skills = proposal_block.get("technical_operational_skills")
        
        if not isinstance(it_ai_skills, list) or not isinstance(tech_ops_skills, list):
            meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Proposal was empty or invalid.", meta_out=meta2, cv_out=cv_data)
    
        cv2 = dict(cv_data or {})
        it_ai_clean = deps.dedupe_strings_case_insensitive(list(it_ai_skills), max_items=8)
        tech_ops_clean = deps.dedupe_strings_case_insensitive(list(tech_ops_skills), max_items=8)
        # De-duplicate across sections (IT/AI wins ties; avoid repeated skills in both lists).
        it_ai_set = {s.casefold() for s in it_ai_clean}
        tech_ops_clean = [s for s in tech_ops_clean if s.casefold() not in it_ai_set][:8]
        cv2["it_ai_skills"] = it_ai_clean
        cv2["technical_operational_skills"] = tech_ops_clean
        
        cv_data = cv2
        meta2["it_ai_skills_tailored"] = True
        meta2["skills_proposal_accepted_at"] = deps.now_iso()
    
        violations_after = deps.find_work_bullet_hard_limit_violations(cv_data=cv_data, hard_limit=200)
        if violations_after:
            meta2["work_experience_proposal_error"] = "Work experience violates hard limits"
            meta2 = deps.wizard_set_stage(meta2, "work_tailor_feedback")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=(
                    "Work experience still violates hard limits:\n"
                    + "\n".join(violations_after[:5])
                    + "\n\nPlease regenerate the work experience proposal before generating the PDF."
                ),
                meta_out=meta2,
                cv_out=cv_data,
            )
    
        meta2 = deps.wizard_set_stage(meta2, "review_final")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        # Snapshot: Skills proposal accepted
        deps.snapshot_session(session_id, cv_data, snapshot_type="skills_accepted")
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Proposal applied. Ready to generate PDF.", meta_out=meta2, cv_out=cv_data)
    
    # ====== SKILLS REORDERING/REMOVAL ACTIONS ======
    if aid == "REMOVE_SKILL_IT_AI":
        payload = user_action_payload or {}
        try:
            skill_index = int(payload.get("skill_index", -1))
        except Exception:
            skill_index = -1
        
        skills = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
        if 0 <= skill_index < len(skills):
            removed_skill = skills.pop(skill_index)
            cv_data["it_ai_skills"] = skills
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="skill_removed")
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=f"Removed '{removed_skill}' from IT & AI skills.", meta_out=meta2, cv_out=cv_data)
        else:
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Invalid skill index.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "REORDER_SKILLS_IT_AI":
        payload = user_action_payload or {}
        try:
            from_index = int(payload.get("from_index", -1))
            to_index = int(payload.get("to_index", -1))
        except Exception:
            from_index = -1
            to_index = -1
        
        skills = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
        if 0 <= from_index < len(skills) and 0 <= to_index < len(skills):
            skill = skills.pop(from_index)
            skills.insert(to_index, skill)
            cv_data["it_ai_skills"] = skills
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="skills_reordered")
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="IT & AI skills reordered.", meta_out=meta2, cv_out=cv_data)
        else:
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Invalid skill indices.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "CLEAR_SKILLS_IT_AI":
        cv_data["it_ai_skills"] = []
        cv_data, meta2 = deps.persist(cv_data, meta2)
        deps.snapshot_session(session_id, cv_data, snapshot_type="skills_cleared")
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cleared all IT & AI skills.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "REMOVE_SKILL_TECHNICAL_OPERATIONAL":
        payload = user_action_payload or {}
        try:
            skill_index = int(payload.get("skill_index", -1))
        except Exception:
            skill_index = -1
        
        skills = cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else []
        if 0 <= skill_index < len(skills):
            removed_skill = skills.pop(skill_index)
            cv_data["technical_operational_skills"] = skills
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="skill_removed")
            return True, cv_data, meta2, deps.wizard_resp(assistant_text=f"Removed '{removed_skill}' from Technical & Operational skills.", meta_out=meta2, cv_out=cv_data)
        else:
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Invalid skill index.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "REORDER_SKILLS_TECHNICAL_OPERATIONAL":
        payload = user_action_payload or {}
        try:
            from_index = int(payload.get("from_index", -1))
            to_index = int(payload.get("to_index", -1))
        except Exception:
            from_index = -1
            to_index = -1
        
        skills = cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else []
        if 0 <= from_index < len(skills) and 0 <= to_index < len(skills):
            skill = skills.pop(from_index)
            skills.insert(to_index, skill)
            cv_data["technical_operational_skills"] = skills
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="skills_reordered")
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Technical & Operational skills reordered.", meta_out=meta2, cv_out=cv_data)
        else:
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(assistant_text="Invalid skill indices.", meta_out=meta2, cv_out=cv_data)
    
    if aid == "CLEAR_SKILLS_TECHNICAL_OPERATIONAL":
        cv_data["technical_operational_skills"] = []
        cv_data, meta2 = deps.persist(cv_data, meta2)
        deps.snapshot_session(session_id, cv_data, snapshot_type="skills_cleared")
        return True, cv_data, meta2, deps.wizard_resp(assistant_text="Cleared all Technical & Operational skills.", meta_out=meta2, cv_out=cv_data)
    
    
    return False, cv_data, meta2, None
