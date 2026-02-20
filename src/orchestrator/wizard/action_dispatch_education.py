from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class EducationActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]


def handle_education_basic_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    deps: EducationActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "EDUCATION_EDIT_JSON":
        meta2 = deps.wizard_set_stage(meta2, "education_edit_json")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Edit your education JSON below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "EDUCATION_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "education")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your education below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "EDUCATION_SAVE":
        payload = user_action_payload or {}
        raw = str(payload.get("education_json") or "").strip()
        try:
            parsed = json.loads(raw) if raw else []
            if not isinstance(parsed, list):
                raise ValueError("education_json must be a list")
        except Exception as e:
            meta2 = deps.wizard_set_stage(meta2, "education_edit_json")
            meta2["job_posting_text"] = meta2.get("job_posting_text")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=f"Invalid education JSON: {e}",
                meta_out=meta2,
                cv_out=cv_data,
            )
        cv_data2 = dict(cv_data or {})
        cv_data2["education"] = parsed
        cv_data = cv_data2
        meta2 = deps.wizard_set_stage(meta2, "education")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Saved. Please confirm & lock education.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
