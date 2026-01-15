from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import zipfile
import xml.etree.ElementTree as ET

from docx import Document
from docx.oxml.ns import qn


@dataclass
class TemplateStyles:
    # Page geometry (mm)
    page_width_mm: float
    page_height_mm: float
    margin_top_mm: float
    margin_right_mm: float
    margin_bottom_mm: float
    margin_left_mm: float

    # Header/footer distances (from page edge, mm)
    header_distance_mm: Optional[float]
    footer_distance_mm: Optional[float]

    # Typography
    font_family: str
    body_font_size_pt: float
    title_font_size_pt: float
    name_font_size_pt: float
    title_color_hex: str
    body_color_hex: str

    # Spacing (mm)
    section_gap_mm: float
    bullet_hanging_mm: float

    # Page breaking
    page_break_after_section: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _rgb_to_hex(rgb) -> Optional[str]:
    # Handles python-docx RGBColor and simple hex-like inputs gracefully
    if rgb is None:
        return None
    try:
        # Common case: python-docx RGBColor; try to get hex text
        hex_text = getattr(rgb, "hex", None)
        if hex_text:
            return f"#{hex_text}"
        # Some environments expose it as bytes-like or tuple
        r, g, b = rgb  # may raise if not iterable
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        try:
            s = str(rgb)
            # Fallback: extract 6 hex digits from a repr like RGBColor(0x00,0x00,0x00)
            import re

            m = re.findall(r"0x([0-9A-Fa-f]{2})", s)
            if len(m) == 3:
                return f"#{m[0]}{m[1]}{m[2]}"
        except Exception:
            pass
        return None


def _style_chain_attr(style, attr_name):
    try:
        visited = set()
        s = style
        while s is not None and s not in visited:
            visited.add(s)
            font = getattr(s, "font", None)
            if font is not None:
                val = getattr(font, attr_name, None)
                if val is not None:
                    return val
            s = getattr(s, "based_on", None)
    except Exception:
        pass
    return None


