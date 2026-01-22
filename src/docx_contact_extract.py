from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, List, Tuple


_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
# Loose phone matcher; we validate by digit count after matching.
_PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s\-]?)?(?:\(?\d+\)?[\s\-]?){6,}\d")

_IGNORE_NAME_RE = re.compile(r"(?i)\b(curriculum\s+vitae|resume|résumé|lebenslauf|cv)\b")
# Note: some DOCXs contain an en-dash that becomes U+FFFD (replacement char) during XML decoding on Windows consoles.
_CV_TITLE_LINE_RE = re.compile(
    r"(?i)^\s*(?:curriculum\s+vitae|resume|résumé|lebenslauf|cv)\b.*?[\u2013\u2014\u2212\uFFFD-]\s*(.+?)\s*$"
)

_ADDRESS_LABEL_RE = re.compile(r"(?i)^\s*(adresse|address)\s*:\s*(.+?)\s*$")
_NATIONALITY_LABEL_RE = re.compile(r"(?i)^\s*(nationality|staatsangeh[oö]rigkeit)\s*:\s*(.+?)\s*$")

_NS_W = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass(frozen=True)
class ContactExtract:
    full_name: str = ""
    email: str = ""
    phone: str = ""
    address_lines: Tuple[str, ...] = ()


def _iter_text_parts(root: ET.Element) -> Iterable[str]:
    for t in root.findall(".//w:t", _NS_W):
        if t.text:
            yield t.text


def _iter_paragraph_lines(root: ET.Element) -> Iterable[str]:
    # Join w:t runs within each paragraph.
    for p in root.findall(".//w:p", _NS_W):
        parts = []
        for t in p.findall(".//w:t", _NS_W):
            if t.text:
                parts.append(t.text)
        line = "".join(parts).strip()
        if line:
            yield re.sub(r"\s+", " ", line)


def _iter_doc_parts(z: zipfile.ZipFile) -> Iterable[str]:
    names = set(z.namelist())
    # document + headers/footers (photos/contact often in headers)
    candidates = ["word/document.xml"]
    candidates += sorted([n for n in names if re.fullmatch(r"word/header\d+\.xml", n)])
    candidates += sorted([n for n in names if re.fullmatch(r"word/footer\d+\.xml", n)])
    for name in candidates:
        if name in names:
            yield name


def _docx_lines_from_bytes(docx_bytes: bytes) -> List[str]:
    lines: List[str] = []
    try:
        with zipfile.ZipFile(io := __import__("io").BytesIO(docx_bytes)) as z:
            for part in _iter_doc_parts(z):
                try:
                    root = ET.fromstring(z.read(part))
                except Exception:
                    continue
                for line in _iter_paragraph_lines(root):
                    lines.append(line)
    except Exception:
        return []

    # De-duplicate while preserving order
    seen = set()
    out: List[str] = []
    for l in lines:
        key = l.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _pick_email(lines: List[str]) -> str:
    for l in lines:
        m = _EMAIL_RE.search(l)
        if m:
            return m.group(0)
    return ""


def _pick_phone(lines: List[str]) -> str:
    for l in lines:
        m = _PHONE_RE.search(l)
        if not m:
            continue
        candidate = m.group(0).strip()
        digits = re.sub(r"\D+", "", candidate)
        if len(digits) >= 8:
            return candidate
    return ""


def _looks_like_name(s: str) -> bool:
    if not s:
        return False
    if s.lstrip().startswith(("-", "•", "*")):
        return False
    if "@" in s:
        return False
    if ":" in s:
        return False
    if _IGNORE_NAME_RE.search(s):
        return False
    # Avoid obvious section headers (single word all-caps like "PROFIL")
    if s.strip().isupper() and len(s.strip()) <= 30:
        if len(re.split(r"\s+", s.strip())) == 1:
            return False
    # Avoid address/phone-like lines
    if re.search(r"\d", s) and len(re.sub(r"\D+", "", s)) >= 6:
        return False
    # At least two words with letters
    parts = [p for p in re.split(r"\s+", s.strip()) if p]
    if len(parts) < 2:
        return False
    alpha_words = sum(1 for p in parts if re.search(r"[A-Za-zÀ-ž]", p))
    if alpha_words < 2:
        return False
    # Reasonable length
    return len(s) <= 80


def _pick_full_name(lines: List[str], *, email: str, phone: str) -> str:
    # Common: first line is a title like "LEBENSLAUF – NAME SURNAME"
    if lines:
        m = _CV_TITLE_LINE_RE.match(lines[0])
        if m:
            candidate = m.group(1).strip()
            if _looks_like_name(candidate):
                return candidate.title()

    # Otherwise, try to pick from the "header-ish" part only
    for l in lines[:12]:
        if email and email in l:
            continue
        if phone and phone in l:
            continue
        if _looks_like_name(l):
            # Normalize all-caps names
            candidate = l.strip()
            if candidate.isupper():
                candidate = candidate.title()
            return candidate
    return ""


def _pick_address(lines: List[str], *, name: str, email: str, phone: str) -> Tuple[str, ...]:
    # Prefer explicit labeled address line (common in EU CVs)
    for l in lines[:10]:
        m = _ADDRESS_LABEL_RE.match(l)
        if not m:
            continue
        raw = m.group(2).strip()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            break
        if len(parts) == 1:
            return (parts[0],)
        return (parts[0], parts[1])

    # Fallback: heuristically pick 1-2 lines after name
    if not name:
        return ()
    try:
        idx = lines.index(name)
    except ValueError:
        return ()

    addr: List[str] = []
    for l in lines[idx + 1 : idx + 6]:
        if email and email in l:
            break
        if phone and phone in l:
            break
        if _EMAIL_RE.search(l) or _PHONE_RE.search(l):
            break
        if ":" in l:
            # Skip labeled fields in fallback mode
            continue
        if len(addr) < 2 and l.strip():
            addr.append(l.strip())
        if len(addr) >= 2:
            break
    return tuple(addr)


def extract_contact_from_docx_bytes(docx_bytes: bytes) -> ContactExtract:
    """Best-effort extraction of contact fields from DOCX bytes (no OpenAI call)."""
    lines = _docx_lines_from_bytes(docx_bytes)
    email = _pick_email(lines)
    phone = _pick_phone(lines)
    full_name = _pick_full_name(lines, email=email, phone=phone)
    address_lines = _pick_address(lines, name=full_name, email=email, phone=phone)
    return ContactExtract(full_name=full_name, email=email, phone=phone, address_lines=address_lines)
