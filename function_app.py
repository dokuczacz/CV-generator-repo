"""
Azure Functions app for CV Generator.

Public surface area (intentionally minimal):
  - GET  /api/health
  - POST /api/cv-tool-call-handler

All workflow operations are routed through the tool dispatcher to keep the API surface small and the UI thin.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
import uuid
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import azure.functions as func

# Reduce Azure SDK HTTP noise; keep only warnings/errors.
for _logger_name in (
    "azure",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.data.tables",
    "azure.storage.blob",
):
    try:
        logging.getLogger(_logger_name).setLevel(logging.WARNING)
    except Exception:
        pass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.blob_store import BlobPointer, CVBlobStore
from src.context_pack import build_context_pack_v2, build_context_pack_v2_delta, format_context_pack_with_delimiters
from src.docx_photo import extract_first_photo_from_docx_bytes
from src.docx_prefill import prefill_cv_from_docx_bytes
from src.normalize import normalize_cv_data
from src.render import render_cover_letter_pdf, render_html
from src.schema_validator import validate_canonical_schema
from src.profile_store import get_profile_store
from src.session_store import CVSessionStore
from src.structured_response import parse_structured_response, format_user_message_for_ui
from src.validator import validate_cv
from src.cv_fsm import CVStage, SessionState, ValidationState, resolve_stage, detect_edit_intent
from src.job_reference import get_job_reference_response_format, parse_job_reference, format_job_reference_for_display
from src.work_experience_proposal import get_work_experience_bullets_proposal_response_format, parse_work_experience_bullets_proposal
from src.cover_letter_proposal import get_cover_letter_proposal_response_format, parse_cover_letter_proposal
from src.skills_unified_proposal import (
    get_skills_unified_proposal_response_format,
    parse_skills_unified_proposal,
)
from src.orchestrator.openai_client import OpenAIJsonSchemaDeps, openai_json_schema_call
from src.orchestrator.wizard.action_dispatch_contact import ContactActionDeps, handle_contact_and_language_actions
from src.orchestrator.wizard.action_dispatch_education import EducationActionDeps, handle_education_basic_actions
from src.orchestrator.wizard.action_dispatch_job_posting_ai import JobPostingAIDeps, handle_job_posting_ai_actions
from src.orchestrator.wizard.action_dispatch_job_posting_basic import JobPostingBasicDeps, handle_job_posting_basic_actions
from src.orchestrator.wizard.action_dispatch_navigation import NavigationActionDeps, handle_navigation_actions
from src.orchestrator.wizard.action_dispatch_cover_pdf import CoverPdfActionDeps, handle_cover_pdf_actions
from src.orchestrator.wizard.action_dispatch_fast_paths import FastPathsActionDeps, handle_fast_paths_actions
from src.orchestrator.wizard.action_dispatch_profile_confirm import ProfileConfirmActionDeps, handle_profile_confirm_actions
from src.orchestrator.wizard.action_dispatch_skills import SkillsActionDeps, handle_skills_actions
from src.orchestrator.wizard.action_dispatch_work_basic import WorkBasicActionDeps, handle_work_basic_actions
from src.orchestrator.wizard.action_dispatch_work_manage import WorkManageActionDeps, handle_work_manage_actions
from src.orchestrator.wizard.action_dispatch_work_tailor_ai import WorkTailorAIActionDeps, handle_work_tailor_ai_actions
from src.orchestrator.wizard.ui_builder import UiBuilderDeps, build_ui_action
from src.orchestrator.entrypoints import EntryPointDeps, handle_cv_tool_call, handle_health_check
from src.orchestrator.responses_loop import ResponsesLoopDeps, run_responses_tool_loop_v2
from src.orchestrator.tools.context_pack_tools import ContextPackToolDeps, tool_generate_context_pack_v2
from src.orchestrator.tools.cv_pdf_tools import CvPdfToolDeps, tool_generate_cv_from_session
from src.orchestrator.tools.pdf_tools import CoverLetterToolDeps, tool_generate_cover_letter_from_session, tool_get_pdf_by_ref
from src.orchestrator.tools.session_tools import ExtractStoreToolDeps, tool_extract_and_store_cv
from src.orchestrator.tools.tool_schemas import tool_schemas_for_responses
from src.prompt_registry import get_prompt
from src import product_config
from src.i18n import get_cover_letter_signoff


_SCHEMA_REPAIR_HINTS_BY_STAGE: dict[str, str] = {
    # All hints are additive to the schema requirement. Keep them short and actionable.
    "job_posting": (
        "Return ONLY valid JSON (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings; use spaces instead. "
        "Keep strings concise."
    ),
    "work_experience": (
        "Return ONLY valid JSON (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings; use spaces instead. "
        "Keep bullets short and single-line (<= 90 chars each)."
    ),
    "further_experience": (
        "Return ONLY valid JSON (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings; use spaces instead. "
        "Keep bullets short and single-line (<= 90 chars each)."
    ),
    "it_ai_skills": (
        "Return ONLY valid JSON (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings; use spaces instead. "
        "Ensure both it_ai_skills and technical_operational_skills are arrays of strings (max 6 items each). "
        "Use short recruiter-friendly labels that are easy for non-technical reviewers to scan. "
        "Do not duplicate skills between the two sections."
    ),
    "bulk_translation": (
        "Return ONLY valid JSON (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings; use spaces instead. "
        "Do not truncate the JSON; ensure all required keys are present. "
        "Keep arrays the same length as input and keep every string single-line."
    ),
    "cover_letter": (
        "Return ONLY valid JSON (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings; use spaces instead (signoff may contain one '\\n'). "
        "No bullet points. Max 450 words total."
    ),
}


WORK_ROLE_ALIGNMENT_THRESHOLD = 0.5

ALIGNMENT_RUBRIC_LIMITS: dict[str, float] = {
    "core_responsibilities_match": 0.40,
    "methods_tools_match": 0.25,
    "context_match": 0.15,
    "seniority_scope": 0.10,
    "language_requirements_match": 0.10,
}

_EVIDENCE_STRICT_TERMS = [
    "smed",
    "oee",
    "ppap",
    "apqp",
    "fmea",
    "8d",
    "six sigma",
    "dmaic",
    "vsm",
    "rca",
    "kaizen",
    "iatf",
]


def _schema_repair_instructions(*, stage: str | None, parse_error: str | None = None) -> str:
    """Build a stage-specific, MCP-like repair instruction for the model."""
    stage_key = (stage or "").strip()
    hint = _SCHEMA_REPAIR_HINTS_BY_STAGE.get(stage_key) or (
        "Return ONLY valid JSON that strictly conforms to the schema (no markdown/code fences, no prose). "
        "Do not include literal newline characters inside JSON strings."
    )
    if parse_error:
        return f"Your previous response had invalid JSON syntax: {parse_error}. {hint}"
    return f"Your previous response did not match the required JSON schema. {hint}"


def _build_work_bullet_violation_payload(*, roles: list, hard_limit: int, min_reduction_chars: int = 30) -> dict:
    """Build MCP-like payload for overlong work bullets."""

    def _clean_one_line(s: str) -> str:
        return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()

    def _get_bullets(role) -> list:
        if isinstance(role, dict):
            bullets = role.get("bullets") if isinstance(role.get("bullets"), list) else role.get("responsibilities")
            return bullets if isinstance(bullets, list) else []
        return list(getattr(role, "bullets", []) or [])

    def _get_company(role) -> str:
        if isinstance(role, dict):
            return _clean_one_line(str(role.get("employer") or role.get("company") or ""))
        return _clean_one_line(str(getattr(role, "company", "") or ""))

    def _get_title(role) -> str:
        if isinstance(role, dict):
            return _clean_one_line(str(role.get("title") or role.get("position") or ""))
        return _clean_one_line(str(getattr(role, "title", "") or ""))

    violations: list[dict] = []
    for role_idx, role in enumerate(roles or []):
        bullets = _get_bullets(role)
        for bullet_idx, bullet in enumerate(bullets or []):
            text = _clean_one_line(str(bullet or ""))
            blen = len(text)
            if blen > int(hard_limit):
                violations.append(
                    {
                        "role_index": role_idx,
                        "bullet_index": bullet_idx,
                        "company": _get_company(role),
                        "title": _get_title(role),
                        "length": blen,
                        "max_chars": int(hard_limit),
                        "min_reduction_chars": int(min_reduction_chars),
                        "bullet": text[:240],
                    }
                )

    return {
        "error_code": "VALIDATION:WORK_EXPERIENCE_BULLET_TOO_LONG",
        "violations": violations,
    }


def _select_roles_by_violation_indices(*, roles: list, violations: list[dict]) -> list:
    """Select roles that contain violating bullets, preserving original order."""
    if not roles or not violations:
        return []
    idxs = {int(v.get("role_index")) for v in violations if isinstance(v, dict) and str(v.get("role_index", "")).isdigit()}
    if not idxs:
        return []
    return [r for i, r in enumerate(roles) if i in idxs]


def _friendly_schema_error_message(err: str) -> str:
    """Avoid leaking low-level parser errors to the end-user."""
    e = (err or "").strip()
    if not e:
        return "AI output format issue. Please try again."
    low = e.lower()
    if "invalid json" in low or "non-object json" in low or "json" in low:
        return "AI output format issue. Please click Generate again (it retries automatically once)."
    return f"AI failed: {e}"


_SESSION_STORE: CVSessionStore | None = None
_CLEANUP_EXPIRED_RAN = False


def _get_session_store() -> CVSessionStore:
    global _SESSION_STORE
    if _SESSION_STORE is None:
        _SESSION_STORE = CVSessionStore()
    return _SESSION_STORE


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _sha256_text(s: str) -> str:
    """Compute SHA256 hash of text for idempotency detection."""
    try:
        return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()
    except Exception:
        return ""


def _snapshot_session(session_id: str, cv_data: dict, snapshot_type: str = "cv") -> BlobPointer | None:
    """
    Upload a timestamped session snapshot to cv-artifacts blob container.
    
    Args:
        session_id: Session ID
        cv_data: CV data or other snapshot data (skills proposal, etc.)
        snapshot_type: Type of snapshot ('cv', 'skills_proposal', 'work_proposal', etc.)
    
    Returns:
        BlobPointer if successful, None if error
    """
    try:
        blob_store = CVBlobStore(container="cv-artifacts")
        pointer = blob_store.upload_session_snapshot(
            session_id=session_id,
            cv_data=cv_data,
            snapshot_type=snapshot_type
        )
        logging.info(f"Session snapshot saved: {snapshot_type} for session {session_id[:8]}")
        return pointer
    except Exception as e:
        logging.warning(f"Failed to upload session snapshot: {e}")
        return None



def _work_role_lock_key(*, role_index: int) -> str:
    return str(int(role_index))


def _is_work_role_locked(*, meta: dict, role_index: int) -> bool:
    locks = meta.get("work_role_locks") if isinstance(meta.get("work_role_locks"), dict) else {}
    k = _work_role_lock_key(role_index=role_index)
    return bool((locks or {}).get(k) is True)


def _normalize_date_range_one_line(s: str) -> str:
    """Normalize date range separators to ASCII for PDF rendering stability."""
    txt = " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()
    if not txt:
        return ""
    # Replace common dash variants that may render as tofu (□) in some PDF fonts.
    txt = (
        txt.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    # Normalize year-month tokens like "2016 - 04" -> "2016-04".
    txt = re.sub(r"(\b\d{4})\s*-\s*(\d{2}\b)", r"\1-\2", txt)
    # Normalize full ranges like "2012 - 04 - 2016 - 05" -> "2012-04 - 2016-05".
    txt = re.sub(
        r"(\b\d{4})\s*-\s*(\d{2})\s*-\s*(\b\d{4})\s*-\s*(\d{2}\b)",
        r"\1-\2 - \3-\4",
        txt,
    )
    # Normalize ranges with present/current like "2012 - 04 - present".
    txt = re.sub(
        r"(\b\d{4})\s*-\s*(\d{2})\s*-\s*(\bpresent\b|\bcurrent\b)",
        r"\1-\2 - \3",
        txt,
        flags=re.IGNORECASE,
    )
    txt = re.sub(
        r"(\bpresent\b|\bcurrent\b)\s*-\s*(\b\d{4})\s*-\s*(\d{2}\b)",
        r"\1 - \2-\3",
        txt,
        flags=re.IGNORECASE,
    )
    # Standardize spacing around range separators only (preserve YYYY-MM).
    txt = re.sub(
        r"(\b\d{4}(?:-\d{2})?|\bpresent\b|\bcurrent\b)\s*-\s*(\b\d{4}(?:-\d{2})?|\bpresent\b|\bcurrent\b)",
        r"\1 - \2",
        txt,
        flags=re.IGNORECASE,
    )
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _infer_style_profile(cv_data: dict) -> str:
    """Infer a simple style profile from CV data (deterministic heuristic)."""
    try:
        it = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
        tech = cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else []
        work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
        has_metrics = False
        for r in work[:6] if isinstance(work, list) else []:
            if not isinstance(r, dict):
                continue
            bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else []
            for b in bullets[:8] if isinstance(bullets, list) else []:
                if re.search(r"\b\d+%|\b\d+\s*(k|K)\b|\b\d+\s*(months?|weeks?)\b", str(b)):
                    has_metrics = True
                    break
            if has_metrics:
                break
        if len(it) >= 6 and len(tech) <= 4:
            return "technical"
        if len(tech) >= 6 and len(it) <= 4:
            return "managerial"
        if has_metrics:
            return "mixed_metrics"
        return "mixed"
    except Exception:
        return "mixed"


def _count_words(s: str) -> int:
    return len([w for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", str(s or "")) if w.strip()])


def _validate_cover_letter_block(*, block: dict, cv_data: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(block, dict):
        return False, ["Cover letter block missing or invalid"]

    opening = str(block.get("opening_paragraph") or "").strip()
    core = block.get("core_paragraphs") if isinstance(block.get("core_paragraphs"), list) else []
    closing = str(block.get("closing_paragraph") or "").strip()
    signoff = str(block.get("signoff") or "").strip()

    if not opening or not closing or not signoff:
        errors.append("Missing required paragraphs")

    core_clean = [str(p).strip() for p in (core or []) if str(p).strip()]
    if not core_clean:
        errors.append("Missing core paragraphs")

    text_all = "\n\n".join([opening] + core_clean + [closing, signoff]).strip()

    # No bullets
    if re.search(r"(^|\n)\s*[-•]\s+", text_all):
        errors.append("Bullet points are not allowed")

    # Word cap (exclude header, which backend derives)
    wc = _count_words("\n\n".join([opening] + core_clean + [closing]).strip())
    if wc > 450:
        errors.append(f"Word cap exceeded: {wc} (max 450)")

    # Ensure sign-off is anchored to the CV identity
    full_name = str(cv_data.get("full_name") or "").strip()
    if not full_name:
        errors.append("CV full_name is missing (needed for sign-off)")
    elif full_name.casefold() not in signoff.casefold():
        errors.append("Sign-off must include the CV full name")

    return (len(errors) == 0), errors


def _normalize_work_role_from_proposal(raw: dict) -> dict:
    def _clean_one_line(s: str) -> str:
        return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()

    if not isinstance(raw, dict):
        return {"employer": "", "title": "", "date_range": "", "location": "", "bullets": []}

    bullets_in = raw.get("bullets", []) if isinstance(raw.get("bullets"), list) else []
    bullets = [_clean_one_line(str(b)) for b in bullets_in if _clean_one_line(str(b))][:5]
    employer = _clean_one_line(str(raw.get("company") or raw.get("employer") or ""))
    title = _clean_one_line(str(raw.get("title") or ""))

    # Some model outputs accidentally embed the company in `title` (e.g., "Role, Company").
    # Make a best-effort split so employer is not missing (validator requires it).
    if (not employer) and title and "," in title:
        left, right = title.split(",", 1)
        left = left.strip()
        right = right.strip()
        if left and right:
            title = left
            employer = right

    return {
        "employer": employer,
        "title": title,
        "date_range": _normalize_date_range_one_line(raw.get("date_range") or ""),
        # Location is intentionally ignored for work tailoring proposals; backend preserves imported locations.
        "location": "",
        "bullets": bullets,
    }


def _find_work_bullet_hard_limit_violations(*, cv_data: dict, hard_limit: int = 200) -> list[str]:
    """Return a list of hard-limit violations for work_experience bullets."""

    def _clean_one_line(s: str) -> str:
        return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()

    violations: list[str] = []
    work = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
    for i, role in enumerate(work or []):
        if not isinstance(role, dict):
            continue
        bullets = role.get("bullets") if isinstance(role.get("bullets"), list) else role.get("responsibilities")
        if not isinstance(bullets, list):
            continue
        for j, b in enumerate(bullets):
            blen = len(_clean_one_line(b))
            if blen > int(hard_limit):
                violations.append(f"work_experience[{i}].bullets[{j}]: {blen} chars (max {hard_limit})")
    return violations


def _extract_e0_corpus_from_labeled_blocks(user_text: str, labels: list[str]) -> str:
    blocks: list[str] = []
    for label in labels:
        chunk = _extract_labeled_block_text(user_text, label)
        if chunk:
            blocks.append(chunk)
    return "\n".join(blocks)


def _contains_metric_like_claim(text: str) -> bool:
    s = str(text or "")
    return bool(re.search(r"\b\d+\s*%|\b\d+\s*(k|m|million|months?|weeks?|days?|hours?)\b|\breduced by\b|\bincreased by\b", s, flags=re.IGNORECASE))


def _contains_any_digit(text: str) -> bool:
    return bool(re.search(r"\d", str(text or "")))


def _extract_strict_terms(text: str) -> set[str]:
    normalized = str(text or "").casefold()
    found: set[str] = set()
    for term in _EVIDENCE_STRICT_TERMS:
        if term in normalized:
            found.add(term)
    return found


def _find_work_e0_violations(*, roles: list[Any], e0_corpus: str) -> list[str]:
    violations: list[str] = []
    source = str(e0_corpus or "")
    source_terms = _extract_strict_terms(source)
    source_has_digits = _contains_any_digit(source)

    for role_idx, role in enumerate(roles or []):
        bullets = []
        if isinstance(role, dict):
            bullets = role.get("bullets") if isinstance(role.get("bullets"), list) else []
        elif hasattr(role, "bullets"):
            bullets = list(getattr(role, "bullets", []) or [])

        for bullet_idx, bullet in enumerate(bullets or []):
            text = str(bullet or "").strip()
            if not text:
                continue
            if _contains_metric_like_claim(text) and not source_has_digits:
                violations.append(f"Role {role_idx+1}, Bullet {bullet_idx+1}: metric-like claim without E0 metric evidence")
            for term in sorted(_extract_strict_terms(text)):
                if term not in source_terms:
                    violations.append(f"Role {role_idx+1}, Bullet {bullet_idx+1}: uses '{term}' without E0 evidence")
    return violations


def _find_cover_letter_e0_violations(*, paragraphs: list[str], e0_corpus: str) -> list[str]:
    text = "\n".join([str(p or "").strip() for p in (paragraphs or []) if str(p or "").strip()])
    source = str(e0_corpus or "")
    source_terms = _extract_strict_terms(source)
    source_has_digits = _contains_any_digit(source)
    violations: list[str] = []
    if _contains_metric_like_claim(text) and not source_has_digits:
        violations.append("Metric-like claims in cover letter are not supported by E0 evidence")
    for term in sorted(_extract_strict_terms(text)):
        if term not in source_terms:
            violations.append(f"Cover letter uses '{term}' without E0 evidence")
    return violations


def _reset_metadata_for_new_version(meta: dict) -> dict:
    """Reset job-scoped artifacts for a new version while keeping translation/cache state."""
    out = dict(meta or {})
    out["pdf_generated"] = False
    out.pop("pdf_refs", None)
    out.pop("pdf_refs_blob_ref", None)
    out.pop("latest_pdf_ref", None)

    out.pop("job_reference", None)
    out.pop("job_reference_status", None)
    out.pop("job_reference_error", None)
    out["job_reference_sig"] = ""

    out.pop("work_experience_proposal_block", None)
    out.pop("work_experience_proposal_error", None)
    out["work_experience_proposal_sig"] = ""
    out.pop("work_experience_proposal_base_sig", None)

    out.pop("skills_proposal_block", None)
    out.pop("skills_proposal_error", None)
    out["skills_proposal_sig"] = ""
    out.pop("skills_proposal_base_sig", None)

    out.pop("work_experience_proposal_accepted_at", None)
    out.pop("skills_proposal_accepted_at", None)
    out.pop("work_experience_tailored", None)
    out.pop("it_ai_skills_tailored", None)
    out.pop("cover_letter_generated", None)

    out.pop("pending_confirmation", None)
    out.pop("work_selected_index", None)
    out["new_version_reset_at"] = _now_iso()
    return out


def _apply_work_experience_proposal_with_locks(*, cv_data: dict, proposal_roles: list[dict], meta: dict) -> dict:
    """Apply a work_experience proposal to cv_data while respecting per-role locks.

    Locking is index-based (role index in current cv_data['work_experience']),
    but proposal application is fingerprint-based to avoid shifting metadata (e.g., locations)
    when the model reorders or filters roles.
    """
    cv2 = dict(cv_data or {})
    cur = cv2.get("work_experience") if isinstance(cv2.get("work_experience"), list) else []
    cur_list = cur if isinstance(cur, list) else []
    if not cur_list:
        return cv2

    def _clean_one_line(s: str) -> str:
        return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()

    def _role_employer(role: dict) -> str:
        return _clean_one_line(str(role.get("employer") or role.get("company") or ""))

    def _role_title(role: dict) -> str:
        return _clean_one_line(str(role.get("title") or role.get("position") or ""))

    def _role_date_range(role: dict) -> str:
        return _normalize_date_range_one_line(role.get("date_range") or "")

    def _role_location(role: dict) -> str:
        return (
            _clean_one_line(str(role.get("location") or ""))
            or _clean_one_line(str(role.get("city") or ""))
            or _clean_one_line(str(role.get("place") or ""))
        )

    def _fp_primary(role: dict) -> str:
        return "|".join([_role_employer(role).casefold(), _role_date_range(role).casefold()]).strip("|")

    def _fp_secondary(role: dict) -> str:
        return "|".join([_role_title(role).casefold(), _role_employer(role).casefold(), _role_date_range(role).casefold()]).strip("|")

    def _title_prefix(title: str) -> str:
        t = _clean_one_line(title or "")
        if not t:
            return ""
        for sep in (" | ", " — ", " – ", " - ", " @ ", " at "):
            if sep in t:
                t = t.split(sep, 1)[0].strip()
        if "," in t:
            t = t.split(",", 1)[0].strip()
        return t

    def _extract_employer_from_title(title: str) -> tuple[str, str]:
        t = _clean_one_line(title or "")
        if not t or "," not in t:
            return t, ""
        left, right = t.split(",", 1)
        left = left.strip()
        right = right.strip()
        if not left or not right:
            return t, ""
        return left, right

    def _bullets_within_limit(bullets: list[str], *, hard_limit: int) -> bool:
        for b in bullets or []:
            if len(_clean_one_line(b)) > int(hard_limit):
                return False
        return True

    def _strip_suffixes_from_title(*, title: str, employer: str, location: str) -> str:
        t = str(title or "").strip()
        if not t:
            return ""
        parts = [t]
        for needle in [employer, location]:
            n = str(needle or "").strip()
            if not n:
                continue
            idx = t.casefold().find(n.casefold())
            if idx >= 0:
                parts.append(t[:idx].rstrip(" ,-|—–").strip())
        best = min([p for p in parts if p], key=len, default=t)
        return best or t

    proposed_norm = [_normalize_work_role_from_proposal(r) for r in (proposal_roles or []) if isinstance(r, dict)]
    proposed_by_secondary: dict[str, list[int]] = {}
    proposed_by_primary: dict[str, list[int]] = {}
    proposed_by_title_date: dict[str, list[int]] = {}
    proposed_by_date_only: dict[str, list[int]] = {}
    for j, pr in enumerate(proposed_norm):
        ks = _fp_secondary(pr)
        kp = _fp_primary(pr)
        ktd = "|".join([_title_prefix(_role_title(pr)).casefold(), _role_date_range(pr).casefold()]).strip("|")
        kdo = _role_date_range(pr).casefold()
        if ks:
            proposed_by_secondary.setdefault(ks, []).append(j)
        if kp:
            proposed_by_primary.setdefault(kp, []).append(j)
        if ktd:
            proposed_by_title_date.setdefault(ktd, []).append(j)
        if kdo:
            proposed_by_date_only.setdefault(kdo, []).append(j)

    used: set[int] = set()
    out: list[dict] = []
    for i, existing in enumerate(cur_list):
        existing_role = dict(existing) if isinstance(existing, dict) else {}
        if _is_work_role_locked(meta=meta or {}, role_index=i):
            out.append(existing_role)
            continue

        # Ensure employer is not silently missing (validator requires it).
        if not _role_employer(existing_role):
            t = _role_title(existing_role)
            t2, emp2 = _extract_employer_from_title(t)
            if emp2:
                existing_role["title"] = t2
                existing_role["employer"] = emp2

        ks = _fp_secondary(existing_role)
        kp = _fp_primary(existing_role)
        ktd = "|".join([_title_prefix(_role_title(existing_role)).casefold(), _role_date_range(existing_role).casefold()]).strip("|")
        kdo = _role_date_range(existing_role).casefold()
        cand_idx = None
        if ks and ks in proposed_by_secondary:
            while proposed_by_secondary[ks] and proposed_by_secondary[ks][0] in used:
                proposed_by_secondary[ks].pop(0)
            if proposed_by_secondary[ks]:
                cand_idx = proposed_by_secondary[ks][0]
        if cand_idx is None and kp and kp in proposed_by_primary:
            while proposed_by_primary[kp] and proposed_by_primary[kp][0] in used:
                proposed_by_primary[kp].pop(0)
            if proposed_by_primary[kp]:
                cand_idx = proposed_by_primary[kp][0]
        if cand_idx is None and ktd and ktd in proposed_by_title_date:
            while proposed_by_title_date[ktd] and proposed_by_title_date[ktd][0] in used:
                proposed_by_title_date[ktd].pop(0)
            if proposed_by_title_date[ktd]:
                cand_idx = proposed_by_title_date[ktd][0]
        if cand_idx is None and kdo and kdo in proposed_by_date_only:
            # Only accept a date-only match if the title prefix also matches to avoid shifting roles.
            while proposed_by_date_only[kdo] and proposed_by_date_only[kdo][0] in used:
                proposed_by_date_only[kdo].pop(0)
            if proposed_by_date_only[kdo]:
                j = proposed_by_date_only[kdo][0]
                pr = proposed_norm[j] if 0 <= j < len(proposed_norm) else {}
                if _title_prefix(_role_title(pr)).casefold() == _title_prefix(_role_title(existing_role)).casefold():
                    cand_idx = j

        if cand_idx is None or cand_idx >= len(proposed_norm):
            out.append(existing_role)
            continue
        used.add(cand_idx)
        cand = dict(proposed_norm[cand_idx] or {})

        existing_employer = _role_employer(existing_role)
        existing_date = _role_date_range(existing_role)
        existing_loc = _role_location(existing_role)
        existing_title = _role_title(existing_role)

        new_role = dict(existing_role)
        cand_title = _strip_suffixes_from_title(title=str(cand.get("title") or ""), employer=existing_employer, location=existing_loc)
        if cand_title:
            new_role["title"] = cand_title
        elif existing_title:
            new_role["title"] = existing_title

        # Preserve employer/date_range from imported CV to prevent mismatches; only fill if missing.
        if existing_employer:
            new_role["employer"] = existing_employer
        else:
            new_role["employer"] = _role_employer(cand)
        if existing_date:
            new_role["date_range"] = existing_date
        else:
            new_role["date_range"] = _role_date_range(cand)

        # Preserve imported location (never take from AI output).
        new_role["location"] = existing_loc or ""

        bullets = cand.get("bullets") if isinstance(cand.get("bullets"), list) else []
        bullets_clean = [_clean_one_line(b) for b in bullets if _clean_one_line(b)]
        bullets_clean = bullets_clean[:5]

        # Never truncate bullets in backend. If the proposal violates hard limits,
        # skip applying this role to avoid silently corrupting content.
        hard_limit = product_config.WORK_EXPERIENCE_HARD_LIMIT_CHARS
        if bullets_clean and _bullets_within_limit(bullets_clean, hard_limit=hard_limit):
            new_role["bullets"] = bullets_clean

        # Final guard: employer must be present for validation/PDF generation.
        if not _clean_one_line(str(new_role.get("employer") or "")):
            tt = _clean_one_line(str(new_role.get("title") or ""))
            tt2, emp2 = _extract_employer_from_title(tt)
            if emp2:
                new_role["title"] = tt2
                new_role["employer"] = emp2
        out.append(new_role)

    cv2["work_experience"] = out
    return cv2


def _overwrite_work_experience_from_proposal_roles(*, cv_data: dict, proposal_roles: list[dict]) -> dict:
    """Replace entire work_experience section with normalized proposal roles."""

    def _clean_one_line(s: str) -> str:
        return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()

    cv2 = dict(cv_data or {})
    out: list[dict] = []

    for raw in (proposal_roles or [])[:12]:
        if not isinstance(raw, dict):
            continue
        rr = _normalize_work_role_from_proposal(raw)
        if not str(rr.get("employer") or "").strip():
            continue

        location = _clean_one_line(str(raw.get("location") or raw.get("city") or raw.get("place") or ""))
        out.append(
            {
                "employer": str(rr.get("employer") or "").strip(),
                "title": str(rr.get("title") or "").strip(),
                "date_range": str(rr.get("date_range") or "").strip(),
                "location": location,
                "bullets": list(rr.get("bullets") or []),
            }
        )

    cv2["work_experience"] = out
    return cv2


def _backfill_missing_work_locations(*, cv_data: dict, previous_work: list[dict] | None, meta: dict | None) -> dict:
    def _clean_one_line(s: str) -> str:
        return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()

    def _role_employer(role: dict) -> str:
        return _clean_one_line(str(role.get("employer") or role.get("company") or ""))

    def _role_title(role: dict) -> str:
        return _clean_one_line(str(role.get("title") or role.get("position") or ""))

    def _role_date_range(role: dict) -> str:
        return _normalize_date_range_one_line(role.get("date_range") or "")

    def _role_location(role: dict) -> str:
        return (
            _clean_one_line(str(role.get("location") or ""))
            or _clean_one_line(str(role.get("city") or ""))
            or _clean_one_line(str(role.get("place") or ""))
        )

    cv2 = dict(cv_data or {})
    cur = cv2.get("work_experience") if isinstance(cv2.get("work_experience"), list) else []

    source_roles: list[dict] = []
    if isinstance(previous_work, list):
        source_roles.extend([r for r in previous_work if isinstance(r, dict)])

    if isinstance(meta, dict):
        dpu = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else None
        dpu_work = dpu.get("work_experience") if isinstance(dpu, dict) and isinstance(dpu.get("work_experience"), list) else []
        source_roles.extend([r for r in dpu_work if isinstance(r, dict)])

    if (not isinstance(cur, list) or not cur) and source_roles:
        hydrated: list[dict] = []
        for src in source_roles:
            emp = _role_employer(src)
            title = _role_title(src)
            date_range = _role_date_range(src)
            bullets = src.get("bullets") if isinstance(src.get("bullets"), list) else []
            if not emp or not title:
                continue
            hydrated.append(
                {
                    "employer": emp,
                    "title": title,
                    "date_range": date_range,
                    "location": _role_location(src),
                    "bullets": [str(b).strip() for b in bullets if str(b).strip()][:8],
                }
            )
        if hydrated:
            cv2["work_experience"] = hydrated
            return cv2

    if not isinstance(cur, list) or not cur:
        return cv2

    by_primary: dict[str, str] = {}
    by_secondary: dict[str, str] = {}
    for src in source_roles:
        loc = _role_location(src)
        if not loc:
            continue
        primary = "|".join([_role_employer(src).casefold(), _role_date_range(src).casefold()]).strip("|")
        secondary = "|".join([_role_title(src).casefold(), _role_employer(src).casefold(), _role_date_range(src).casefold()]).strip("|")
        if primary and primary not in by_primary:
            by_primary[primary] = loc
        if secondary and secondary not in by_secondary:
            by_secondary[secondary] = loc

    out: list[dict] = []
    for role in cur:
        role2 = dict(role) if isinstance(role, dict) else {}
        if _role_location(role2):
            out.append(role2)
            continue

        primary = "|".join([_role_employer(role2).casefold(), _role_date_range(role2).casefold()]).strip("|")
        secondary = "|".join([_role_title(role2).casefold(), _role_employer(role2).casefold(), _role_date_range(role2).casefold()]).strip("|")
        loc = by_secondary.get(secondary) or by_primary.get(primary) or ""
        if loc:
            role2["location"] = loc
        out.append(role2)

    cv2["work_experience"] = out
    return cv2


def _drop_one_work_bullet_bottom_up(*, cv_in: dict, min_bullets_per_role: int) -> tuple[dict, str | None]:
    """Drop exactly one work-experience bullet (bottom-up), keeping a floor per role.

    Deterministic and non-destructive: never shortens text, only removes the last bullet.
    """
    cv2 = dict(cv_in or {})
    work = cv2.get("work_experience") if isinstance(cv2.get("work_experience"), list) else None
    if not isinstance(work, list) or not work:
        return cv2, None

    work2 = list(work)
    for i in range(len(work2) - 1, -1, -1):
        role = work2[i]
        if not isinstance(role, dict):
            continue
        bullets = role.get("bullets")
        if not isinstance(bullets, list):
            bullets = role.get("responsibilities") if isinstance(role.get("responsibilities"), list) else []
        bullets = list(bullets or [])
        if len(bullets) <= int(min_bullets_per_role):
            continue
        role2 = dict(role)
        role2["bullets"] = bullets[:-1]
        if "responsibilities" in role2 and isinstance(role2.get("responsibilities"), list):
            role2["responsibilities"] = list(role2["bullets"])
        work2[i] = role2
        cv2["work_experience"] = work2
        return cv2, f"work_drop_bullet[{i}]"
    return cv2, None


def _dedupe_strings_case_insensitive(items: list, *, max_items: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for it in items or []:
        s = str(it).strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _extract_labeled_block_text(raw_text: str, label: str) -> str:
    text = str(raw_text or "")
    lbl = str(label or "").strip().upper()
    if not text.strip() or not lbl:
        return ""
    pattern = rf"(?is)\[{re.escape(lbl)}\]\s*(.*?)(?=\n\s*\[[A-Z0-9_]+\]|\Z)"
    m = re.search(pattern, text)
    return str(m.group(1) or "").strip() if m else ""


def _parse_candidate_skills_text(raw_text: str, *, max_items: int = 120) -> list[str]:
    text = str(raw_text or "")
    if not text.strip():
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in normalized.split("\n") if str(ln).strip()]
    out: list[str] = []
    split_on_commas = ("\n" not in normalized) and (normalized.count(",") >= 2)
    for line in lines:
        cleaned = re.sub(r"^\s*[-*•\u2022]+\s*", "", line).strip()
        cleaned = re.sub(r"^\s*\d+[\).\-:\s]+", "", cleaned).strip()
        if not cleaned:
            continue
        splitter = r"\s*[;,|]\s*" if split_on_commas else r"\s*[;|]\s*"
        parts = [p.strip() for p in re.split(splitter, cleaned) if p.strip()]
        if parts:
            out.extend(parts)
        else:
            out.append(cleaned)
    return _dedupe_strings_case_insensitive(out, max_items=max_items)


def _collect_raw_docx_skills_context(*, meta: dict, max_items: int = 20) -> list[str]:
    dpu = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else None
    if not isinstance(dpu, dict):
        return []

    out: list[str] = []

    def _sanitize_raw_skill_line(value: str) -> str:
        s = str(value or "").strip()
        if not s:
            return ""
        s = re.sub(
            r"(?is)^\s*(fähigkeiten\s*&\s*kompetenzen|faehigkeiten\s*&\s*kompetenzen|skills|kompetenzen)\s*[:\-\u2013\u2014]*\s*",
            "",
            s,
        ).strip()
        s = re.sub(r"(?is),?\s*git\s*hub\s*:\s*h\s*$", "", s).strip()
        s = re.sub(r"(?is),?\s*github\s*:\s*h\s*$", "", s).strip()
        return s

    raw_lines = dpu.get("skills_raw_lines") if isinstance(dpu.get("skills_raw_lines"), list) else []
    if raw_lines:
        cleaned_from_raw: list[str] = []
        for item in raw_lines:
            cleaned = _sanitize_raw_skill_line(item)
            if cleaned:
                cleaned_from_raw.append(cleaned)
        out.extend(cleaned_from_raw)

    direct_it = dpu.get("it_ai_skills") if isinstance(dpu.get("it_ai_skills"), list) else []
    direct_tech = dpu.get("technical_operational_skills") if isinstance(dpu.get("technical_operational_skills"), list) else []
    direct_cleaned: list[str] = []
    for value in list(direct_it) + list(direct_tech):
        cleaned = _sanitize_raw_skill_line(value)
        if cleaned:
            direct_cleaned.append(cleaned)
    out.extend(direct_cleaned)

    if not out:
        langs = dpu.get("languages") if isinstance(dpu.get("languages"), list) else []
        for raw in langs:
            value = str(raw or "").strip()
            low = value.lower()
            if not value:
                continue
            if any(tag in low for tag in ("fähigkeiten", "faehigkeiten", "kompetenzen", "skills", "github")):
                out.extend(_parse_candidate_skills_text(value, max_items=max_items))

    if not out:
        further = dpu.get("further_experience") if isinstance(dpu.get("further_experience"), list) else []
        for item in further:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if title:
                out.append(title)

    out = [_sanitize_raw_skill_line(item) for item in out]
    out = [item for item in out if item]

    return _dedupe_strings_case_insensitive(out, max_items=max_items)


def _fetch_text_from_url(url: str, *, timeout: float = 8.0, max_bytes: int = 20000) -> tuple[bool, str, str]:
    """Fetch text content from a URL with size/timeout guards."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Read more than `max_bytes` so we can still locate JSON-LD JobPosting blocks that appear later
            # in the HTML, while ensuring we only ever RETURN at most `max_bytes` characters.
            parse_bytes = max_bytes
            try:
                # Some job boards embed very large JSON-LD blocks; read up to 1MB so we can still
                # extract JobPosting.description reliably without returning huge payloads.
                parse_bytes = max(max_bytes, min(max_bytes * 50, 1_000_000))
            except Exception:
                parse_bytes = max_bytes
            raw = resp.read(parse_bytes + 1)
            data = raw[:parse_bytes]
            charset = resp.headers.get_content_charset() or "utf-8"
            html = data.decode(charset, errors="replace")

            # Best-effort: extract schema.org JobPosting JSON-LD first (much cleaner than stripping HTML).
            try:
                m = re.findall(r'(?is)<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script\s*>', html)
                job_desc = ""
                job_title = ""
                job_company = ""
                job_location = ""
                # jobs.ch can include multiple JSON-LD blocks (BreadcrumbList, WebSite, JobPosting, etc.).
                # Scan more than the first few blocks to reliably find the JobPosting payload.
                for block in m[:25]:
                    block_txt = (block or "").strip()
                    if not block_txt:
                        continue
                    try:
                        obj = json.loads(block_txt)
                    except Exception:
                        continue
                    objs = obj if isinstance(obj, list) else [obj]
                    flat: list[dict] = []
                    for it in objs:
                        if isinstance(it, dict):
                            flat.append(it)
                            graph = it.get("@graph")
                            if isinstance(graph, list):
                                flat.extend([g for g in graph if isinstance(g, dict)])
                    for one in flat:
                        if not isinstance(one, dict):
                            continue
                        t = one.get("@type")
                        t_norm = ""
                        if isinstance(t, str):
                            t_norm = t
                        elif isinstance(t, list):
                            t_norm = " ".join([str(x) for x in t if str(x).strip()])
                        if "JobPosting" not in str(t_norm):
                            continue
                        job_title = str(one.get("title") or job_title).strip()
                        try:
                            hiring = one.get("hiringOrganization")
                            if isinstance(hiring, dict):
                                job_company = str(hiring.get("name") or job_company).strip()
                        except Exception:
                            pass
                        try:
                            loc = one.get("jobLocation")
                            loc_one = None
                            if isinstance(loc, list) and loc:
                                loc_one = loc[0]
                            elif isinstance(loc, dict):
                                loc_one = loc
                            if isinstance(loc_one, dict):
                                addr = loc_one.get("address")
                                if isinstance(addr, dict):
                                    parts = [
                                        str(addr.get("streetAddress") or "").strip(),
                                        str(addr.get("addressLocality") or "").strip(),
                                        str(addr.get("postalCode") or "").strip(),
                                        str(addr.get("addressRegion") or "").strip(),
                                        str(addr.get("addressCountry") or "").strip(),
                                    ]
                                    job_location = " ".join([p for p in parts if p])
                        except Exception:
                            pass
                        job_desc = str(one.get("description") or job_desc).strip()
                if job_desc:
                    # description often contains HTML entities/tags; sanitize to plain text.
                    txt = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", job_desc)
                    txt = re.sub(r"(?is)<[^>]+>", " ", txt)
                    txt = re.sub(r"\\s+", " ", txt).strip()
                    header = " — ".join([p for p in [job_title, job_company, job_location] if p])
                    merged = (header + "\n\n" + txt).strip() if header else txt
                    return True, merged[:max_bytes], ""
            except Exception:
                pass

            # Fallback: HTML-to-text cleanup (best-effort).
            text = html
            # Strip HTML tags whenever the payload looks like HTML (jobs.ch often returns fragments without <html>).
            if "<" in text and ">" in text:
                text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", text)
                text = re.sub(r"(?is)<[^>]+>", " ", text)
            text = re.sub(r"\\s+", " ", text).strip()

            # Heuristic cleanup for common JS/global blobs that survive stripping.
            text = re.sub(r"(?is)window\\.[a-zA-Z0-9_]+\\s*=\\s*\\{.*?\\}\\s*;?", " ", text)
            text = re.sub(r"(?is)__GLOBAL__\\s*=\\s*\\{.*?\\}\\s*;?", " ", text)
            text = re.sub(r"(?is)var\\s+utag_data\\s*=\\s*\\{.*?\\}\\s*;?", " ", text)
            text = re.sub(r"\\s+", " ", text).strip()

            return True, text[:max_bytes], ""
    except Exception as e:
        return False, "", str(e)


