from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ProfileConfirmActionDeps:
    merge_docx_prefill_into_cv_data_if_needed: Callable[..., tuple[dict, dict, bool]]
    clear_pending_confirmation: Callable[[dict], dict]
    openai_enabled: Callable[[], bool]
    hash_bulk_translation_payload: Callable[[dict], str]
    build_bulk_translation_payload: Callable[[dict], dict]
    bulk_translation_cache_hit: Callable[..., bool]
    run_bulk_translation: Callable[..., tuple[dict, dict, bool, str | None]]
    maybe_apply_fast_profile: Callable[..., tuple[dict, dict, bool]]
    now_iso: Callable[[], str]
    wizard_set_stage: Callable[[dict, str], dict]
    persist: Callable[[dict, dict], tuple[dict, dict]]
    wizard_resp: Callable[..., tuple[int, dict]]
    sha256_text: Callable[[str], str]
    upload_json_blob_for_session: Callable[..., dict | None]
    stable_profile_user_id: Callable[[dict, dict], str | None]
    stable_profile_payload: Callable[..., dict]
    get_profile_store: Callable[[], Any]


def handle_profile_confirm_actions(
    *,
    aid: str,
    cv_data: dict,
    meta2: dict,
    session_id: str,
    trace_id: str,
    client_context: dict | None,
    deps: ProfileConfirmActionDeps,
) -> tuple[bool, dict, dict, tuple[int, dict] | None]:
    if aid in ("CONFIRM_IMPORT_PREFILL_YES", "CONFIRM_IMPORT_PREFILL_NO"):
        if aid == "CONFIRM_IMPORT_PREFILL_YES":
            docx_prefill = meta2.get("docx_prefill_unconfirmed")
            if isinstance(docx_prefill, dict):
                cv_data2, meta2, _merged = deps.merge_docx_prefill_into_cv_data_if_needed(
                    cv_data=cv_data,
                    docx_prefill=docx_prefill,
                    meta=meta2,
                    keys_to_merge=[
                        "full_name",
                        "email",
                        "phone",
                        "address_lines",
                        "profile",
                        "work_experience",
                        "education",
                        "languages",
                        "interests",
                        "references",
                    ],
                    clear_prefill=False,
                )
                cv_data = cv_data2

        meta2 = deps.clear_pending_confirmation(meta2)
        if aid == "CONFIRM_IMPORT_PREFILL_NO":
            meta2["docx_prefill_unconfirmed"] = None

        try:
            if isinstance(client_context, dict) and "fast_path_profile" in client_context:
                meta2["fast_path_profile"] = bool(client_context.get("fast_path_profile"))
        except Exception:
            pass

        target_lang = str(meta2.get("target_language") or meta2.get("language") or "en").strip().lower()
        source_lang = str(meta2.get("source_language") or cv_data.get("language") or "en").strip().lower()
        explicit_target_lang_selected = bool(meta2.get("target_language"))
        source_hash = deps.hash_bulk_translation_payload(deps.build_bulk_translation_payload(cv_data))
        needs_bulk_translation = (
            aid == "CONFIRM_IMPORT_PREFILL_YES"
            and deps.openai_enabled()
            and (source_lang != target_lang or explicit_target_lang_selected)
            and not deps.bulk_translation_cache_hit(meta=meta2, target_language=target_lang, source_hash=source_hash)
        )

        if needs_bulk_translation:
            cv_data, meta2, _ok_bt, _err_bt = deps.run_bulk_translation(
                cv_data=cv_data,
                meta=meta2,
                trace_id=trace_id,
                session_id=session_id,
                target_language=target_lang,
            )

        cv_data, meta2, applied_profile = deps.maybe_apply_fast_profile(
            cv_data=cv_data,
            meta=meta2,
            client_context=client_context if isinstance(client_context, dict) else None,
        )

        if applied_profile:
            cf = meta2.get("confirmed_flags") if isinstance(meta2.get("confirmed_flags"), dict) else {}
            cf = dict(cf or {})
            cf["contact_confirmed"] = True
            cf["education_confirmed"] = True
            cf["confirmed_at"] = cf.get("confirmed_at") or deps.now_iso()
            meta2["confirmed_flags"] = cf
            meta2 = deps.wizard_set_stage(meta2, "job_posting")

            restored_parts = ["contact", "education", "interests", "language"]
            if meta2.get("work_prefilled_from_profile"):
                restored_parts.append("work experience")
            profile_msg = f"Fast path: applied saved profile ({', '.join(restored_parts)})."
        else:
            meta2 = deps.wizard_set_stage(meta2, "contact")
            profile_msg = "Review your contact details below."

        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text=profile_msg,
            meta_out=meta2,
            cv_out=cv_data,
        )

    if aid == "EDUCATION_CONFIRM":
        cf = meta2.get("confirmed_flags") if isinstance(meta2.get("confirmed_flags"), dict) else {}
        cf = dict(cf or {})
        cf["education_confirmed"] = True
        cf["confirmed_at"] = cf.get("confirmed_at") or deps.now_iso()
        meta2["confirmed_flags"] = cf

        try:
            if not isinstance(meta2.get("base_cv"), dict):
                base_json = json.dumps(cv_data, ensure_ascii=False, sort_keys=True)
                base_sig = deps.sha256_text(base_json)
                blob_name = f"base/{session_id}/{base_sig}.json"
                ptr = deps.upload_json_blob_for_session(session_id=session_id, blob_name=blob_name, payload={"cv_data": cv_data})
                if ptr:
                    meta2["base_cv"] = {
                        "container": ptr.get("container"),
                        "blob_name": ptr.get("blob_name"),
                        "sha256": base_sig,
                        "created_at": deps.now_iso(),
                    }
                    meta2["base_cv_sha256"] = base_sig
        except Exception:
            pass

        try:
            user_id = deps.stable_profile_user_id(cv_data, meta2)
            if user_id and cf.get("contact_confirmed") and cf.get("education_confirmed"):
                payload = deps.stable_profile_payload(cv_data=cv_data, meta=meta2)
                ref = deps.get_profile_store().put_latest(
                    user_id=user_id,
                    payload=payload,
                    target_language=str(payload.get("target_language") or ""),
                )
                meta2["stable_profile_saved"] = True
                meta2["stable_profile_ref"] = {"store": ref.store, "key": ref.key}
        except Exception:
            pass

        meta2 = deps.wizard_set_stage(meta2, "job_posting")
        cv_data, meta2 = deps.persist(cv_data, meta2)
        return True, cv_data, meta2, deps.wizard_resp(
            assistant_text="Optionally add a job offer for tailoring (or skip).",
            meta_out=meta2,
            cv_out=cv_data,
        )

    return False, cv_data, meta2, None
