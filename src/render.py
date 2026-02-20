from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "html"
TEMPLATE_NAME = "cv_template_2pages_2025.html"
CSS_NAME = "cv_template_2pages_2025.css"
CL_TEMPLATE_NAME = "cover_letter_template_2025.html"
CL_CSS_NAME = "cover_letter_template_2025.css"


class RenderError(Exception):
    pass


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        # Fallback heuristic (no dependency): count "/Type /Page" markers (exclude "/Pages").
        # This is sufficient for DoD enforcement in CI/dev where PyPDF2 may be absent.
        import re

        try:
            n = len(re.findall(rb"/Type\s*/Page(?!s)\b", pdf_bytes or b""))
            if n > 0:
                return int(n)
        except Exception:
            pass
        raise RenderError(
            "PyPDF2 not installed and page-count heuristic failed. Install with `pip install PyPDF2` to enable strict page-count validation."
        ) from exc

    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)


def count_pdf_pages(pdf_bytes: bytes) -> int:
    """Public helper for counting pages in an already-rendered PDF."""
    return _count_pdf_pages(pdf_bytes)


# Module-level singleton for template environment (optimization: pre-compile templates)
_jinja_env = None

def _load_env() -> Environment:
    """Load Jinja2 environment with template caching enabled"""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
            cache_size=400,  # Enable bytecode caching
        )
        # Pre-compile the CV template on first load
        _jinja_env.get_template(TEMPLATE_NAME)
        try:
            _jinja_env.get_template(CL_TEMPLATE_NAME)
        except Exception:
            # Keep CV rendering working in older checkouts where the CL template isn't present.
            pass
    return _jinja_env


def render_html(cv: Dict[str, Any], inline_css: bool = True) -> str:
    # Normalize GPT/backend payload differences (e.g. interests list -> string)
    try:
        from src.normalize import normalize_cv_data  # type: ignore
    except Exception:
        from normalize import normalize_cv_data  # type: ignore

    cv = normalize_cv_data(cv)    
    # Ensure critical fields exist with fallbacks
    cv.setdefault('full_name', 'CV')
    cv.setdefault('email', '')
    cv.setdefault('phone', '')
    cv.setdefault('address_lines', [])
    cv.setdefault('profile', '')
    cv.setdefault('work_experience', [])
    cv.setdefault('education', [])
    cv.setdefault('languages', [])
    cv.setdefault('interests', '')
    cv.setdefault('further_experience', [])
    env = _load_env()
    template = env.get_template(TEMPLATE_NAME)
    css = ""
    if inline_css:
        css_path = TEMPLATES_DIR / CSS_NAME
        css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    docx_path = Path(__file__).resolve().parents[1] / "wzory" / "CV_template_2pages_2025.docx"
    if docx_path.exists():
        # Extract styles from the DOCX template.
        # Import lazily so environments without `lxml` can still render using defaults.
        # Support both `python src/render.py` and imports like `from src.render import ...`.
        try:
            from src.style_extractor import extract_styles_dict  # type: ignore
        except Exception:
            from style_extractor import extract_styles_dict  # type: ignore
        styles = extract_styles_dict(docx_path)
    else:
        # Keep tests/dev working even if the DOCX is not available in the repo.
        # Values mirror the defaults in templates/html/cv_template_2pages_2025.css.
        styles = {
            "page_width_mm": 210.0,
            "page_height_mm": 297.0,
            "margin_top_mm": 20.0,
            "margin_right_mm": 22.4,
            "margin_bottom_mm": 20.0,
            "margin_left_mm": 25.0,
            "header_distance_mm": None,
            "footer_distance_mm": None,
            "font_family": "Arial",
            "body_font_size_pt": 11.0,
            "title_font_size_pt": 11.0,
            "name_font_size_pt": 16.0,
            "title_color_hex": "#0000ff",
            "body_color_hex": "#000000",
            "section_gap_mm": 6.0,
            "bullet_hanging_mm": 5.0,
            "page_break_after_section": "Work experience",
        }

    context = dict(cv)
    if inline_css:
        context["_inline_css"] = css
    context["_styles"] = styles
    return template.render(**context)


