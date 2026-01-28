from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Literal

from .normalize import normalize_cv_data

# Type alias for phase
PhaseType = Literal['preparation', 'confirmation', 'execution']


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _compute_section_hash(section_data: Any) -> str:
    """Compute stable hash for a CV section.
    
    Args:
        section_data: Any CV section data (list, dict, string, or None)
    
    Returns:
        Short hash (16 chars) for delta detection
    """
    if section_data is None:
        return "null"
    if isinstance(section_data, (list, dict)):
        canonical = json.dumps(section_data, ensure_ascii=False, sort_keys=True)
        return _sha256_hex(canonical)[:16]  # Short hash (64 bits)
    return _sha256_hex(str(section_data))[:16]


def compute_cv_section_hashes(cv_data: Dict[str, Any]) -> Dict[str, str]:
    """Compute hashes for all major CV sections.
    
    Args:
        cv_data: Complete CV data dictionary
    
    Returns:
        Dict mapping section names to their hashes
    """
    sections = [
        'work_experience',
        'education',
        'languages',
        'it_ai_skills',
        'interests',
        'profile',
        'further_experience'
    ]
    hashes = {}
    
    # Special case: contact is composite of multiple top-level fields
    contact_blob = {
        'full_name': cv_data.get('full_name'),
        'email': cv_data.get('email'),
        'phone': cv_data.get('phone'),
        'address_lines': cv_data.get('address_lines'),
    }
    hashes['contact'] = _compute_section_hash(contact_blob)
    
    # Hash each major section independently
    for section in sections:
        hashes[section] = _compute_section_hash(cv_data.get(section))
    
    return hashes


def detect_section_changes(
    current_hashes: Dict[str, str],
    previous_hashes: Optional[Dict[str, str]]
) -> Dict[str, bool]:
    """Return {section_name: changed} for all sections.
    
    Args:
        current_hashes: Current section hashes
        previous_hashes: Previous section hashes (None on first run)
    
    Returns:
        Dict mapping section names to True (changed) or False (unchanged)
    """
    if not previous_hashes:
        # First run: all sections are "new" (treat as changed)
        return {k: True for k in current_hashes.keys()}
    
    changes = {}
    for section, curr_hash in current_hashes.items():
        prev_hash = previous_hashes.get(section)
        changes[section] = (curr_hash != prev_hash)
    
    return changes


DEFAULT_MAX_PACK_CHARS = 8000  # Reduced from 12000 to target ~2.5k tokens instead of ~4k


TEMPLATE_SPEC_V1 = {
    "template_name": "cv_template_2pages_2025",
    "notes": [
        "The current fixed PDF template does NOT render a dedicated Profile/Summary section.",
        "Optimize content for the rendered sections and hard limits.",
    ],
    "rendered_sections_order": [
        "Education",
        "Work experience",
        "Further experience / commitment",
        "Language Skills",
        "IT & AI Skills",
        "Interests",
        "References",
    ],
    "rendered_fields": [
        "full_name",
        "address_lines",
        "phone",
        "email",
        "birth_date",
        "nationality",
        "education",
        "work_experience",
        "further_experience",
        "languages",
        "it_ai_skills",
        "interests",
        "references",
        "photo_url",
        "language",
    ],
}


def build_context_pack(
    cv_data: Dict[str, Any],
    user_message: Optional[str] = None,
    job_posting_text: Optional[str] = None,
    user_preferences: Optional[Dict[str, Any]] = None,
    max_pack_chars: int = DEFAULT_MAX_PACK_CHARS,
) -> Dict[str, Any]:
    """Build a ContextPackV1 from parsed CV JSON and optional job posting.

    Guarantees:
    - Preserve work_experience[*].bullets verbatim (never truncated or removed).
    - Omit empty sections from `cv_structured` (renderer will skip them).
    - Enforce a size cap by removing low-priority sections when necessary.
    - Compute a stable fingerprint from the normalized CV JSON.
    """

    normalized = normalize_cv_data(cv_data)

    # Stable string for fingerprinting: deterministic JSON with sorted keys
    normalized_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    fingerprint = "sha256:" + _sha256_hex(normalized_json)

    # Build structured CV: copy relevant keys, omit empty/None
    keep_keys = [
        "full_name",
        "email",
        "phone",
        "address_lines",
        "nationality",
        "profile",
        "work_experience",
        "education",
        "languages",
        "it_ai_skills",
        "trainings",
        "interests",
        "data_privacy",
        "further_experience",
    ]

    cv_structured: Dict[str, Any] = {}
    for k in keep_keys:
        v = normalized.get(k)
        if v is None:
            continue
        # omit empty lists or empty strings
        if isinstance(v, list) and len(v) == 0:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        cv_structured[k] = v

    # Ensure bullets are preserved and accessible for checks
    # (no-op here; just guarantee key exists)
    for job in cv_structured.get("work_experience", []):
        if "bullets" not in job:
            job["bullets"] = []

    # Job posting snippet bounded
    job_snippet = None
    if job_posting_text:
        job_snippet = job_posting_text[:6000]

    pack: Dict[str, Any] = {
        "schema_version": "cvgen.context_pack.v1",
        "language": normalized.get("language", ""),
        "cv_fingerprint": fingerprint,
        "inputs": {
            "has_docx": False,
        },
        "cv_structured": cv_structured,
        "job_posting": {
            "text_snippet": job_snippet,
            "fingerprint": None,
        },
        "user_preferences": user_preferences or {},
        "limits": {
            "max_pack_chars": max_pack_chars,
            "cv_text_max_chars": 0,
            "job_text_max_chars": 6000,
        },
    }

    if job_snippet:
        pack["job_posting"]["fingerprint"] = "sha256:" + _sha256_hex(job_snippet)

    # Serialize and check size; if over limit, remove low-priority fields
    def _pack_size(p: Dict[str, Any]) -> int:
        return len(json.dumps(p, ensure_ascii=False, sort_keys=True))

    truncated_fields: List[str] = []
    size = _pack_size(pack)
    if size > max_pack_chars:
        # Stepwise drop priorities (never touch work_experience.bullets)
        for field in ["trainings", "interests", "it_ai_skills"]:
            if field in pack["cv_structured"]:
                del pack["cv_structured"][field]
                truncated_fields.append(field)
                size = _pack_size(pack)
                if size <= max_pack_chars:
                    break

    # If still too large, trim education.details entries (but keep education entries)
    if size > max_pack_chars and "education" in pack["cv_structured"]:
        for edu in pack["cv_structured"]["education"]:
            if isinstance(edu.get("details"), list) and edu["details"]:
                edu["details"] = []
                truncated_fields.append("education.details")
                size = _pack_size(pack)
                if size <= max_pack_chars:
                    break

    # Final check: if still too large, mark truncated flag (do not remove bullets)
    if size > max_pack_chars:
        pack.setdefault("limits", {})["truncated_fields"] = truncated_fields
        pack.setdefault("limits", {})["final_size"] = size
        pack.setdefault("limits", {})["note"] = (
            "Pack exceeds max size after safe removals; work_experience bullets preserved."
        )
    else:
        if truncated_fields:
            pack.setdefault("limits", {})["truncated_fields"] = truncated_fields
            pack.setdefault("limits", {})["final_size"] = size

    return pack


