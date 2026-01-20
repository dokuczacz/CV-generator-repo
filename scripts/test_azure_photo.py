from __future__ import annotations

import base64
import json
import re
import sys
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = ROOT / "samples" / "max_valid_cv_payload.json"
OUT_PDF_PATH = ROOT / "cv_azure_with_photo.pdf"
OUT_IMG_DIR = ROOT / "extracted_images_from_pdf"

AZURE_BASE_URL = "https://cv-generator-6695.azurewebsites.net/api"
ENDPOINT = f"{AZURE_BASE_URL}/generate-cv-action"


def _png_data_uri(width: int = 240, height: int = 300) -> str:
    """Generate a simple RGB PNG (no external deps) and return as data URI."""
    import struct
    import zlib

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type)
        crc = zlib.crc32(data, crc)
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc & 0xFFFFFFFF)

    # Create a solid-ish color with a tiny diagonal variation so we can visually confirm.
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0
        for x in range(width):
            r = 20 + (x * 180) // max(1, (width - 1))
            g = 40 + (y * 160) // max(1, (height - 1))
            b = 120
            raw.extend([r & 0xFF, g & 0xFF, b & 0xFF])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, truecolor
    idat = zlib.compress(bytes(raw), level=9)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _load_function_key() -> str:
    """Extract x-functions-key from INTEGRATION_GUIDE.md without printing it."""
    guide = ROOT / "INTEGRATION_GUIDE.md"
    if not guide.exists():
        raise RuntimeError("Missing INTEGRATION_GUIDE.md (expected to contain x-functions-key example)")

    text = guide.read_text(encoding="utf-8", errors="ignore")

    # Example line:
    # Header: x-functions-key: cPAXdShMyz...
    m = re.search(r"x-functions-key\s*:\s*([A-Za-z0-9_\-]+=*)", text)
    if not m:
        raise RuntimeError("Could not find x-functions-key in INTEGRATION_GUIDE.md")

    return m.group(1)


def _post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")

    key = _load_function_key()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-functions-key": key,
            "User-Agent": "cv-generator-repo/test_azure_photo.py",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            resp_body = resp.read()
    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from Azure endpoint. Body: {details[:2000]}")

    return json.loads(resp_body.decode("utf-8"))


def main() -> int:
    if not PAYLOAD_PATH.exists():
        print(f"Missing payload: {PAYLOAD_PATH}", file=sys.stderr)
        return 2

    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    payload.setdefault("cv_data", {})

    # Embed photo directly in CV data so the HTML template can render it.
    payload["cv_data"]["photo_url"] = _png_data_uri()

    print(f"Calling Azure: {ENDPOINT}")
    resp = _post_json(ENDPOINT, payload)

    if not resp.get("success"):
        raise RuntimeError(f"Azure response not successful: {resp}")

    pdf_b64 = resp.get("pdf_base64")
    if not pdf_b64:
        raise RuntimeError("Azure response missing pdf_base64")

    pdf_bytes = base64.b64decode(pdf_b64)
    OUT_PDF_PATH.write_bytes(pdf_bytes)
    print(f"Saved PDF: {OUT_PDF_PATH}")

    # Extract images
    OUT_IMG_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(OUT_PDF_PATH)

    extracted = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        images = page.get_images(full=True)
        for img_index, img in enumerate(images):
            xref = img[0]
            info = doc.extract_image(xref)
            ext = info.get("ext", "bin")
            img_bytes = info.get("image", b"")

            out_path = OUT_IMG_DIR / f"page_{page_index+1:02d}_img_{img_index+1:02d}.{ext}"
            out_path.write_bytes(img_bytes)
            extracted.append(out_path)

    print(f"Pages: {doc.page_count}")
    print(f"Extracted images: {len(extracted)}")
    if extracted:
        print(f"First image: {extracted[0]}")
    else:
        print("No images found in PDF (photo may be vectorized or not embedded).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