def render_cover_letter_html(payload: Dict[str, Any], inline_css: bool = True) -> str:
    """Render cover letter HTML from a backend-derived payload."""
    env = _load_env()
    template = env.get_template(CL_TEMPLATE_NAME)
    css = ""
    if inline_css:
        css_path = TEMPLATES_DIR / CL_CSS_NAME
        css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    # Reuse style tokens from the CV extractor for visual consistency.
    docx_path = Path(__file__).resolve().parents[1] / "wzory" / "CV_template_2pages_2025.docx"
    if docx_path.exists():
        try:
            from src.style_extractor import extract_styles_dict  # type: ignore
        except Exception:
            from style_extractor import extract_styles_dict  # type: ignore
        styles = extract_styles_dict(docx_path)
    else:
        styles = {
            "page_width_mm": 210.0,
            "page_height_mm": 297.0,
            "margin_top_mm": 20.0,
            "margin_right_mm": 22.4,
            "margin_bottom_mm": 20.0,
            "margin_left_mm": 25.0,
            "font_family": "Arial",
            "body_font_size_pt": 11.0,
            "name_font_size_pt": 16.0,
            "title_color_hex": "#0000ff",
            "body_color_hex": "#000000",
            "section_gap_mm": 6.0,
        }

    context = dict(payload or {})
    if inline_css:
        context["_inline_css"] = css
    context["_styles"] = styles
    return template.render(**context)


def render_cover_letter_pdf(
    payload: Dict[str, Any], *, enforce_one_page: bool = True, use_cache: bool = True
) -> bytes:
    if use_cache:
        cache_key = _cv_cache_key({"cover_letter": payload})
        cl_json = json.dumps(payload, sort_keys=True)
        pdf = _render_cover_letter_pdf_cached(cache_key, cl_json)
    else:
        html = render_cover_letter_html(payload, inline_css=True)
        pdf = _render_pdf_weasyprint(html, cv_data=None)

    if enforce_one_page:
        pages = count_pdf_pages(pdf)
        if pages != 1:
            raise RenderError(f"DoD violation: pages != 1 (got {pages}).")
    return pdf


@lru_cache(maxsize=16)
def _render_cover_letter_pdf_cached(cache_key: str, payload_json: str) -> bytes:
    """Cached CL rendering (same cache infra as CV, but distinct renderer)."""
    _ = cache_key  # stable key; payload_json is used for correctness
    data = json.loads(payload_json)
    html = render_cover_letter_html(data, inline_css=True)
    return _render_pdf_weasyprint(html, cv_data=None)


# Module-level singleton for WeasyPrint font configuration (optimization: cache fonts)
_font_config = None

def _get_font_config():
    """Get cached font configuration for WeasyPrint"""
    global _font_config
    if _font_config is None:
        try:
            from weasyprint.text.fonts import FontConfiguration
            _font_config = FontConfiguration()
        except ImportError:
            # Older WeasyPrint versions don't have FontConfiguration
            _font_config = None
    return _font_config

def _render_pdf_weasyprint(html: str, cv_data: Dict[str, Any] = None) -> bytes:
    """Render PDF using WeasyPrint (pure Python, no browser needed)

    Args:
        html: HTML string to render
        cv_data: Optional CV data for metadata (Author, Title)
    """
    try:
        from weasyprint import HTML

        # Use cached font configuration for faster rendering
        font_config = _get_font_config()

        # Render HTML to document
        if font_config:
            doc = HTML(string=html).render(font_config=font_config)
        else:
            doc = HTML(string=html).render()

        # Build PDF metadata
        metadata = {}
        if cv_data:
            full_name = cv_data.get('full_name', '').strip()
            if full_name:
                metadata['author'] = full_name
                metadata['title'] = f'CV - {full_name}'
                metadata['subject'] = 'Curriculum Vitae'

        # Always set creator/producer
        metadata['creator'] = 'CV Generator'
        metadata['producer'] = 'WeasyPrint'

        # Write PDF with metadata
        return doc.write_pdf(
            pdf_version='1.7',  # Widest compatibility
            pdf_forms=False,    # Not needed for CVs
            uncompressed_pdf=False,  # Keep compressed for smaller file size
            custom_metadata=metadata if metadata else None
        )
    except Exception as exc:
        # WeasyPrint on Windows often requires external native deps (GTK/Pango).
        # IMPORTANT: Do NOT silently switch renderers in production.
        # Production runs on Linux (WeasyPrint preferred). Local Windows dev defaults to Playwright.
        renderer = os.getenv("CV_PDF_RENDERER", "").strip().lower()
        allow_playwright = renderer == "playwright" or os.getenv("CV_ALLOW_PLAYWRIGHT_FALLBACK", "").strip() in {
            "1",
            "true",
            "yes",
        }
        if os.name == "nt" and (allow_playwright or not renderer):
            return _render_pdf_playwright(html)
        raise RenderError(
            "WeasyPrint failed to render PDF. Install WeasyPrint native dependencies, or set CV_PDF_RENDERER=playwright for local Windows testing."
        ) from exc