def build_context_pack_v2(
    phase: PhaseType,
    cv_data: Dict[str, Any],
    job_posting_text: Optional[str] = None,
    job_reference: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
    pack_mode: str = "full",
    max_pack_chars: int = DEFAULT_MAX_PACK_CHARS,
) -> Dict[str, Any]:
    """Build phase-specific context pack (ContextPackV2).

    Args:
        phase: Current workflow phase ('preparation' | 'confirmation' | 'execution')
        cv_data: Current CV data from session
        job_posting_text: Job posting text (needed for Phase 1)
        session_metadata: Session metadata (includes phase history, original CV, proposals)
        max_pack_chars: Size limit (default: 12,000 chars)

    Returns:
        ContextPackV2 dict with phase-specific context
    """
    normalized = normalize_cv_data(cv_data)
    normalized_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    fingerprint = "sha256:" + _sha256_hex(normalized_json)

    session_id = session_metadata.get('session_id') if session_metadata else None
    language = normalized.get('language', 'en')
    event_log = session_metadata.get("event_log") if isinstance(session_metadata, dict) else None
    if not isinstance(event_log, list):
        event_log = []

    def _compact_event(e: Any) -> Dict[str, Any]:
        if not isinstance(e, dict):
            return {}
        out: Dict[str, Any] = {
            "ts": e.get("ts"),
            "type": e.get("type"),
        }
        if "field_path" in e:
            out["field_path"] = e.get("field_path")
        if "preview" in e:
            p = e.get("preview")
            if isinstance(p, str) and len(p) > 160:
                p = p[:160] + "…"
            out["preview"] = p
        if "language" in e:
            out["language"] = e.get("language")
        cc = e.get("client_context")
        if isinstance(cc, dict):
            out["client_context"] = {"stage": cc.get("stage"), "stage_seq": cc.get("stage_seq")}
        return out

    pack_mode = (pack_mode or "full").strip().lower()
    if pack_mode not in ("full", "mini"):
        pack_mode = "full"

    pack: Dict[str, Any] = {
        'schema_version': 'cvgen.context_pack.v2',
        'phase': phase,
        'language': language,
        'session_id': session_id,
        'cv_fingerprint': fingerprint,
        'template': TEMPLATE_SPEC_V1,
        'session_freshness': {
            "version": session_metadata.get("version") if isinstance(session_metadata, dict) else None,
            "updated_at": session_metadata.get("updated_at") if isinstance(session_metadata, dict) else None,
        },
        'recent_events': [_compact_event(e) for e in event_log[-(5 if pack_mode == "mini" else 15):]],
    }

    jr = job_reference
    if jr is None and isinstance(session_metadata, dict):
        jr = session_metadata.get("job_reference")
    if not isinstance(jr, dict):
        jr = None

    if phase == 'preparation':
        pack['preparation'] = _build_preparation_context(
            normalized, job_posting_text, jr, session_metadata, pack_mode=pack_mode
        )
    elif phase == 'confirmation':
        pack['confirmation'] = _build_confirmation_context(
            normalized, session_metadata, pack_mode=pack_mode
        )
    elif phase == 'execution':
        pack['execution'] = _build_execution_context(
            normalized, session_metadata, pack_mode=pack_mode
        )

    # Add completeness + next_missing_section
    completeness = _compute_completeness(normalized)
    confirmation_state = _compute_confirmation_state(normalized, session_metadata)
    pack['confirmation_state'] = confirmation_state
    pack['readiness'] = {
        "can_generate": confirmation_state.get("can_generate"),
        "missing": confirmation_state.get("missing"),
        "required_present": completeness.get("required_present"),
    }
    pack['completeness'] = completeness

    # Apply size limits
    pack = _apply_size_limits_v2(pack, max_pack_chars)

    return pack


