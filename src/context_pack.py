from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Literal

from .normalize import normalize_cv_data

# Type alias for phase
PhaseType = Literal['preparation', 'confirmation', 'execution']


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


DEFAULT_MAX_PACK_CHARS = 12000


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
    session_metadata: Optional[Dict[str, Any]] = None,
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

    pack: Dict[str, Any] = {
        'schema_version': 'cvgen.context_pack.v2',
        'phase': phase,
        'language': language,
        'session_id': session_id,
        'cv_fingerprint': fingerprint,
    }

    if phase == 'preparation':
        pack['preparation'] = _build_preparation_context(
            normalized, job_posting_text, session_metadata
        )
    elif phase == 'confirmation':
        pack['confirmation'] = _build_confirmation_context(
            normalized, session_metadata
        )
    elif phase == 'execution':
        pack['execution'] = _build_execution_context(
            normalized, session_metadata
        )

    # Apply size limits
    pack = _apply_size_limits_v2(pack, max_pack_chars)

    return pack


def _build_preparation_context(
    cv_data: Dict[str, Any],
    job_posting_text: Optional[str],
    session_metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build context for Phase 1 (Preparation)."""
    context: Dict[str, Any] = {}

    # Job analysis (if job posting available)
    if job_posting_text:
        # Bound to 6000 chars to fit within budget
        context['job_analysis'] = {
            'text_snippet': job_posting_text[:6000],
            'has_full_text': len(job_posting_text) <= 6000,
            'note': 'Analyze deeply: extract explicit/implicit requirements, must-have vs nice-to-have, ambiguities, culture signals.'
        }

    # CV structured data (for mapping) - compact version
    context['cv_data'] = _extract_cv_structured_compact(cv_data)

    # Proposal history (from session metadata) - keep last 3 only
    if session_metadata and 'proposal_history' in session_metadata:
        proposals = session_metadata['proposal_history']
        context['proposal_history'] = _trim_proposal_history(proposals, max_turns=3)

    return context


def _build_confirmation_context(
    cv_data: Dict[str, Any],
    session_metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build context for Phase 2 (Confirmation)."""
    context: Dict[str, Any] = {}

    # Original CV summary (from session metadata)
    if session_metadata and 'original_cv_data' in session_metadata:
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
    if session_metadata and 'phase1_analysis' in session_metadata:
        context['phase1_analysis_summary'] = session_metadata['phase1_analysis']

    return context


def _build_execution_context(
    cv_data: Dict[str, Any],
    session_metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build context for Phase 3 (Execution)."""
    context: Dict[str, Any] = {}

    # Approved CV data (full structure for generation)
    context['approved_cv_data'] = _extract_cv_structured_compact(cv_data)

    # Hard limits (for self-validation)
    context['hard_limits'] = {
        'work_experience_max': 5,
        'work_bullets_per_entry_max': 4,
        'work_bullet_chars_max': 90,
        'education_max': 3,
        'profile_chars_max': 320,
        'languages_max': 5,
        'it_ai_skills_max': 8,
    }

    # Self-validation checklist (pre-computed checks)
    context['self_validation_checklist'] = _build_validation_checklist(cv_data)

    return context


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
    """Apply size limits to context pack (similar to V1 but for V2 structure)."""
    pack_str = json.dumps(pack, ensure_ascii=False, sort_keys=True)
    size = len(pack_str)

    if size > max_chars:
        # Log warning but don't truncate critical data
        # Phase-specific packs should already be within budget
        pack.setdefault('limits', {})['final_size'] = size
        pack.setdefault('limits', {})['max_chars'] = max_chars
        pack.setdefault('limits', {})['note'] = f'Pack size ({size} chars) exceeds limit ({max_chars} chars)'

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
