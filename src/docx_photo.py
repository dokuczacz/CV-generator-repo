from __future__ import annotations

import base64
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# OpenXML namespaces
_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

_IMAGE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


@dataclass(frozen=True)
class ExtractedImage:
    mime: str
    data: bytes

    def as_data_uri(self) -> str:
        b64 = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime};base64,{b64}"


def _guess_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(ext, "application/octet-stream")


def _iter_part_xml_names(z: zipfile.ZipFile) -> Iterable[str]:
    # CV photos are commonly placed in header parts (header1.xml, etc.), but can also be in document.xml.
    names = set(z.namelist())

    if "word/document.xml" in names:
        yield "word/document.xml"

    for n in sorted(names):
        if re.fullmatch(r"word/header\d+\.xml", n):
            yield n

    for n in sorted(names):
        if re.fullmatch(r"word/footer\d+\.xml", n):
            yield n


def _rels_for_part(part_xml: str) -> str:
    # word/document.xml -> word/_rels/document.xml.rels
    base = posixpath.basename(part_xml)
    return posixpath.join("word", "_rels", f"{base}.rels")


def _extract_first_image_rid(part_xml_bytes: bytes) -> Optional[str]:
    root = ET.fromstring(part_xml_bytes)

    # Images in DOCX drawings use a:blip with r:embed="rIdX".
    for blip in root.findall(".//a:blip", _NS):
        rid = blip.get(f"{{{_NS['r']}}}embed")
        if rid:
            return rid

    return None


def _resolve_rel_target(part_xml: str, rel_target: str) -> str:
    # Relationship targets are typically relative (e.g. media/image1.jpeg or ../media/image1.jpeg)
    # Normalize them into a zip internal path.
    if rel_target.startswith("/"):
        rel_target = rel_target.lstrip("/")

    part_dir = posixpath.dirname(part_xml)  # 'word'
    combined = posixpath.normpath(posixpath.join(part_dir, rel_target))
    return combined


def extract_first_photo_from_docx_bytes(docx_bytes: bytes) -> Optional[ExtractedImage]:
    """Extract the first embedded image from a DOCX (typically the profile photo).

    Strategy:
    - Scan document.xml and header*.xml parts for the first a:blip r:embed relationship id.
    - Resolve that rId via the part's .rels file.
    - Load the image bytes from word/media.

    Returns None if no embedded image is found.
    """

    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        names = set(z.namelist())

        for part_xml in _iter_part_xml_names(z):
            try:
                rid = _extract_first_image_rid(z.read(part_xml))
            except Exception:
                continue
            if not rid:
                continue

            rels_name = _rels_for_part(part_xml)
            if rels_name not in names:
                continue

            try:
                rels_root = ET.fromstring(z.read(rels_name))
            except Exception:
                continue

            for rel in rels_root.findall(".//rel:Relationship", _NS):
                if rel.get("Id") != rid:
                    continue
                if rel.get("Type") != _IMAGE_REL_TYPE:
                    continue
                target = rel.get("Target")
                if not target:
                    continue

                image_path = _resolve_rel_target(part_xml, target)
                if image_path not in names:
                    # Some docs may store targets like "media/image1.jpeg" without "word/" prefix;
                    # try to add word/ as a fallback.
                    alt = posixpath.join("word", target.lstrip("/"))
                    image_path = alt if alt in names else image_path

                if image_path not in names:
                    continue

                data = z.read(image_path)
                return ExtractedImage(mime=_guess_mime(image_path), data=data)

    return None


def extract_first_photo_data_uri_from_docx_bytes(docx_bytes: bytes) -> Optional[str]:
    img = extract_first_photo_from_docx_bytes(docx_bytes)
    return img.as_data_uri() if img else None