def build_context_pack_v2_delta(
    phase: PhaseType,
    cv_data: Dict[str, Any],
    session_metadata: Optional[Dict[str, Any]] = None,
    job_posting_text: Optional[str] = None,
    job_reference: Optional[Dict[str, Any]] = None,
    max_pack_chars: int = DEFAULT_MAX_PACK_CHARS,
) -> Dict[str, Any]:
    """Build delta-aware context pack (only changed sections get full data).
    
    Args:
        phase: Current workflow phase
        cv_data: Current CV data
        session_metadata: Session metadata (must contain section_hashes_prev for delta)
        job_posting_text: Job posting text
        max_pack_chars: Size limit
    
    Returns:
        ContextPackV2Delta with section_changes markers
    """
    normalized = normalize_cv_data(cv_data)
    normalized_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    fingerprint = "sha256:" + _sha256_hex(normalized_json)
    
    # Compute delta
    current_hashes = compute_cv_section_hashes(normalized)
    previous_hashes = session_metadata.get("section_hashes_prev") if session_metadata else None
    section_changes = detect_section_changes(current_hashes, previous_hashes)
    
    session_id = session_metadata.get('session_id') if session_metadata else None
    language = normalized.get('language', 'en')
    event_log = session_metadata.get("event_log") if isinstance(session_metadata, dict) else None
    if not isinstance(event_log, list):
        event_log = []
    
    def _compact_event(e: Any) -> Dict[str, Any]:
        if not isinstance(e, dict):
            return {}
        out: Dict[str, Any] = {"ts": e.get("ts"), "type": e.get("type")}
        if "field_path" in e:
            out["field_path"] = e.get("field_path")
        if "preview" in e:
            p = e.get("preview")
            if isinstance(p, str) and len(p) > 160:
                p = p[:160] + "…"
            out["preview"] = p
        return out
    
    pack: Dict[str, Any] = {
        'schema_version': 'cvgen.context_pack.v2_delta',
        'phase': phase,
        'language': language,
        'session_id': session_id,
        'cv_fingerprint': fingerprint,
        'template': TEMPLATE_SPEC_V1,
        'section_changes': section_changes,
        'section_hashes': current_hashes,
        'session_freshness': {
            "version": session_metadata.get("version") if isinstance(session_metadata, dict) else None,
            "updated_at": session_metadata.get("updated_at") if isinstance(session_metadata, dict) else None,
        },
        'recent_events': [_compact_event(e) for e in event_log[-5:]],
    }

    jr = job_reference
    if jr is None and isinstance(session_metadata, dict):
        jr = session_metadata.get("job_reference")
    if not isinstance(jr, dict):
        jr = None
    
    # Build section-specific packs (changed=full, unchanged=summary)
    def _pack_section_delta(section_name: str, section_data: Any) -> Dict[str, Any]:
        is_changed = section_changes.get(section_name, True)
        section_hash = current_hashes.get(section_name, "unknown")
        
        if is_changed:
            # CHANGED: send full data
            return {
                'status': 'changed',
                'hash': section_hash,
                'data': section_data
            }
        else:
            # UNCHANGED: send summary only
            if isinstance(section_data, list):
                preview = section_data[0] if section_data else None
                return {
                    'status': 'unchanged',
                    'hash': section_hash,
                    'count': len(section_data),
                    'preview': preview
                }
            elif isinstance(section_data, str):
                return {
                    'status': 'unchanged',
                    'hash': section_hash,
                    'preview': section_data[:200] if section_data else None
                }
            else:
                return {
                    'status': 'unchanged',
                    'hash': section_hash,
                    'data': section_data  # Small primitives: just send it
                }
    
    # Pack all major sections
    pack['work_experience'] = _pack_section_delta('work_experience', normalized.get('work_experience'))
    pack['education'] = _pack_section_delta('education', normalized.get('education'))
    pack['languages'] = _pack_section_delta('languages', normalized.get('languages'))
    pack['it_ai_skills'] = _pack_section_delta('it_ai_skills', normalized.get('it_ai_skills'))
    pack['interests'] = _pack_section_delta('interests', normalized.get('interests'))
    pack['profile'] = _pack_section_delta('profile', normalized.get('profile'))
    pack['further_experience'] = _pack_section_delta('further_experience', normalized.get('further_experience'))
    
    # Contact: always send if changed (critical)
    if section_changes.get('contact'):
        pack['contact'] = {
            'status': 'changed',
            'hash': current_hashes['contact'],
            'full_name': normalized.get('full_name'),
            'email': normalized.get('email'),
            'phone': normalized.get('phone'),
            'address_lines': normalized.get('address_lines'),
        }
    else:
        pack['contact'] = {
            'status': 'unchanged',
            'hash': current_hashes['contact'],
            'has_data': bool(normalized.get('full_name') or normalized.get('email'))
        }
    
    # Job reference: prefer structured object; do not embed raw offer text once normalized.
    if jr:
        pack['job_reference'] = jr
    elif job_posting_text:
        pack['job_posting'] = {'text': job_posting_text[:2000]}  # Cap at 2k chars
    
    # Add readiness
    completeness = _compute_completeness(normalized)
    confirmation_state = _compute_confirmation_state(normalized, session_metadata)
    pack['confirmation_state'] = confirmation_state
    pack['readiness'] = {
        "can_generate": confirmation_state.get("can_generate"),
        "missing": confirmation_state.get("missing"),
        "required_present": completeness.get("required_present"),
    }
    pack['completeness'] = completeness
    
    # Apply size limits (lighter trimming since we already sent summaries)
    pack = _apply_size_limits_v2(pack, max_pack_chars)
    
    return pack