def _is_http_url(text: str) -> bool:
    return bool(re.match(r"^https?://", str(text or "").strip(), re.IGNORECASE))


def _looks_like_job_posting_text(text: str) -> tuple[bool, str]:
    """
    Deterministic gate for accepting free text as job posting source.
    Returns (is_valid, reason_code).
    """
    raw = str(text or "")
    s = raw.strip()
    if len(s) < 80:
        return False, "too_short"

    low = s.lower()

    job_keywords = [
        "responsibilities",
        "requirements",
        "qualifications",
        "what you'll do",
        "what we are looking for",
        "what we're looking for",
        "must have",
        "preferred",
        "role",
        "position",
        "apply",
        "benefits",
        "salary",
        "contract",
        "experience",
        "required",
        "skills",
        "job id",
        "responsibility",
        "duties",
        "tasks",
    ]
    section_markers = [
        "what you'll do",
        "what we are looking for",
        "what we're looking for",
        "about the role",
        "key responsibilities",
        "required qualifications",
        "requirements:",
        "responsibilities:",
    ]
    note_markers = [
        "this is refer",
        "this refers",
        "my achievements",
        "my experience",
        "tailoring notes",
        "refering to",
        "in gl solution",
        "in expondo",
        "in sumitomo",
    ]

    keyword_hits = sum(1 for kw in job_keywords if kw in low)
    section_hits = sum(1 for kw in section_markers if kw in low)
    note_hits = sum(1 for kw in note_markers if kw in low)
    first_person_hits = len(re.findall(r"\b(i|my|me|mine)\b", low))
    bullet_lines = len(re.findall(r"(?m)^\s*[-*•]\s+", s))

    likely_notes = (first_person_hits >= 3) or (note_hits > 0)
    if likely_notes and keyword_hits < 2 and section_hits == 0:
        return False, "looks_like_candidate_notes"

    if section_hits >= 1:
        return True, "ok_section_marker"
    if keyword_hits >= 2:
        return True, "ok_keywords"
    if bullet_lines >= 4 and keyword_hits >= 1:
        return True, "ok_bullets_with_keywords"
    if len(s) >= 500 and not likely_notes:
        return True, "ok_long_text"
    return False, "not_job_like"


