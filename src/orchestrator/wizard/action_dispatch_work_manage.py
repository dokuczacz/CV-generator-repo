from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class WorkManageActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    snapshot_session: Callable[..., Any]
    work_role_lock_key: Callable[..., str]


def handle_work_manage_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    deps: WorkManageActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "WORK_SELECT_ROLE":
        meta2 = deps.wizard_set_stage(meta2, "work_select_role")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Select a role index to review.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_SELECT_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        meta2.pop("work_selected_index", None)
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your work experience roles below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_OPEN_ROLE":
        payload = user_action_payload or {}
        raw_idx = str(payload.get("role_index") or "").strip()
        try:
            i = int(raw_idx)
        except Exception:
            i = -1
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if not (0 <= i < len(work)):
            meta2 = deps.wizard_set_stage(meta2, "work_select_role")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Invalid role index",
                meta_out=meta2,
                cv_out=cv_data,
            )
        meta2["work_selected_index"] = i
        meta2 = deps.wizard_set_stage(meta2, "work_role_view")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text=f"Review role #{i} below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_LOCK_ROLE":
        try:
            i = int(meta2.get("work_selected_index"))
        except Exception:
            i = -1
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if not (0 <= i < len(work)):
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            meta2.pop("work_selected_index", None)
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Invalid role index",
                meta_out=meta2,
                cv_out=cv_data,
            )
        locks = meta2.get("work_role_locks") if isinstance(meta2.get("work_role_locks"), dict) else {}
        locks = dict(locks or {})
        locks[deps.work_role_lock_key(role_index=i)] = True
        meta2["work_role_locks"] = locks
        meta2 = deps.wizard_set_stage(meta2, "work_role_view")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Role locked.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_UNLOCK_ROLE":
        try:
            i = int(meta2.get("work_selected_index"))
        except Exception:
            i = -1
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if not (0 <= i < len(work)):
            meta2 = deps.wizard_set_stage(meta2, "work_experience")
            meta2.pop("work_selected_index", None)
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Invalid role index",
                meta_out=meta2,
                cv_out=cv_data,
            )
        locks = meta2.get("work_role_locks") if isinstance(meta2.get("work_role_locks"), dict) else {}
        locks = dict(locks or {})
        locks.pop(deps.work_role_lock_key(role_index=i), None)
        meta2["work_role_locks"] = locks
        meta2 = deps.wizard_set_stage(meta2, "work_role_view")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Role unlocked.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_TOGGLE_LOCK":
        payload = user_action_payload or {}
        raw = payload.get("role_index")
        raw_idx = "" if raw is None else str(raw).strip()
        try:
            i = int(raw_idx)
        except Exception:
            i = -1
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if not (0 <= i < len(work)):
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Invalid role index",
                meta_out=meta2,
                cv_out=cv_data,
            )

        locks = meta2.get("work_role_locks") if isinstance(meta2.get("work_role_locks"), dict) else {}
        locks = dict(locks or {})
        k = deps.work_role_lock_key(role_index=i)
        if locks.get(k) is True:
            locks.pop(k, None)
            msg = "Role unlocked."
        else:
            locks[k] = True
            msg = "Role locked."
        meta2["work_role_locks"] = locks
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text=msg,
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "WORK_BACK_TO_LIST":
        meta2 = deps.wizard_set_stage(meta2, "work_experience")
        meta2.pop("work_selected_index", None)
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your work experience roles below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "MOVE_WORK_EXPERIENCE_UP":
        payload = user_action_payload or {}
        try:
            position_index = int(payload.get("position_index", -1))
        except Exception:
            position_index = -1

        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if position_index > 0 and position_index < len(work):
            work[position_index], work[position_index - 1] = work[position_index - 1], work[position_index]
            cv_data["work_experience"] = work
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="work_reordered")
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=f"Moved position {position_index + 1} up.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Cannot move: position is already at the top or invalid.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "MOVE_WORK_EXPERIENCE_DOWN":
        payload = user_action_payload or {}
        try:
            position_index = int(payload.get("position_index", -1))
        except Exception:
            position_index = -1

        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if position_index >= 0 and position_index < len(work) - 1:
            work[position_index], work[position_index + 1] = work[position_index + 1], work[position_index]
            cv_data["work_experience"] = work
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="work_reordered")
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=f"Moved position {position_index + 1} down.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Cannot move: position is already at the bottom or invalid.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "REMOVE_WORK_EXPERIENCE":
        payload = user_action_payload or {}
        try:
            position_index = int(payload.get("position_index", -1))
        except Exception:
            position_index = -1

        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if 0 <= position_index < len(work):
            removed_employer = work[position_index].get("employer", "position") if isinstance(work[position_index], dict) else "position"
            work.pop(position_index)
            cv_data["work_experience"] = work
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="work_removed")
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=f"Removed {removed_employer}.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Invalid position index.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "REMOVE_WORK_EXPERIENCE_BULLET":
        payload = user_action_payload or {}
        try:
            position_index = int(payload.get("position_index", -1))
            bullet_index = int(payload.get("bullet_index", -1))
        except Exception:
            position_index = -1
            bullet_index = -1

        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if 0 <= position_index < len(work):
            role = work[position_index] if isinstance(work[position_index], dict) else {}
            bullets = role.get("bullets") if isinstance(role.get("bullets"), list) else []
            if 0 <= bullet_index < len(bullets):
                bullets.pop(bullet_index)
                role["bullets"] = bullets
                work[position_index] = role
                cv_data["work_experience"] = work
                cv_data, meta2 = deps.persist(cv_data, meta2)
                deps.snapshot_session(session_id, cv_data, snapshot_type="bullet_removed")
                return True, cv_data, meta2, deps.wizard_resp(
                    assistant_text=f"Removed bullet {bullet_index + 1} from position {position_index + 1}.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )

        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Invalid position or bullet index.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "CLEAR_WORK_EXPERIENCE_BULLETS":
        payload = user_action_payload or {}
        try:
            position_index = int(payload.get("position_index", -1))
        except Exception:
            position_index = -1

        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        if 0 <= position_index < len(work):
            role = work[position_index] if isinstance(work[position_index], dict) else {}
            role["bullets"] = []
            work[position_index] = role
            cv_data["work_experience"] = work
            cv_data, meta2 = deps.persist(cv_data, meta2)
            deps.snapshot_session(session_id, cv_data, snapshot_type="bullets_cleared")
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text=f"Cleared all bullets from position {position_index + 1}.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Invalid position index.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