def _build_preparation_context(
    cv_data: Dict[str, Any],
    job_posting_text: Optional[str],
    job_reference: Optional[Dict[str, Any]],
    session_metadata: Optional[Dict[str, Any]],
    *,
    pack_mode: str = "full",
) -> Dict[str, Any]:
    """Build context for Phase 1 (Preparation)."""
    context: Dict[str, Any] = {}

    # Job reference: prefer structured object; do not embed raw offer text once normalized.
    if isinstance(job_reference, dict) and job_reference:
        # Keep compact: the analyzer already normalized content.
        context["job_reference"] = job_reference
    elif job_posting_text:
        # Legacy fallback (should not be persisted long-term).
        max_chars = 1200 if pack_mode == "mini" else 6000
        context['job_analysis'] = {
            'text_snippet': job_posting_text[:max_chars],
            'has_full_text': len(job_posting_text) <= max_chars,
            'note': 'Analyze deeply: extract explicit/implicit requirements, must-have vs nice-to-have, ambiguities, culture signals.'
        }

    # CV structured data (for mapping)
    context['cv_data'] = _extract_cv_structured_mini(cv_data) if pack_mode == "mini" else _extract_cv_structured_compact(cv_data)

    # Unconfirmed DOCX extraction snapshot (reference only).
    # Sessions now start empty; this helps the agent re-populate required fields quickly and explicitly.
    if isinstance(session_metadata, dict) and session_metadata.get("docx_prefill_unconfirmed"):
        if pack_mode == "mini":
            context["docx_prefill_summary"] = _summarize_docx_prefill(session_metadata.get("docx_prefill_unconfirmed"))
        else:
            context["docx_prefill_unconfirmed"] = session_metadata.get("docx_prefill_unconfirmed")

    # Proposal history (from session metadata) - keep last 3 only
    if session_metadata and 'proposal_history' in session_metadata:
        if pack_mode != "mini":
            proposals = session_metadata['proposal_history']
            context['proposal_history'] = _trim_proposal_history(proposals, max_turns=3)

    return context


def _build_confirmation_context(
    cv_data: Dict[str, Any],
    session_metadata: Optional[Dict[str, Any]],
    *,
    pack_mode: str = "full",
) -> Dict[str, Any]:
    """Build context for Phase 2 (Confirmation)."""
    context: Dict[str, Any] = {}

    # Original CV summary (from session metadata)
    if pack_mode != "mini" and session_metadata and 'original_cv_data' in session_metadata:
        context['original_cv_summary'] = _summarize_cv(
            session_metadata['original_cv_data']
        )

    # Proposed CV summary (current cv_data)
    context['proposed_cv_summary'] = _summarize_cv(cv_data)

    # Changes diff (if original CV available)
    if session_metadata and 'original_cv_data' in session_metadata:
        context['changes_summary'] = _compute_changes_diff(
            original=session_metadata['original_cv_data'],
            proposed=cv_data
        )

    # Phase 1 analysis summary (from session metadata)
    if pack_mode != "mini" and session_metadata and 'phase1_analysis' in session_metadata:
        context['phase1_analysis_summary'] = session_metadata['phase1_analysis']

    return context


def _build_execution_context(
    cv_data: Dict[str, Any],
    session_metadata: Optional[Dict[str, Any]],
    *,
    pack_mode: str = "full",
) -> Dict[str, Any]:
    """Build context for Phase 3 (Execution)."""
    context: Dict[str, Any] = {}

    # Approved CV data (full structure for generation)
    context['approved_cv_data'] = _extract_cv_structured_compact(cv_data)

    # Hard limits (for self-validation)
    context['hard_limits'] = {
        'work_experience_max': 5,
        'work_bullets_per_entry_max': 4,
        # Soft limits: bullet wrapping is allowed; page-fit is the DoD.
        'work_bullet_chars_soft': 99,
        'work_bullet_chars_hard': 180,
        'education_max': 3,
        'profile_chars_max': 320,
        'languages_max': 5,
        'it_ai_skills_max': 8,
    }

    # Self-validation checklist (pre-computed checks)
    if pack_mode != "mini":
        context['self_validation_checklist'] = _build_validation_checklist(cv_data)

    return context