def _openai_enabled() -> bool:
    return bool(str(os.environ.get("OPENAI_API_KEY") or "").strip()) and product_config.CV_ENABLE_AI


def _openai_model() -> str:
    return product_config.OPENAI_MODEL


_AI_PROMPT_BASE = (
    "Return JSON only that strictly matches the provided schema. "
    "Preserve facts, names, and date ranges exactly; do not invent. "
    "Do not add line breaks inside any JSON string values."
)

# NOTE: Prompts have been extracted to src/prompts/*.txt and are loaded via PromptRegistry.
# See src/prompt_registry.py for details.


def _build_ai_system_prompt(*, stage: str, target_language: str | None = None, extra: str | None = None) -> str:
    """Backend-owned prompt builder (single source of truth).

    The dashboard prompt should be minimal/stable; stage-specific instructions live here.
    Loads from external files via PromptRegistry.
    """
    stage_key = (stage or "").strip()
    try:
        stage_rules = get_prompt(stage_key)
    except FileNotFoundError:
        # Fallback if prompt file not found (should not happen in production)
        stage_rules = ""
    
    prompt = f"{_AI_PROMPT_BASE}\n\n{stage_rules}".strip()
    # NOTE: Do not use str.format() here.
    # Many prompt templates include literal JSON snippets with `{ ... }` which
    # str.format() interprets as format fields (e.g. `{\n  roles: ...}`) and
    # will crash with KeyError.
    
    # DIAGNOSTICS: Log target_language substitution for debugging language issues
    has_placeholder = "{target_language}" in prompt
    target_lang_final = target_language or "en"
    if has_placeholder:
        logging.info(
            "PROMPT_LANG_SUBSTITUTION stage=%s has_placeholder=%s target_language_input=%s target_language_final=%s",
            stage_key,
            has_placeholder,
            repr(target_language),
            repr(target_lang_final),
        )
        prompt = prompt.replace("{target_language}", target_lang_final)
    else:
        logging.debug(
            "PROMPT_NO_LANG_PLACEHOLDER stage=%s target_language_requested=%s",
            stage_key,
            repr(target_language),
        )
    
    if extra and str(extra).strip():
        prompt = f"{prompt}\n\n{str(extra).strip()}"
    return prompt.strip()



def _coerce_int(val: object, default: int) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return int(default)


def _build_bulk_translation_payload(cv_data: dict) -> dict:
    """Build canonical payload for bulk translation stage."""
    return {
        "profile": str(cv_data.get("profile") or ""),
        "work_experience": cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else [],
        "further_experience": cv_data.get("further_experience") if isinstance(cv_data.get("further_experience"), list) else [],
        "education": cv_data.get("education") if isinstance(cv_data.get("education"), list) else [],
        "it_ai_skills": cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else [],
        "technical_operational_skills": cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else [],
        "languages": cv_data.get("languages") if isinstance(cv_data.get("languages"), list) else [],
        "interests": str(cv_data.get("interests") or ""),
        "references": str(cv_data.get("references") or ""),
    }


def _hash_bulk_translation_payload(payload: dict) -> str:
    """Stable hash for translation cache hit detection."""
    try:
        return _sha256_text(json.dumps(payload or {}, ensure_ascii=False, sort_keys=True))
    except Exception:
        return ""


def _bulk_translation_cache_hit(*, meta: dict, target_language: str, source_hash: str) -> bool:
    cache = meta.get("bulk_translation_cache") if isinstance(meta.get("bulk_translation_cache"), dict) else {}
    cached = str(cache.get(str(target_language).strip().lower()) or "")
    return bool(cached and source_hash and cached == source_hash)


