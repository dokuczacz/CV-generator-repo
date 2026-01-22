from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .docx_contact_extract import extract_contact_from_docx_bytes
from .docx_contact_extract import _docx_lines_from_bytes as _lines_from_docx  # local helper


def _dejank(text: str) -> str:
    # Insert spaces where DOCX text extraction often collapses runs.
    # CRITICAL: Do NOT insert spaces before diacritics (ü, ö, ä, ń, etc.)
    # as DOCX extraction sometimes splits "Ausführung" -> "Ausf" + "ührung"
    s = text
    s = re.sub(r"(?<=\d)(?=[A-Za-zÀ-ž])", " ", s)
    s = re.sub(r"(?<=[A-Za-zÀ-ž])(?=\d)", " ", s)
    # DO NOT add space between lowercase and uppercase if uppercase is a diacritic continuation
    # Remove this pattern entirely to prevent "Ausf ührung", "Pozna ń" issues:
    # s = re.sub(r"(?<=[a-zà-ž])(?=[A-ZÀ-Ž])", " ", s)
    # Instead, only insert space for clear CamelCase (ASCII A-Z after lowercase a-z):
    s = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", s)  # e.g., "wordWord" -> "word Word"
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _find_heading_index(lines: List[str], heading_variants: List[str]) -> Optional[int]:
    variants = {h.strip().lower() for h in heading_variants}
    for i, l in enumerate(lines):
        if l.strip().lower() in variants:
            return i
    return None


def _slice_between(lines: List[str], start_idx: Optional[int], end_idx: Optional[int]) -> List[str]:
    if start_idx is None:
        return []
    start = start_idx + 1
    end = end_idx if end_idx is not None else len(lines)
    if start < 0 or start >= len(lines) or end <= start:
        return []
    return lines[start:end]


def _parse_profile(lines: List[str]) -> str:
    # Join up to ~2 lines into a single paragraph.
    if not lines:
        return ""
    parts: List[str] = []
    for l in lines[:2]:
        l = _dejank(l)
        if l:
            parts.append(l)
    return " ".join(parts).strip()


_DATE_PREFIX_RE = re.compile(
    r"^\s*(?P<dates>(?:\d{4}(?:-\d{2})?)(?:\s*[\u2013\u2014\-]\s*(?:\d{4}(?:-\d{2})?|Present|today))?)\s*(?P<rest>.+?)\s*$"
)