def _extract_cv_structured_mini(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a smaller CV structure for prompt budgets (outline + top roles)."""
    compact = _extract_cv_structured_compact(cv_data)

    out: Dict[str, Any] = {}
    for k in ("full_name", "email", "phone", "address_lines"):
        if compact.get(k):
            out[k] = compact.get(k)

    profile = compact.get("profile")
    if isinstance(profile, str) and profile.strip():
        out["profile"] = profile.strip()[:320]

    # Work experience: keep at most 3 roles, at most 2 bullets each
    we = compact.get("work_experience")
    if isinstance(we, list) and we:
        trimmed = []
        for role in we[:3]:
            if not isinstance(role, dict):
                continue
            r = {k: role.get(k) for k in ("date_range", "employer", "location", "title") if role.get(k)}
            bullets = role.get("bullets")
            if isinstance(bullets, list) and bullets:
                rb = []
                for b in bullets[:2]:
                    if not isinstance(b, str):
                        continue
                    rb.append(b.strip()[:120])
                if rb:
                    r["bullets"] = rb
            trimmed.append(r)
        if trimmed:
            out["work_experience_outline"] = trimmed

    edu = compact.get("education")
    if isinstance(edu, list) and edu:
        trimmed = []
        for e in edu[:2]:
            if not isinstance(e, dict):
                continue
            r = {k: e.get(k) for k in ("date_range", "institution", "title") if e.get(k)}
            trimmed.append(r)
        if trimmed:
            out["education_outline"] = trimmed

    langs = compact.get("languages")
    if isinstance(langs, list) and langs:
        out["languages"] = [str(x)[:60] for x in langs[:5]]

    skills = compact.get("it_ai_skills")
    if isinstance(skills, list) and skills:
        out["it_ai_skills"] = [str(x)[:80] for x in skills[:8]]

    interests = compact.get("interests")
    if isinstance(interests, str) and interests.strip():
        out["interests"] = interests.strip()[:240]

    return out


def _summarize_docx_prefill(prefill: Any) -> Dict[str, Any]:
    """Summarize a DOCX prefill snapshot to keep prompt budgets small."""
    if not isinstance(prefill, dict):
        return {}
    out: Dict[str, Any] = {}

    for k in ("full_name", "email", "phone", "address_lines"):
        v = prefill.get(k)
        if v:
            out[k] = v

    edu = prefill.get("education")
    if isinstance(edu, list) and edu:
        trimmed = []
        for e in edu[:2]:
            if not isinstance(e, dict):
                continue
            trimmed.append({k: e.get(k) for k in ("date_range", "institution", "title") if e.get(k)})
        if trimmed:
            out["education_outline"] = trimmed

    we = prefill.get("work_experience")
    if isinstance(we, list) and we:
        trimmed = []
        for role in we[:5]:
            if not isinstance(role, dict):
                continue
            r = {k: role.get(k) for k in ("date_range", "employer", "location", "title") if role.get(k)}
            bullets = role.get("bullets")
            if isinstance(bullets, list) and bullets:
                rb = []
                for b in bullets[:2]:
                    if not isinstance(b, str):
                        continue
                    rb.append(b.strip()[:120])
                if rb:
                    r["bullets"] = rb
            trimmed.append(r)
        if trimmed:
            out["work_experience_outline"] = trimmed

    langs = prefill.get("languages")
    if isinstance(langs, list) and langs:
        out["languages"] = [str(x)[:60] for x in langs[:5]]

    skills = prefill.get("it_ai_skills")
    if isinstance(skills, list) and skills:
        out["it_ai_skills"] = [str(x)[:80] for x in skills[:8]]

    return out


def _compute_completeness(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    required_present = {
        "full_name": bool(cv_data.get("full_name", "").strip()) if isinstance(cv_data.get("full_name"), str) else False,
        "email": bool(cv_data.get("email", "").strip()) if isinstance(cv_data.get("email"), str) else False,
        "phone": bool(cv_data.get("phone", "").strip()) if isinstance(cv_data.get("phone"), str) else False,
        "work_experience": bool(cv_data.get("work_experience")) and isinstance(cv_data.get("work_experience"), list),
        "education": bool(cv_data.get("education")) and isinstance(cv_data.get("education"), list),
    }

    work = cv_data.get("work_experience", []) if isinstance(cv_data.get("work_experience"), list) else []
    edu = cv_data.get("education", []) if isinstance(cv_data.get("education"), list) else []
    langs = cv_data.get("languages", []) if isinstance(cv_data.get("languages"), list) else []
    skills = cv_data.get("it_ai_skills", []) if isinstance(cv_data.get("it_ai_skills"), list) else []
    interests = cv_data.get("interests", "")

    counts = {
        "work_experience": len(work),
        "education": len(edu),
        "languages": len(langs),
        "it_ai_skills": len(skills),
    }

    # Determine next missing section in template order
    template_order = [
        ("education", edu),
        ("work_experience", work),
        ("further_experience", cv_data.get("further_experience", []) if isinstance(cv_data.get("further_experience"), list) else []),
        ("languages", langs),
        ("it_ai_skills", skills),
        ("interests", interests if isinstance(interests, str) else ""),
        ("references", cv_data.get("references", "")),
    ]
    next_missing = None
    for name, val in template_order:
        if isinstance(val, list) and len(val) == 0:
            next_missing = name
            break
        if isinstance(val, str) and len(val.strip()) == 0:
            next_missing = name
            break

    return {
        "required_present": required_present,
        "counts": counts,
        "next_missing_section": next_missing,
    }


def _compute_confirmation_state(cv_data: Dict[str, Any], session_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    confirmed_flags = {}
    if isinstance(session_metadata, dict):
        confirmed_flags = session_metadata.get("confirmed_flags") or {}
    contact_confirmed = bool(confirmed_flags.get("contact_confirmed"))
    education_confirmed = bool(confirmed_flags.get("education_confirmed"))
    required_present = _compute_completeness(cv_data).get("required_present", {})
    missing: List[str] = []
    for k, v in required_present.items():
        if not v:
            missing.append(k)
    if not contact_confirmed:
        missing.append("contact_not_confirmed")
    if not education_confirmed:
        missing.append("education_not_confirmed")

    return {
        "confirmed_flags": {
            "contact_confirmed": contact_confirmed,
            "education_confirmed": education_confirmed,
            "confirmed_at": confirmed_flags.get("confirmed_at"),
        },
        "missing": missing,
        "can_generate": all(required_present.values()) and contact_confirmed and education_confirmed,
    }


def _extract_cv_structured_compact(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract compact CV structure (omit empty sections)."""
    keep_keys = [
        'full_name', 'email', 'phone', 'address_lines',
        'profile', 'work_experience', 'education',
        'languages', 'it_ai_skills', 'interests'
    ]

    compact: Dict[str, Any] = {}
    for k in keep_keys:
        v = cv_data.get(k)
        if v is None:
            continue
        # Omit empty lists or empty strings
        if isinstance(v, list) and len(v) == 0:
            continue
        if isinstance(v, str) and v.strip() == '':
            continue
        compact[k] = v

    return compact


def _trim_proposal_history(proposals: List[Dict[str, Any]], max_turns: int = 3) -> List[Dict[str, Any]]:
    """Keep only last N proposals (like OpenAI's keep-last-N-turns pattern)."""
    if len(proposals) <= max_turns:
        return proposals
    return proposals[-max_turns:]


def _summarize_cv(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create compact summary of CV data."""
    work = cv_data.get('work_experience', [])
    edu = cv_data.get('education', [])
    langs = cv_data.get('languages', [])
    skills = cv_data.get('it_ai_skills', [])

    return {
        'full_name': cv_data.get('full_name', ''),
        'work_experience_count': len(work),
        'education_count': len(edu),
        'languages_count': len(langs),
        'it_ai_skills_count': len(skills),
        'work_experience_titles': [w.get('title', '') for w in work[:3]],
        'education_titles': [e.get('title', '') for e in edu[:2]],
    }


def _compute_changes_diff(original: Dict[str, Any], proposed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compute changes between original and proposed CV."""
    changes: List[Dict[str, Any]] = []

    # Compare work experience
    orig_work = original.get('work_experience', [])
    prop_work = proposed.get('work_experience', [])

    if len(orig_work) != len(prop_work):
        changes.append({
            'section': 'work_experience',
            'change_type': 'count_changed',
            'description': f'Work experience entries: {len(orig_work)} → {len(prop_work)}',
            'rationale': 'Adjusted number of positions to fit 2-page constraint or emphasize relevant experience'
        })

    # Compare education
    orig_edu = original.get('education', [])
    prop_edu = proposed.get('education', [])

    if len(orig_edu) != len(prop_edu):
        changes.append({
            'section': 'education',
            'change_type': 'count_changed',
            'description': f'Education entries: {len(orig_edu)} → {len(prop_edu)}',
            'rationale': 'Adjusted to fit space constraints'
        })

    # Compare profile
    orig_profile = original.get('profile', '')
    prop_profile = proposed.get('profile', '')

    if orig_profile != prop_profile:
        changes.append({
            'section': 'profile',
            'change_type': 'modified',
            'description': f'Profile updated ({len(orig_profile)} → {len(prop_profile)} chars)',
            'rationale': 'Tailored profile to match job requirements'
        })

    return changes


def _build_validation_checklist(cv_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build pre-computed self-validation checklist."""
    checklist: List[Dict[str, Any]] = []

    # Check work experience count
    work = cv_data.get('work_experience', [])
    checklist.append({
        'check': 'work_experience_count <= 5',
        'passed': len(work) <= 5,
        'current_value': len(work),
        'action_if_failed': 'Remove oldest or least relevant positions'
    })

    # Check work bullets per entry
    if work:
        max_bullets = max(len(w.get('bullets', [])) for w in work)
        checklist.append({
            'check': 'work_bullets_per_entry <= 4',
            'passed': max_bullets <= 4,
            'current_value': max_bullets,
            'action_if_failed': 'Trim bullets to max 4 per position'
        })

    # Check education count
    edu = cv_data.get('education', [])
    checklist.append({
        'check': 'education_count <= 3',
        'passed': len(edu) <= 3,
        'current_value': len(edu),
        'action_if_failed': 'Remove older or less relevant degrees'
    })

    # Check profile length
    profile = cv_data.get('profile', '')
    checklist.append({
        'check': 'profile_chars <= 320',
        'passed': len(profile) <= 320,
        'current_value': len(profile),
        'action_if_failed': 'Shorten profile to fit limit'
    })

    return checklist


def _apply_size_limits_v2(pack: Dict[str, Any], max_chars: int) -> Dict[str, Any]:
    """Apply size limits to context pack (for V2 structure).

    Strategy: keep the pack useful to the agent but bounded.
    - Prefer dropping low-priority history before dropping CV structure.
    - Never drop required session metadata fields.
    """
    limits = pack.setdefault('limits', {})

    def _size(p: Dict[str, Any]) -> int:
        return len(json.dumps(p, ensure_ascii=False, sort_keys=True))

    truncated_fields: List[str] = []
    size = _size(pack)
    if size <= max_chars:
        return pack

    phase = pack.get("phase")

    # 1) Drop proposal history first (most token-heavy + low priority).
    try:
        if phase == "preparation" and isinstance(pack.get("preparation"), dict):
            prep = pack["preparation"]
            if isinstance(prep.get("proposal_history"), list) and prep["proposal_history"]:
                prep["proposal_history"] = []
                truncated_fields.append("preparation.proposal_history")
    except Exception:
        pass

    size = _size(pack)
    if size <= max_chars:
        limits["final_size"] = size
        limits["max_chars"] = max_chars
        limits["truncated_fields"] = truncated_fields
        return pack

    # 2) Drop job snippet early *only if it is large* (it is also included in the UI capsule separately).
    size = _size(pack)
    try:
        if phase == "preparation" and isinstance(pack.get("preparation"), dict):
            prep = pack["preparation"]
            if isinstance(prep.get("job_analysis"), dict):
                snippet = prep["job_analysis"].get("text_snippet")
                if isinstance(snippet, str) and len(snippet) > 2000:
                    prep["job_analysis"]["text_snippet"] = ""
                    truncated_fields.append("preparation.job_analysis.text_snippet")
    except Exception:
        pass

    size = _size(pack)
    if size <= max_chars:
        limits["final_size"] = size
        limits["max_chars"] = max_chars
        limits["truncated_fields"] = truncated_fields
        return pack

    # 3) Drop recent event ledger before touching CV structure (keep template + core identifiers).
    if size > max_chars and isinstance(pack.get("recent_events"), list) and pack["recent_events"]:
        pack["recent_events"] = []
        truncated_fields.append("recent_events")

    size = _size(pack)
    if size <= max_chars:
        limits["final_size"] = size
        limits["max_chars"] = max_chars
        limits["truncated_fields"] = truncated_fields
        return pack

    # 4) Compact CV structures: trim bullets/details to avoid bloat.
    def _compact_work(work: Any) -> Any:
        if not isinstance(work, list):
            return work
        out: List[Dict[str, Any]] = []
        for j in work:
            if not isinstance(j, dict):
                continue
            bullets = j.get("bullets", [])
            if isinstance(bullets, list):
                bullets = [str(b)[:140] for b in bullets if str(b).strip()]
                bullets = bullets[:2]
            out.append(
                {
                    "date_range": j.get("date_range", ""),
                    "employer": j.get("employer", ""),
                    "location": j.get("location", ""),
                    "title": j.get("title", ""),
                    "bullets": bullets,
                    "bullets_count": len(j.get("bullets", [])) if isinstance(j.get("bullets"), list) else 0,
                }
            )
        return out

    def _compact_edu(edu: Any) -> Any:
        if not isinstance(edu, list):
            return edu
        out: List[Dict[str, Any]] = []
        for e in edu:
            if not isinstance(e, dict):
                continue
            out.append(
                {
                    "date_range": e.get("date_range", ""),
                    "institution": e.get("institution", ""),
                    "title": e.get("title", ""),
                    "details_count": len(e.get("details", [])) if isinstance(e.get("details"), list) else 0,
                }
            )
        return out

    def _apply_compaction(section: Dict[str, Any], prefix: str) -> None:
        if not isinstance(section, dict):
            return
        cv = section.get("cv_data") or section.get("approved_cv_data") or None
        if isinstance(cv, dict):
            if "work_experience" in cv:
                cv["work_experience"] = _compact_work(cv.get("work_experience"))
                truncated_fields.append(f"{prefix}.work_experience(compact)")
            if "education" in cv:
                cv["education"] = _compact_edu(cv.get("education"))
                truncated_fields.append(f"{prefix}.education(compact)")
            if "it_ai_skills" in cv and isinstance(cv.get("it_ai_skills"), list):
                cv["it_ai_skills"] = [str(x)[:70] for x in cv.get("it_ai_skills") if str(x).strip()][:8]
                truncated_fields.append(f"{prefix}.it_ai_skills(compact)")
            if "languages" in cv and isinstance(cv.get("languages"), list):
                cv["languages"] = [str(x)[:60] for x in cv.get("languages") if str(x).strip()][:5]
                truncated_fields.append(f"{prefix}.languages(compact)")
            if "interests" in cv and isinstance(cv.get("interests"), str):
                if len(cv["interests"]) > 320:
                    cv["interests"] = cv["interests"][:320] + "…"
                    truncated_fields.append(f"{prefix}.interests(truncate)")

    try:
        if phase == "preparation" and isinstance(pack.get("preparation"), dict):
            _apply_compaction(pack["preparation"], "preparation")
        if phase == "confirmation" and isinstance(pack.get("confirmation"), dict):
            # Confirmation packs don't include full CV data by default, but keep safe.
            pass
        if phase == "execution" and isinstance(pack.get("execution"), dict):
            _apply_compaction(pack["execution"], "execution")
    except Exception:
        pass

    size = _size(pack)

    # 5) Last-resort shrink: keep only the most recent entries in large lists.
    # This is intentionally conservative (keeps structure useful, but bounded).
    try:
        if size > max_chars and phase == "preparation" and isinstance(pack.get("preparation"), dict):
            prep = pack["preparation"]
            cv = prep.get("cv_data")
            if isinstance(cv, dict):
                we = cv.get("work_experience")
                if isinstance(we, list) and len(we) > 3:
                    cv["work_experience"] = we[:3]
                    truncated_fields.append("preparation.work_experience(truncate)")
                edu = cv.get("education")
                if isinstance(edu, list) and len(edu) > 2:
                    cv["education"] = edu[:2]
                    truncated_fields.append("preparation.education(truncate)")
                skills = cv.get("it_ai_skills")
                if isinstance(skills, list) and len(skills) > 6:
                    cv["it_ai_skills"] = skills[:6]
                    truncated_fields.append("preparation.it_ai_skills(truncate)")
                langs = cv.get("languages")
                if isinstance(langs, list) and len(langs) > 3:
                    cv["languages"] = langs[:3]
                    truncated_fields.append("preparation.languages(truncate)")
    except Exception:
        pass

    size = _size(pack)
    limits["final_size"] = size
    limits["max_chars"] = max_chars
    if truncated_fields:
        limits["truncated_fields"] = truncated_fields
    if size > max_chars:
        limits["note"] = f'Pack size ({size} chars) exceeds limit ({max_chars} chars) after compaction'
    return pack


def format_context_pack_with_delimiters(pack: Dict[str, Any]) -> str:
    """
    Format context pack with explicit delimiters (OpenAI best practice).

    Uses XML-style tags to clearly separate sections, making it easier for
    the model to reason over different components of the context.
    """
    phase = pack.get('phase', 'unknown')
    lines = [
        '<CONTEXT_PACK_V2>',
        f'<schema>{pack.get("schema_version", "cvgen.context_pack.v2")}</schema>',
        f'<phase>{phase}</phase>',
        '',
        '<session_metadata>',
        f'session_id: {pack.get("session_id", "unknown")}',
        f'language: {pack.get("language", "en")}',
        f'cv_fingerprint: {pack.get("cv_fingerprint", "unknown")}',
        '</session_metadata>',
        '',
    ]

    # Add confirmation state and readiness up front (applies to all phases)
    if "confirmation_state" in pack:
        cs = pack["confirmation_state"]
        lines.append("<confirmation_state>")
        lines.append(json.dumps(cs, ensure_ascii=False, indent=2))
        lines.append("</confirmation_state>")
        lines.append("")
    if "readiness" in pack:
        lines.append("<readiness>")
        lines.append(json.dumps(pack["readiness"], ensure_ascii=False, indent=2))
        lines.append("</readiness>")
        lines.append("")

    # Add phase-specific context
    if phase == 'preparation' and 'preparation' in pack:
        prep = pack['preparation']

        # Job analysis section
        if 'job_analysis' in prep:
            lines.append('<job_analysis>')
            job_analysis = prep['job_analysis']
            if 'note' in job_analysis:
                lines.append(f'Note: {job_analysis["note"]}')
            if 'text_snippet' in job_analysis:
                lines.append('')
                lines.append(job_analysis['text_snippet'])
            lines.append('</job_analysis>')
            lines.append('')

        # CV data section
        if 'cv_data' in prep:
            lines.append('<cv_structured>')
            lines.append(json.dumps(prep['cv_data'], ensure_ascii=False, indent=2))
            lines.append('</cv_structured>')
            lines.append('')

        # Unconfirmed DOCX snapshot (reference-only): used to hydrate empty sessions quickly.
        if 'docx_prefill_summary' in prep:
            lines.append('<docx_prefill_summary>')
            lines.append(json.dumps(prep['docx_prefill_summary'], ensure_ascii=False, indent=2))
            lines.append('</docx_prefill_summary>')
        if 'docx_prefill_unconfirmed' in prep:
            lines.append('<docx_prefill_unconfirmed>')
            lines.append(json.dumps(prep['docx_prefill_unconfirmed'], ensure_ascii=False, indent=2))
            lines.append('</docx_prefill_unconfirmed>')
            lines.append('')

        # Proposal history section
        if 'proposal_history' in prep:
            lines.append('<proposal_history>')
            for i, proposal in enumerate(prep['proposal_history'], 1):
                lines.append(f'\nIteration {i}:')
                lines.append(json.dumps(proposal, ensure_ascii=False, indent=2))
            lines.append('</proposal_history>')
            lines.append('')

    elif phase == 'confirmation' and 'confirmation' in pack:
        conf = pack['confirmation']

        lines.append('<confirmation_context>')

        if 'original_cv_summary' in conf:
            lines.append('\n<original_cv>')
            lines.append(json.dumps(conf['original_cv_summary'], ensure_ascii=False, indent=2))
            lines.append('</original_cv>')

        if 'proposed_cv_summary' in conf:
            lines.append('\n<proposed_cv>')
            lines.append(json.dumps(conf['proposed_cv_summary'], ensure_ascii=False, indent=2))
            lines.append('</proposed_cv>')

        if 'changes_summary' in conf:
            lines.append('\n<changes>')
            for change in conf['changes_summary']:
                lines.append(f"- {change['section']}: {change['description']}")
                lines.append(f"  Rationale: {change['rationale']}")
            lines.append('</changes>')

        if 'phase1_analysis_summary' in conf:
            lines.append('\n<phase1_analysis>')
            lines.append(str(conf['phase1_analysis_summary']))
            lines.append('</phase1_analysis>')

        lines.append('</confirmation_context>')
        lines.append('')

    elif phase == 'execution' and 'execution' in pack:
        exe = pack['execution']

        lines.append('<execution_context>')

        if 'approved_cv_data' in exe:
            lines.append('\n<approved_cv>')
            lines.append(json.dumps(exe['approved_cv_data'], ensure_ascii=False, indent=2))
            lines.append('</approved_cv>')

        if 'hard_limits' in exe:
            lines.append('\n<hard_limits>')
            for key, value in exe['hard_limits'].items():
                lines.append(f'{key}: {value}')
            lines.append('</hard_limits>')

        if 'self_validation_checklist' in exe:
            lines.append('\n<validation_checklist>')
            for check in exe['self_validation_checklist']:
                status = '✓' if check['passed'] else '✗'
                lines.append(f'{status} {check["check"]}: {check["current_value"]}')
                if not check['passed']:
                    lines.append(f'  Action: {check["action_if_failed"]}')
            lines.append('</validation_checklist>')

        lines.append('</execution_context>')
        lines.append('')

    lines.append('</CONTEXT_PACK_V2>')

    return '\n'.join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: context_pack.py <cv_json_file>")
        raise SystemExit(2)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        cv = json.load(f)

    p = build_context_pack(cv)
    print(json.dumps(p, ensure_ascii=False, indent=2, sort_keys=True))