def _bulk_translation_output_budget(*, user_text: str, requested_tokens: object) -> int:
    """Compute a safe output token budget for full-document translation JSON.

    Under-budgeting deterministically truncates JSON and causes parse failures.
    """
    req = _coerce_int(requested_tokens, 800)
    # Guard rails: config mistakes (e.g. setting 900) deterministically truncate JSON and break parsing.
    # Keep a hard floor for full-document translation.
    min_tokens = product_config.CV_BULK_TRANSLATION_MIN_OUTPUT_TOKENS
    base = product_config.CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS
    base = max(base, min_tokens)
    approx = int(max(min_tokens, min(8000, (len(user_text or "") // 3) + 600)))
    return min(8192, max(req, base, approx))

def _openai_json_schema_call(
    *,
    system_prompt: str,
    user_text: str,
    response_format: dict,
    max_output_tokens: int = 800,
    stage: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
) -> tuple[bool, dict | None, str]:
    deps = OpenAIJsonSchemaDeps(
        openai_enabled=_openai_enabled,
        openai_model=_openai_model,
        get_openai_prompt_id=_get_openai_prompt_id,
        require_openai_prompt_id=_require_openai_prompt_id,
        normalize_stage_env_key=_normalize_stage_env_key,
        bulk_translation_output_budget=lambda user_text_arg, requested_tokens: _bulk_translation_output_budget(
            user_text=user_text_arg,
            requested_tokens=requested_tokens,
        ),
        coerce_int=_coerce_int,
        schema_repair_instructions=lambda stage_arg, parse_error_arg: _schema_repair_instructions(
            stage=stage_arg,
            parse_error=parse_error_arg,
        ),
        now_iso=_now_iso,
    )
    return openai_json_schema_call(
        deps=deps,
        system_prompt=system_prompt,
        user_text=user_text,
        response_format=response_format,
        max_output_tokens=max_output_tokens,
        stage=stage,
        trace_id=trace_id,
        session_id=session_id,
    )

def _sanitize_for_prompt(raw: str) -> str:
    """Sanitize ANY text before embedding in prompts.
    
    Converts multi-line text to single-line by replacing newlines with spaces.
    This prevents JSON corruption in OpenAI responses when user input or CV data
    contains line breaks, quotes, or control characters.
    
    Args:
        raw: Text to sanitize (user input, CV data, profile text, etc.)
    
    Returns:
        Single-line, space-collapsed text safe for embedding in prompts
    """
    if not raw:
        return ""
    # Replace all line breaks with spaces (preserve readability for the model)
    text = raw.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # Collapse multiple consecutive spaces into single space
    text = " ".join(text.split())
    # Remove control characters except tab
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch == "\t")
    return text.strip()


def _escape_user_input_for_prompt(raw: str) -> str:
    """Legacy alias for _sanitize_for_prompt. Use _sanitize_for_prompt instead."""
    return _sanitize_for_prompt(raw)


def _stable_profile_user_id(cv_data: dict, meta: dict) -> str | None:
    """Return a stable, non-PII user id derived from contact info (email preferred)."""
    try:
        email = str(cv_data.get("email") or "").strip().lower()
        if email and "@" in email:
            return hashlib.sha256(f"email:{email}".encode("utf-8")).hexdigest()
        full_name = str(cv_data.get("full_name") or "").strip().lower()
        phone = str(cv_data.get("phone") or "").strip().lower()
        if full_name and phone:
            return hashlib.sha256(f"name_phone:{full_name}|{phone}".encode("utf-8")).hexdigest()
    except Exception:
        return None
    return None


def _stable_profile_payload(*, cv_data: dict, meta: dict) -> dict:
    """Build the stable profile payload for caching (contact/education/interests/languages).
    
    Optionally includes work_experience if it's been confirmed (for even faster repeat CVs).
    """
    d = dict(cv_data or {})
    
    profile = {
        "schema_version": "profile_v1",
        "saved_at": _now_iso(),
        "contact": {
            "full_name": str(d.get("full_name") or "").strip(),
            "email": str(d.get("email") or "").strip(),
            "phone": str(d.get("phone") or "").strip(),
            "address_lines": d.get("address_lines") if isinstance(d.get("address_lines"), list) else [],
        },
        "education": d.get("education") if isinstance(d.get("education"), list) else [],
        "interests": str(d.get("interests") or "").strip(),
        "languages": d.get("languages") if isinstance(d.get("languages"), list) else [],
        # Keep target language alongside CV language fields.
        "language": str(d.get("language") or meta.get("language") or "en").strip().lower() or "en",
        "target_language": str(meta.get("target_language") or meta.get("language") or d.get("language") or "en").strip().lower() or "en",
    }
    
    # Optional: include work_experience if confirmed (helps with repeat CVs)
    # This is job-agnostic base experience that can be tailored later
    cf = meta.get("confirmed_flags") if isinstance(meta.get("confirmed_flags"), dict) else {}
    if cf.get("work_confirmed") and isinstance(d.get("work_experience"), list):
        profile["work_experience"] = d.get("work_experience")
    
    return profile


def _apply_stable_profile_payload(*, cv_data: dict, meta: dict, payload: dict) -> tuple[dict, dict]:
    """Apply cached stable profile into cv_data/meta (does not touch tailored sections).
    
    Restores contact, education, interests, languages, and optionally work_experience
    if it was saved in the profile.
    """
    cv2 = dict(cv_data or {})
    meta2 = dict(meta or {})

    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    if isinstance(contact, dict):
        cv2["full_name"] = str(contact.get("full_name") or "").strip()
        cv2["email"] = str(contact.get("email") or "").strip()
        cv2["phone"] = str(contact.get("phone") or "").strip()
        cv2["address_lines"] = contact.get("address_lines") if isinstance(contact.get("address_lines"), list) else []

    if isinstance(payload.get("education"), list):
        cv2["education"] = payload.get("education")
    cv2["interests"] = str(payload.get("interests") or "").strip()
    if isinstance(payload.get("languages"), list):
        cv2["languages"] = payload.get("languages")
    
    # Optional: restore work_experience if saved in profile (for faster repeat CVs)
    if isinstance(payload.get("work_experience"), list) and len(payload.get("work_experience", [])) > 0:
        cv2["work_experience"] = payload.get("work_experience")
        # Mark as pre-filled from profile
        meta2["work_prefilled_from_profile"] = True

    lang = str(payload.get("language") or "").strip().lower()
    target = str(payload.get("target_language") or "").strip().lower()
    if lang:
        cv2["language"] = lang
        meta2["language"] = lang
    if target:
        meta2["target_language"] = target
        meta2["language"] = target
        cv2["language"] = target

    return cv2, meta2


def _maybe_apply_fast_profile(*, cv_data: dict, meta: dict, client_context: dict | None) -> tuple[dict, dict, bool]:
    """If enabled, load and apply the cached stable profile (cache miss is non-fatal)."""
    enabled = bool((client_context or {}).get("fast_path_profile")) or bool(meta.get("fast_path_profile"))
    if not enabled:
        return cv_data, meta, False

    user_id = _stable_profile_user_id(cv_data, meta)
    if not user_id:
        return cv_data, meta, False

    try:
        desired_lang = str(meta.get("target_language") or meta.get("language") or cv_data.get("language") or "en").strip().lower() or "en"
        payload = get_profile_store().get_latest(user_id=user_id, target_language=desired_lang)
    except Exception:
        payload = None

    if not isinstance(payload, dict) or payload.get("schema_version") != "profile_v1":
        return cv_data, meta, False

    cv2, meta2 = _apply_stable_profile_payload(cv_data=cv_data, meta=meta, payload=payload)
    meta2["fast_profile_applied"] = True
    meta2["fast_profile_user_id"] = user_id
    meta2["fast_profile_saved_at"] = str(payload.get("saved_at") or "")[:64]
    meta2["fast_profile_lang"] = str(payload.get("target_language") or payload.get("language") or desired_lang).strip().lower() or desired_lang
    return cv2, meta2, True


def _update_section_hashes_in_metadata(session_id: str, cv_data: dict) -> None:
    """Update section_hashes in session metadata after CV changes.
    
    Stores current hashes and preserves previous hashes for delta detection.
    Call this after any update_cv_field operation.
    """
    from src.context_pack import compute_cv_section_hashes
    
    store = _get_session_store()
    session = store.get_session(session_id)
    if not session:
        logging.warning(f"Cannot update hashes: session {session_id} not found")
        return
    
    metadata = session.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    
    metadata = dict(metadata)
    
    # Compute new hashes
    new_hashes = compute_cv_section_hashes(cv_data)
    
    # Preserve previous hashes for delta detection
    prev_hashes = metadata.get("section_hashes")
    if prev_hashes:
        metadata["section_hashes_prev"] = prev_hashes
    
    metadata["section_hashes"] = new_hashes
    metadata["section_hashes_updated_at"] = _now_iso()
    
    # Update metadata only (cv_data already updated by caller)
    store.update_session(session_id, cv_data, metadata)
    logging.debug(f"Updated section hashes for session {session_id}")


def _normalize_stage_env_key(stage: str) -> str:
    """Normalize a stage name into a safe ENV suffix."""
    stage_up = (stage or "").strip().upper()
    stage_up = re.sub(r"[^A-Z0-9]+", "_", stage_up)
    stage_up = re.sub(r"_+", "_", stage_up).strip("_")
    return stage_up or "UNKNOWN"


def _get_openai_prompt_id(stage: str | None = None) -> str | None:
    """Return OpenAI dashboard prompt id.

    Supports stage overrides via env vars, e.g. OPENAI_PROMPT_ID_WORK_TAILOR_RUN.
    Falls back to OPENAI_PROMPT_ID.
    """
    require_per_stage = product_config.REQUIRE_OPENAI_PROMPT_ID_PER_STAGE
    stage_key = _normalize_stage_env_key(stage) if stage else ""
    if stage_key:
        prompt_id = (os.environ.get(f"OPENAI_PROMPT_ID_{stage_key}") or "").strip() or None
        if prompt_id:
            return prompt_id

        # Strict per-stage mode: do not fall back to OPENAI_PROMPT_ID.
        if require_per_stage:
            try:
                settings_path = Path(__file__).parent / "local.settings.json"
                if settings_path.exists():
                    doc = json.loads(settings_path.read_text(encoding="utf-8"))
                    values = doc.get("Values") if isinstance(doc, dict) else None
                    if isinstance(values, dict):
                        prompt_id = (values.get(f"OPENAI_PROMPT_ID_{stage_key}") or "").strip() or None
                        if prompt_id:
                            return prompt_id
            except Exception:
                pass
            return None

    prompt_id = product_config.OPENAI_PROMPT_ID or None
    if prompt_id:
        return prompt_id

    # Local dev fallback: read from local.settings.json if available (Azure Functions loads it into env
    # when using `func start`, but IDE/debug setups sometimes don't).
    try:
        settings_path = Path(__file__).parent / "local.settings.json"
        if settings_path.exists():
            doc = json.loads(settings_path.read_text(encoding="utf-8"))
            values = doc.get("Values") if isinstance(doc, dict) else None
            if isinstance(values, dict):
                if stage_key:
                    prompt_id = (values.get(f"OPENAI_PROMPT_ID_{stage_key}") or "").strip() or None
                    if prompt_id:
                        return prompt_id

                prompt_id = (values.get("OPENAI_PROMPT_ID") or "").strip() or None
                if prompt_id:
                    return prompt_id
    except Exception:
        pass
    return None


def _require_openai_prompt_id() -> bool:
    return product_config.REQUIRE_OPENAI_PROMPT_ID


def _json_response(payload: dict, *, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        mimetype="application/json; charset=utf-8",
        status_code=status_code,
    )


def _serialize_validation_result(validation_result) -> dict:
    """Convert ValidationResult to JSON-safe dict."""
    return {
        "is_valid": validation_result.is_valid,
        "errors": [asdict(err) for err in validation_result.errors],
        "warnings": validation_result.warnings,
        "estimated_pages": validation_result.estimated_pages,
        "estimated_height_mm": validation_result.estimated_height_mm,
        "details": validation_result.details,
    }


def _compute_required_present(cv_data: dict) -> dict:
    return {
        "full_name": bool(cv_data.get("full_name", "").strip()) if isinstance(cv_data.get("full_name"), str) else False,
        "email": bool(cv_data.get("email", "").strip()) if isinstance(cv_data.get("email"), str) else False,
        "phone": bool(cv_data.get("phone", "").strip()) if isinstance(cv_data.get("phone"), str) else False,
        "work_experience": bool(cv_data.get("work_experience")) and isinstance(cv_data.get("work_experience"), list),
        "education": bool(cv_data.get("education")) and isinstance(cv_data.get("education"), list),
    }


def _compute_readiness(cv_data: dict, metadata: dict) -> dict:
    required_present = _compute_required_present(cv_data)
    strict_template = product_config.CV_GENERATION_STRICT_TEMPLATE
    if strict_template:
        required_present = dict(required_present)
        required_present.update(
            {
                "address_lines": isinstance(cv_data.get("address_lines"), list) and len(cv_data.get("address_lines") or []) > 0,
                "profile": isinstance(cv_data.get("profile"), str) and bool(cv_data.get("profile", "").strip()),
                "languages": isinstance(cv_data.get("languages"), list) and len(cv_data.get("languages") or []) > 0,
                "it_ai_skills": isinstance(cv_data.get("it_ai_skills"), list) and len(cv_data.get("it_ai_skills") or []) > 0,
            }
        )
    confirmed_flags = (metadata or {}).get("confirmed_flags") or {}
    contact_ok = bool(confirmed_flags.get("contact_confirmed"))
    education_ok = bool(confirmed_flags.get("education_confirmed"))
    missing: list[str] = []
    for k, v in required_present.items():
        if not v:
            missing.append(k)
    if not contact_ok:
        missing.append("contact_not_confirmed")
    if not education_ok:
        missing.append("education_not_confirmed")
    can_generate = all(required_present.values()) and contact_ok and education_ok
    return {
        "can_generate": can_generate,
        "required_present": required_present,
        "strict_template": strict_template,
        "confirmed_flags": {
            "contact_confirmed": contact_ok,
            "education_confirmed": education_ok,
            "confirmed_at": confirmed_flags.get("confirmed_at"),
        },
        "missing": missing,
    }


def _merge_docx_prefill_into_cv_data_if_needed(
    *,
    cv_data: dict,
    docx_prefill: dict,
    meta: dict,
    keys_to_merge: list[str] | None = None,
    clear_prefill: bool = True,
) -> tuple[dict, dict, int]:
    """
    When a session was created from DOCX, we keep an unconfirmed prefill snapshot in metadata.
    After user confirmation, we can safely copy missing fields into canonical cv_data to unblock
    validation + PDF generation.
    Returns: (new_cv_data, new_meta, applied_fields_count)
    """
    if not isinstance(cv_data, dict) or not isinstance(docx_prefill, dict) or not isinstance(meta, dict):
        return cv_data, meta, 0

    def _is_empty(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str):
            return not v.strip()
        if isinstance(v, (list, tuple, dict)):
            return len(v) == 0
        return False

    # Only copy a conservative allowlist of fields we actually store in canonical CV schema.
    allow_fields = [
        "full_name",
        "email",
        "phone",
        "address_lines",
        "profile",
        "work_experience",
        "education",
        "further_experience",
        "languages",
        "it_ai_skills",
        "interests",
        "references",
    ]

    if isinstance(keys_to_merge, list) and keys_to_merge:
        allow_set = set(allow_fields)
        requested = [str(k) for k in keys_to_merge if str(k) in allow_set]
        allow_fields = requested

    applied = 0
    new_cv = dict(cv_data)
    for k in allow_fields:
        if k not in docx_prefill:
            continue
        if k in new_cv and not _is_empty(new_cv.get(k)):
            continue
        v = docx_prefill.get(k)
        # Do not write obviously wrong types.
        if k in ("address_lines", "work_experience", "education", "further_experience", "languages", "it_ai_skills", "technical_operational_skills") and not isinstance(v, list):
            continue
        if k in ("full_name", "email", "phone", "profile", "interests", "references") and not isinstance(v, str):
            continue
        new_cv[k] = v
        applied += 1

    new_meta = dict(meta)
    # Once we copied prefill into canonical cv_data, the unconfirmed snapshot is no longer needed.
    if applied > 0 and clear_prefill:
        new_meta["docx_prefill_unconfirmed"] = None
    return new_cv, new_meta, applied


def _wants_generate_from_message(message: str) -> bool:
    """
    Heuristic intent detection (keep narrow; avoid false positives from pasted job ads).
    Only examines first 3 lines.
    """
    intent_header = "\n".join((message or "").splitlines()[:3]).lower()
    patterns = [
        r"\bgenerate\b",
        r"\bgo ahead\b",
        r"\bproceed\b",
        r"\bfinal\b",
        r"\bpdf\b",
        r"\bproduce (a )?(cv|resume|pdf)\b",
        r"\bcreate (a )?(cv|resume|pdf)\b",
        r"\bmake (a )?(cv|resume|pdf)\b",
        r"\bprovide me (a )?(cv|resume)\b",
    ]
    return any(re.search(p, intent_header) for p in patterns)


def _user_confirm_yes(message: str) -> bool:
    t = (message or "").strip().lower()
    # Accept both exact confirmations and common variants like "yes, ..." / "ok ...".
    if t in ("yes", "y", "ok", "okay", "tak", "jasne", "sure", "confirm", "confirmed"):
        return True
    return bool(re.match(r"^(yes|y|ok|okay|tak|jasne|sure|confirm|confirmed)\b", t))


def _user_confirm_no(message: str) -> bool:
    t = (message or "").strip().lower()
    if t in ("no", "n", "nie", "nope"):
        return True
    return bool(re.match(r"^(no|n|nie|nope)\b", t))


def _is_import_prefill_intent(message: str) -> bool:
    t = (message or "").lower()
    return any(x in t for x in ("import prefill", "use prefill", "copy prefill", "zaimportuj", "przenieś", "importuj", "użyj prefill"))


def _is_generate_pdf_intent(message: str) -> bool:
    t = (message or "").lower()
    return any(x in t for x in ("generate pdf", "generate the pdf", "final pdf", "create pdf", "pdf now", "generuj pdf", "wygeneruj pdf"))


def _get_pending_confirmation(meta: dict) -> dict | None:
    pc = meta.get("pending_confirmation") if isinstance(meta, dict) else None
    return pc if isinstance(pc, dict) else None


def _set_pending_confirmation(meta: dict, *, kind: str) -> dict:
    out = dict(meta or {})
    out["pending_confirmation"] = {"kind": kind, "created_at": _now_iso()}
    return out


def _clear_pending_confirmation(meta: dict) -> dict:
    out = dict(meta or {})
    out["pending_confirmation"] = None
    return out


def _get_turns_in_review(meta: dict) -> int:
    """Get the count of turns spent in REVIEW stage (used for auto-advance logic)."""
    try:
        return int(meta.get("turns_in_review", 0))
    except (ValueError, TypeError):
        return 0


def _increment_turns_in_review(meta: dict) -> dict:
    """Increment turn counter when staying in REVIEW stage."""
    out = dict(meta or {})
    current = _get_turns_in_review(out)
    out["turns_in_review"] = current + 1
    return out


def _reset_turns_in_review(meta: dict) -> dict:
    """Reset turn counter when leaving REVIEW stage."""
    out = dict(meta or {})
    out["turns_in_review"] = 0
    return out


def _estimate_pages_ok(cv_data: dict) -> bool:
    try:
        cv_norm = normalize_cv_data(cv_data or {})
        result = validate_cv(cv_norm)
        est = getattr(result, "estimated_pages", None)
        if isinstance(est, (int, float)):
            return est <= 2
    except Exception:
        pass
    return True


def _get_stage_from_metadata(meta: dict) -> CVStage:
    stage = None
    if isinstance(meta, dict):
        stage = meta.get("stage")
    try:
        return CVStage(str(stage or CVStage.INGEST.value))
    except Exception:
        return CVStage.INGEST


def _set_stage_in_metadata(meta: dict, stage: CVStage) -> dict:
    out = dict(meta or {})
    out["stage"] = stage.value
    out["stage_updated_at"] = _now_iso()
    return out


def _is_debug_export_enabled() -> bool:
    return product_config.CV_ENABLE_DEBUG_EXPORT


def _redact_debug_value(value: Any) -> Any:
    """
    Ensure exported diagnostics do not contain large payloads or sensitive content.
    This is best-effort and should stay conservative.
    """
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        # Redact base64-like content and very large strings.
        if len(value) > 2000:
            return f"<str:{len(value)}>"
        if "base64" in value.lower() and len(value) > 256:
            return f"<base64_str:{len(value)}>"
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, list):
        # Keep only a small head; redact nested values.
        head = value[:10]
        return [_redact_debug_value(v) for v in head] + (["<…>"] if len(value) > 10 else [])
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            ks = str(k)
            # Common large fields
            if ks in ("docx_base64", "pdf_base64", "cv_data_json", "metadata_json"):
                out[ks] = "<redacted>"
                continue
            out[ks] = _redact_debug_value(v)
        return out
    return f"<{type(value).__name__}>"


def _shrink_metadata_for_table(metadata: dict) -> dict:
    """
    Azure Table Storage property size limit is 64KB. Keep metadata_json well below that.
    We only trim fields that are non-critical for correctness (event_log verbosity).
    """
    if not isinstance(metadata, dict):
        return {}

    meta = dict(metadata)

    # Job posting text can easily exceed Azure Table Storage limits when combined with event logs.
    # Keep a snippet for debugging, but avoid persistence failures.
    jpt = meta.get("job_posting_text")
    if isinstance(jpt, str) and len(jpt) > 2000:
        meta["job_posting_text"] = jpt[:2000]

    # DOCX prefill snapshot can also be large; keep it bounded.
    dpu = meta.get("docx_prefill_unconfirmed")
    if isinstance(dpu, dict):
        dpu2 = dict(dpu)
        for k, v in list(dpu2.items()):
            if isinstance(v, str) and len(v) > 2000:
                dpu2[k] = v[:2000]
            if isinstance(v, list) and len(v) > 50:
                dpu2[k] = v[:50]
        meta["docx_prefill_unconfirmed"] = dpu2

    # pdf_refs can grow unbounded if user regenerates PDF many times. Keep only 3 most recent.
    pdf_refs = meta.get("pdf_refs")
    if isinstance(pdf_refs, dict) and len(pdf_refs) > 3:
        sorted_refs = sorted(
            pdf_refs.items(),
            key=lambda item: (item[1].get("created_at") or "") if isinstance(item[1], dict) else "",
            reverse=True,
        )
        meta["pdf_refs"] = dict(sorted_refs[:3])

    event_log = meta.get("event_log")
    if isinstance(event_log, list):
        trimmed: list[dict] = []
        for e in event_log[-10:]:
            if not isinstance(e, dict):
                continue
            e2 = dict(e)
            # Bound long texts
            if isinstance(e2.get("text"), str) and len(e2["text"]) > 800:
                e2["text"] = e2["text"][:800]
            if isinstance(e2.get("assistant_text"), str) and len(e2["assistant_text"]) > 800:
                e2["assistant_text"] = e2["assistant_text"][:800]
            trimmed.append(e2)
        meta["event_log"] = trimmed
    return meta


_FILENAME_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename_part(value: str, *, max_len: int = 48) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    v = v.translate(
        str.maketrans(
            {
                # Polish
                "ą": "a",
                "ć": "c",
                "ę": "e",
                "ł": "l",
                "ń": "n",
                "ó": "o",
                "ś": "s",
                "ż": "z",
                "ź": "z",
                "Ą": "A",
                "Ć": "C",
                "Ę": "E",
                "Ł": "L",
                "Ń": "N",
                "Ó": "O",
                "Ś": "S",
                "Ż": "Z",
                "Ź": "Z",
                # German
                "ä": "a",
                "ö": "o",
                "ü": "u",
                "ß": "ss",
                "Ä": "A",
                "Ö": "O",
                "Ü": "U",
            }
        )
    )
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode("ascii")
    v = _FILENAME_FORBIDDEN_RE.sub(" ", v)
    v = re.sub(r"\\s+", " ", v).strip().replace(" ", "_")
    v = re.sub(r"_+", "_", v).strip("._-")
    if len(v) > max_len:
        v = v[:max_len].rstrip("._-")
    return v


def _latest_pdf_download_name(*, meta: dict, cv_data_fallback: dict | None = None) -> str:
    if not isinstance(meta, dict):
        return ""
    pdf_refs = meta.get("pdf_refs")
    if isinstance(pdf_refs, dict) and pdf_refs:
        entries = [(k, v) for k, v in pdf_refs.items() if isinstance(v, dict)]
        if entries:
            entries.sort(key=lambda x: str(x[1].get("created_at") or ""), reverse=True)
            for _, info in entries:
                dn = info.get("download_name")
                if isinstance(dn, str) and dn.strip():
                    return dn.strip()
    if isinstance(cv_data_fallback, dict):
        return _compute_pdf_download_name(cv_data=cv_data_fallback, meta=meta)
    return ""


def _extract_job_title_from_metadata(meta: dict) -> str:
    if not isinstance(meta, dict):
        return ""
    for k in ("job_title", "target_job_title", "role_title", "position_title"):
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    jpt = meta.get("job_posting_text")
    if isinstance(jpt, str) and jpt.strip():
        for line in jpt.splitlines():
            line = line.strip()
            if not line:
                continue
            for sep in (" | ", " — ", " – ", " - ", " @ ", " at "):
                if sep in line:
                    line = line.split(sep, 1)[0].strip()
                    break
            return line
    return ""


def _extract_company_from_metadata(meta: dict) -> str:
    if not isinstance(meta, dict):
        return ""
    # 1) job_reference.company (preferred)
    jr = meta.get("job_reference")
    if isinstance(jr, dict):
        c = jr.get("company")
        if isinstance(c, str) and c.strip():
            return c.strip()
    # 2) try to guess from job_posting_text first line
    jpt = meta.get("job_posting_text")
    if isinstance(jpt, str) and jpt.strip():
        for line in jpt.splitlines():
            line = line.strip()
            if not line:
                continue
            # If the line looks like "Acme Corp — ...", take the first part.
            for sep in (" — ", " - ", " | ", " @ ", " at "):
                if sep in line:
                    line = line.split(sep, 1)[0].strip()
                    break
            return line
    # 3) fallback: domain of job_posting_url
    url = meta.get("job_posting_url")
    if isinstance(url, str) and url.strip():
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
            host = host.replace("www.", "").strip()
            return host
        except Exception:
            return ""
    return ""


def _compute_pdf_download_name(*, cv_data: dict, meta: dict) -> str:
    full_name = ""
    if isinstance(cv_data, dict):
        v = cv_data.get("full_name")
        if isinstance(v, str):
            full_name = v.strip()
    
    # Try to extract company name first.
    company = _extract_company_from_metadata(meta if isinstance(meta, dict) else {})

    # Fallback to job_title
    job_title = _extract_job_title_from_metadata(meta)

    name_part = _sanitize_filename_part(full_name, max_len=40) or "Candidate"
    
    # Add date stamp for better organization
    from datetime import datetime
    date_stamp = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Prefer company name, fallback to job title
    if company:
        company_part = _sanitize_filename_part(company, max_len=40)
        return f"CV_{name_part}_{company_part}_{date_stamp}.pdf"
    elif job_title:
        job_part = _sanitize_filename_part(job_title, max_len=40)
        return f"CV_{name_part}_{job_part}_{date_stamp}.pdf"
    
    return f"CV_{name_part}_{date_stamp}.pdf"


def _compute_cover_letter_download_name(*, cv_data: dict, meta: dict) -> str:
    full_name = ""
    if isinstance(cv_data, dict):
        v = cv_data.get("full_name")
        if isinstance(v, str):
            full_name = v.strip()

    company = _extract_company_from_metadata(meta if isinstance(meta, dict) else {})
    job_title = _extract_job_title_from_metadata(meta)

    name_part = _sanitize_filename_part(full_name, max_len=40) or "Candidate"
    date_stamp = datetime.utcnow().strftime("%Y-%m-%d")

    if company:
        company_part = _sanitize_filename_part(company, max_len=40)
        return f"CoverLetter_{name_part}_{company_part}_{date_stamp}.pdf"
    if job_title:
        job_part = _sanitize_filename_part(job_title, max_len=40)
        return f"CoverLetter_{name_part}_{job_part}_{date_stamp}.pdf"
    return f"CoverLetter_{name_part}_{date_stamp}.pdf"


def _build_cover_letter_render_payload(*, cv_data: dict, meta: dict, block: dict) -> dict:
    addr_lines = cv_data.get("address_lines")
    if isinstance(addr_lines, list):
        addr = "\n".join([str(x).strip() for x in addr_lines if str(x).strip()])
    else:
        addr = str(cv_data.get("address") or "").strip()

    jr = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else {}
    recipient_company = ""
    recipient_job_title = str(jr.get("title") or "").strip()

    return {
        "sender_name": str(cv_data.get("full_name") or "").strip(),
        "sender_email": str(cv_data.get("email") or "").strip(),
        "sender_phone": str(cv_data.get("phone") or "").strip(),
        "sender_address": addr,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "recipient_company": recipient_company,
        "recipient_job_title": recipient_job_title,
        "opening_paragraph": str(block.get("opening_paragraph") or "").strip(),
        "core_paragraphs": [str(p).strip() for p in (block.get("core_paragraphs") or []) if str(p).strip()],
        "closing_paragraph": str(block.get("closing_paragraph") or "").strip(),
        # Backend enforces deterministic sign-off identity.
        "signoff": f"Kind regards,\n{str(cv_data.get('full_name') or '').strip()}",
    }


def _run_bulk_translation(
    *,
    cv_data: dict,
    meta: dict,
    trace_id: str,
    session_id: str,
    target_language: str,
) -> tuple[dict, dict, bool, str]:
    cv_payload = _build_bulk_translation_payload(cv_data)
    source_hash = _hash_bulk_translation_payload(cv_payload)
    system_prompt = _build_ai_system_prompt(stage="bulk_translation", target_language=target_language)
    prompt_id_used = _get_openai_prompt_id("bulk_translation")

    ok, parsed, err = _openai_json_schema_call(
        system_prompt=system_prompt,
        user_text=json.dumps(cv_payload, ensure_ascii=False),
        trace_id=trace_id,
        session_id=session_id,
        response_format={
            "type": "json_schema",
            "name": "bulk_translation",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "profile": {"type": "string"},
                    "work_experience": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "employer": {"type": "string"},
                                "title": {"type": "string"},
                                "date_range": {"type": "string"},
                                "location": {"type": "string"},
                                "bullets": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["employer", "title", "date_range", "location", "bullets"],
                        },
                    },
                    "further_experience": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "organization": {"type": "string"},
                                "date_range": {"type": "string"},
                                "location": {"type": "string"},
                                "bullets": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "organization", "date_range", "location", "bullets"],
                        },
                    },
                    "education": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "institution": {"type": "string"},
                                "date_range": {"type": "string"},
                                "specialization": {"type": "string"},
                                "details": {"type": "array", "items": {"type": "string"}},
                                "location": {"type": "string"},
                            },
                            "required": ["title", "institution", "date_range", "specialization", "details", "location"],
                        },
                    },
                    "it_ai_skills": {"type": "array", "items": {"type": "string"}},
                    "technical_operational_skills": {"type": "array", "items": {"type": "string"}},
                    "languages": {"type": "array", "items": {"type": "string"}},
                    "interests": {"type": "string"},
                    "references": {"type": "string"},
                },
                "required": [
                    "profile",
                    "work_experience",
                    "further_experience",
                    "education",
                    "it_ai_skills",
                    "technical_operational_skills",
                    "languages",
                    "interests",
                    "references",
                ],
            },
        },
        max_output_tokens=product_config.CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS,
        stage="bulk_translation",
    )

    meta2 = dict(meta or {})
    # Prompt provenance (stateless auditability)
    prompt_trace = meta2.get("bulk_translation_prompt_trace") if isinstance(meta2.get("bulk_translation_prompt_trace"), list) else []
    prompt_trace.append(
        {
            "ts_utc": _now_iso(),
            "target_language": target_language,
            "prompt_id_used": prompt_id_used,
            "effective_system_prompt_hash": _sha256_text(system_prompt),
            "user_payload_hash": source_hash,
            "user_payload_chars": len(json.dumps(cv_payload, ensure_ascii=False)),
        }
    )
    meta2["bulk_translation_prompt_trace"] = prompt_trace[-5:]

    # Preserve original state once (avoid losing state-machine history)
    if not str(meta2.get("cv_state_original_hash") or ""):
        try:
            orig_hash = _sha256_text(json.dumps(cv_data or {}, ensure_ascii=False, sort_keys=True))
            meta2["cv_state_original_hash"] = orig_hash
            ptr = _snapshot_session(session_id=session_id, cv_data=(cv_data or {}), snapshot_type="cv_original")
            if ptr:
                meta2["cv_state_original_ref"] = f"{ptr.container}/{ptr.blob_name}"
        except Exception:
            pass

    if ok and isinstance(parsed, dict):
        cv_data2 = dict(cv_data or {})
        cv_data2["profile"] = str(parsed.get("profile") or "")
        cv_data2["work_experience"] = parsed.get("work_experience") if isinstance(parsed.get("work_experience"), list) else []
        cv_data2["further_experience"] = parsed.get("further_experience") if isinstance(parsed.get("further_experience"), list) else []
        cv_data2["education"] = parsed.get("education") if isinstance(parsed.get("education"), list) else []
        cv_data2["it_ai_skills"] = parsed.get("it_ai_skills") if isinstance(parsed.get("it_ai_skills"), list) else []
        cv_data2["technical_operational_skills"] = parsed.get("technical_operational_skills") if isinstance(parsed.get("technical_operational_skills"), list) else []
        cv_data2["languages"] = parsed.get("languages") if isinstance(parsed.get("languages"), list) else []
        cv_data2["interests"] = str(parsed.get("interests") or "")
        cv_data2["references"] = str(parsed.get("references") or "")

        translated_hash = _sha256_text(json.dumps(cv_data2 or {}, ensure_ascii=False, sort_keys=True))
        meta2["bulk_translated_to"] = target_language
        meta2["bulk_translation_status"] = "ok"
        meta2["bulk_translation_source_hash"] = source_hash
        cache = meta2.get("bulk_translation_cache") if isinstance(meta2.get("bulk_translation_cache"), dict) else {}
        cache = dict(cache)
        cache[str(target_language).strip().lower()] = source_hash
        meta2["bulk_translation_cache"] = cache
        meta2["active_cv_state_id"] = f"translated:{target_language}:{translated_hash[:12]}"
        meta2["active_cv_state_lang"] = target_language
        meta2["active_cv_state_hash"] = translated_hash
        refs = meta2.get("cv_state_translated_refs") if isinstance(meta2.get("cv_state_translated_refs"), dict) else {}
        refs = dict(refs)
        ptr_tr = _snapshot_session(session_id=session_id, cv_data=cv_data2, snapshot_type=f"cv_translated_{target_language}")
        if ptr_tr:
            refs[str(target_language).strip().lower()] = f"{ptr_tr.container}/{ptr_tr.blob_name}"
            meta2["cv_state_translated_refs"] = refs
        meta2.pop("bulk_translation_error", None)
        return cv_data2, meta2, True, ""

    meta2["bulk_translation_status"] = "call_failed"
    meta2["bulk_translation_error"] = str(err or "").strip()[:400]
    return cv_data, meta2, False, str(err or "")