def _split_rest_title_employer(rest: str) -> Tuple[str, str]:
    # Common pattern: "Title – Employer, Location"
    parts = [p.strip() for p in re.split(r"\s*[\u2013\u2014\-]\s*", rest, maxsplit=2) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return rest.strip(), ""


def _parse_employer_location(employer_part: str) -> Tuple[str, str]:
    if not employer_part:
        return "", ""
    # "Imbodden AG, Visp, Schweiz" -> employer="Imbodden AG", location="Visp, Schweiz"
    chunks = [c.strip() for c in employer_part.split(",") if c.strip()]
    if not chunks:
        return employer_part.strip(), ""
    if len(chunks) == 1:
        return chunks[0], ""
    return chunks[0], ", ".join(chunks[1:])


def _parse_work_experience(lines: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw in lines:
        l = raw.strip()
        if not l:
            continue

        if l.lstrip().startswith(("-", "•", "*")):
            bullet = _dejank(l.lstrip("-•* ").strip())
            if current is not None and bullet:
                current.setdefault("bullets", []).append(bullet)
            continue

        m = _DATE_PREFIX_RE.match(l)
        if not m:
            # Some DOCX extractions glue dates and titles: "2025-05Bauarbeiter …"
            glued = re.sub(r"^(\d{4}(?:-\d{2})?)(?=[A-Za-zÀ-ž])", r"\1 ", l)
            m = _DATE_PREFIX_RE.match(glued)

        if m:
            if current is not None:
                items.append(current)

            dates = m.group("dates").strip()
            rest = _dejank(m.group("rest").strip())
            title_part, employer_part = _split_rest_title_employer(rest)
            employer, location = _parse_employer_location(employer_part)
            current = {
                "date_range": dates,
                "employer": employer,
                "location": location,
                "title": title_part,
                "bullets": [],
            }
            continue

        # Continuation line
        if current is not None:
            cont = _dejank(l)
            if cont:
                current.setdefault("bullets", []).append(cont)

    if current is not None:
        items.append(current)
    return items


_EDU_DATE_RE = re.compile(r"^\s*(?P<dates>\d{4}(?:\s*[\u2013\u2014\-]\s*\d{4})?)\s*(?P<rest>.+?)\s*$")
_DEGREE_MARKERS = re.compile(r"(?i)\b(master|bachelor|msc|bsc|phd|doktor|diplom)\b")


def _parse_education(lines: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw in lines:
        l = raw.strip()
        if not l:
            continue

        m = _EDU_DATE_RE.match(l)
        if not m:
            glued = re.sub(r"^(\d{4}(?:[\u2013\u2014\-]\d{4})?)(?=[A-Za-zÀ-ž])", r"\1 ", l)
            m = _EDU_DATE_RE.match(glued)

        if m:
            if current is not None:
                items.append(current)

            dates = m.group("dates").strip()
            rest = _dejank(m.group("rest").strip())

            institution = rest
            title = ""
            dm = _DEGREE_MARKERS.search(rest)
            if dm:
                institution = rest[: dm.start()].strip(" ,;-")
                title = rest[dm.start() :].strip()

            # Keep institution non-empty for template (avoid ", title")
            if not institution:
                institution = rest.split(" ", 1)[0] if rest else ""

            current = {
                "date_range": dates,
                "institution": institution,
                "title": title,
                "details": [],
            }
            
            # Move specialization/major indicators from title to details
            # Common patterns: "Schwerpunkt:", "Specialization:", "Major:", "Focus:", "Concentration:"
            if title:
                split_pattern = r"\s+(Schwerpunkt|Specialization|Major|Focus|Concentration|Fachrichtung|Vertiefung):\s*"
                parts = re.split(split_pattern, title, maxsplit=1, flags=re.IGNORECASE)
                if len(parts) >= 3:  # [degree_part, marker, specialization_part]
                    # Keep only the degree in title (bold)
                    current["title"] = parts[0].strip()
                    # Move specialization to details (regular weight)
                    specialization_text = f"{parts[1]}: {parts[2]}" if parts[2] else ""
                    if specialization_text:
                        current["details"].append(specialization_text)
            
            continue

        if current is not None:
            detail = _dejank(l.lstrip("-•* ").strip())
            if detail:
                current.setdefault("details", []).append(detail)

    if current is not None:
        items.append(current)
    return items


def _parse_languages(lines: List[str]) -> List[str]:
    out: List[str] = []
    for raw in lines:
        l = _dejank(raw).strip()
        if not l:
            continue
        # Skip obvious section headers that might have leaked into the slice.
        if l.isupper() and len(l) <= 30:
            continue

        # Typical: "English (fluent)"
        m = re.match(r"^\s*(.+?)\s*(\(.+?\))\s*$", l)
        if m:
            name = m.group(1).strip()
            level = m.group(2).strip()
            if name:
                out.append(f"{name} {level}".strip())
                if len(out) >= 5:
                    break
            continue

        # Common: "English - fluent", "English: fluent", "English – fluent"
        m = re.match(r"^\s*(.+?)\s*[:\-\u2013\u2014]\s*(.+?)\s*$", l)
        if m:
            name = m.group(1).strip()
            level = m.group(2).strip()
            if name and level:
                out.append(f"{name} ({level})")
                if len(out) >= 5:
                    break
                continue

        # Common: "English fluent" (best-effort; keep 1-word name + rest as level)
        parts = [p for p in l.split(" ") if p]
        if len(parts) >= 2 and len(parts[0]) <= 20 and len(parts[1:]) <= 6:
            out.append(f"{parts[0]} ({' '.join(parts[1:])})")
        else:
            # Fallback: treat full line as name
            out.append(l)

        if len(out) >= 5:
            break

    # Enforce validator constraints (max 5 items, max ~50 chars per item)
    return [s[:50].rstrip() for s in out[:5]]


def _parse_it_ai_skills(lines: List[str]) -> List[str]:
    items: List[str] = []
    for raw in lines:
        l = _dejank(raw).strip()
        if not l:
            continue
        if l.isupper() and len(l) <= 30:
            continue
        # Split only on hard list separators; avoid commas because they commonly appear inside parentheses.
        parts = [p.strip() for p in re.split(r"[;•\u2022]", l) if p.strip()]
        if not parts:
            continue
        for p in parts:
            p = p[:70].rstrip()
            if p:
                items.append(p)
            if len(items) >= 8:
                break
        if len(items) >= 8:
            break
    return items[:8]


_FURTHER_DATE_RE = re.compile(
    r"^\s*(?P<dates>(?:\d{2}/\d{4}|\d{4}(?:-\d{2})?)(?:\s*[\u2013\u2014\-]\s*(?:\d{2}/\d{4}|\d{4}(?:-\d{2})?|Present|today))?)\s*(?P<rest>.+?)\s*$"
)


def _parse_further_experience(lines: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in lines:
        l = raw.strip()
        if not l:
            continue
        m = _FURTHER_DATE_RE.match(l)
        if not m:
            glued = re.sub(r"^(\d{2}/\d{4}|\d{4}(?:-\d{2})?)(?=[A-Za-zÀ-ž])", r"\1 ", l)
            m = _FURTHER_DATE_RE.match(glued)
        if not m:
            continue
        dates = m.group("dates").strip()[:25]
        rest = _dejank(m.group("rest").strip())
        title_part, org_part = _split_rest_title_employer(rest)
        organization, _location = _parse_employer_location(org_part)
        items.append(
            {
                "date_range": dates,
                "organization": organization[:70].rstrip(),
                "title": title_part[:90].rstrip(),
                "bullets": [],
            }
        )
        if len(items) >= 4:
            break
    return items[:4]


def _parse_interests(lines: List[str]) -> str:
    if not lines:
        return ""
    parts: List[str] = []
    for raw in lines[:4]:
        l = _dejank(raw).strip(" -•*").strip()
        if l:
            parts.append(l)
    s = ", ".join(parts).strip()
    return s[:350].rstrip()


def prefill_cv_from_docx_bytes(docx_bytes: bytes) -> Dict[str, Any]:
    """Prefill CV fields deterministically from DOCX bytes (no OpenAI call).

    Focus: contact + profile + work_experience + education (enough to avoid 'missing required fields').
    """
    lines = _lines_from_docx(docx_bytes)
    contact = extract_contact_from_docx_bytes(docx_bytes)

    idx_profile = _find_heading_index(lines, ["profil", "profile", "summary"])
    idx_work = _find_heading_index(lines, ["berufserfahrung", "work experience", "experience"])
    idx_edu = _find_heading_index(lines, ["ausbildung", "education"])
    idx_lang = _find_heading_index(lines, ["sprachen", "languages"])
    idx_skills = _find_heading_index(
        lines,
        [
            "it & ai skills",
            "it skills",
            "skills",
            "kenntnisse",
            "fähigkeiten & kompetenzen",
            "faehigkeiten & kompetenzen",
            "fähigkeiten",
            "kompetenzen",
            "it-kenntnisse",
            "it kenntnisse",
        ],
    )
    idx_further = _find_heading_index(
        lines,
        [
            "weiterbildungen",
            "weiterbildung",
            "courses",
            "trainings",
            "training",
            "certifications",
            "certificates",
            "further experience",
            "additional experience",
            "commitment",
        ],
    )
    idx_interests = _find_heading_index(lines, ["interessen", "interests"])
    idx_refs = _find_heading_index(lines, ["referenzen", "references"])

    profile_lines = _slice_between(lines, idx_profile, idx_work or idx_edu)
    work_lines = _slice_between(lines, idx_work, idx_edu)
    edu_lines = _slice_between(lines, idx_edu, idx_lang)

    # Languages slice ends at the next known heading after languages
    next_after_lang = None
    for idx in [idx_skills, idx_interests, idx_refs]:
        if idx is not None and idx_lang is not None and idx > idx_lang:
            next_after_lang = idx if next_after_lang is None else min(next_after_lang, idx)
    lang_lines = _slice_between(lines, idx_lang, next_after_lang)

    # Skills slice ends at next known heading after skills
    next_after_skills = None
    for idx in [idx_further, idx_interests, idx_refs]:
        if idx is not None and idx_skills is not None and idx > idx_skills:
            next_after_skills = idx if next_after_skills is None else min(next_after_skills, idx)
    skills_lines = _slice_between(lines, idx_skills, next_after_skills)

    # Further experience / training slice ends at next known heading after it.
    next_after_further = None
    for idx in [idx_interests, idx_refs]:
        if idx is not None and idx_further is not None and idx > idx_further:
            next_after_further = idx if next_after_further is None else min(next_after_further, idx)
    further_lines = _slice_between(lines, idx_further, next_after_further)

    # Interests slice ends at references (if any)
    interests_lines = _slice_between(lines, idx_interests, idx_refs)

    profile = _parse_profile(profile_lines)
    work_experience = _parse_work_experience(work_lines)
    education = _parse_education(edu_lines)
    languages = _parse_languages(lang_lines)
    it_ai_skills = _parse_it_ai_skills(skills_lines)
    further_experience = _parse_further_experience(further_lines)
    interests = _parse_interests(interests_lines)

    return {
        "full_name": contact.full_name or "",
        "email": contact.email or "",
        "phone": contact.phone or "",
        "address_lines": list(contact.address_lines) if contact.address_lines else [],
        "profile": profile,
        "work_experience": work_experience,
        "education": education,
        "languages": languages,
        "it_ai_skills": it_ai_skills,
        "further_experience": further_experience,
        "interests": interests,
    }
