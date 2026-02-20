from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class JobPostingBasicDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    stable_profile_user_id: Callable[[dict, dict], str | None]
    stable_profile_payload: Callable[..., dict]
    get_profile_store: Callable[[], Any]


def handle_job_posting_basic_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    deps: JobPostingBasicDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "JOB_OFFER_PASTE":
        meta2 = deps.wizard_set_stage(meta2, "job_posting_paste")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Paste the job offer text below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid in ("JOB_OFFER_INVALID_FIX_URL", "JOB_OFFER_INVALID_PASTE_TEXT"):
        draft = str(meta2.get("job_posting_invalid_draft") or "")[:20000]
        if draft:
            meta2["job_posting_text"] = draft
        meta2 = deps.wizard_set_stage(meta2, "job_posting_paste")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Please correct the URL or paste a full job description, then Analyze.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "JOB_OFFER_INVALID_CONTINUE_NO_SUMMARY":
        meta2["job_posting_text"] = ""
        meta2["job_input_status"] = "skipped_no_summary"
        meta2["job_reference_status"] = "skipped_no_job_summary"
        meta2.pop("job_reference", None)
        meta2.pop("job_reference_error", None)
        meta2["job_reference_sig"] = ""
        meta2 = deps.wizard_set_stage(meta2, "work_notes_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Continuing without job summary. You can still add tailoring notes manually.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "INTERESTS_EDIT":
        meta2 = deps.wizard_set_stage(meta2, "interests_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Edit interests below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "INTERESTS_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "job_posting")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Back to job offer.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "INTERESTS_SAVE":
        payload = user_action_payload or {}
        interests = str(payload.get("interests") or "").strip()[:400]
        cv2 = dict(cv_data or {})
        cv2["interests"] = interests
        cv_data = cv2

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
            assistant_text="Interests saved.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "JOB_OFFER_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "job_posting")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Optionally add a job offer for tailoring (or skip).",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "JOB_OFFER_SKIP":
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your work experience roles below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
