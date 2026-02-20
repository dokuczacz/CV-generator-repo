from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class UiBuilderDeps:
    cv_enable_cover_letter: bool
    get_pending_confirmation: Callable[[dict], dict | None]
    openai_enabled: Callable[[], bool]
    format_job_reference_for_display: Callable[[dict], str]
    is_work_role_locked: Callable[..., bool]


def build_ui_action(stage: str, cv_data: dict, meta: dict, readiness: dict, deps: UiBuilderDeps) -> dict | None:
    """Build UI action object for guided flow based on current stage."""
    stage = (stage or "").lower().strip()

    # Wizard mode: backend-driven deterministic UI actions (Playwright-backed).
    # Stage is stored in metadata under wizard_stage; stage argument is used as fallback only.
    if isinstance(meta, dict) and meta.get("flow_mode") == "wizard":
        wizard_stage = str(meta.get("wizard_stage") or stage or "").strip().lower()
        wizard_total = 7 if deps.cv_enable_cover_letter else 6

        def _join_lines(items: list[dict], *, key: str, prefix: str = "") -> str:
            lines = []
            for i, it in enumerate(items or []):
                if not isinstance(it, dict):
                    continue
                v = str(it.get(key) or "").strip()
                if not v:
                    continue
                lines.append(f"{i+1}. {prefix}{v}" if not prefix else f"{i+1}. {v}")
            return "\n".join(lines)

        def _contact_values() -> tuple[str, str, str, str]:
            # Back-compat: some older snapshots used contact_information; canonical is top-level.
            contact_data = meta.get("contact_information") if isinstance(meta.get("contact_information"), dict) else None
            if isinstance(cv_data.get("contact_information"), dict):
                contact_data = cv_data.get("contact_information")
            src = contact_data if isinstance(contact_data, dict) else (cv_data if isinstance(cv_data, dict) else {})
            full_name = str(src.get("full_name") or cv_data.get("full_name") or "").strip()
            email = str(src.get("email") or cv_data.get("email") or "").strip()
            phone = str(src.get("phone") or cv_data.get("phone") or "").strip()
            addr_lines = cv_data.get("address_lines")
            if isinstance(addr_lines, list):
                addr = "\n".join([str(x) for x in addr_lines if str(x).strip()])
            else:
                addr = str(cv_data.get("address") or "").strip()
            return full_name, email, phone, addr

        # Language selection: first step after upload
        if wizard_stage == "language_selection":
            source_lang = str(meta.get("source_language") or meta.get("language") or "en").strip().lower()
            lang_names = {"en": "English", "de": "German", "pl": "Polish", "fr": "French", "es": "Spanish"}
            detected = lang_names.get(source_lang, source_lang.upper())
            return {
                "kind": "review_form",
                "stage": "LANGUAGE_SELECTION",
                "title": "Language Selection",
                "text": f"Source language detected: {detected}. What language should your final CV be in?",
                "fields": [],
                "actions": [
                    {"id": "LANGUAGE_SELECT_EN", "label": "English", "style": "primary"},
                    {"id": "LANGUAGE_SELECT_DE", "label": "German (Deutsch)", "style": "secondary"},
                    {"id": "LANGUAGE_SELECT_PL", "label": "Polish (Polski)", "style": "secondary"},
                ],
                "disable_free_text": True,
            }

        # Import gate: check both explicit pending_confirmation AND import_gate_pending stage
        pending_confirmation = deps.get_pending_confirmation(meta) if isinstance(meta, dict) else None
        if (wizard_stage == "import_gate_pending") or (pending_confirmation and pending_confirmation.get("kind") == "import_prefill"):
            return {
                "kind": "confirm",
                "stage": "IMPORT_PREFILL",
                "title": "Import DOCX data?",
                "text": "Do you want to import the data extracted from your DOCX file?",
                "actions": [
                    {"id": "CONFIRM_IMPORT_PREFILL_YES", "label": "Import DOCX prefill", "style": "primary"},
                    {"id": "CONFIRM_IMPORT_PREFILL_NO", "label": "Do not import", "style": "secondary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "bulk_translation":
            target_lang = str(meta.get("target_language") or meta.get("language") or "en").strip().lower()
            return {
                "kind": "review_form",
                "stage": "BULK_TRANSLATION",
                "title": "Translating content",
                "text": f"Translating all sections to {target_lang}. Please wait...",
                "fields": [],
                "actions": [],
                "disable_free_text": True,
            }

        if wizard_stage == "contact":
            full_name, email, phone, addr = _contact_values()
            return {
                "kind": "review_form",
                "stage": "CONTACT",
                "title": f"Stage 1/{wizard_total} — Contact",
                "text": "Review contact details. Edit if needed, then Confirm & lock.",
                "fields": [
                    {"key": "full_name", "label": "Full name", "value": full_name},
                    {"key": "email", "label": "Email", "value": email},
                    {"key": "phone", "label": "Phone", "value": phone},
                    {"key": "address", "label": "Address (optional)", "value": addr},
                ],
                "actions": [
                    {"id": "CONTACT_EDIT", "label": "Edit", "style": "secondary"},
                    {"id": "CONTACT_CONFIRM", "label": "Confirm & lock", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "contact_edit":
            full_name, email, phone, addr = _contact_values()
            return {
                "kind": "edit_form",
                "stage": "CONTACT",
                "title": f"Stage 1/{wizard_total} — Contact",
                "text": "Edit contact details, then Save.",
                "fields": [
                    {"key": "full_name", "label": "Full name", "value": full_name},
                    {"key": "email", "label": "Email", "value": email},
                    {"key": "phone", "label": "Phone", "value": phone},
                    {"key": "address", "label": "Address (optional)", "value": addr, "type": "textarea"},
                ],
                "actions": [
                    {"id": "CONTACT_CANCEL", "label": "Cancel", "style": "secondary"},
                    {"id": "CONTACT_SAVE", "label": "Save", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "education":
            edu = cv_data.get("education", []) if isinstance(cv_data, dict) else []
            edu_list = edu if isinstance(edu, list) else []
            def _edu_line(item: dict) -> str:
                if not isinstance(item, dict):
                    return ""
                title = str(item.get("title") or "").strip()
                inst = str(item.get("institution") or item.get("school") or "").strip()
                date = str(item.get("date_range") or "").strip()
                parts = [p for p in [title, inst, date] if p]
                return " — ".join(parts) if parts else ""

            edu_lines = []
            for i, it in enumerate(edu_list):
                line = _edu_line(it)
                if line:
                    edu_lines.append(f"{i+1}. {line}")
            edu_value = "\n".join(edu_lines)
            return {
                "kind": "review_form",
                "stage": "EDUCATION",
                "title": f"Stage 2/{wizard_total} — Education",
                "text": "Review education entries. Edit if needed, then Confirm & lock.",
                "fields": [
                    {"key": "education_entries", "label": "Education", "value": edu_value or "(none)"},
                ],
                "actions": [
                    {"id": "EDUCATION_EDIT_JSON", "label": "Edit (JSON)", "style": "secondary"},
                    {"id": "EDUCATION_CONFIRM", "label": "Confirm & lock", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "education_edit_json":
            import json

            edu = cv_data.get("education", []) if isinstance(cv_data, dict) else []
            edu_list = edu if isinstance(edu, list) else []
            return {
                "kind": "edit_form",
                "stage": "EDUCATION",
                "title": f"Stage 2/{wizard_total} — Education",
                "text": "Edit education JSON, then Save.",
                "fields": [
                    {"key": "education_json", "label": "Education (JSON)", "value": json.dumps(edu_list, ensure_ascii=False, indent=2), "type": "textarea"},
                ],
                "actions": [
                    {"id": "EDUCATION_CANCEL", "label": "Cancel", "style": "secondary"},
                    {"id": "EDUCATION_SAVE", "label": "Save", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "job_posting":
            job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
            job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
            has_text = bool(str(meta.get("job_posting_text") or "").strip())
            interests = str(cv_data.get("interests") or "").strip() if isinstance(cv_data, dict) else ""
            cf = meta.get("confirmed_flags") if isinstance(meta.get("confirmed_flags"), dict) else {}
            can_fast = bool(
                has_text
                and isinstance(cf, dict)
                and cf.get("contact_confirmed")
                and cf.get("education_confirmed")
                and deps.openai_enabled()
            )
            actions: list[dict] = []
            # Keep the step simple: one clear primary action, everything else as advanced/optional.
            if has_text:
                actions.append({"id": "JOB_OFFER_CONTINUE", "label": "Continue", "style": "primary"})
                if can_fast:
                    actions.append({"id": "FAST_RUN_TO_PDF", "label": "Fast tailor + PDF", "style": "secondary"})
                actions.append({"id": "JOB_OFFER_PASTE", "label": "Edit job offer text / URL", "style": "tertiary"})
                actions.append({"id": "JOB_OFFER_SKIP", "label": "Skip", "style": "tertiary"})
            else:
                actions.append({"id": "JOB_OFFER_PASTE", "label": "Paste job offer text / URL", "style": "primary"})
                actions.append({"id": "JOB_OFFER_SKIP", "label": "Skip", "style": "secondary"})
            actions.append({"id": "INTERESTS_EDIT", "label": "Edit interests", "style": "tertiary"})
            if has_text and deps.openai_enabled():
                actions.append({"id": "INTERESTS_TAILOR_RUN", "label": "Tailor interests (optional)", "style": "tertiary"})

            fields: list[dict] = [
                {
                    "key": "job_posting_text_present",
                    "label": "Job offer text",
                    "value": "(present)" if has_text else "(none)",
                }
            ]
            if job_summary:
                fields.append({"key": "job_reference", "label": "Job summary", "value": job_summary})

            return {
                "kind": "review_form",
                "stage": "JOB_POSTING",
                "title": f"Stage 3/{wizard_total} — Job offer (optional)",
                "text": "Optional: paste a job offer for tailoring, then Continue. (Interests are edited separately.) Use Fast tailor + PDF only if contact + education are confirmed.",
                "fields": fields,
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "interests_edit":
            interests = str(cv_data.get("interests") or "") if isinstance(cv_data, dict) else ""
            has_job_context = bool(str(meta.get("job_posting_text") or "").strip() or isinstance(meta.get("job_reference"), dict))
            actions = [
                {"id": "INTERESTS_CANCEL", "label": "Cancel", "style": "secondary"},
                {"id": "INTERESTS_SAVE", "label": "Save", "style": "primary"},
            ]
            if has_job_context and deps.openai_enabled():
                actions.append({"id": "INTERESTS_TAILOR_RUN", "label": "Tailor with AI", "style": "secondary"})
            return {
                "kind": "edit_form",
                "stage": "JOB_POSTING",
                "title": f"Stage 3/{wizard_total} — Interests (optional)",
                "text": "Edit interests (and optionally tailor them to the job offer). Saved interests can be reused across jobs until changed.",
                "fields": [
                    {
                        "key": "interests",
                        "label": "Interests",
                        "value": interests,
                        "type": "textarea",
                    }
                ],
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "job_posting_paste":
            analyze_label = "Analyze" if deps.openai_enabled() else "Save"
            return {
                "kind": "edit_form",
                "stage": "JOB_POSTING",
                "title": f"Stage 3/{wizard_total} — Job offer (optional)",
                "text": "Paste the job offer text (or a URL), then Analyze.",
                "fields": [
                    {
                        "key": "job_offer_text",
                        "label": "Job offer text (or paste a URL)",
                        "value": str(meta.get("job_posting_text") or ""),
                        "type": "textarea",
                    }
                ],
                "actions": [
                    {"id": "JOB_OFFER_CANCEL", "label": "Cancel", "style": "secondary"},
                    {"id": "JOB_OFFER_ANALYZE", "label": analyze_label, "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "job_posting_invalid_input":
            reason = str(meta.get("job_input_invalid_reason") or "not_job_like")
            preview = str(meta.get("job_posting_invalid_draft") or "")[:700]
            reason_map = {
                "too_short": "Text is too short to represent a real job posting.",
                "looks_like_candidate_notes": "Input looks like candidate notes/achievements, not a job offer.",
                "not_job_like": "Input does not look like a job posting.",
            }
            reason_label = reason_map.get(reason, "Input is not suitable for job summary extraction.")
            return {
                "kind": "review_form",
                "stage": "JOB_POSTING",
                "title": f"Stage 3/{wizard_total} — Job offer (validation)",
                "text": "The provided input cannot be used as a job posting source. Choose how to proceed.",
                "fields": [
                    {"key": "invalid_reason", "label": "Validation", "value": reason_label},
                    {"key": "invalid_preview", "label": "Detected input (preview)", "value": preview or "(empty)"},
                ],
                "actions": [
                    {"id": "JOB_OFFER_INVALID_FIX_URL", "label": "Correct URL", "style": "secondary"},
                    {"id": "JOB_OFFER_INVALID_PASTE_TEXT", "label": "Paste proper job text", "style": "primary"},
                    {"id": "JOB_OFFER_INVALID_CONTINUE_NO_SUMMARY", "label": "Continue without job summary (not recommended)", "style": "tertiary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "work_experience":
            work = cv_data.get("work_experience", []) if isinstance(cv_data, dict) else []
            work_list = work if isinstance(work, list) else []

            notes = str(meta.get("work_tailoring_notes") or "").strip()
            job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
            job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""

            role_lines: list[str] = []
            missing_loc_lines: list[str] = []
            for i, r in enumerate(work_list[:10]):
                if not isinstance(r, dict):
                    continue
                company = str(r.get("company") or r.get("employer") or "").strip()
                title = str(r.get("title") or r.get("position") or "").strip()
                date = str(r.get("date_range") or "").strip()
                loc = str(r.get("location") or r.get("city") or r.get("place") or "").strip()
                head = " | ".join([p for p in [title, company, date] if p]) or f"Role #{i+1}"
                role_lines.append(f"{i+1}. {head}")
                if not loc:
                    missing_loc_lines.append(f"{i}. {head}")
            roles_preview = "\n".join(role_lines) if role_lines else "(no roles detected in CV)"

            fields = [
                {"key": "roles_preview", "label": f"Work roles ({len(work_list)} total)", "value": roles_preview},
            ]
            if job_summary:
                fields.append({"key": "job_reference", "label": "Job summary", "value": job_summary})
            if notes:
                fields.append({"key": "tailoring_notes", "label": "Tailoring notes", "value": notes})
            if missing_loc_lines:
                fields.append(
                    {
                        "key": "missing_locations",
                        "label": f"Missing locations ({len(missing_loc_lines)} roles)",
                        "value": "\n".join(missing_loc_lines[:12]),
                    }
                )

            actions = [{"id": "WORK_ADD_TAILORING_NOTES", "label": "Add tailoring notes", "style": "secondary"}]
            if missing_loc_lines:
                actions.append({"id": "WORK_LOCATIONS_EDIT", "label": "Add missing locations", "style": "secondary"})
            has_job_context = bool(job_ref or str(meta.get("job_posting_text") or "").strip())
            if has_job_context and deps.openai_enabled():
                actions.append({"id": "WORK_TAILOR_RUN", "label": "Generate tailored work experience", "style": "primary"})
                actions.append({"id": "WORK_TAILOR_SKIP", "label": "Skip tailoring", "style": "secondary"})
            else:
                # If AI is disabled (or no job context), avoid showing a "ghost" button that cannot succeed.
                actions.append({"id": "WORK_TAILOR_SKIP", "label": "Continue", "style": "primary"})

            return {
                "kind": "review_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work experience",
                "text": "Tailor your work experience to the job offer (recommended), or skip. If locations are missing, add them manually first.",
                "fields": fields,
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "work_locations_edit":
            work = cv_data.get("work_experience", []) if isinstance(cv_data, dict) else []
            work_list = work if isinstance(work, list) else []

            lines: list[str] = []
            for i, r in enumerate(work_list[:20]):
                if not isinstance(r, dict):
                    continue
                loc = str(r.get("location") or r.get("city") or r.get("place") or "").strip()
                if loc:
                    continue
                company = str(r.get("company") or r.get("employer") or "").strip()
                title = str(r.get("title") or r.get("position") or "").strip()
                date = str(r.get("date_range") or "").strip()
                head = " | ".join([p for p in [title, company, date] if p]) or f"Role #{i+1}"
                # Format: index | location # context
                lines.append(f"{i} |  # {head}".rstrip())

            prefill = "\n".join(lines).strip()
            if not prefill:
                prefill = ""

            return {
                "kind": "edit_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work locations",
                "text": "Fill missing locations using: index | location. Lines starting with # are ignored.",
                "fields": [
                    {
                        "key": "work_locations_lines",
                        "label": "Missing locations",
                        "value": prefill,
                        "type": "textarea",
                        "placeholder": "0 | Zurich, Switzerland\n3 | Zielona Góra, Poland",
                    }
                ],
                "actions": [
                    {"id": "WORK_LOCATIONS_CANCEL", "label": "Cancel", "style": "secondary"},
                    {"id": "WORK_LOCATIONS_SAVE", "label": "Save locations", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "work_notes_edit":
            has_job_context = bool(
                isinstance(meta.get("job_reference"), dict) or str(meta.get("job_posting_text") or "").strip()
            )
            allow_run = bool(has_job_context and deps.openai_enabled())
            actions = [
                {"id": "WORK_NOTES_CANCEL", "label": "Cancel", "style": "secondary"},
                {"id": "WORK_NOTES_SAVE", "label": "Save notes", "style": "secondary"},
            ]
            if allow_run:
                actions.append({"id": "WORK_TAILOR_RUN", "label": "Generate tailored work experience", "style": "primary"})
            else:
                # AI disabled: allow progressing without getting stuck in the notes screen.
                actions.append({"id": "WORK_TAILOR_SKIP", "label": "Continue", "style": "primary"})
            return {
                "kind": "edit_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work experience",
                "text": "List concrete achievements or outcomes you want reflected in the CV (numbers, scope, impact). One line per achievement is enough.",
                "fields": [
                    {
                        "key": "work_tailoring_notes",
                        "label": "Tailoring notes",
                        "value": str(meta.get("work_tailoring_notes") or ""),
                        "type": "textarea",
                        "placeholder": (
                            "– Reduced customer claims by 70%\n"
                            "– Built greenfield quality organization (80 people)\n"
                            "– Delivered public‑sector projects worth 30–40k EUR"
                        ),
                    }
                ],
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "work_tailor_feedback":
            # Feedback is optional; this screen must not be a dead-end.
            has_proposal = bool(isinstance(meta.get("work_experience_proposal_block"), dict))
            already_applied = bool(meta.get("work_experience_tailored") or meta.get("work_experience_proposal_accepted_at"))

            actions: list[dict] = []
            if has_proposal or already_applied:
                actions.append({"id": "WORK_TAILOR_ACCEPT", "label": "Accept proposal", "style": "primary"})
                actions.append({"id": "WORK_TAILOR_FEEDBACK_CANCEL", "label": "Back to proposal", "style": "secondary"})
            else:
                actions.append({"id": "WORK_TAILOR_SKIP", "label": "Continue", "style": "primary"})
                actions.append({"id": "WORK_NOTES_CANCEL", "label": "Back", "style": "secondary"})
            if deps.openai_enabled():
                actions.append({"id": "WORK_TAILOR_RUN", "label": "Regenerate proposal", "style": "secondary"})
            return {
                "kind": "edit_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work experience (feedback)",
                "text": "Add feedback to improve the proposal, then Regenerate. If a proposal is available, you can Accept it; otherwise Continue.",
                "fields": [
                    {
                        "key": "work_tailoring_feedback",
                        "label": "Feedback",
                        "value": str(meta.get("work_tailoring_feedback") or ""),
                        "type": "textarea",
                    }
                ],
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "work_tailor_review":
            proposal_block = meta.get("work_experience_proposal_block") if isinstance(meta.get("work_experience_proposal_block"), dict) else None
            proposal = meta.get("work_experience_proposal") if isinstance(meta.get("work_experience_proposal"), list) else []
            proposal_notes = str((proposal_block or {}).get("notes") or "").strip()
            lines: list[str] = []
            if isinstance(proposal_block, dict):
                # Display structured roles
                roles = proposal_block.get("roles") if isinstance(proposal_block.get("roles"), list) else []
                for r in roles[:5]:  # Max 5 roles
                    if not isinstance(r, dict):
                        continue
                    title = str(r.get("title") or "").strip()
                    company = str(r.get("company") or r.get("employer") or "").strip()
                    date_range = str(r.get("date_range") or "").strip()
                    bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else []
                    
                    header_parts = []
                    if title:
                        header_parts.append(title)
                    if company:
                        header_parts.append(f"@ {company}")
                    if date_range:
                        header_parts.append(f"({date_range})")
                    header = " ".join(header_parts)
                    
                    bullet_lines = "\n".join([f"- {str(b).strip()}" for b in bullets if str(b).strip()][:8])
                    if header or bullet_lines:
                        lines.append(f"**{header}**\n{bullet_lines}".strip() if header else bullet_lines)
            else:
                for item in proposal[:10]:
                    if not isinstance(item, dict):
                        continue
                    header = str(item.get("header") or "").strip()
                    bullets = item.get("proposed_bullets") if isinstance(item.get("proposed_bullets"), list) else []
                    bullet_lines = "\n".join([f"- {str(b).strip()}" for b in bullets if str(b).strip()][:10])
                    if header or bullet_lines:
                        lines.append(f"{header}\n{bullet_lines}".strip())
            return {
                "kind": "review_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work experience (proposal)",
                "text": "Review the proposed tailored bullets. Accept to apply to your CV.",
                "fields": [
                    {"key": "proposal", "label": "Proposed work experience", "value": "\n\n".join(lines) if lines else "(no proposal)"},
                    {"key": "notes", "label": "Notes", "value": proposal_notes or "(no notes)"},
                ],
                "actions": [
                    {"id": "WORK_TAILOR_ACCEPT", "label": "Accept proposal", "style": "primary"},
                    {"id": "WORK_TAILOR_FEEDBACK", "label": "Improve (feedback)", "style": "secondary"},
                    {"id": "WORK_ADD_TAILORING_NOTES", "label": "Edit notes", "style": "secondary"},
                    {"id": "WORK_TAILOR_SKIP", "label": "Skip tailoring", "style": "secondary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "work_select_role":
            return {
                "kind": "edit_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work experience",
                "text": "Select a role index (0-based) to review and lock.",
                "fields": [
                    {"key": "role_index", "label": "Role index", "value": ""},
                ],
                "actions": [
                    {"id": "WORK_SELECT_CANCEL", "label": "Cancel", "style": "secondary"},
                    {"id": "WORK_OPEN_ROLE", "label": "Open role", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "work_role_view":
            work = cv_data.get("work_experience", []) if isinstance(cv_data, dict) else []
            work_list = work if isinstance(work, list) else []
            idx = meta.get("work_selected_index")
            try:
                i = int(idx)
            except Exception:
                i = -1

            role = work_list[i] if 0 <= i < len(work_list) and isinstance(work_list[i], dict) else {}
            company = str(role.get("company") or "").strip()
            title = str(role.get("title") or role.get("position") or "").strip()
            bullets = role.get("bullets") if isinstance(role.get("bullets"), list) else role.get("responsibilities")
            bullet_lines = "\n".join([f"- {str(b).strip()}" for b in (bullets or []) if str(b).strip()]) if isinstance(bullets, list) else ""

            is_locked = deps.is_work_role_locked(meta=meta if isinstance(meta, dict) else {}, role_index=i)

            return {
                "kind": "review_form",
                "stage": "WORK_EXPERIENCE",
                "title": f"Stage 4/{wizard_total} — Work experience",
                "text": f"Role #{i}: review and lock.",
                "fields": [
                    {"key": "company", "label": "Company", "value": company},
                    {"key": "title", "label": "Role", "value": title},
                    {"key": "bullets", "label": "Bullets", "value": bullet_lines or "(none)"},
                    {"key": "locked", "label": "Locked", "value": "Yes" if is_locked else "No"},
                ],
                "actions": [
                    {"id": "WORK_BACK_TO_LIST", "label": "Back to list", "style": "secondary"},
                    {"id": "WORK_UNLOCK_ROLE" if is_locked else "WORK_LOCK_ROLE", "label": "Unlock role" if is_locked else "Lock role", "style": "primary"},
                ],
                "disable_free_text": True,
            }

        # ====== FURTHER EXPERIENCE (TECHNICAL PROJECTS) TAILORING ======
        if wizard_stage == "further_experience":
            further = cv_data.get("further_experience", []) if isinstance(cv_data, dict) else []
            further_list = further if isinstance(further, list) else []

            notes = str(meta.get("further_tailoring_notes") or "").strip()
            job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
            job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
            
            total_count = len(further_list)

            project_lines: list[str] = []
            for i, p in enumerate(further_list[:10]):
                if not isinstance(p, dict):
                    continue
                title = str(p.get("title") or "").strip()
                org = str(p.get("organization") or "").strip()
                date = str(p.get("date_range") or "").strip()
                head = " | ".join([x for x in [title, org, date] if x]) or f"Project #{i+1}"
                project_lines.append(f"{i+1}. {head}")
            projects_preview = "\n".join(project_lines) if project_lines else "(no technical projects detected in CV)"

            # Format skills for display - get from docx_prefill_unconfirmed if cv_data is empty
            dpu = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else {}
            skills_it_ai = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
            if not skills_it_ai and isinstance(dpu, dict):
                skills_it_ai = dpu.get("it_ai_skills") if isinstance(dpu.get("it_ai_skills"), list) else []
            
            skills_technical = cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else []
            if not skills_technical and isinstance(dpu, dict):
                skills_technical = dpu.get("technical_operational_skills") if isinstance(dpu.get("technical_operational_skills"), list) else []
            
            def _format_skills_display(skills: list) -> str:
                if not skills:
                    return ""
                lines = []
                for skill in (skills or [])[:10]:
                    s = str(skill or "").strip()
                    if s:
                        lines.append(f"- {s}")
                return "\n".join(lines) if lines else ""
            
            skills_parts = []
            it_formatted = _format_skills_display(skills_it_ai)
            tech_formatted = _format_skills_display(skills_technical)
            if it_formatted:
                skills_parts.append(it_formatted)
            if tech_formatted:
                skills_parts.append(tech_formatted)
            skills_display = "\n".join(skills_parts) if skills_parts else "(no skills)"

            work_notes = str(meta.get("work_tailoring_notes") or "").strip()

            fields = [
                {"key": "projects_preview", "label": f"Technical projects ({total_count} total)", "value": projects_preview},
            ]
            if job_summary:
                fields.append({"key": "job_reference", "label": "Job summary", "value": job_summary})
            if work_notes:
                fields.append({"key": "work_notes", "label": "Work tailoring context", "value": work_notes})
            fields.append({"key": "skills_preview", "label": "Your skills (FÄHIGKEITEN & KOMPETENZEN)", "value": skills_display})
            if notes:
                fields.append({"key": "tailoring_notes", "label": "Tailoring notes", "value": notes})

            actions = [{"id": "FURTHER_ADD_NOTES", "label": "Add tailoring notes", "style": "secondary"}]
            has_job_context = bool(job_ref or str(meta.get("job_posting_text") or "").strip())
            if has_job_context and deps.openai_enabled():
                actions.append({"id": "FURTHER_TAILOR_RUN", "label": "Generate tailored projects", "style": "primary"})
                actions.append({"id": "FURTHER_TAILOR_SKIP", "label": "Skip tailoring", "style": "secondary"})
            else:
                actions.append({"id": "FURTHER_TAILOR_SKIP", "label": "Continue", "style": "primary"})

            return {
                "kind": "review_form",
                "stage": "FURTHER_EXPERIENCE",
                "title": f"Stage 5a/{wizard_total} — Technical projects",
                "text": "Tailor your technical projects to the job offer (recommended), or skip.",
                "fields": fields,
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "further_notes_edit":
            actions = [
                {"id": "FURTHER_NOTES_CANCEL", "label": "Cancel", "style": "secondary"},
                {"id": "FURTHER_NOTES_SAVE", "label": "Save notes", "style": "secondary"},
            ]
            if deps.openai_enabled():
                actions.append({"id": "FURTHER_TAILOR_RUN", "label": "Generate tailored projects", "style": "primary"})
            else:
                actions.append({"id": "FURTHER_TAILOR_SKIP", "label": "Continue", "style": "primary"})
            return {
                "kind": "edit_form",
                "stage": "FURTHER_EXPERIENCE",
                "title": f"Stage 5a/{wizard_total} — Technical projects",
                "text": "Add tailoring notes for the AI (optional), then Save or Generate.",
                "fields": [
                    {
                        "key": "further_tailoring_notes",
                        "label": "Tailoring notes",
                        "value": str(meta.get("further_tailoring_notes") or ""),
                        "type": "textarea",
                    }
                ],
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "further_tailor_review":
            proposal_block = meta.get("further_experience_proposal_block") if isinstance(meta.get("further_experience_proposal_block"), dict) else None
            lines: list[str] = []
            if isinstance(proposal_block, dict):
                projects = proposal_block.get("projects") if isinstance(proposal_block.get("projects"), list) else []
                for p in projects[:3]:  # Max 3 projects
                    if not isinstance(p, dict):
                        continue
                    title = str(p.get("title") or "").strip()
                    org = str(p.get("organization") or "").strip()
                    date_range = str(p.get("date_range") or "").strip()
                    bullets = p.get("bullets") if isinstance(p.get("bullets"), list) else []
                    
                    header_parts = []
                    if title:
                        header_parts.append(title)
                    if org:
                        header_parts.append(f"@ {org}")
                    if date_range:
                        header_parts.append(f"({date_range})")
                    header = " ".join(header_parts)
                    
                    bullet_lines = "\n".join([f"- {str(b).strip()}" for b in bullets if str(b).strip()][:3])
                    if header or bullet_lines:
                        lines.append(f"**{header}**\n{bullet_lines}".strip() if header else bullet_lines)
            return {
                "kind": "review_form",
                "stage": "FURTHER_EXPERIENCE",
                "title": f"Stage 5a/{wizard_total} — Technical projects (proposal)",
                "text": "Review the proposed tailored projects. Accept to apply to your CV.",
                "fields": [
                    {"key": "proposal", "label": "Proposed technical projects", "value": "\n\n".join(lines) if lines else "(no proposal)"},
                ],
                "actions": [
                    {"id": "FURTHER_TAILOR_ACCEPT", "label": "Accept proposal", "style": "primary"},
                    {"id": "FURTHER_TAILOR_SKIP", "label": "Skip tailoring", "style": "secondary"},
                ],
                "disable_free_text": True,
            }

        # ====== SKILLS (FÄHIGKEITEN & KOMPETENZEN) ======
        if wizard_stage == "it_ai_skills":
            skills_from_cv = cv_data.get("it_ai_skills", []) if isinstance(cv_data, dict) else []
            skills_legacy_from_cv = cv_data.get("technical_operational_skills", []) if isinstance(cv_data, dict) else []
            dpu = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else None
            skills_from_docx = dpu.get("it_ai_skills") if isinstance(dpu, dict) and isinstance(dpu.get("it_ai_skills"), list) else []
            skills_legacy_from_docx = dpu.get("technical_operational_skills") if isinstance(dpu, dict) and isinstance(dpu.get("technical_operational_skills"), list) else []

            seen_lower: set[str] = set()
            skills_list: list[str] = []
            for s in list(skills_from_cv) + list(skills_legacy_from_cv) + list(skills_from_docx) + list(skills_legacy_from_docx):
                s_str = str(s).strip()
                if s_str and s_str.lower() not in seen_lower:
                    seen_lower.add(s_str.lower())
                    skills_list.append(s_str)
            
            total_count = len(skills_list)

            notes = str(meta.get("skills_ranking_notes") or "").strip()
            work_notes = str(meta.get("work_tailoring_notes") or "").strip()
            job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
            job_summary = deps.format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""

            skills_preview = "\n".join([f"{i+1}. {str(s).strip()}" for i, s in enumerate(skills_list[:20]) if str(s).strip()]) or "(no skills found)"

            fields = [
                {"key": "skills_preview", "label": f"Your skills (FÄHIGKEITEN & KOMPETENZEN) ({total_count} total)", "value": skills_preview},
            ]
            if job_summary:
                fields.append({"key": "job_reference", "label": "Job summary", "value": job_summary})
            # Always show work tailoring context here (users want to adjust it close to skill ranking and reuse it later).
            fields.append(
                {
                    "key": "work_tailoring_notes",
                    "label": "Work tailoring context (optional)",
                    "value": work_notes,
                    "type": "textarea",
                    "editable": True,
                    "placeholder": "What should recruiters notice in your work experience for this role? (keywords, achievements, focus areas)",
                }
            )
            if notes:
                fields.append({"key": "ranking_notes", "label": "Ranking notes", "value": notes})

            actions = [{"id": "SKILLS_ADD_NOTES", "label": "Add ranking notes", "style": "secondary"}]
            has_job_context = bool(job_ref or str(meta.get("job_posting_text") or "").strip())
            if has_job_context and deps.openai_enabled():
                actions.append({"id": "SKILLS_TAILOR_RUN", "label": "Generate ranked skills", "style": "primary"})
                actions.append({"id": "SKILLS_TAILOR_SKIP", "label": "Skip ranking", "style": "secondary"})
            else:
                actions.append({"id": "SKILLS_TAILOR_SKIP", "label": "Continue", "style": "primary"})

            return {
                "kind": "review_form",
                "stage": "IT_AI_SKILLS",
                "title": f"Stage 5b/{wizard_total} — Skills (FÄHIGKEITEN & KOMPETENZEN)",
                "text": "Rank your skills by job relevance (recommended), or skip.",
                "fields": fields,
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "skills_notes_edit":
            actions = [
                {"id": "SKILLS_NOTES_CANCEL", "label": "Cancel", "style": "secondary"},
                {"id": "SKILLS_NOTES_SAVE", "label": "Save notes", "style": "secondary"},
            ]
            if deps.openai_enabled():
                actions.append({"id": "SKILLS_TAILOR_RUN", "label": "Generate ranked skills", "style": "primary"})
            else:
                actions.append({"id": "SKILLS_TAILOR_SKIP", "label": "Continue", "style": "primary"})
            return {
                "kind": "edit_form",
                "stage": "IT_AI_SKILLS",
                "title": f"Stage 5b/{wizard_total} — Skills (FÄHIGKEITEN & KOMPETENZEN)",
                "text": "Add ranking notes for the AI (optional), then Save or Generate.",
                "fields": [
                    {
                        "key": "skills_ranking_notes",
                        "label": "Ranking notes",
                        "value": str(meta.get("skills_ranking_notes") or ""),
                        "type": "textarea",
                    }
                ],
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "skills_tailor_review":
            proposal_block = meta.get("skills_proposal_block") if isinstance(meta.get("skills_proposal_block"), dict) else None
            fields_list = []
            
            if isinstance(proposal_block, dict):
                # Extract both skill sections from unified proposal
                it_ai_skills = proposal_block.get("it_ai_skills") if isinstance(proposal_block.get("it_ai_skills"), list) else []
                tech_ops_skills = proposal_block.get("technical_operational_skills") if isinstance(proposal_block.get("technical_operational_skills"), list) else []
                
                # Format IT & AI skills
                it_ai_lines = [f"{i+1}. {str(s).strip()}" for i, s in enumerate(it_ai_skills[:8]) if str(s).strip()]
                fields_list.append({
                    "key": "it_ai_skills",
                    "label": "IT & AI Skills",
                    "value": "\n".join(it_ai_lines) if it_ai_lines else "(no skills proposed)"
                })
                
                # Format Technical & Operational skills
                tech_ops_lines = [f"{i+1}. {str(s).strip()}" for i, s in enumerate(tech_ops_skills[:8]) if str(s).strip()]
                fields_list.append({
                    "key": "technical_operational_skills",
                    "label": "Technical & Operational Skills",
                    "value": "\n".join(tech_ops_lines) if tech_ops_lines else "(no skills proposed)"
                })
                
                # Add notes if present
                notes = proposal_block.get("notes")
                if notes and str(notes).strip():
                    fields_list.append({
                        "key": "notes",
                        "label": "Notes",
                        "value": str(notes).strip()[:500]
                    })
            
            if not fields_list:
                fields_list = [{"key": "proposal", "label": "Proposal", "value": "(no proposal generated)"}]
            
            actions = [{"id": "SKILLS_TAILOR_ACCEPT", "label": "Accept proposal", "style": "primary"}]
            if deps.openai_enabled():
                actions.append({"id": "SKILLS_TAILOR_RUN", "label": "Regenerate proposal", "style": "secondary"})
            actions.append({"id": "SKILLS_TAILOR_SKIP", "label": "Skip ranking", "style": "secondary"})
            return {
                "kind": "review_form",
                "stage": "SKILLS_RANKING",
                "title": f"Stage 5/{wizard_total} — Skills (proposal)",
                "text": "Review the proposed skills (IT & AI + Technical & Operational). Accept to apply to your CV.",
                "fields": fields_list,
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "review_final":
            pdf_refs = meta.get("pdf_refs") if isinstance(meta.get("pdf_refs"), dict) else {}
            has_pdf = bool(meta.get("pdf_generated") or (isinstance(pdf_refs, dict) and len(pdf_refs) > 0))
            target_lang = str(meta.get("target_language") or meta.get("language") or "en").strip().lower()

            actions: list[dict] = []
            
            # Button order (as per plan):
            # 1. REQUEST_GENERATE_PDF (or regenerate if already generated)
            # 2. DOWNLOAD_PDF (always visible after PDF generation)
            # 3. GENERATE_COVER_LETTER (optional, gated)
            
            if not has_pdf:
                # Before PDF generation: show only generate button
                actions.append({
                    "id": "REQUEST_GENERATE_PDF",
                    "label": "Generate PDF",
                    "style": "primary",
                })
            else:
                # After PDF generation: show download first, then optional regenerate
                actions.append({
                    "id": "DOWNLOAD_PDF",
                    "label": "Pobierz PDF / Download PDF",
                    "style": "primary",
                })
                actions.append({
                    "id": "REQUEST_GENERATE_PDF",
                    "label": "Regenerate PDF",
                    "style": "secondary",
                })

            # Cover letter action (always after PDF actions)
            if deps.cv_enable_cover_letter and deps.openai_enabled() and target_lang in ("en", "de"):
                actions.append({
                    "id": "COVER_LETTER_PREVIEW",
                    "label": "Generate Cover Letter",
                    "style": "secondary",
                })

            return {
                "kind": "review_form",
                "stage": "REVIEW_FINAL",
                "title": f"Stage 6/{wizard_total} — Generate",
                "text": "PDF is ready. Download it?" if has_pdf else "Your CV is ready. Generate PDF?",
                "fields": [],
                "actions": actions,
                "disable_free_text": True,
            }

        if wizard_stage == "cover_letter_review":
            cl = meta.get("cover_letter_block") if isinstance(meta.get("cover_letter_block"), dict) else None
            fields_list: list[dict] = []
            if isinstance(cl, dict):
                fields_list.append({"key": "opening", "label": "Opening", "value": str(cl.get("opening_paragraph") or "").strip()})
                core = cl.get("core_paragraphs") if isinstance(cl.get("core_paragraphs"), list) else []
                if len(core) >= 1:
                    fields_list.append({"key": "core1", "label": "Core paragraph 1", "value": str(core[0] or "").strip()})
                if len(core) >= 2:
                    fields_list.append({"key": "core2", "label": "Core paragraph 2", "value": str(core[1] or "").strip()})
                fields_list.append({"key": "closing", "label": "Closing", "value": str(cl.get("closing_paragraph") or "").strip()})
                fields_list.append({"key": "signoff", "label": "Sign-off", "value": str(cl.get("signoff") or "").strip()})
            if not fields_list:
                fields_list = [{"key": "cover_letter", "label": "Cover letter", "value": "(not generated)"}]

            return {
                "kind": "review_form",
                "stage": "COVER_LETTER",
                "title": f"Stage 7/{wizard_total} — Cover Letter (optional)",
                "text": "Review your cover letter draft. Generate the final 1-page PDF when ready.",
                "fields": fields_list,
                "actions": [
                    {"id": "COVER_LETTER_BACK", "label": "Back", "style": "secondary"},
                    {
                        "id": "COVER_LETTER_GENERATE",
                        "label": "Generate final Cover Letter PDF",
                        "style": "primary",
                    },
                ],
                "disable_free_text": True,
            }

        if wizard_stage == "generate_confirm":
            return {
                "kind": "confirm",
                "stage": "GENERATE_PDF",
                "title": "Generate PDF?",
                "text": "This will generate the final PDF for your current session.",
                "actions": [{"id": "REQUEST_GENERATE_PDF", "label": "Generate PDF", "style": "primary"}],
                "disable_free_text": True,
            }

        # Default: no action
        return None

    # Legacy: no ui_action for now (wizard sessions cover the UI).
    return None


