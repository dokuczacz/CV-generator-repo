from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ContactActionDeps:
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    now_iso: Callable[[], str]
    log_info: Callable[..., Any]


def handle_contact_and_language_actions(
    *,
    aid: str,
    user_action_payload: dict | None,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    deps: ContactActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid == "CONTACT_EDIT":
        meta2 = deps.wizard_set_stage(meta2, "contact_edit")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Edit your contact details below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "CONTACT_CANCEL":
        meta2 = deps.wizard_set_stage(meta2, "contact")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your contact details below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "CONTACT_SAVE":
        payload = user_action_payload or {}
        cv_data2 = dict(cv_data or {})
        cv_data2["full_name"] = str(payload.get("full_name") or "").strip()
        cv_data2["email"] = str(payload.get("email") or "").strip()
        cv_data2["phone"] = str(payload.get("phone") or "").strip()
        addr = str(payload.get("address") or "").strip()
        if addr:
            cv_data2["address_lines"] = [ln.strip() for ln in addr.splitlines() if ln.strip()]
        cv_data = cv_data2
        meta2 = deps.wizard_set_stage(meta2, "contact")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Saved. Please confirm & lock contact.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid in ("LANGUAGE_SELECT_EN", "LANGUAGE_SELECT_DE", "LANGUAGE_SELECT_PL"):
        lang_map = {"LANGUAGE_SELECT_EN": "en", "LANGUAGE_SELECT_DE": "de", "LANGUAGE_SELECT_PL": "pl"}
        target_lang = lang_map.get(aid, "en")

        deps.log_info(
            "ACTION_LANGUAGE_SELECT aid=%s target_lang=%s session=%s",
            aid,
            repr(target_lang),
            session_id,
        )

        meta2["target_language"] = target_lang
        meta2["language"] = target_lang

        deps.log_info(
            "BEFORE_PERSIST meta2_target_language=%s meta2_language=%s",
            repr(meta2.get("target_language")),
            repr(meta2.get("language")),
        )

        dpu = meta2.get("docx_prefill_unconfirmed")
        needs_import = bool(isinstance(dpu, dict) and (not cv_data.get("work_experience") and not cv_data.get("education")))
        if needs_import:
            meta2 = deps.wizard_set_stage(meta2, "import_gate_pending")
        else:
            meta2 = deps.wizard_set_stage(meta2, "contact")

        cv_data, meta2 = deps.persist(cv_data, meta2)

        deps.log_info(
            "AFTER_PERSIST meta2_target_language=%s meta2_language=%s",
            repr(meta2.get("target_language")),
            repr(meta2.get("language")),
        )

        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Language selected. Proceeding...",
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "CONTACT_CONFIRM":
        full_name = str(cv_data.get("full_name") or "").strip()
        email = str(cv_data.get("email") or "").strip()
        phone = str(cv_data.get("phone") or "").strip()
        if not (full_name and email and phone):
            meta2 = deps.wizard_set_stage(meta2, "contact")
            cv_data, meta2 = deps.persist(cv_data, meta2)
            return True, cv_data, meta2, deps.wizard_resp(
                assistant_text="Contact is incomplete. Please click Edit and fill Full name, Email, and Phone.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        cf = meta2.get("confirmed_flags") if isinstance(meta2.get("confirmed_flags"), dict) else {}
        cf = dict(cf or {})
        cf["contact_confirmed"] = True
        cf["confirmed_at"] = cf.get("confirmed_at") or deps.now_iso()
        meta2["confirmed_flags"] = cf
        meta2 = deps.wizard_set_stage(meta2, "education")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Review your education below.",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
