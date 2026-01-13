from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "html"
TEMPLATE_NAME = "cv_template_2pages_2025.html"
CSS_NAME = "cv_template_2pages_2025.css"


class RenderError(Exception):
    pass


def _load_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(cv: Dict[str, Any], inline_css: bool = True) -> str:
    env = _load_env()
    template = env.get_template(TEMPLATE_NAME)
    css = ""
    if inline_css:
        css_path = TEMPLATES_DIR / CSS_NAME
        css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    context = dict(cv)
    if inline_css:
        context["_inline_css"] = css
    return template.render(**context)


async def _render_pdf_async(html: str) -> bytes:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RenderError(
            "Playwright not installed. Install with `pip install playwright` and `playwright install chromium`."
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf = await page.pdf(format="A4", print_background=True)
        await browser.close()
        return pdf


def render_pdf(cv: Dict[str, Any]) -> bytes:
    html = render_html(cv, inline_css=True)
    try:
        return asyncio.run(_render_pdf_async(html))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_render_pdf_async(html))


def render_pdf_b64(cv: Dict[str, Any]) -> str:
    return base64.b64encode(render_pdf(cv)).decode("ascii")


if __name__ == "__main__":
    sample = {
        "full_name": "Mariusz Horodecki",
        "address_lines": ["Zer Chirchu 20", "3933 Staldenried"],
        "phone": "+41 77 952 24 37",
        "email": "horodecki.mariusz@gmail.com",
        "profile": "Projekt- und Betriebsleiter mit über 10 Jahren Erfahrung ...",
        "work_experience": [
            {
                "date_range": "2025-05",
                "employer": "Imbodden AG",
                "location": "Visp, Schweiz",
                "title": "Bauarbeiter",
                "bullets": [
                    "Ausführung von manuellen Tätigkeiten",
                    "Unterstützung bei Grabungsarbeiten",
                    "Mithilfe beim Materialtransport",
                ],
            }
        ],
        "education": [
            {
                "date_range": "2012–2015",
                "institution": "Poznań University of Technology",
                "title": "MSc Electrical Engineering",
                "details": ["Schwerpunkt: Industrielle und fahrzeugtechnische Systeme"],
            }
        ],
        "languages": ["Polnisch – Muttersprache", "Englisch – fliessend", "Deutsch – Mittelstufe"],
        "it_ai_skills": ["Technisches Projektmanagement", "KI-gestützte Effizienz"],
        "trainings": ["2025 – Beispiel Schulung"],
        "interests": "Systemdenken; Automatisierung",
        "references": "References on request.",
    }

    pdf_bytes = render_pdf(sample)
    out = Path(__file__).resolve().parents[1] / "preview.pdf"
    out.write_bytes(pdf_bytes)
    print(f"Preview written to {out} ({len(pdf_bytes)} bytes)")