def _generate_cover_letter_block_via_openai(
    *,
    cv_data: dict,
    meta: dict,
    trace_id: str,
    session_id: str,
    target_language: str,
) -> tuple[bool, dict | None, str]:
    job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
    job_summary = format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
    job_text = str(meta.get("job_posting_text") or "")

    # If we only have raw job text, extract a compact job summary first (best-effort).
    if (not job_summary) and job_text and len(job_text) >= 80:
        ok_jr, parsed_jr, err_jr = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="job_posting"),
            user_text=job_text[:20000],
            trace_id=trace_id,
            session_id=session_id,
            response_format=get_job_reference_response_format(),
            max_output_tokens=1200,
            stage="job_posting",
        )
        if ok_jr and isinstance(parsed_jr, dict):
            try:
                jr = parse_job_reference(parsed_jr)
                meta["job_reference"] = jr.dict()
                meta["job_reference_status"] = "ok"
                job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
                job_summary = format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
            except Exception as e:
                meta["job_reference_error"] = str(e)[:400]
                meta["job_reference_status"] = "parse_failed"
        else:
            meta["job_reference_error"] = str(err_jr)[:400]
            meta["job_reference_status"] = "call_failed"

    summary_clean = str(job_summary or "").strip()
    if (not summary_clean) or (summary_clean.lower() == "(no job reference)"):
        return (
            False,
            None,
            "Job reference is missing. Please provide a valid job posting (responsibilities and requirements) before generating cover letter.",
        )

    # Compact CV excerpt.
    role_blocks: list[str] = []
    work_list = cv_data.get("work_experience") if isinstance(cv_data.get("work_experience"), list) else []
    for r in (work_list or [])[:5]:
        if not isinstance(r, dict):
            continue
        company = _sanitize_for_prompt(str(r.get("employer") or r.get("company") or ""))
        title = _sanitize_for_prompt(str(r.get("title") or r.get("position") or ""))
        date = _sanitize_for_prompt(str(r.get("date_range") or ""))
        bullets = r.get("bullets") if isinstance(r.get("bullets"), list) else r.get("responsibilities")
        bullet_lines = "\n".join([f"- {_sanitize_for_prompt(str(b))}" for b in (bullets or []) if str(b).strip()][:5])
        head = " | ".join([p for p in [title, company, date] if p]) or "Role"
        role_blocks.append(f"{head}\n{bullet_lines}")
    roles_text = "\n\n".join(role_blocks)

    it_ai = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
    tech = cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else []
    skills_text = "\n".join([f"- {str(s).strip()}" for s in (it_ai or [])[:8] if str(s).strip()] + [f"- {str(s).strip()}" for s in (tech or [])[:8] if str(s).strip()])

    style_profile = _infer_style_profile(cv_data)

    user_text = (
        f"[JOB_REFERENCE]\n{_sanitize_for_prompt(job_summary)}\n\n"
        f"[STYLE_PROFILE]\n{_sanitize_for_prompt(style_profile)}\n\n"
        f"[WORK_EXPERIENCE]\n{roles_text}\n\n"
        f"[SKILLS]\n{_sanitize_for_prompt(skills_text[:2000])}\n"
    )
    e0_corpus = "\n".join([
        str(cv_data.get("profile") or ""),
        str(roles_text or ""),
        str(skills_text or ""),
        str(meta.get("work_tailoring_notes") or ""),
    ])

    def _call(extra_fix: str | None = None) -> tuple[bool, dict | None, str]:
        system_prompt = _build_ai_system_prompt(stage="cover_letter", target_language=target_language, extra=extra_fix)
        return _openai_json_schema_call(
            system_prompt=system_prompt,
            user_text=user_text,
            trace_id=trace_id,
            session_id=session_id,
            response_format=get_cover_letter_proposal_response_format(),
            max_output_tokens=1680,
            stage="cover_letter",
        )

    ok, parsed, err = _call(None)
    if not ok or not isinstance(parsed, dict):
        return False, None, str(err)

    try:
        prop = parse_cover_letter_proposal(parsed)
        # Use localized signoff based on target language
        signoff_phrase = get_cover_letter_signoff(target_language)
        signoff = f"{signoff_phrase},\n{str(cv_data.get('full_name') or '').strip()}"
        cl_block = {
            "opening_paragraph": str(prop.opening_paragraph or "").strip(),
            "core_paragraphs": [str(p).strip() for p in (prop.core_paragraphs or []) if str(p).strip()],
            "closing_paragraph": str(prop.closing_paragraph or "").strip(),
            "signoff": signoff,
            "notes": str(prop.notes or "")[:500],
            "openai_response_id": str(parsed.get("_openai_response_id") or "")[:120],
            "created_at": _now_iso(),
        }
        ok2, errs2 = _validate_cover_letter_block(block=cl_block, cv_data=cv_data)
        errs2.extend(
            _find_cover_letter_e0_violations(
                paragraphs=[cl_block.get("opening_paragraph", "")] + list(cl_block.get("core_paragraphs") or []) + [cl_block.get("closing_paragraph", "")],
                e0_corpus=e0_corpus,
            )
        )
        if ok2 and not errs2:
            return True, cl_block, ""

        # Bounded fix attempt (semantic validation, not schema repair).
        ok_fix, parsed_fix, err_fix = _call("Fix these validation errors:\n- " + "\n- ".join(errs2[:8]))
        if not ok_fix or not isinstance(parsed_fix, dict):
            return False, None, "Validation failed: " + "; ".join(errs2[:4])
        prop_fix = parse_cover_letter_proposal(parsed_fix)
        # Use localized signoff based on target language
        signoff_phrase = get_cover_letter_signoff(target_language)
        signoff = f"{signoff_phrase},\n{str(cv_data.get('full_name') or '').strip()}"
        cl_block2 = {
            "opening_paragraph": str(prop_fix.opening_paragraph or "").strip(),
            "core_paragraphs": [str(p).strip() for p in (prop_fix.core_paragraphs or []) if str(p).strip()],
            "closing_paragraph": str(prop_fix.closing_paragraph or "").strip(),
            "signoff": signoff,
            "notes": str(prop_fix.notes or "")[:500],
            "openai_response_id": str(parsed_fix.get("_openai_response_id") or "")[:120],
            "created_at": _now_iso(),
        }
        ok3, errs3 = _validate_cover_letter_block(block=cl_block2, cv_data=cv_data)
        errs3.extend(
            _find_cover_letter_e0_violations(
                paragraphs=[cl_block2.get("opening_paragraph", "")] + list(cl_block2.get("core_paragraphs") or []) + [cl_block2.get("closing_paragraph", "")],
                e0_corpus=e0_corpus,
            )
        )
        if (not ok3) or errs3:
            return False, None, "Validation failed: " + "; ".join(errs3[:4])
        return True, cl_block2, ""
    except Exception as e:
        return False, None, str(e)

def _build_session_debug_snapshot(session: dict) -> dict:
    cv_data = session.get("cv_data") or {}
    meta = session.get("metadata") or {}
    readiness = _compute_readiness(cv_data if isinstance(cv_data, dict) else {}, meta if isinstance(meta, dict) else {})
    confirmed_flags = (meta.get("confirmed_flags") or {}) if isinstance(meta, dict) else {}
    docx_prefill = meta.get("docx_prefill_unconfirmed") if isinstance(meta, dict) else None

    def _count_list(obj: Any) -> int:
        return len(obj) if isinstance(obj, list) else 0

    pdf_refs = meta.get("pdf_refs") if isinstance(meta, dict) else None
    pdf_ref_count = len(pdf_refs) if isinstance(pdf_refs, dict) else 0
    pdf_ref_keys = list(pdf_refs.keys())[:10] if isinstance(pdf_refs, dict) else []

    events = meta.get("event_log") if isinstance(meta, dict) else None
    event_tail: list[dict] = []
    if isinstance(events, list):
        for e in events[-20:]:
            if not isinstance(e, dict):
                continue
            rs = e.get("run_summary") if isinstance(e.get("run_summary"), dict) else {}
            steps = rs.get("steps") if isinstance(rs.get("steps"), list) else []
            tool_steps = [s for s in steps if isinstance(s, dict) and s.get("step") == "tool"]
            event_tail.append(
                {
                    "ts": e.get("ts"),
                    "type": e.get("type"),
                    "stage": e.get("stage"),
                    "trace_id": e.get("trace_id"),
                    "text_preview": (str(e.get("text") or "")[:180] if e.get("type") in ("user_message", "assistant_message") else None),
                    "run": {
                        "model_calls": rs.get("model_calls"),
                        "tool_steps": len(tool_steps),
                        "tools": [str(s.get("tool")) for s in tool_steps][:10],
                    },
                }
            )

    snapshot = {
        "readiness": readiness,
        "cv_counts": {
            "work_experience": _count_list(cv_data.get("work_experience") if isinstance(cv_data, dict) else None),
            "education": _count_list(cv_data.get("education") if isinstance(cv_data, dict) else None),
            "languages": _count_list(cv_data.get("languages") if isinstance(cv_data, dict) else None),
            "it_ai_skills": _count_list(cv_data.get("it_ai_skills") if isinstance(cv_data, dict) else None),
            "technical_operational_skills": _count_list(cv_data.get("technical_operational_skills") if isinstance(cv_data, dict) else None),
        },
        "confirmed_flags": confirmed_flags,
        "docx_prefill_unconfirmed_present": isinstance(docx_prefill, dict),
        "docx_prefill_counts": {
            "work_experience": _count_list(docx_prefill.get("work_experience") if isinstance(docx_prefill, dict) else None),
            "education": _count_list(docx_prefill.get("education") if isinstance(docx_prefill, dict) else None),
            "languages": _count_list(docx_prefill.get("languages") if isinstance(docx_prefill, dict) else None),
            "it_ai_skills": _count_list(docx_prefill.get("it_ai_skills") if isinstance(docx_prefill, dict) else None),
            "technical_operational_skills": _count_list(docx_prefill.get("technical_operational_skills") if isinstance(docx_prefill, dict) else None),
        },
        "pdf_refs": {
            "count": pdf_ref_count,
            "keys_head": pdf_ref_keys,
        },
        "event_tail": event_tail,
    }
    return _redact_debug_value(snapshot)


