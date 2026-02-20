from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class JobPostingAIDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    openai_enabled: Callable[[], bool]
    build_ai_system_prompt: Callable[..., str]
    openai_json_schema_call: Callable[..., tuple[bool, dict | None, str | None]]
    friendly_schema_error_message: Callable[[str], str]
    format_job_reference_for_display: Callable[[dict], str]
    now_iso: Callable[[], str]
    stable_profile_user_id: Callable[[dict, dict], str | None]
    stable_profile_payload: Callable[..., dict]
    get_profile_store: Callable[[], Any]
    is_http_url: Callable[[str], bool]
    fetch_text_from_url: Callable[[str], tuple[bool, str, str | None]]
    looks_like_job_posting_text: Callable[[str], tuple[bool, str]]
    get_job_reference_response_format: Callable[[], dict]
    parse_job_reference: Callable[[dict], Any]


def handle_job_posting_ai_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    trace_id: str,
    session_id: str,
    deps: JobPostingAIDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "INTERESTS_TAILOR_RUN":
        if not deps.openai_enabled():
            meta2 = deps.wizard_set_stage(meta2, "interests_edit")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="AI is not configured. You can still edit interests manually.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        current_interests = str(cv_data.get("interests") or "").strip()
        job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
        job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
        job_text = str(meta2.get("job_posting_text") or "").strip()
        target_lang = str(meta2.get("target_language") or meta2.get("language") or cv_data.get("language") or "en").strip().lower()

        ctx = {
            "current_interests": current_interests,
            "job_summary": job_summary,
            "job_text_excerpt": job_text[:1200] if job_text else "",
        }

        ok, parsed, err = deps.openai_json_schema_call(
            system_prompt=deps.build_ai_system_prompt(
                stage="interests",
                target_language=target_lang,
                extra=(
                    "You may reorder or select a subset of the provided interests to best fit the job, "
                    "but you MUST NOT invent new interests.\n"
                    "Return JSON only."
                ),
            ),
            user_text=json.dumps(ctx, ensure_ascii=False),
            trace_id=trace_id,
            session_id=session_id,
            response_format={
                "type": "json_schema",
                "name": "interests_tailor",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"interests": {"type": "string"}},
                    "required": ["interests"],
                },
            },
            max_output_tokens=220,
            stage="interests",
        )
        if not ok or not isinstance(parsed, dict):
            meta2 = deps.wizard_set_stage(meta2, "interests_edit")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=deps.friendly_schema_error_message(str(err)),
                meta_out=meta2,
                cv_out=cv_data,
            )

        tailored = str(parsed.get("interests") or "").strip()[:400]
        cv2 = dict(cv_data or {})
        cv2["interests"] = tailored
        cv_data = cv2
        meta2["interests_tailored"] = True
        meta2["interests_tailored_at"] = deps.now_iso()

        try:
            user_id = deps.stable_profile_user_id(cv_data, meta2)
            if user_id:
                prof = deps.stable_profile_payload(cv_data=cv_data, meta=meta2)
                ref = deps.get_profile_store().put_latest(
                    user_id=user_id,
                    payload=prof,
                    target_language=str(prof.get("target_language") or ""),
                )
                meta2["stable_profile_saved"] = True
                meta2["stable_profile_ref"] = {"store": ref.store, "key": ref.key}
        except Exception:
            pass

        meta2 = deps.wizard_set_stage(meta2, "job_posting")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Interests tailored and saved.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "JOB_OFFER_CONTINUE":
        jt = str(meta2.get("job_posting_text") or "")[:20000]
        if jt:
            ok_job_text, reason_job_text = deps.looks_like_job_posting_text(jt)
            if not ok_job_text:
                meta2["job_input_status"] = "invalid"
                meta2["job_input_invalid_reason"] = reason_job_text
                meta2["job_posting_invalid_draft"] = jt[:2000]
                meta2["job_posting_text"] = ""
                meta2["job_reference_status"] = "invalid_job_input"
                meta2 = deps.wizard_set_stage(meta2, "job_posting_invalid_input")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text="Provided text cannot be used as job posting source. Choose how to proceed.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )

        if not isinstance(meta2.get("job_reference"), dict) and deps.openai_enabled():
            if len(jt) >= 80:
                ok, parsed, err = deps.openai_json_schema_call(
                    system_prompt=deps.build_ai_system_prompt(stage="job_posting"),
                    user_text=jt,
                    trace_id=trace_id,
                    session_id=session_id,
                    response_format=deps.get_job_reference_response_format(),
                    max_output_tokens=1200,
                    stage="job_posting",
                )
                if ok and isinstance(parsed, dict):
                    try:
                        jr = deps.parse_job_reference(parsed)
                        meta2["job_reference"] = jr.dict()
                        meta2["job_reference_status"] = "ok"
                    except Exception as e:
                        meta2["job_reference_error"] = str(e)[:400]
                        meta2["job_reference_status"] = "parse_failed"
                else:
                    meta2["job_reference_error"] = str(err)[:400]
                    meta2["job_reference_status"] = "call_failed"

        meta2 = deps.wizard_set_stage(meta2, "work_notes_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Add tailoring suggestions for your work experience.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "JOB_OFFER_ANALYZE":
        payload = user_action_payload or {}
        text = str(payload.get("job_offer_text") or "").strip()
        is_url = deps.is_http_url(text)

        if is_url:
            meta2["job_posting_url"] = text
            ok, fetched_text, err = deps.fetch_text_from_url(text)
            if not ok:
                meta2 = deps.wizard_set_stage(meta2, "job_posting_paste")
                cv_data, meta2 = deps.persist(cv_data, meta2)
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=f"Could not fetch job offer URL ({err}). Please paste the full description.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )
            candidate_text = fetched_text[:20000]
        else:
            candidate_text = text[:20000] if text else ""

        meta2["job_posting_text"] = candidate_text

        job_text_len = len(meta2.get("job_posting_text") or "")
        if job_text_len < 80:
            meta2["job_input_status"] = "invalid"
            meta2["job_input_invalid_reason"] = "too_short"
            meta2["job_posting_invalid_draft"] = str(meta2.get("job_posting_text") or "")[:2000]
            meta2["job_posting_text"] = ""
            meta2["job_reference_status"] = "invalid_job_input"
            meta2 = deps.wizard_set_stage(meta2, "job_posting_invalid_input")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Job input is too short. Choose: correct URL, paste proper job text, or continue without summary.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        ok_job_text, reason_job_text = deps.looks_like_job_posting_text(str(meta2.get("job_posting_text") or ""))
        if not ok_job_text:
            meta2["job_input_status"] = "invalid"
            meta2["job_input_invalid_reason"] = reason_job_text
            meta2["job_posting_invalid_draft"] = str(meta2.get("job_posting_text") or "")[:2000]
            meta2["job_posting_text"] = ""
            meta2["job_reference_status"] = "invalid_job_input"
            meta2 = deps.wizard_set_stage(meta2, "job_posting_invalid_input")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Input looks like candidate notes, not a job posting. Choose how to proceed.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        job_reference_status = "skipped"
        if deps.openai_enabled():
            ok, parsed, err = deps.openai_json_schema_call(
                system_prompt=deps.build_ai_system_prompt(stage="job_posting"),
                user_text=str(meta2.get("job_posting_text") or "")[:20000],
                trace_id=trace_id,
                session_id=session_id,
                response_format=deps.get_job_reference_response_format(),
                max_output_tokens=1200,
                stage="job_posting",
            )
            if ok and isinstance(parsed, dict):
                try:
                    jr = deps.parse_job_reference(parsed)
                    meta2["job_reference"] = jr.dict()
                    job_reference_status = "ok"
                except Exception as e:
                    meta2["job_reference_error"] = str(e)[:400]
                    job_reference_status = "parse_failed"
            else:
                meta2["job_reference_error"] = str(err)[:400]
                job_reference_status = "call_failed"
        meta2["job_reference_status"] = job_reference_status

        meta2 = deps.wizard_set_stage(meta2, "work_notes_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Job offer captured. Add tailoring suggestions for your work experience.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
