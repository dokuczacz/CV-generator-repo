from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "html"
TEMPLATE_NAME = "cv_template_2pages_2025.html"
CSS_NAME = "cv_template_2pages_2025.css"


class RenderError(Exception):
    pass


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        raise RenderError(
            "PyPDF2 not installed. Install with `pip install PyPDF2` to enable DoD page-count validation."
        ) from exc

    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)


def _load_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


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


def _render_pdf_weasyprint(html: str) -> bytes:
    """Render PDF using WeasyPrint (pure Python, no browser needed)"""
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except Exception as exc:
        # WeasyPrint on Windows often requires external native deps (GTK/Pango).
        # IMPORTANT: Do NOT silently switch renderers in production. Playwright fallback is opt-in.
        allow_playwright = (
            os.getenv("CV_PDF_RENDERER", "").strip().lower() == "playwright"
            or os.getenv("CV_ALLOW_PLAYWRIGHT_FALLBACK", "").strip() in {"1", "true", "yes"}
        )
        if os.name == "nt" and allow_playwright:
            return _render_pdf_playwright(html)
        raise RenderError(
            "WeasyPrint failed to render PDF. Install WeasyPrint native dependencies, or set CV_PDF_RENDERER=playwright for local Windows testing."
        ) from exc


def _render_pdf_playwright(html: str) -> bytes:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "print_pdf_playwright.mjs"
    if not script_path.exists():
        raise RenderError(f"Missing Playwright PDF helper script at {script_path}")

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


def render_pdf(cv: Dict[str, Any], *, enforce_two_pages: bool = True) -> bytes:
    """Generate PDF from CV data using WeasyPrint."""
    html = render_html(cv, inline_css=True)
    pdf = _render_pdf_weasyprint(html)
    
    if enforce_two_pages:
        # DoD: PDF must have exactly 2 pages
        pages = _count_pdf_pages(pdf)
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


def render_pdf_b64(cv: Dict[str, Any]) -> str:
    return base64.b64encode(render_pdf(cv)).decode("ascii")


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