def _render_pdf_playwright(html: str) -> bytes:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "print_pdf_playwright.mjs"
    if not script_path.exists():
        raise RenderError(f"Missing Playwright PDF helper script at {script_path}")

    repo_root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="cvgen-") as tmp:
        tmp_dir = Path(tmp)
        html_path = tmp_dir / "input.html"
        pdf_path = tmp_dir / "output.pdf"
        html_path.write_text(html, encoding="utf-8")

        try:
            subprocess.run(
                [
                    "node",
                    str(script_path),
                    str(html_path),
                    str(pdf_path),
                ],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RenderError(
                "Node.js not found on PATH. Install Node.js to enable Playwright PDF fallback on Windows."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RenderError(
                "Playwright PDF rendering failed. Ensure Playwright browsers are installed (try `npx playwright install chromium`)."
                + (f"\n\nDetails:\n{stderr}" if stderr else "")
            ) from exc

        if not pdf_path.exists():
            raise RenderError("Playwright PDF rendering did not produce an output PDF")

        return pdf_path.read_bytes()


def _cv_cache_key(cv: Dict[str, Any]) -> str:
    """
    Generate stable cache key for CV data.

    Creates a SHA256 hash of the normalized CV data for use as cache key.
    Excludes volatile fields that don't affect rendering (like timestamps).
    """
    # Create a copy and remove volatile/metadata fields that don't affect rendering
    cache_data = dict(cv)

    # Remove metadata fields that don't affect PDF output
    for key in ['_metadata', '_timestamp', '_session_id']:
        cache_data.pop(key, None)

    # Normalize to JSON for stable hashing
    normalized = json.dumps(cache_data, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


@lru_cache(maxsize=32)
def _render_pdf_cached(cache_key: str, cv_json: str, enforce_two_pages: bool) -> bytes:
    """
    Cached PDF rendering using LRU cache.

    Args:
        cache_key: SHA256 hash of CV data (for cache invalidation)
        cv_json: JSON-serialized CV data
        enforce_two_pages: Whether to enforce 2-page constraint

    Returns:
        Rendered PDF bytes

    Note: This is a separate function to enable @lru_cache decorator.
    """
    cv_data = json.loads(cv_json)
    html = render_html(cv_data, inline_css=True)
    return _render_pdf_weasyprint(html, cv_data=cv_data)


def render_pdf(cv: Dict[str, Any], *, enforce_two_pages: bool = True, use_cache: bool = True) -> bytes:
    """
    Generate PDF from CV data using WeasyPrint.

    Args:
        cv: CV data dictionary
        enforce_two_pages: Whether to enforce 2-page DoD constraint
        use_cache: Whether to use render caching (default: True)

    Returns:
        PDF bytes

    Note: Caching provides ~40-60% speedup for repeated renders with same CV data.
    Particularly useful for validate → generate workflows in session-based processing.
    """
    if use_cache:
        # Use cached rendering
        cache_key = _cv_cache_key(cv)
        cv_json = json.dumps(cv, sort_keys=True)
        pdf = _render_pdf_cached(cache_key, cv_json, enforce_two_pages)
    else:
        # Direct rendering (no cache)
        html = render_html(cv, inline_css=True)
        pdf = _render_pdf_weasyprint(html, cv_data=cv)

    if enforce_two_pages:
        # DoD: PDF must have exactly 2 pages
        pages = count_pdf_pages(pdf)
        if pages != 2:
            raise RenderError(f"DoD violation: pages != 2 (got {pages}).")

    # Sanity check: PDF should have meaningful content
    # Minimum expected size: ~40KB for empty template, ~100KB+ for filled template
    pdf_size = len(pdf)
    work_exp_count = len(cv.get('work_experience', []))
    education_count = len(cv.get('education', []))
    full_name = cv.get('full_name', '').strip()

    if pdf_size < 30000:  # Less than 30KB suggests minimal content
        # This could be a photo-only PDF or mostly empty template
        if not full_name or (work_exp_count == 0 and education_count == 0):
            import logging
            logging.warning(
                f"Template rendered with minimal content: PDF size={pdf_size} bytes, "
                f"full_name={bool(full_name)}, work_experience={work_exp_count}, education={education_count}. "
                f"This may indicate incomplete cv_data input."
            )

    return pdf

if __name__ == "__main__":
    import json

    root = Path(__file__).resolve().parents[1]
    sample_path = root / "samples" / "minimal_cv.json"
    if not sample_path.exists():
        raise SystemExit(
            f"Missing sample input: {sample_path}. Run tests/generate_test_artifacts.py or add the sample file."
        )

    cv = json.loads(sample_path.read_text(encoding="utf-8"))
    html = render_html(cv, inline_css=True)
    (root / "preview.html").write_text(html, encoding="utf-8")

    pdf = render_pdf(cv)
    (root / "preview.pdf").write_bytes(pdf)
    print(f"Wrote: {root / 'preview.html'}")
    print(f"Wrote: {root / 'preview.pdf'}")