def _export_session_debug_files(*, session_id: str, session: dict, include_logs: bool, minutes: int) -> dict:
    out_dir = Path("tmp") / "exports" / f"session_debug_{session_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _build_session_debug_snapshot(session)
    (out_dir / "session_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    exported: dict[str, Any] = {"out_dir": str(out_dir), "files": ["session_snapshot.json"]}
    if not include_logs:
        return exported

    cutoff = datetime.utcnow().timestamp() - max(1, int(minutes)) * 60
    sid = session_id

    def _filter_log(path: Path) -> int:
        if not path.exists():
            return 0
        kept: list[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if sid not in line:
                continue
            # Try to filter by timestamp prefix [YYYY-MM-DDTHH:MM:SS...]
            m = re.search(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
            if m:
                try:
                    ts = datetime.fromisoformat(m.group(1)).timestamp()
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            kept.append(line)
        if not kept:
            return 0
        outp = out_dir / f"{path.name}.sid.log"
        outp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        exported["files"].append(outp.name)
        return len(kept)

    # Only consider the latest func + azurite logs (fast, local dev).
    logs_dir = Path("tmp") / "logs"
    func_latest = None
    az_latest = None
    if logs_dir.exists():
        func_logs = sorted(logs_dir.glob("func_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        az_logs = sorted(logs_dir.glob("azurite_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        func_latest = func_logs[0] if func_logs else None
        az_latest = az_logs[0] if az_logs else None

    exported["log_matches"] = {}
    if func_latest:
        exported["log_matches"]["func"] = {"file": str(func_latest), "lines": _filter_log(func_latest)}
    if az_latest:
        exported["log_matches"]["azurite"] = {"file": str(az_latest), "lines": _filter_log(az_latest)}
    return exported


def _responses_max_output_tokens(stage: str) -> int:
    # Increased limits to give model space to complete thoughts and avoid premature truncation.
    # Target: finish in 1-2 turns instead of 3-4.
    if stage == "draft_proposal":
        return 1800
    if stage == "fix_validation":
        return 1400
    if stage == "it_ai_skills":
        return 1800
    if stage == "generate_pdf":
        return 1500  # was 1200: space for confirmation message
    if stage == "review_session":
        return 2500  # was 1800: space for concrete proposals without cutting off
    if stage == "apply_edits":
        return 2000  # was 1200 (inherited from default): space for batch edits + status
    return 1200


def _stage_prompt(stage: str) -> str:
    # Ultra-compact stage hint to anchor the model without bloating tokens.
    # Key change: CONFIRM stage (apply_edits) now auto-enabled after 3 turns → assistant applies edits without approval.
    if stage == "review_session":
        return "Stage=review_session. Goal: review session data, propose concise edits, no PDF. Keep answers short. [Note: sections marked 'unchanged' contain only summary; 'changed' sections have full data]. [After 3 turns, system auto-enables editing without explicit approval]"
    if stage == "apply_edits":
        return "Stage=apply_edits. FIRST ACTION: call update_cv_field(edits=[...]) with ALL proposed changes in ONE batch. Then respond with 1-line confirmation. NO questions, NO waiting for approval. System auto-advanced to this stage; commit your best proposals immediately. [Note: sections marked 'unchanged' contain only summary; 'changed' sections have full data]"
    if stage == "generate_pdf":
        return "Stage=generate_pdf. Goal: user approved; generate once if readiness allows. Keep answers short."
    if stage == "fix_validation":
        return "Stage=fix_validation. Goal: fix validation errors in one pass, then generate once. Keep answers short."
    return "Stage=bootstrap. Goal: gather missing inputs; keep answers short."


def _looks_truncated(text: str) -> bool:
    t = (text or "").rstrip()
    if not t:
        return False
    return not any(t.endswith(x) for x in (".", "!", "?", "…"))


def _should_log_prompt_debug() -> bool:
    return product_config.CV_DEBUG_PROMPT_LOG


def _describe_responses_input(items: list[Any]) -> list[dict]:
    described: list[dict] = []
    for it in items:
        if isinstance(it, dict) and "role" in it:
            role = str(it.get("role") or "")
            content = it.get("content")
            if isinstance(content, str):
                described.append({"kind": "message", "role": role, "content_len": len(content)})
            else:
                described.append({"kind": "message", "role": role, "content_type": type(content).__name__})
            continue

        t = getattr(it, "type", None)
        described.append({"kind": "output_item", "type": str(t or type(it).__name__)})
    return described


def _tool_schemas_for_responses(*, allow_persist: bool, stage: str = "review_session") -> list[dict]:
    return tool_schemas_for_responses(allow_persist=allow_persist, stage=stage)


def _run_responses_tool_loop_v2(
    *,
    user_message: str,
    session_id: str,
    stage: str,
    job_posting_text: str | None,
    trace_id: str,
    max_model_calls: int,
    execution_mode: bool = False,
) -> tuple[str, list[dict], dict, str | None, bytes | None]:
    deps = ResponsesLoopDeps(
        use_structured_output=product_config.USE_STRUCTURED_OUTPUT,
        cv_single_call_execution=product_config.CV_SINGLE_CALL_EXECUTION,
        get_openai_prompt_id=_get_openai_prompt_id,
        require_openai_prompt_id=_require_openai_prompt_id,
        get_session_store=_get_session_store,
        compute_readiness=_compute_readiness,
        build_context_pack_v2=build_context_pack_v2,
        format_context_pack_with_delimiters=format_context_pack_with_delimiters,
        tool_schemas_for_responses=_tool_schemas_for_responses,
        responses_max_output_tokens=_responses_max_output_tokens,
        stage_prompt=_stage_prompt,
        should_log_prompt_debug=_should_log_prompt_debug,
        describe_responses_input=_describe_responses_input,
        parse_structured_response=parse_structured_response,
        format_user_message_for_ui=format_user_message_for_ui,
        schema_repair_instructions=_schema_repair_instructions,
        now_iso=_now_iso,
        validate_cv_data_for_tool=_validate_cv_data_for_tool,
        cv_session_search_hits=_cv_session_search_hits,
        tool_generate_context_pack_v2=_tool_generate_context_pack_v2,
        render_html_for_tool=_render_html_for_tool,
        tool_generate_cv_from_session=_tool_generate_cv_from_session,
        tool_generate_cover_letter_from_session=_tool_generate_cover_letter_from_session,
        tool_get_pdf_by_ref=_tool_get_pdf_by_ref,
        looks_truncated=_looks_truncated,
    )
    return run_responses_tool_loop_v2(
        user_message=user_message,
        session_id=session_id,
        stage=stage,
        job_posting_text=job_posting_text,
        trace_id=trace_id,
        max_model_calls=max_model_calls,
        execution_mode=execution_mode,
        deps=deps,
    )

def _build_ui_action(stage: str, cv_data: dict, meta: dict, readiness: dict) -> dict | None:
    deps = UiBuilderDeps(
        cv_enable_cover_letter=product_config.CV_ENABLE_COVER_LETTER,
        get_pending_confirmation=_get_pending_confirmation,
        openai_enabled=_openai_enabled,
        format_job_reference_for_display=format_job_reference_for_display,
        is_work_role_locked=_is_work_role_locked,
    )
    return build_ui_action(stage=stage, cv_data=cv_data, meta=meta, readiness=readiness, deps=deps)
def _tool_process_cv_orchestrated(params: dict) -> tuple[int, dict]:
    """
    Backend-owned orchestration entrypoint (thin UI client).
    """
    trace_id = str(params.get("trace_id") or uuid.uuid4())
    message = str(params.get("message") or "").strip()
    docx_base64 = str(params.get("docx_base64") or "")
    session_id = str(params.get("session_id") or "").strip()
    job_posting_text = (str(params.get("job_posting_text") or "").strip() or None)
    job_posting_url = (str(params.get("job_posting_url") or "").strip() or None)
    language = str(params.get("language") or "en").strip() or "en"
    client_context = params.get("client_context") if isinstance(params.get("client_context"), dict) else None
    user_action = params.get("user_action") if isinstance(params.get("user_action"), dict) else None
    user_action_id = str((user_action or {}).get("id") or "").strip()
    user_action_payload = (user_action or {}).get("payload")
    user_action_payload = user_action_payload if isinstance(user_action_payload, dict) else None

    if not message and not user_action_id:
        return 400, {"success": False, "error": "message is required (or provide user_action)", "trace_id": trace_id}

    # Contract stage selection is backend-owned. We keep the old scoring only for UI/prompt hints.
    stage_debug = {}
    wants_generate = False

    # Previously this returned early with an error if URL fetch failed.
    # In wizard mode we instead continue the flow and let the user paste or skip inside the job_offer stage.
    if (job_posting_url and not job_posting_text) and not wants_generate:
        if product_config.CV_REQUIRE_JOB_TEXT:
            return 200, {
                "success": True,
                "trace_id": trace_id,
                "session_id": session_id or None,
                "assistant_text": "I could not fetch the job posting text. Please paste the full job description (responsibilities + requirements + title/company).",
                "run_summary": {"trace_id": trace_id, "steps": [{"step": "ask_for_job_text"}]},
                "turn_trace": [],
            }
        else:
            # Carry the URL forward; job offer stage will handle paste/skip and we can still fetch in background if implemented.
            pass

    # Ensure session exists if docx provided.
    if not session_id and docx_base64:
        status, created = _tool_extract_and_store_cv(
            docx_base64=docx_base64,
            language=language,
            extract_photo_flag=bool(params.get("extract_photo", True)),
            job_posting_url=job_posting_url,
            job_posting_text=job_posting_text,
        )
        if status != 200:
            return status, {"success": False, "trace_id": trace_id, "error": created.get("error") if isinstance(created, dict) else "extract_failed"}
        session_id = str(created.get("session_id") or "")

    if not session_id:
        return 200, {"success": True, "trace_id": trace_id, "assistant_text": "Please upload your CV DOCX to start.", "run_summary": {"trace_id": trace_id, "steps": [{"step": "ask_for_docx"}]}, "turn_trace": []}

    # Validate session exists
    store = _get_session_store()

    def _session_get(session_id_in: str) -> dict | None:
        getter = getattr(store, "get_session_with_blob_retrieval", None)
        if callable(getter):
            return getter(session_id_in)
        return store.get_session(session_id_in)

    sess = _session_get(session_id)
    if not sess:
        logging.warning(
            "Session missing before orchestration trace_id=%s session_id=%s",
            trace_id,
            session_id,
        )
        return 200, {"success": True, "trace_id": trace_id, "assistant_text": "Your session is no longer available. Please re-upload your CV DOCX to start a new session.", "session_id": None, "run_summary": {"trace_id": trace_id, "steps": [{"step": "session_missing"}]}, "turn_trace": []}

    # Keep metadata language in sync with user preference (stateless calls).
    if isinstance(sess.get("metadata"), dict) and language:
        meta = dict(sess.get("metadata") or {})
        if meta.get("language") != language:
            meta["language"] = language
            store.update_session(session_id, (sess.get("cv_data") or {}), meta)
            sess = _session_get(session_id) or sess

    meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else {}
    meta = dict(meta) if isinstance(meta, dict) else {}
    cv_data = sess.get("cv_data") if isinstance(sess.get("cv_data"), dict) else {}
    cv_data = dict(cv_data) if isinstance(cv_data, dict) else {}
    
    # DIAGNOSTIC: Log what we loaded from session
    try:
        logging.info(
            "SESSION_LOADED target_language=%s language=%s wizard_stage=%s session=%s",
            repr(meta.get("target_language")),
            repr(meta.get("language")),
            repr(meta.get("wizard_stage")),
            session_id,
        )
    except Exception:
        pass

    # CRITICAL FAST-PATH: Detect edit intent BEFORE wizard/normal mode split
    # This ensures edit intent works for ALL sessions regardless of flow_mode
    edit_intent = detect_edit_intent(message)
    if edit_intent:
        current_stage = _get_stage_from_metadata(meta)
        logging.info(f"Edit intent detected (universal fast-path), session={session_id}, stage={current_stage}")
        
        # Clear any pending confirmation that might block editing
        if _get_pending_confirmation(meta):
            logging.info(f"Clearing pending_confirmation due to edit intent")
            meta = _clear_pending_confirmation(meta)
            try:
                store.update_session(session_id, cv_data, meta)
            except Exception as e:
                logging.warning(f"Failed to clear pending_confirmation: {e}")
        
        # Return immediately with edit intent confirmed (works for both wizard and normal modes)
        stage_debug_fastpath = {
            "edit_intent": True,
            "current_stage": current_stage.value,
            "flow_mode": meta.get("flow_mode"),
        }
        run_summary_fastpath = {
            "stage_debug": stage_debug_fastpath,
            "steps": [{"step": "edit_intent_universal_fast_path"}],
            "execution_mode": False,
            "model_calls": 0,
            "max_model_calls": product_config.CV_MAX_MODEL_CALLS,
        }
        return 200, {
            "success": True,
            "trace_id": trace_id,
            "session_id": session_id,
            "stage": current_stage.value,
            "assistant_text": "Edit intent detected. Tell me what to change, and I will update your CV fields.",
            "pdf_base64": "",
            "last_response_id": None,
            "run_summary": run_summary_fastpath,
            "turn_trace": [],
        }

    # Wizard mode: deterministic, backend-driven stage UI (Playwright-backed).
    if meta.get("flow_mode") == "wizard":
        def _state_sig(cv_obj: dict, meta_obj: dict) -> str:
            try:
                payload = {"cv": cv_obj or {}, "meta": meta_obj or {}}
                return _sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            except Exception:
                return ""

        _last_persist_sig = _state_sig(cv_data if isinstance(cv_data, dict) else {}, meta if isinstance(meta, dict) else {})

        def _wizard_get_stage(m: dict) -> str:
            return str((m or {}).get("wizard_stage") or "contact").strip().lower() or "contact"

        def _wizard_set_stage(m: dict, st: str) -> dict:
            out = dict(m or {})
            next_stage = str(st or "").strip().lower()
            prev_stage = str(out.get("wizard_stage") or "").strip().lower()
            out["wizard_stage"] = next_stage
            # Avoid timestamp churn on no-op stage writes.
            if prev_stage != next_stage:
                out["wizard_stage_updated_at"] = _now_iso()
            return out

        def _wizard_resp(*, assistant_text: str, meta_out: dict, cv_out: dict, pdf_bytes: bytes | None = None, stage_updates: list[dict] | None = None) -> tuple[int, dict]:
            readiness_now = _compute_readiness(cv_out, meta_out)
            ui_action = _build_ui_action(_wizard_get_stage(meta_out), cv_out, meta_out, readiness_now)
            pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else ""
            filename = _latest_pdf_download_name(meta=meta_out, cv_data_fallback=cv_out) if pdf_bytes else ""
            return 200, {
                "success": True,
                "trace_id": trace_id,
                "session_id": session_id,
                "stage": _wizard_get_stage(meta_out),
                # UI expects `response`; keep `assistant_text` for legacy/debug.
                "response": assistant_text,
                "assistant_text": assistant_text,
                "pdf_base64": pdf_base64,
                "filename": filename,
                "run_summary": None,
                "turn_trace": None,
                "ui_action": ui_action,
                "job_posting_url": str(meta_out.get("job_posting_url") or ""),
                "job_posting_text": str(meta_out.get("job_posting_text") or ""),
                "metadata": meta_out,
                "cv_data": cv_out,
                "stage_updates": stage_updates or [],
            }

        def _persist(cv_out: dict, meta_out: dict) -> tuple[dict, dict]:
            nonlocal _last_persist_sig
            # DIAGNOSTIC: Log metadata before calling store.update_session
            try:
                logging.debug(
                    "PERSIST_INPUT target_language=%s language=%s wizard_stage=%s session=%s",
                    repr(meta_out.get("target_language")),
                    repr(meta_out.get("language")),
                    repr(meta_out.get("wizard_stage")),
                    session_id,
                )
            except Exception:
                pass

            sig_now = _state_sig(
                cv_out if isinstance(cv_out, dict) else {},
                meta_out if isinstance(meta_out, dict) else {},
            )
            if sig_now and sig_now == _last_persist_sig:
                return dict(cv_out or {}), dict(meta_out or {})

            persisted = False
            persisted_meta = dict(meta_out or {})
            persist_error: Exception | None = None

            # Prefer blob-offload update path to survive large cv_data payloads.
            update_with_offload = getattr(store, "update_session_with_blob_offload", None)
            if callable(update_with_offload):
                try:
                    persisted = bool(update_with_offload(session_id, cv_out, persisted_meta))
                except Exception as exc:
                    persist_error = exc

            # Fallback to legacy direct update when offload path is unavailable/fails.
            if not persisted:
                try:
                    persisted = bool(store.update_session(session_id, cv_out, persisted_meta))
                except Exception as exc:
                    persist_error = exc

            # Last-chance shrink fallback for Azure Table 64KB limit issues.
            if (
                not persisted
                and persist_error is not None
                and "PropertyValueTooLarge" in str(persist_error)
                and callable(update_with_offload)
            ):
                try:
                    shrunk_meta = _shrink_metadata_for_table(persisted_meta)
                    persisted = bool(update_with_offload(session_id, cv_out, shrunk_meta))
                    if persisted:
                        persisted_meta = shrunk_meta
                except Exception as exc:
                    persist_error = exc

            if not persisted:
                logging.error(
                    "PERSIST_FAILED session=%s err=%s",
                    session_id,
                    str(persist_error)[:400] if persist_error else "unknown",
                )
                return dict(cv_out or {}), dict(persisted_meta or {})

            s2 = _session_get(session_id) or {}
            m2 = s2.get("metadata") if isinstance(s2.get("metadata"), dict) else persisted_meta
            c2 = s2.get("cv_data") if isinstance(s2.get("cv_data"), dict) else cv_out
            _last_persist_sig = _state_sig(
                c2 if isinstance(c2, dict) else {},
                m2 if isinstance(m2, dict) else {},
            )
            
            # DIAGNOSTIC: Log metadata after retrieving from store
            try:
                logging.debug(
                    "PERSIST_OUTPUT target_language=%s language=%s wizard_stage=%s session=%s",
                    repr(m2.get("target_language")),
                    repr(m2.get("language")),
                    repr(m2.get("wizard_stage")),
                    session_id,
                )
            except Exception:
                pass
            
            return dict(c2 or {}), dict(m2 or {})

        # Sync job posting fields from client into session metadata (best-effort).
        meta2 = dict(meta)

        # Persist client-side preferences on the session so later wizard actions (which don't send client_context)
        # can still see them.
        try:
            if isinstance(client_context, dict) and "fast_path_profile" in client_context:
                meta2["fast_path_profile"] = bool(client_context.get("fast_path_profile"))
        except Exception:
            pass
        if job_posting_url:
            meta2["job_posting_url"] = job_posting_url
        if job_posting_text:
            candidate_text = str(job_posting_text)[:20000]
            ok_text, reason_text = _looks_like_job_posting_text(candidate_text)
            if ok_text:
                meta2["job_posting_text"] = candidate_text
                meta2["job_input_status"] = "ok"
                meta2.pop("job_input_invalid_reason", None)
                meta2.pop("job_posting_invalid_draft", None)
            else:
                meta2["job_posting_text"] = ""
                meta2["job_input_status"] = "invalid"
                meta2["job_input_invalid_reason"] = reason_text
                meta2["job_posting_invalid_draft"] = candidate_text[:2000]

        # If job text changed, invalidate job-scoped artifacts and cached PDF usage.
        try:
            jt = str(meta2.get("job_posting_text") or "")[:20000]
            new_job_sig = _sha256_text(jt) if len(jt.strip()) >= 80 else ""
            prev_job_sig = str(meta2.get("current_job_sig") or "")
            if new_job_sig and new_job_sig != prev_job_sig:
                meta2["current_job_sig"] = new_job_sig
                meta2["job_changed_at"] = _now_iso()
                # Never reuse a previously generated PDF for a different job offer.
                meta2["pdf_generated"] = False
                # Job-scoped artifacts (will be recomputed as needed).
                meta2.pop("job_reference", None)
                meta2.pop("job_reference_status", None)
                meta2.pop("job_reference_error", None)
                meta2["job_reference_sig"] = ""
                meta2.pop("work_experience_proposal_block", None)
                meta2.pop("work_experience_proposal_error", None)
                meta2["work_experience_proposal_sig"] = ""
                meta2.pop("skills_proposal_block", None)
                meta2.pop("skills_proposal_error", None)
                meta2["skills_proposal_sig"] = ""
        except Exception:
            pass

        # Best-effort URL fetch (non-blocking): if user provided job_posting_url via sidebar,
        # try to fetch content and store it so the user doesn't have to paste manually.
        # Skip if already fetched or in progress.
        try:
            url = str(meta2.get("job_posting_url") or "").strip()
            has_text = bool(str(meta2.get("job_posting_text") or "").strip())
            fetch_status = str(meta2.get("job_fetch_status") or "")
            
            # Only fetch if no text, no previous successful fetch, and not currently pending
            if url and not has_text and fetch_status not in ("success", "manual") and re.match(r"^https?://", url, re.IGNORECASE):
                meta2["job_fetch_status"] = "fetching"
                ok, fetched_text, err = _fetch_text_from_url(url)
                if ok and fetched_text.strip():
                    meta2["job_posting_text"] = fetched_text[:20000]
                    meta2["job_fetch_status"] = "success"
                    meta2["job_fetch_timestamp"] = _now_iso()
                    meta2.pop("job_posting_fetch_error", None)
                    meta2.pop("job_fetch_error", None)
                else:
                    meta2["job_fetch_status"] = "failed"
                    meta2["job_fetch_error"] = str(err)[:400]
                    meta2["job_fetch_timestamp"] = _now_iso()
                    # Keep legacy error field for compatibility
                    meta2["job_posting_fetch_error"] = str(err)[:400]
        except Exception:
            pass

        # Ensure import gate is present only in early flow stages.
        stage_hint = _wizard_get_stage(meta2)
        import_gate_stages = {"language_selection", "import_gate_pending", "contact"}

        pc = _get_pending_confirmation(meta2)
        dpu = meta2.get("docx_prefill_unconfirmed")
        if (
            stage_hint in import_gate_stages
            and isinstance(dpu, dict)
            and (not cv_data.get("work_experience") and not cv_data.get("education"))
            and not pc
        ):
            meta2 = _set_pending_confirmation(meta2, kind="import_prefill")
            cv_data, meta2 = _persist(cv_data, meta2)
            return _wizard_resp(assistant_text="Please confirm whether to import the DOCX prefill.", meta_out=meta2, cv_out=cv_data)

        # If a stale import gate leaked into later stages, clear it instead of hijacking flow.
        pc = _get_pending_confirmation(meta2)
        if pc and pc.get("kind") == "import_prefill" and stage_hint not in import_gate_stages:
            meta2 = _clear_pending_confirmation(meta2)
            cv_data, meta2 = _persist(cv_data, meta2)
            pc = None

        # If import gate is pending in early stages, always present it (and accept only import actions).
        if pc and pc.get("kind") == "import_prefill" and user_action_id not in (
            "CONFIRM_IMPORT_PREFILL_YES",
            "CONFIRM_IMPORT_PREFILL_NO",
            "LANGUAGE_SELECT_EN",
            "LANGUAGE_SELECT_DE",
            "LANGUAGE_SELECT_PL",
        ):
            return _wizard_resp(assistant_text="Please confirm whether to import the DOCX prefill.", meta_out=meta2, cv_out=cv_data)

        stage_now = _wizard_get_stage(meta2)

        # SoT: Technical Projects step (5a) is deleted; skip straight to skills.
        if stage_now in ("further_experience", "further_notes_edit", "further_tailor_review"):
            meta2 = _wizard_set_stage(meta2, "it_ai_skills")
            cv_data, meta2 = _persist(cv_data, meta2)
            return _wizard_resp(
                assistant_text="Technical projects step removed. Moving to skills.",
                meta_out=meta2,
                cv_out=cv_data,
            )

        # Action handling (deterministic; no model call).
        if user_action_id:
            aid = user_action_id
            try:
                logging.info(
                    "WIZARD_ACTION aid=%s session=%s stage_before=%s trace_id=%s",
                    aid,
                    session_id,
                    stage_now,
                    trace_id,
                )
            except Exception:
                pass

            fast_paths_deps = FastPathsActionDeps(
                reset_metadata_for_new_version=_reset_metadata_for_new_version,
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                fetch_text_from_url=_fetch_text_from_url,
                now_iso=_now_iso,
                looks_like_job_posting_text=_looks_like_job_posting_text,
                compute_readiness=_compute_readiness,
                sha256_text=_sha256_text,
                download_json_blob=_download_json_blob,
                openai_enabled=_openai_enabled,
                openai_json_schema_call=_openai_json_schema_call,
                build_ai_system_prompt=_build_ai_system_prompt,
                get_job_reference_response_format=get_job_reference_response_format,
                parse_job_reference=parse_job_reference,
                format_job_reference_for_display=format_job_reference_for_display,
                escape_user_input_for_prompt=_escape_user_input_for_prompt,
                sanitize_for_prompt=_sanitize_for_prompt,
                get_work_experience_bullets_proposal_response_format=get_work_experience_bullets_proposal_response_format,
                parse_work_experience_bullets_proposal=parse_work_experience_bullets_proposal,
                extract_e0_corpus_from_labeled_blocks=_extract_e0_corpus_from_labeled_blocks,
                find_work_e0_violations=_find_work_e0_violations,
                build_work_bullet_violation_payload=_build_work_bullet_violation_payload,
                select_roles_by_violation_indices=_select_roles_by_violation_indices,
                overwrite_work_experience_from_proposal_roles=_overwrite_work_experience_from_proposal_roles,
                backfill_missing_work_locations=_backfill_missing_work_locations,
                find_work_bullet_hard_limit_violations=_find_work_bullet_hard_limit_violations,
                collect_raw_docx_skills_context=_collect_raw_docx_skills_context,
                get_skills_unified_proposal_response_format=get_skills_unified_proposal_response_format,
                parse_skills_unified_proposal=parse_skills_unified_proposal,
                tool_generate_cv_from_session=_tool_generate_cv_from_session,
                get_session_with_blob_retrieval=store.get_session_with_blob_retrieval,
                get_session=store.get_session,
                work_experience_hard_limit_chars=product_config.WORK_EXPERIENCE_HARD_LIMIT_CHARS,
                log_warning=logging.warning,
            )
            handled, cv_data, meta2, fast_paths_resp = handle_fast_paths_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                trace_id=trace_id,
                stage_now=stage_now,
                language=language,
                client_context=client_context if isinstance(client_context, dict) else None,
                deps=fast_paths_deps,
            )
            if handled:
                return fast_paths_resp

            profile_confirm_deps = ProfileConfirmActionDeps(
                merge_docx_prefill_into_cv_data_if_needed=_merge_docx_prefill_into_cv_data_if_needed,
                clear_pending_confirmation=_clear_pending_confirmation,
                openai_enabled=_openai_enabled,
                hash_bulk_translation_payload=_hash_bulk_translation_payload,
                build_bulk_translation_payload=_build_bulk_translation_payload,
                bulk_translation_cache_hit=_bulk_translation_cache_hit,
                run_bulk_translation=_run_bulk_translation,
                maybe_apply_fast_profile=_maybe_apply_fast_profile,
                now_iso=_now_iso,
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                sha256_text=_sha256_text,
                upload_json_blob_for_session=_upload_json_blob_for_session,
                stable_profile_user_id=_stable_profile_user_id,
                stable_profile_payload=_stable_profile_payload,
                get_profile_store=get_profile_store,
            )
            handled, cv_data, meta2, profile_confirm_resp = handle_profile_confirm_actions(
                aid=aid,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                trace_id=trace_id,
                client_context=client_context if isinstance(client_context, dict) else None,
                deps=profile_confirm_deps,
            )
            if handled:
                return profile_confirm_resp

            contact_deps = ContactActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                now_iso=_now_iso,
                log_info=logging.info,
            )
            handled, cv_data, meta2, contact_resp = handle_contact_and_language_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                deps=contact_deps,
            )
            if handled:
                return contact_resp

            education_deps = EducationActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
            )
            handled, cv_data, meta2, education_resp = handle_education_basic_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                deps=education_deps,
            )
            if handled:
                return education_resp

            navigation_deps = NavigationActionDeps(
                wizard_get_stage=_wizard_get_stage,
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                log_info=logging.info,
            )
            handled, cv_data, meta2, navigation_resp = handle_navigation_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                deps=navigation_deps,
            )
            if handled:
                return navigation_resp

            job_posting_basic_deps = JobPostingBasicDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                stable_profile_user_id=_stable_profile_user_id,
                stable_profile_payload=_stable_profile_payload,
                get_profile_store=get_profile_store,
            )
            handled, cv_data, meta2, job_posting_basic_resp = handle_job_posting_basic_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                deps=job_posting_basic_deps,
            )
            if handled:
                return job_posting_basic_resp

            job_posting_ai_deps = JobPostingAIDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                openai_enabled=_openai_enabled,
                build_ai_system_prompt=_build_ai_system_prompt,
                openai_json_schema_call=_openai_json_schema_call,
                friendly_schema_error_message=_friendly_schema_error_message,
                format_job_reference_for_display=format_job_reference_for_display,
                now_iso=_now_iso,
                stable_profile_user_id=_stable_profile_user_id,
                stable_profile_payload=_stable_profile_payload,
                get_profile_store=get_profile_store,
                is_http_url=_is_http_url,
                fetch_text_from_url=_fetch_text_from_url,
                looks_like_job_posting_text=_looks_like_job_posting_text,
                get_job_reference_response_format=get_job_reference_response_format,
                parse_job_reference=parse_job_reference,
            )
            handled, cv_data, meta2, job_posting_ai_resp = handle_job_posting_ai_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                trace_id=trace_id,
                session_id=session_id,
                deps=job_posting_ai_deps,
            )
            if handled:
                return job_posting_ai_resp

            work_basic_deps = WorkBasicActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                append_event=store.append_event,
                sha256_text=_sha256_text,
                now_iso=_now_iso,
            )
            handled, cv_data, meta2, work_basic_resp = handle_work_basic_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                deps=work_basic_deps,
            )
            if handled:
                return work_basic_resp

            work_manage_deps = WorkManageActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                snapshot_session=_snapshot_session,
                work_role_lock_key=_work_role_lock_key,
            )
            handled, cv_data, meta2, work_manage_resp = handle_work_manage_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                deps=work_manage_deps,
            )
            if handled:
                return work_manage_resp

            work_tailor_ai_deps = WorkTailorAIActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                openai_enabled=_openai_enabled,
                append_event=store.append_event,
                sha256_text=_sha256_text,
                now_iso=_now_iso,
                format_job_reference_for_display=format_job_reference_for_display,
                escape_user_input_for_prompt=_escape_user_input_for_prompt,
                openai_json_schema_call=_openai_json_schema_call,
                build_ai_system_prompt=_build_ai_system_prompt,
                get_job_reference_response_format=get_job_reference_response_format,
                parse_job_reference=parse_job_reference,
                sanitize_for_prompt=_sanitize_for_prompt,
                log_info=logging.info,
                log_warning=logging.warning,
                get_work_experience_bullets_proposal_response_format=get_work_experience_bullets_proposal_response_format,
                parse_work_experience_bullets_proposal=parse_work_experience_bullets_proposal,
                work_experience_hard_limit_chars=product_config.WORK_EXPERIENCE_HARD_LIMIT_CHARS,
                extract_e0_corpus_from_labeled_blocks=_extract_e0_corpus_from_labeled_blocks,
                find_work_e0_violations=_find_work_e0_violations,
                friendly_schema_error_message=_friendly_schema_error_message,
                normalize_work_role_from_proposal=_normalize_work_role_from_proposal,
                overwrite_work_experience_from_proposal_roles=_overwrite_work_experience_from_proposal_roles,
                backfill_missing_work_locations=_backfill_missing_work_locations,
                find_work_bullet_hard_limit_violations=_find_work_bullet_hard_limit_violations,
                build_work_bullet_violation_payload=_build_work_bullet_violation_payload,
                select_roles_by_violation_indices=_select_roles_by_violation_indices,
                snapshot_session=_snapshot_session,
            )
            handled, cv_data, meta2, work_tailor_ai_resp = handle_work_tailor_ai_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                trace_id=trace_id,
                deps=work_tailor_ai_deps,
            )
            if handled:
                return work_tailor_ai_resp

            cover_pdf_deps = CoverPdfActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                cv_enable_cover_letter=product_config.CV_ENABLE_COVER_LETTER,
                log_info=logging.info,
                openai_enabled=_openai_enabled,
                generate_cover_letter_block_via_openai=_generate_cover_letter_block_via_openai,
                friendly_schema_error_message=_friendly_schema_error_message,
                validate_cover_letter_block=_validate_cover_letter_block,
                build_cover_letter_render_payload=_build_cover_letter_render_payload,
                render_cover_letter_pdf=render_cover_letter_pdf,
                upload_pdf_blob_for_session=_upload_pdf_blob_for_session,
                compute_cover_letter_download_name=_compute_cover_letter_download_name,
                now_iso=_now_iso,
                wizard_get_stage=_wizard_get_stage,
                tool_generate_cv_from_session=_tool_generate_cv_from_session,
                session_get=_session_get,
            )
            handled, cv_data, meta2, cover_pdf_resp = handle_cover_pdf_actions(
                aid=aid,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                trace_id=trace_id,
                stage_now=stage_now,
                language=language,
                client_context=client_context if isinstance(client_context, dict) else None,
                deps=cover_pdf_deps,
            )
            if handled:
                return cover_pdf_resp

            skills_deps = SkillsActionDeps(
                wizard_set_stage=_wizard_set_stage,
                persist=_persist,
                wizard_resp=_wizard_resp,
                append_event=store.append_event,
                sha256_text=_sha256_text,
                now_iso=_now_iso,
                openai_enabled=_openai_enabled,
                format_job_reference_for_display=format_job_reference_for_display,
                escape_user_input_for_prompt=_escape_user_input_for_prompt,
                collect_raw_docx_skills_context=_collect_raw_docx_skills_context,
                sanitize_for_prompt=_sanitize_for_prompt,
                openai_json_schema_call=_openai_json_schema_call,
                build_ai_system_prompt=_build_ai_system_prompt,
                get_skills_unified_proposal_response_format=get_skills_unified_proposal_response_format,
                friendly_schema_error_message=_friendly_schema_error_message,
                parse_skills_unified_proposal=parse_skills_unified_proposal,
                dedupe_strings_case_insensitive=_dedupe_strings_case_insensitive,
                find_work_bullet_hard_limit_violations=_find_work_bullet_hard_limit_violations,
                snapshot_session=_snapshot_session,
            )
            handled, cv_data, meta2, skills_resp = handle_skills_actions(
                aid=aid,
                user_action_payload=user_action_payload if isinstance(user_action_payload, dict) else None,
                cv_data=cv_data,
                meta2=meta2,
                session_id=session_id,
                trace_id=trace_id,
                deps=skills_deps,
            )
            if handled:
                return skills_resp

            # Legacy: Technical projects (Stage 5a) actions are deprecated; keep a soft landing.
            if aid.startswith("FURTHER_"):
                meta2 = _wizard_set_stage(meta2, "it_ai_skills")
                cv_data, meta2 = _persist(cv_data, meta2)
                return _wizard_resp(
                    assistant_text="Technical projects step removed. Moving to skills.",
                    meta_out=meta2,
                    cv_out=cv_data,
                )

            # Unknown action in wizard mode: keep current stage UI.
            cv_data, meta2 = _persist(cv_data, meta2)
            return _wizard_resp(assistant_text=f"Unknown action: {aid}", meta_out=meta2, cv_out=cv_data)

        # Auto-processing: bulk translation gate (no user action required).
        if stage_now == "bulk_translation":
            target_lang = str(meta2.get("target_language") or meta2.get("language") or "en").strip().lower()
            source_hash = _hash_bulk_translation_payload(_build_bulk_translation_payload(cv_data))
            if _bulk_translation_cache_hit(meta=meta2, target_language=target_lang, source_hash=source_hash):
                meta2 = _wizard_set_stage(meta2, "contact")
                cv_data, meta2 = _persist(cv_data, meta2)
                return _wizard_resp(assistant_text="Translation completed. Review your contact details below.", meta_out=meta2, cv_out=cv_data)

            cv_payload = _build_bulk_translation_payload(cv_data)

            has_content = bool(
                cv_payload.get("profile")
                or cv_payload.get("interests")
                or cv_payload.get("references")
                or cv_payload.get("work_experience")
                or cv_payload.get("further_experience")
                or cv_payload.get("education")
                or cv_payload.get("it_ai_skills")
                or cv_payload.get("technical_operational_skills")
                or cv_payload.get("languages")
            )
            if not has_content:
                meta2["bulk_translated_to"] = target_lang
                meta2["bulk_translation_status"] = "skipped_empty"
                meta2["bulk_translation_source_hash"] = source_hash
                cache = meta2.get("bulk_translation_cache") if isinstance(meta2.get("bulk_translation_cache"), dict) else {}
                cache = dict(cache)
                cache[target_lang] = source_hash
                meta2["bulk_translation_cache"] = cache
                meta2.pop("bulk_translation_error", None)
                meta2 = _wizard_set_stage(meta2, "contact")
                cv_data, meta2 = _persist(cv_data, meta2)
                return _wizard_resp(assistant_text="No content to translate. Review your contact details below.", meta_out=meta2, cv_out=cv_data)

            cv_data, meta2, ok_bt, err_bt = _run_bulk_translation(
                cv_data=cv_data,
                meta=meta2,
                trace_id=trace_id,
                session_id=session_id,
                target_language=target_lang,
            )
            if not ok_bt:
                cv_data, meta2 = _persist(cv_data, meta2)
                return _wizard_resp(
                    assistant_text=(
                        _friendly_schema_error_message(str(err_bt))
                        if str(err_bt or "").strip()
                        else "AI failed: empty model output. Please try again."
                    ),
                    meta_out=meta2,
                    cv_out=cv_data,
                )

            meta2 = _wizard_set_stage(meta2, "contact")
            cv_data, meta2 = _persist(cv_data, meta2)
            return _wizard_resp(assistant_text="Translation completed. Review your contact details below.", meta_out=meta2, cv_out=cv_data)

        # No user_action: present current stage UI deterministically.
        if stage_now not in (
            "bulk_translation",
            "contact",
            "contact_edit",
            "education",
            "education_edit_json",
            "job_posting",
            "job_posting_paste",
            "work_experience",
            "work_notes_edit",
            "work_select_role",
            "work_role_view",
            "it_ai_skills",
            "skills_notes_edit",
            "skills_tailor_review",
            "review_final",
            "generate_confirm",
        ):
            meta2 = _wizard_set_stage(meta2, "contact")
            cv_data, meta2 = _persist(cv_data, meta2)
            stage_now = _wizard_get_stage(meta2)

        cv_data, meta2 = _persist(cv_data, meta2)
        stage_text = {
            "bulk_translation": "Translating all content...",
            "contact": "Review your contact details below.",
            "education": "Review your education below.",
            "job_posting": "Optionally add a job offer for tailoring (or skip).",
            "work_experience": "Review your work experience roles below.",
            "review_final": "Ready to generate your PDF.",
            "generate_confirm": "Please confirm PDF generation.",
        }.get(stage_now, "Continue.")
        return _wizard_resp(assistant_text=stage_text, meta_out=meta2, cv_out=cv_data)

    # NON-WIZARD MODE: Continue with normal orchestration
    current_stage = _get_stage_from_metadata(meta)
    generate_requested = _wants_generate_from_message(message)
    # edit_intent is handled early (before wizard split) and returns immediately, so it's always False here
    edit_intent = False

    # confirmation_required is backend-owned: either we have explicit pending edits, or identity-critical fields not confirmed.
    pending_patch = meta.get("pending_patch") if isinstance(meta.get("pending_patch"), dict) else None
    docx_prefill_unconfirmed = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else None
    pending_edits = 1 if (pending_patch is not None) else 0
    pending_confirmation = _get_pending_confirmation(meta)
    confirmation_required = bool(pending_confirmation)

    # Validation state is deterministic: schema + validator (includes estimated_pages).
    schema_valid, _schema_errors = validate_canonical_schema(normalize_cv_data(cv_data), strict=True)
    val_result = validate_cv(normalize_cv_data(cv_data))
    validation_passed = bool(schema_valid) and bool(getattr(val_result, "is_valid", False))
    readiness = _compute_readiness(cv_data, meta)
    readiness_ok = bool(readiness.get("can_generate")) and _estimate_pages_ok(cv_data) and pending_edits == 0

    # Ensure a deterministic pending confirmation when DOCX prefill exists but is not committed.
    # Note: edit intent is handled early and returns before this code, so no need to check here.
    if isinstance(docx_prefill_unconfirmed, dict) and (not cv_data.get("work_experience") or not cv_data.get("education")):
        if not pending_confirmation:
            logging.info(f"Setting pending_confirmation for import_prefill (DOCX has data, canonical CV empty)")
            meta = _set_pending_confirmation(meta, kind="import_prefill")
            pending_confirmation = _get_pending_confirmation(meta)
            # Persist immediately; stage may not change on this turn, but the confirmation gate must.
            try:
                store.update_session(session_id, cv_data, meta)
                sess = store.get_session(session_id) or sess
                meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else meta

                # CRITICAL: Return IMMEDIATELY with ui_action buttons - DO NOT call AI yet!
                readiness_now = _compute_readiness(cv_data, meta)
                ui_action = _build_ui_action(current_stage, cv_data, meta, readiness_now)
                return 200, {
                    "success": True,
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "stage": current_stage,
                    "assistant_text": "Please confirm: do you want to import the data extracted from your CV?",
                    "ui_action": ui_action,
                    "run_summary": {"trace_id": trace_id, "steps": [{"step": "import_prefill_confirmation_required"}]},
                    "turn_trace": [],
                }
            except Exception as e:
                logging.warning(f"Failed to persist pending_confirmation: {e}")
        else:
            # Pending confirmation already exists - also return immediately with buttons
            logging.info(f"Pending confirmation already set: {pending_confirmation}")
            readiness_now = _compute_readiness(cv_data, meta)
            ui_action = _build_ui_action(current_stage, cv_data, meta, readiness_now)
            return 200, {
                "success": True,
                "trace_id": trace_id,
                "session_id": session_id,
                "stage": current_stage,
                "assistant_text": "Please confirm: do you want to import the data extracted from your CV?",
                "ui_action": ui_action,
                "run_summary": {"trace_id": trace_id, "steps": [{"step": "import_prefill_confirmation_required"}]},
                "turn_trace": [],
            }
    
    # CRITICAL: Refresh confirmation_required after any pending_confirmation updates
    # (FSM diagnostics must reflect current state, not stale state from line 2175)
    pending_confirmation = _get_pending_confirmation(meta)
    confirmation_required = bool(pending_confirmation)

    user_confirm_yes = _user_confirm_yes(message) or _is_import_prefill_intent(message) or _is_generate_pdf_intent(message)
    user_confirm_no = _user_confirm_no(message)
    
    # Get turn counter for auto-advance logic
    turns_in_review = _get_turns_in_review(meta)
    
    next_stage = resolve_stage(
        current_stage,
        message,
        SessionState(
            confirmation_required=confirmation_required,
            pending_edits=pending_edits,
            generate_requested=generate_requested,
            user_confirm_yes=user_confirm_yes,
            user_confirm_no=user_confirm_no,
            turns_in_review=turns_in_review,
        ),
        ValidationState(
            validation_passed=validation_passed,
            readiness_ok=readiness_ok,
            pdf_generated=bool(meta.get("pdf_generated")),
            pdf_failed=bool(meta.get("pdf_failed")),
        ),
    )
    
    # Handle turn counter: increment if staying in REVIEW, reset if leaving
    if current_stage == CVStage.REVIEW and next_stage == CVStage.REVIEW:
        meta = _increment_turns_in_review(meta)
        turns_in_review = _get_turns_in_review(meta)
        logging.info(f"Staying in REVIEW: turn {turns_in_review} (auto-advance at turn 3)")
    elif next_stage != CVStage.REVIEW:
        if current_stage == CVStage.REVIEW:
            logging.info(f"Exiting REVIEW after {turns_in_review} turns → {next_stage.value}")
        meta = _reset_turns_in_review(meta)

    # Wave 0.2: Clear pdf_generated when re-entering REVIEW after PDF generation
    if next_stage == CVStage.REVIEW and current_stage in (CVStage.EXECUTE, CVStage.DONE):
        meta = dict(meta) if isinstance(meta, dict) else {}
        meta["pdf_generated"] = False
        meta.pop("pdf_failed", None)
        logging.info(f"Cleared pdf_generated flag (edit intent after {current_stage.value})")

    # Extended diagnostics: show why FSM is or isn't progressing
    stage_debug.update({
        "current_stage": current_stage.value,
        "next_stage": next_stage.value,
        "edit_intent": bool(edit_intent),
        "generate_requested": bool(generate_requested),
        "confirmation_required": confirmation_required,
        "user_confirm_yes": user_confirm_yes,
        "user_confirm_no": user_confirm_no,
        "validation_passed": validation_passed,
        "readiness_ok": readiness_ok,
        "pending_edits": pending_edits,
        "turns_in_review": turns_in_review,
    })
    logging.info(f"FSM: {current_stage.value}→{next_stage.value} | confirm_req={confirmation_required} user_yes={user_confirm_yes} turns={turns_in_review} val={validation_passed} ready={readiness_ok}")

    # Persist stage transitions (backend-owned).
    if next_stage != current_stage:
        meta = _set_stage_in_metadata(meta, next_stage)
        store.update_session(session_id, cv_data, meta)
        sess = store.get_session(session_id) or sess
        meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else meta
        cv_data = sess.get("cv_data") if isinstance(sess.get("cv_data"), dict) else cv_data
    else:
        # Stage didn't change; persist turn counter if still in REVIEW
        if next_stage == CVStage.REVIEW:
            try:
                store.update_session(session_id, cv_data, meta)
            except Exception:
                pass

    # Map contract stages to current internal prompt stages:
    stage_map = {
        CVStage.INGEST: "review_session",
        CVStage.PREPARE: "review_session",
        CVStage.REVIEW: "review_session",
        # CONFIRM is where the user explicitly allows persistence; enable tool-capable stage.
        CVStage.CONFIRM: "apply_edits",
        CVStage.EXECUTE: "generate_pdf",
        CVStage.DONE: "review_session",
    }
    stage = stage_map.get(next_stage, "review_session")

    # CONFIRM stage: apply explicitly confirmed action (scoped; no global "yes commits everything").
    # Auto-clear pending_confirmation when entering CONFIRM stage (already confirmed by FSM auto-advance).
    pc = _get_pending_confirmation(meta)
    if next_stage == CVStage.CONFIRM and pc and pc.get("kind") == "import_prefill":
        try:
            sess_conf = store.get_session(session_id) or sess
            meta_conf = sess_conf.get("metadata") if isinstance(sess_conf.get("metadata"), dict) else {}
            meta_conf = dict(meta_conf) if isinstance(meta_conf, dict) else {}
            cv_conf = sess_conf.get("cv_data") if isinstance(sess_conf.get("cv_data"), dict) else {}
            cv_conf = dict(cv_conf) if isinstance(cv_conf, dict) else {}
            docx_prefill = meta_conf.get("docx_prefill_unconfirmed")
            if isinstance(docx_prefill, dict):
                cv_conf, meta_conf, _merged = _merge_docx_prefill_into_cv_data_if_needed(
                    cv_data=cv_conf,
                    docx_prefill=docx_prefill,
                    meta=meta_conf,
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
            # Mark that this specific confirmation was handled (entering CONFIRM stage is the confirmation).
            meta_conf = _clear_pending_confirmation(meta_conf)
            logging.info(f"Cleared pending_confirmation (kind={pc.get('kind')}) on CONFIRM stage entry")
            store.update_session(session_id, cv_conf, meta_conf)
            sess = store.get_session(session_id) or sess
        except Exception as e:
            logging.error(f"Failed to clear pending_confirmation on CONFIRM entry: {e}")
            pass

    # EXECUTE is the only stage that can generate. Gate it with explicit "generate pdf" confirmation.
    if next_stage == CVStage.EXECUTE:
        if not _is_generate_pdf_intent(message):
            # Force back to REVIEW if user did not explicitly request generation.
            next_stage = CVStage.REVIEW
            meta = _set_stage_in_metadata(meta, next_stage)
            store.update_session(session_id, cv_data, meta)
            stage = "review_session"

    readiness = _compute_readiness(sess.get("cv_data") or {}, sess.get("metadata") or {})

    # If user explicitly requests generation and readiness is satisfied, opt into generate_pdf stage
    # for this turn to enforce single-call execution and expose PDF tools.
    if stage != "generate_pdf" and generate_requested and readiness.get("can_generate"):
        stage = "generate_pdf"

    max_model_calls = product_config.CV_MAX_MODEL_CALLS
    max_model_calls = max(1, min(max_model_calls, 5))

    version_before = sess.get("version")

    # Best-effort: append user event (for semantic debugging).
    try:
        store.append_event(
            session_id,
            {
                "type": "user_message",
                "trace_id": trace_id,
                "stage": stage,
                "text": message[:1500],
                "text_len": len(message or ""),
            },
        )
    except Exception:
        pass

    assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes = _run_responses_tool_loop_v2(
        user_message=message,
        session_id=session_id,
        stage=stage,
        job_posting_text=job_posting_text,
        trace_id=trace_id,
        max_model_calls=max_model_calls,
        execution_mode=(stage == "generate_pdf"),  # Wave 0.3: Enable execution mode for PDF generation
    )

    # Deterministic hard rules and debuggability.
    run_summary.setdefault("stage_debug", {})
    run_summary["stage_debug"].update(stage_debug)
    run_summary["stage_debug"].update({"version_before": version_before})

    def _tool_steps_count(rs: dict) -> int:
        steps = rs.get("steps")
        if not isinstance(steps, list):
            return 0
        return sum(1 for s in steps if isinstance(s, dict) and s.get("step") == "tool")

    sess_after = store.get_session(session_id) or sess
    version_after = sess_after.get("version")
    run_summary["stage_debug"]["version_after"] = version_after
    readiness_after = _compute_readiness(sess_after.get("cv_data") or {}, sess_after.get("metadata") or {})
    run_summary["stage_debug"]["readiness_after"] = readiness_after

    # Hard rule: if generation requested but readiness not met -> never return "Done." and never generate.
    if stage == "generate_pdf" and not readiness_after.get("can_generate"):
        missing = readiness_after.get("missing") or []
        assistant_text = (
            "I can’t generate the PDF yet. The session is not complete.\n\n"
            f"Missing / not confirmed: {', '.join(missing) if missing else 'unknown'}.\n\n"
            "Please fill/confirm those fields, then ask again to generate the PDF."
        )
        pdf_bytes = None

    # Deterministic fallback: if the user asked to generate and we still have no PDF, generate directly
    # once readiness is satisfied. This avoids "Done." responses without a PDF.
    # Wave 0.1: Skip fallback if PDF already exists (latch engaged)
    skip_fallback = False
    if product_config.CV_EXECUTION_LATCH:
        sess_check = store.get_session(session_id) or {}
        meta_check = sess_check.get("metadata") or {}
        pdf_refs_check = meta_check.get("pdf_refs") if isinstance(meta_check, dict) else {}
        if isinstance(pdf_refs_check, dict) and pdf_refs_check:
            skip_fallback = True
            logging.info(f"Skipping fallback PDF generation: PDF already exists (latch engaged)")

    if stage == "generate_pdf" and not pdf_bytes and not skip_fallback:
        try:
            sess2 = store.get_session_with_blob_retrieval(session_id) or {}
            meta2 = sess2.get("metadata") or {}
            cv2 = sess2.get("cv_data") or {}
            readiness2 = _compute_readiness(cv2 if isinstance(cv2, dict) else {}, meta2 if isinstance(meta2, dict) else {})
            if readiness2.get("can_generate"):
                status, payload, content_type = _tool_generate_cv_from_session(
                    session_id=session_id,
                    language=language,
                    client_context=client_context if isinstance(client_context, dict) else None,
                    session=sess2,
                )
                if status == 200 and content_type == "application/pdf" and isinstance(payload, dict) and isinstance(payload.get("pdf_bytes"), (bytes, bytearray)):
                    pdf_bytes = bytes(payload["pdf_bytes"])
                    run_summary.setdefault("steps", []).append({"step": "fallback_pdf_generation", "ok": True})
                else:
                    run_summary.setdefault("steps", []).append({"step": "fallback_pdf_generation", "ok": False, "status": status})
        except Exception as exc:
            run_summary.setdefault("steps", []).append({"step": "fallback_pdf_generation", "ok": False, "error": str(exc)})

    # Hard rule: no-changes-no-generation. If nothing changed in this request and we didn't generate a PDF,
    # return a deterministic next-step instead of "Done.".
    if stage == "generate_pdf" and not pdf_bytes and version_after == version_before and not bool(readiness_after.get("can_generate")):
        assistant_text = (
            "No changes were applied in this request, so I did not generate a PDF.\n\n"
            "Next step: confirm/import the prefilled DOCX data into active cv_data (work experience, education, etc.), "
            "then ask again to generate the PDF."
        )

    # Guardrail: if the model returns a no-op 'Done.' without tools, replace with a deterministic response.
    if (assistant_text or "").strip().lower() in ("done.", "done") and _tool_steps_count(run_summary) == 0:
        assistant_text = (
            "I have your session and the DOCX prefill, but I didn’t apply any changes yet.\n\n"
            f"Current readiness.can_generate = {bool(readiness_after.get('can_generate'))}. "
            f"Missing: {', '.join(readiness_after.get('missing') or []) or 'none'}.\n\n"
            "Tell me: (1) import the DOCX prefill into active cv_data (yes/no), and (2) whether to generate the PDF now."
        )

    # Best-effort: append assistant event (pairs user+assistant in event_log).
    try:
        store.append_event(
            session_id,
            {
                "type": "assistant_message",
                "trace_id": trace_id,
                "stage": stage,
                "text": (assistant_text or "")[:1500],
                "text_len": len(assistant_text or ""),
                "run_summary": {"model_calls": run_summary.get("model_calls"), "steps": run_summary.get("steps")[-10:] if isinstance(run_summary.get("steps"), list) else []},
            },
        )
    except Exception:
        pass

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else ""
    filename = _latest_pdf_download_name(meta=meta_after, cv_data_fallback=cv_data_after) if pdf_bytes else ""

    # Build UI action for guided flow (use UPDATED session data after AI processing)
    cv_data_after = sess_after.get("cv_data") or {}
    meta_after = sess_after.get("metadata") or {}
    stage_after = _get_stage_from_metadata(meta_after) if isinstance(meta_after, dict) else stage
    ui_action = _build_ui_action(stage_after, cv_data_after, meta_after, readiness_after)

    return 200, {
        "success": True,
        "trace_id": trace_id,
        "session_id": session_id,
        "stage": stage,
        "assistant_text": assistant_text,
        "pdf_base64": pdf_base64,
        "filename": filename,
        # Debug-only: useful when OPENAI_STORE=1 and you want to inspect a specific Responses API run.
        "last_response_id": last_response_id,
        "run_summary": run_summary,
        "turn_trace": turn_trace,
        "client_context_keys": list(client_context.keys())[:20] if client_context else None,
        "ui_action": ui_action,
    }


def _cv_session_search_hits(*, session: dict, q: str, limit: int) -> dict:
    """Pure helper: build bounded search hits from a session dict (no storage I/O)."""
    q = (q or "").lower().strip()
    limit = max(1, min(int(limit or 20), 50))

    hits: list[dict] = []

    def _add_hit(source: str, field_path: str, value: Any) -> None:
        preview = ""
        if isinstance(value, str):
            preview = value[:240]
        elif isinstance(value, (int, float)):
            preview = str(value)
        elif isinstance(value, list):
            preview = json.dumps(value[:2], ensure_ascii=False)[:240]
        elif isinstance(value, dict):
            preview = json.dumps(value, ensure_ascii=False)[:240]
        if q and q not in preview.lower():
            return
        hits.append({"source": source, "field_path": field_path, "preview": preview})

    meta = session.get("metadata") or {}
    docx_prefill = meta.get("docx_prefill_unconfirmed") or {}
    cv_data = session.get("cv_data") or {}

    for fp in ["full_name", "email", "phone"]:
        if fp in docx_prefill:
            _add_hit("docx_prefill_unconfirmed", fp, docx_prefill[fp])
        if fp in cv_data:
            _add_hit("cv_data", fp, cv_data.get(fp))

    def _walk_list(lst: Any, base: str, source: str) -> None:
        if not isinstance(lst, list):
            return
        for idx, item in enumerate(lst):
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                _add_hit(source, f"{base}[{idx}].{k}", v)

    _walk_list(docx_prefill.get("education"), "docx.education", "docx_prefill_unconfirmed")
    _walk_list(cv_data.get("education"), "education", "cv_data")
    _walk_list(docx_prefill.get("work_experience"), "docx.work_experience", "docx_prefill_unconfirmed")
    _walk_list(cv_data.get("work_experience"), "work_experience", "cv_data")

    events = meta.get("event_log") or []
    if isinstance(events, list):
        for i, e in enumerate(events[-20:]):
            _add_hit("event_log", f"event_log[-{min(20, len(events))}+{i}]", e)

    truncated = False
    if len(hits) > limit:
        hits = hits[:limit]
        truncated = True

    return {"hits": hits, "truncated": truncated}


def _validate_cv_data_for_tool(cv_data: dict) -> dict:
    """Deterministic validation for tool use (no rendering)."""
    cv_data = normalize_cv_data(cv_data or {})
    is_schema_valid, schema_errors = validate_canonical_schema(cv_data, strict=True)
    validation_result = validate_cv(cv_data)
    return {
        "schema_valid": bool(is_schema_valid),
        "schema_errors": schema_errors,
        "validation": _serialize_validation_result(validation_result),
    }


def _render_html_for_tool(cv_data: dict, *, inline_css: bool = True) -> dict:
    """Render HTML for tool use (debug/preview)."""
    cv_data = normalize_cv_data(cv_data or {})
    html_content = render_html(cv_data, inline_css=inline_css)
    return {"html": html_content, "html_length": len(html_content or "")}


def _tool_extract_and_store_cv(*, docx_base64: str, language: str, extract_photo_flag: bool, job_posting_url: str | None, job_posting_text: str | None) -> tuple[int, dict]:
    def _cleanup_expired_once(store_obj: Any) -> None:
        global _CLEANUP_EXPIRED_RAN
        if _CLEANUP_EXPIRED_RAN:
            return
        _CLEANUP_EXPIRED_RAN = True
        try:
            deleted = store_obj.cleanup_expired()
            if deleted:
                logging.info("Expired sessions cleaned: %s", deleted)
        except Exception:
            pass

    deps = ExtractStoreToolDeps(
        get_session_store=_get_session_store,
        cleanup_expired_once=_cleanup_expired_once,
        extract_first_photo_from_docx_bytes=extract_first_photo_from_docx_bytes,
        prefill_cv_from_docx_bytes=prefill_cv_from_docx_bytes,
        now_iso=_now_iso,
        looks_like_job_posting_text=_looks_like_job_posting_text,
        fetch_text_from_url=_fetch_text_from_url,
        blob_store_factory=CVBlobStore,
        stage_prepare_value=CVStage.PREPARE.value,
    )
    return tool_extract_and_store_cv(
        docx_base64=docx_base64,
        language=language,
        extract_photo_flag=extract_photo_flag,
        job_posting_url=job_posting_url,
        job_posting_text=job_posting_text,
        deps=deps,
    )


def _tool_generate_context_pack_v2(*, session_id: str, phase: str, job_posting_text: str | None, max_pack_chars: int, session: dict) -> tuple[int, dict]:
    deps = ContextPackToolDeps(
        cv_delta_mode=product_config.CV_DELTA_MODE,
        build_context_pack_v2=build_context_pack_v2,
        build_context_pack_v2_delta=build_context_pack_v2_delta,
    )
    return tool_generate_context_pack_v2(
        session_id=session_id,
        phase=phase,
        job_posting_text=job_posting_text,
        max_pack_chars=max_pack_chars,
        session=session,
        deps=deps,
    )


def _tool_generate_cv_from_session(*, session_id: str, language: str | None, client_context: dict | None, session: dict) -> tuple[int, dict | bytes, str]:
    deps = CvPdfToolDeps(
        cv_pdf_always_regenerate=product_config.CV_PDF_ALWAYS_REGENERATE,
        cv_execution_latch=product_config.CV_EXECUTION_LATCH,
        sha256_text=_sha256_text,
        get_session_store=_get_session_store,
        compute_readiness=_compute_readiness,
        openai_enabled=_openai_enabled,
        run_bulk_translation=_run_bulk_translation,
        backfill_missing_work_locations=_backfill_missing_work_locations,
        drop_one_work_bullet_bottom_up=_drop_one_work_bullet_bottom_up,
        serialize_validation_result=_serialize_validation_result,
        upload_pdf_blob_for_session=_upload_pdf_blob_for_session,
        compute_pdf_download_name=_compute_pdf_download_name,
        shrink_metadata_for_table=_shrink_metadata_for_table,
        now_iso=_now_iso,
    )
    return tool_generate_cv_from_session(
        session_id=session_id,
        language=language,
        client_context=client_context,
        session=session,
        deps=deps,
    )

def _upload_pdf_blob_for_session(*, session_id: str, pdf_ref: str, pdf_bytes: bytes) -> dict[str, str] | None:
    container = product_config.STORAGE_CONTAINER_PDFS
    blob_name = f"{session_id}/{pdf_ref}.pdf"
    try:
        blob_store = CVBlobStore(container=container)
        pointer = blob_store.upload_bytes(blob_name=blob_name, data=pdf_bytes, content_type="application/pdf")
        return {"container": pointer.container, "blob_name": pointer.blob_name}
    except Exception as exc:
        logging.warning("Failed to upload generated PDF blob session_id=%s error=%s", session_id, exc)
        return None


def _upload_json_blob_for_session(*, session_id: str, blob_name: str, payload: dict) -> dict[str, str] | None:
    container = product_config.STORAGE_CONTAINER_ARTIFACTS
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        blob_store = CVBlobStore(container=container)
        pointer = blob_store.upload_bytes(blob_name=blob_name, data=data, content_type="application/json")
        return {"container": pointer.container, "blob_name": pointer.blob_name}
    except Exception as exc:
        logging.warning("Failed to upload JSON blob session_id=%s blob_name=%s error=%s", session_id, blob_name, exc)
        return None


def _download_json_blob(*, container: str, blob_name: str) -> dict | None:
    try:
        store = CVBlobStore(container=container)
        data = store.download_bytes(BlobPointer(container=container, blob_name=blob_name, content_type="application/json"))
        text = data.decode("utf-8", errors="replace")
        obj = json.loads(text or "{}")
        return obj if isinstance(obj, dict) else None
    except Exception as exc:
        logging.warning("Failed to download JSON blob container=%s blob_name=%s error=%s", container, blob_name, exc)
        return None


def _tool_generate_cover_letter_from_session(
    *,
    session_id: str,
    language: str | None,
    session: dict,
) -> tuple[int, dict | bytes, str]:
    deps = CoverLetterToolDeps(
        cv_enable_cover_letter=product_config.CV_ENABLE_COVER_LETTER,
        openai_enabled=_openai_enabled,
        generate_cover_letter_block_via_openai=_generate_cover_letter_block_via_openai,
        validate_cover_letter_block=_validate_cover_letter_block,
        build_cover_letter_render_payload=_build_cover_letter_render_payload,
        render_cover_letter_pdf=render_cover_letter_pdf,
        upload_pdf_blob_for_session=_upload_pdf_blob_for_session,
        compute_cover_letter_download_name=_compute_cover_letter_download_name,
        now_iso=_now_iso,
        get_session_store=_get_session_store,
    )
    return tool_generate_cover_letter_from_session(
        session_id=session_id,
        language=language,
        session=session,
        deps=deps,
    )


def _tool_get_pdf_by_ref(*, session_id: str, pdf_ref: str, session: dict) -> tuple[int, dict | bytes, str]:
    return tool_get_pdf_by_ref(session_id=session_id, pdf_ref=pdf_ref, session=session)


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return handle_health_check(json_response=_json_response, log_info=logging.info)


@app.route(route="cv-tool-call-handler", methods=["POST"])
def cv_tool_call_handler(req: func.HttpRequest) -> func.HttpResponse:
    deps = EntryPointDeps(
        json_response=_json_response,
        get_session_store=_get_session_store,
        tool_extract_and_store_cv=_tool_extract_and_store_cv,
        tool_process_cv_orchestrated=_tool_process_cv_orchestrated,
        compute_readiness=_compute_readiness,
        now_iso=_now_iso,
        merge_docx_prefill_into_cv_data_if_needed=_merge_docx_prefill_into_cv_data_if_needed,
        update_section_hashes_in_metadata=_update_section_hashes_in_metadata,
        tool_generate_context_pack_v2=_tool_generate_context_pack_v2,
        cv_session_search_hits=_cv_session_search_hits,
        validate_cv_data_for_tool=_validate_cv_data_for_tool,
        render_html_for_tool=_render_html_for_tool,
        tool_generate_cv_from_session=_tool_generate_cv_from_session,
        compute_pdf_download_name=_compute_pdf_download_name,
        tool_generate_cover_letter_from_session=_tool_generate_cover_letter_from_session,
        compute_cover_letter_download_name=_compute_cover_letter_download_name,
        is_debug_export_enabled=_is_debug_export_enabled,
        export_session_debug_files=_export_session_debug_files,
        tool_get_pdf_by_ref=_tool_get_pdf_by_ref,
    )
    return handle_cv_tool_call(req, deps=deps)





