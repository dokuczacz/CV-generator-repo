from __future__ import annotations

import base64
from pathlib import Path
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

    env = _load_env()
    template = env.get_template(TEMPLATE_NAME)
    css = ""
    if inline_css:
        css_path = TEMPLATES_DIR / CSS_NAME
        css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    # Extract styles from the DOCX template (fail fast if unavailable)
    # Support both `python src/render.py` and imports like `from src.render import ...`.
    try:
        from src.style_extractor import extract_styles_dict  # type: ignore
    except Exception:
        from style_extractor import extract_styles_dict  # type: ignore
    docx_path = Path(__file__).resolve().parents[1] / "wzory" / "CV_template_2pages_2025.docx"
    if not docx_path.exists():
        raise RenderError(f"DOCX template not found at {docx_path}")
    styles = extract_styles_dict(docx_path)

    context = dict(cv)
    if inline_css:
        context["_inline_css"] = css
    context["_styles"] = styles
    return template.render(**context)


def _render_pdf_weasyprint(html: str) -> bytes:
    """Render PDF using WeasyPrint (pure Python, no browser needed)"""
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RenderError(
            "WeasyPrint not installed. Install with `pip install weasyprint`."
        ) from exc
    
    return HTML(string=html).write_pdf()


def render_pdf(cv: Dict[str, Any]) -> bytes:
    """Generate PDF from CV data using WeasyPrint"""
    html = render_html(cv, inline_css=True)
    pdf = _render_pdf_weasyprint(html)
    
    # DoD: PDF must have exactly 2 pages
    pages = _count_pdf_pages(pdf)
    if pages != 2:
        raise RenderError(f"DoD violation: pages != 2 (got {pages}).")
    
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
