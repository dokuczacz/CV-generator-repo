from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class WorkBasicActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    append_event: Callable[[str, dict], Any]
    sha256_text: Callable[[str], str]
    now_iso: Callable[[], str]


def handle_work_basic_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    deps: WorkBasicActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "WORK_ADD_TAILORING_NOTES":
        meta2 = deps.wizard_set_stage(meta2, "work_notes_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Add tailoring notes below (optional).",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_LOCATIONS_EDIT":
        meta2 = deps.wizard_set_stage(meta2, "work_locations_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Fill missing locations below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_LOCATIONS_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Back to work experience.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_LOCATIONS_SAVE":
        payload = user_action_payload or {}
        raw = str(payload.get("work_locations_lines") or "")
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        work_list = list(work) if isinstance(work, list) else []

        updated = 0
        for line in raw.splitlines():
            s = (line or "").strip()
            if not s or s.startswith("#"):
                continue
            s = s.split("#", 1)[0].strip()
            if not s:
                continue
            if "|" in s:
                left, right = s.split("|", 1)
            elif ":" in s:
                left, right = s.split(":", 1)
            else:
                continue
            try:
                idx = int(left.strip())
            except Exception:
                continue
            loc = right.strip()
            if not loc:
                continue
            if 0 <= idx < len(work_list) and isinstance(work_list[idx], dict):
                role2 = dict(work_list[idx])
                role2["location"] = loc
                work_list[idx] = role2
                updated += 1

        cv2 = dict(cv_data or {})
        cv2["work_experience"] = work_list
        cv_data = cv2
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text=f"Saved locations ({updated} updated).",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_TAILOR_FEEDBACK":
        meta2 = deps.wizard_set_stage(meta2, "work_tailor_feedback")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Add feedback to improve the proposal.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_TAILOR_FEEDBACK_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "work_tailor_review")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review the current proposal below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_NOTES_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your work experience roles below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_NOTES_SAVE":
        payload = user_action_payload or {}
        notes = str(payload.get("work_tailoring_notes") or "").strip()[:2000]
        meta2["work_tailoring_notes"] = notes
        try:
            deps.append_event(
                session_id,
                {
                    "type": "wizard_notes_saved",
                    "stage": "work_experience",
                    "field": "work_tailoring_notes",
                    "text_len": len(notes),
                    "text_sha256": deps.sha256_text(notes),
                    "ts_utc": deps.now_iso(),
                },
            )
        except Exception:
            pass
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Notes saved.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_TAILOR_SKIP":
        meta2 = deps.wizard_set_stage(meta2, "it_ai_skills")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Skipped work tailoring. Moving to skills.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
