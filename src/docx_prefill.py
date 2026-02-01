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
    def _norm_heading(s: str) -> str:
        if s is None:
            return ""
        t = str(s).replace("\u00a0", " ")
        t = t.strip()
        # Remove common leading list markers (DOCX extraction sometimes keeps them).
        t = re.sub(r"^[\s\-\*•\u2022\u2013\u2014]+", "", t).strip()
        t = t.lower()
        # Tolerate headings like "WEITERBILDUNGEN:", "SKILLS —", etc.
        t = re.sub(r"[\s:;\-\u2013\u2014]+$", "", t).strip()
        t = re.sub(r"\s+", " ", t).strip()
        return t

    variants = {_norm_heading(h) for h in heading_variants if str(h or "").strip()}
    for i, l in enumerate(lines):
        if _norm_heading(l) in variants:
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
    r"^\s*(?P<dates>(?:\d{4}(?:-\d{2})?)(?:\s*[\u2013\u2014\-]\s*(?:\d{4}(?:-\d{2})?|Present|present|today|Today|PRESENT))?)\s*(?P<rest>.+?)\s*$",
    re.IGNORECASE
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

        # Fallback: check if line contains a date pattern anywhere (reversed format: Title...YYYY-MM – Present...)
        date_anywhere = re.search(r"(\d{4}(?:-\d{2})?)(?:\s*[\u2013\u2014\-]\s*(?:\d{4}(?:-\d{2})?|Present|present|today|Today|PRESENT))?", l, re.IGNORECASE)
        if date_anywhere:
            if current is not None:
                items.append(current)
            
            dates = date_anywhere.group(0).strip()
            # Extract title from everything before the date
            before_date = l[:date_anywhere.start()].strip()
            # Clean up title (remove trailing commas, "GitHub:", URLs, etc.)
            title = re.sub(r",?\s*GitHub:.*$", "", before_date, flags=re.IGNORECASE).strip()
            title = re.sub(r",?\s*http[s]?://.*$", "", title).strip()
            title = title.rstrip(",").strip()
            
            current = {
                "date_range": dates,
                "employer": "",
                "location": "",
                "title": title if title else "Role",
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
        
        # Each line is a separate skill (common format in German CVs)
        # Also split on hard list separators if present
        parts = [p.strip() for p in re.split(r"[;•\u2022\n]", l) if p.strip()]
        if not parts:
            # Fallback: treat whole line as one skill
            parts = [l]
        
        for p in parts:
            # Clean leading bullets/dashes
            p = re.sub(r"^[\-\u2013\u2014\*•\u2022]+\s*", "", p).strip()
            p = p[:70].rstrip()
            if p:
                items.append(p)
            if len(items) >= 20:  # Increased limit to capture more skills
                break
        if len(items) >= 20:
            break
    return items[:20]


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
        # Keep more items in prefill so Stage 5a can select the best subset.
        # Canonical CV limits are enforced later by validator + tailoring stages.
        if len(items) >= 10:
            break
    return items[:10]


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
    it_ai_heading_variants = [
        "it & ai skills",
        "it and ai skills",
        "it ai skills",
        "it skills",
        "it-kenntnisse",
        "it kenntnisse",
    ]
    tech_ops_heading_variants = [
        "technical & operational skills",
        "technical and operational skills",
        "technical operational skills",
    ]
    generic_skills_heading_variants = [
        "skills",
        "kenntnisse",
        "fähigkeiten & kompetenzen",
        "faehigkeiten & kompetenzen",
        "fähigkeiten",
        "kompetenzen",
    ]

    idx_it_ai_skills = _find_heading_index(lines, it_ai_heading_variants)
    idx_tech_ops_skills = _find_heading_index(lines, tech_ops_heading_variants)
    idx_skills_generic = _find_heading_index(lines, generic_skills_heading_variants)
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
            "selected technical projects",
            "technical projects",
            "projects",
            "projekty",
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
    for idx in [idx_it_ai_skills, idx_tech_ops_skills, idx_skills_generic, idx_interests, idx_refs]:
        if idx is not None and idx_lang is not None and idx > idx_lang:
            next_after_lang = idx if next_after_lang is None else min(next_after_lang, idx)
    lang_lines = _slice_between(lines, idx_lang, next_after_lang)

    def _next_after(current_idx: Optional[int], candidates: List[Optional[int]]) -> Optional[int]:
        if current_idx is None:
            return None
        best: Optional[int] = None
        for idx in candidates:
            if idx is None:
                continue
            if idx > current_idx:
                best = idx if best is None else min(best, idx)
        return best

    next_after_it_ai = _next_after(
        idx_it_ai_skills,
        [idx_tech_ops_skills, idx_edu, idx_lang, idx_further, idx_interests, idx_refs],
    )
    it_ai_lines = _slice_between(lines, idx_it_ai_skills, next_after_it_ai)

    next_after_tech_ops = _next_after(
        idx_tech_ops_skills,
        [idx_edu, idx_lang, idx_further, idx_interests, idx_refs],
    )
    tech_ops_lines = _slice_between(lines, idx_tech_ops_skills, next_after_tech_ops)

    next_after_skills_generic = _next_after(
        idx_skills_generic,
        [idx_edu, idx_lang, idx_further, idx_interests, idx_refs],
    )
    skills_lines_generic = _slice_between(lines, idx_skills_generic, next_after_skills_generic)

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
    it_ai_skills = _parse_it_ai_skills(it_ai_lines)
    technical_operational_skills = _parse_it_ai_skills(tech_ops_lines)

    # Fallback: many CVs have multiple skills headings; pick up skills from a generic section
    # if the explicit IT/AI or Technical/Operational sections are empty.
    if (not it_ai_skills) or (not technical_operational_skills):
        combined = _parse_it_ai_skills(skills_lines_generic)
        if combined:
            if not it_ai_skills and not technical_operational_skills:
                # Split into two buckets to avoid an entirely empty PDF section.
                it_ai_skills = combined[:8]
                technical_operational_skills = combined[8:16]
            elif not it_ai_skills:
                it_ai_skills = combined[:8]
            elif not technical_operational_skills:
                technical_operational_skills = combined[:8]
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
        "technical_operational_skills": technical_operational_skills,
        "further_experience": further_experience,
        "interests": interests,
    }