def _doc_defaults(docx_path: Path) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    try:
        z = zipfile.ZipFile(docx_path)
        xml = z.read("word/styles.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        rpr = root.find(".//w:docDefaults/w:rPrDefault/w:rPr", ns)
        if rpr is None:
            return None, None, None

        font_name = None
        size_pt = None
        color_hex = None

        rfonts = rpr.find("w:rFonts", ns)
        if rfonts is not None:
            font_name = (
                rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii")
                or rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hAnsi")
                or rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cs")
            )

        sz_el = rpr.find("w:sz", ns)
        if sz_el is not None:
            val = sz_el.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
            if val:
                size_pt = int(val) / 2.0

        color_el = rpr.find("w:color", ns)
        if color_el is not None:
            val = color_el.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
            if val and val != "auto":
                color_hex = f"#{val.lower()}"

        return font_name, size_pt, color_hex
    except Exception:
        return None, None, None


def _effective_font_props_for_paragraph(
    p, doc, doc_defaults: Tuple[Optional[str], Optional[float], Optional[str]]
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Return (font_name, size_pt, color_hex) using run overrides (including XML rPr),
    then paragraph style (with based_on chain), then Normal style, then docDefaults.
    Size is returned in pt when available.
    """

    def pick(*vals):
        for v in vals:
            if v is not None:
                return v
        return None

    # Try first run that has any explicit formatting (including run XML overrides)
    for run in p.runs:
        if not run.text or not run.text.strip():
            continue
        run_style = getattr(run, "style", None)
        xml_font = None
        xml_size_pt = None
        xml_color = None

        rpr = getattr(run, "_element", None)
        rpr = rpr.rPr if rpr is not None else None
        if rpr is not None:
            rfonts = rpr.find(qn("w:rFonts"))
            if rfonts is not None:
                xml_font = (
                    rfonts.get(qn("w:ascii"))
                    or rfonts.get(qn("w:hAnsi"))
                    or rfonts.get(qn("w:cs"))
                )
            sz_el = rpr.find(qn("w:sz"))
            if sz_el is not None:
                val = sz_el.get(qn("w:val"))
                if val:
                    xml_size_pt = int(val) / 2.0
            color_el = rpr.find(qn("w:color"))
            if color_el is not None:
                val = color_el.get(qn("w:val"))
                if val and val != "auto":
                    xml_color = f"#{val.lower()}"

        name = pick(getattr(run.font, "name", None), xml_font, _style_chain_attr(run_style, "name"))
        size_len = pick(getattr(run.font, "size", None), xml_size_pt, _style_chain_attr(run_style, "size"))
        color_rgb = None
        try:
            color_rgb = pick(getattr(getattr(run.font, "color", None), "rgb", None))
        except Exception:
            color_rgb = None

        if name or size_len or color_rgb or xml_color:
            size_pt = None
            if size_len is not None and hasattr(size_len, "pt"):
                size_pt = float(size_len.pt)
            elif isinstance(size_len, (int, float)):
                size_pt = float(size_len)
            return name, size_pt, _rgb_to_hex(color_rgb) or xml_color

    # Fallback to paragraph style chain
    p_style = getattr(p, "style", None)
    name = _style_chain_attr(p_style, "name")
    size_len = _style_chain_attr(p_style, "size")
    color_rgb = None
    try:
        color_rgb = getattr(getattr(_style_chain_attr(p_style, "color"), "rgb", None), None)
    except Exception:
        color_rgb = None
    if name or size_len or color_rgb:
        size_pt = None
        if size_len is not None and hasattr(size_len, "pt"):
            size_pt = float(size_len.pt)
        elif isinstance(size_len, (int, float)):
            size_pt = float(size_len)
        return name, size_pt, _rgb_to_hex(color_rgb)

    # Fallback to Normal style (with based_on)
    name = size_len = color_rgb = None
    try:
        normal = doc.styles["Normal"]
        name = _style_chain_attr(normal, "name") or getattr(normal.font, "name", None)
        size_len = _style_chain_attr(normal, "size") or getattr(normal.font, "size", None)
        color_rgb = getattr(getattr(normal.font, "color", None), "rgb", None)
    except Exception:
        pass
    if name or size_len or color_rgb:
        size_pt = None
        if size_len is not None and hasattr(size_len, "pt"):
            size_pt = float(size_len.pt)
        elif isinstance(size_len, (int, float)):
            size_pt = float(size_len)
        return name, size_pt, _rgb_to_hex(color_rgb)

    # Last-resort: docDefaults
    return doc_defaults


def extract_styles(docx_path: Path) -> TemplateStyles:
    doc = Document(docx_path)
    sec = doc.sections[0]

    default_font, default_size_pt, default_color_hex = _doc_defaults(docx_path)

    # Page geometry
    page_w = sec.page_width.mm
    page_h = sec.page_height.mm
    m_top = sec.top_margin.mm
    m_right = sec.right_margin.mm
    m_bottom = sec.bottom_margin.mm
    m_left = sec.left_margin.mm

    # Header/footer distances
    header_distance = getattr(sec, "header_distance", None)
    header_distance_mm = header_distance.mm if header_distance is not None else None
    footer_distance = getattr(sec, "footer_distance", None)
    footer_distance_mm = footer_distance.mm if footer_distance is not None else None

    paragraphs = [p for p in doc.paragraphs if p.text.strip()]

    # Detect section title paragraph (e.g., EDUCATION) for title styles
    title_para = next((p for p in paragraphs if p.text.strip().lower() == "education"), None)
    if not title_para:
        raise RuntimeError("Could not locate 'Education' section title in DOCX")

    # Name paragraph assumed first non-empty
    name_para = paragraphs[0]

    # Body paragraph example: first list paragraph after Work experience header
    body_para = None
    work_seen = False
    for p in paragraphs:
        if p.text.strip().lower().startswith("work"):
            work_seen = True
            continue
        if work_seen and p.runs:
            body_para = p
            break
    body_para = body_para or paragraphs[1]

    # Extract effective styles with fallbacks
    defaults = (default_font, default_size_pt, default_color_hex)
    title_name, title_size_pt, title_color_hex = _effective_font_props_for_paragraph(title_para, doc, defaults)
    name_font, name_size_pt, _ = _effective_font_props_for_paragraph(name_para, doc, defaults)
    body_font, body_size_pt, body_color_hex = _effective_font_props_for_paragraph(body_para, doc, defaults)

    # Font family pick: prefer body, fallback to title/name, then docDefaults
    font_family = body_font or title_name or name_font or default_font
    if not font_family:
        raise RuntimeError("Could not extract font family from DOCX (runs/styles/docDefaults)")

    # Color pick: prefer body for body, title for titles, then docDefaults
    body_color_hex = body_color_hex or default_color_hex or "#000000"
    title_color_hex = title_color_hex or default_color_hex or "#0000ff"

    # Font sizes: require at least docDefaults-derived values
    if not body_size_pt:
        body_size_pt = default_size_pt
    if not title_size_pt:
        title_size_pt = default_size_pt
    if not name_size_pt:
        name_size_pt = default_size_pt

    if not body_size_pt or not title_size_pt or not name_size_pt:
        raise RuntimeError("Could not extract one or more font sizes from DOCX (body/title/name)")

    # Vertical rhythm assumptions from template semantics
    section_gap_mm = 6.0
    bullet_hanging_mm = 5.0

    # Page break position in this template is after Work experience
    page_break_after_section = "Work experience"

    return TemplateStyles(
        page_width_mm=page_w,
        page_height_mm=page_h,
        margin_top_mm=m_top,
        margin_right_mm=m_right,
        margin_bottom_mm=m_bottom,
        margin_left_mm=m_left,
        header_distance_mm=header_distance_mm,
        footer_distance_mm=footer_distance_mm,
        font_family=font_family,
        body_font_size_pt=float(body_size_pt),
        title_font_size_pt=float(title_size_pt),
        name_font_size_pt=float(name_size_pt),
        title_color_hex=title_color_hex,
        body_color_hex=body_color_hex,
        section_gap_mm=section_gap_mm,
        bullet_hanging_mm=bullet_hanging_mm,
        page_break_after_section=page_break_after_section,
    )


def extract_styles_dict(docx_path: Path) -> Dict[str, Any]:
    return extract_styles(docx_path).to_dict()
