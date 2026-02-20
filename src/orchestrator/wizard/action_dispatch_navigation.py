from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class NavigationActionDeps:
    wizard_get_stage: Callable[[dict], str]
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    log_info: Callable[..., Any]


def _major(st: str) -> int | None:
    s = str(st or "").strip().lower()
    if s in ("contact", "contact_edit"):
        return 1
    if s in ("education", "education_edit_json"):
        return 2
    if s in ("job_posting", "job_posting_paste", "interests_edit"):
        return 3
    if s in ("work_experience", "work_notes_edit", "work_tailor_review", "work_tailor_feedback", "work_select_role", "work_role_view", "work_locations_edit"):
        return 4
    if s in ("it_ai_skills", "skills_notes_edit", "skills_tailor_review"):
        return 5
    if s in ("review_final", "generate_confirm", "cover_letter_review"):
        return 6
    return None


def handle_navigation_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    deps: NavigationActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid != "WIZARD_GOTO_STAGE":
        return False, cv_data, meta2, None

    payload = user_action_payload or {}
    target = str(payload.get("target_stage") or "").strip().lower()

    cur_stage = deps.wizard_get_stage(meta2)
    cur_major = _major(cur_stage)
    tgt_major = _major(target)
    if cur_major is None or tgt_major is None:
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Cannot navigate: unknown stage.",
            meta_out=meta2,
            cv_out=cv_data,
        )
    if tgt_major > cur_major:
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Cannot jump forward. Finish the current step first.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    stage_history = meta2.get("stage_history") if isinstance(meta2.get("stage_history"), list) else []
    if not isinstance(stage_history, list):
        stage_history = []

    if cur_stage and (not stage_history or stage_history[-1] != cur_stage):
        stage_history.append(cur_stage)
        meta2["stage_history"] = stage_history[-20:]

    major_to_stage = {1: "contact", 2: "education", 3: "job_posting", 4: "work_experience", 5: "it_ai_skills", 6: "review_final"}
    target_stage_resolved = major_to_stage.get(tgt_major, cur_stage)
    meta2 = deps.wizard_set_stage(meta2, target_stage_resolved)

    meta2.pop("work_selected_index", None)
    cv_data, meta2 = deps.persist(cv_data, meta2)

    try:
        deps.log_info(
            "WIZARD_NAV from=%s to=%s (major: %s -> %s) history_len=%s",
            cur_stage,
            target_stage_resolved,
            cur_major,
            tgt_major,
            len(stage_history),
        )
    except Exception:
        pass

    return True, cv_data, meta2, deps.wizard_resp(
        assistant_text=f"Navigated to {target_stage_resolved}.",
        meta_out=meta2,
        cv_out=cv_data,
    )
