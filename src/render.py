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

        # Validate layout rules under print rendering.
        await page.emulate_media(media="print")
        layout = await page.evaluate(
            """() => {
                            const MM_TO_PX = 3.7795275591;
                            const PAGE_HEIGHT_MM = 297;
                            const pageHeightPx = PAGE_HEIGHT_MM * MM_TO_PX;

                            const root = document.querySelector('.page');
                            if (!root) return { error: 'Missing .page root' };
                            const rootTop = root.getBoundingClientRect().top;

                            const sections = Array.from(document.querySelectorAll('section.section'));
                            const pageBreaks = Array.from(document.querySelectorAll('.page-break'));

                            // Simulate the vertical "gap" that a forced print page-break introduces.
                            // This keeps validation deterministic without mutating the DOM and matches
                            // the resulting PDF pagination much better than raw DOM coordinates.
                            let shiftSoFar = 0;
                            const breakInfos = pageBreaks.map((br) => {
                                const r = br.getBoundingClientRect();
                                const topPx = r.top - rootTop;
                                const effectiveTopPx = topPx + shiftSoFar;
                                const rem = ((effectiveTopPx % pageHeightPx) + pageHeightPx) % pageHeightPx;
                                const shift = rem === 0 ? 0 : (pageHeightPx - rem);
                                shiftSoFar += shift;
                                return { node: br, shiftAfter: shiftSoFar };
                            });

                            const shiftBeforeNode = (node) => {
                                let s = 0;
                                for (const info of breakInfos) {
                                    const rel = info.node.compareDocumentPosition(node);
                                    const isBefore = (rel & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
                                    if (isBefore) {
                                        s = info.shiftAfter;
                                    }
                                }
                                return s;
                            };

                            const starts = {};
                            const problems = [];

                            for (const sec of sections) {
                                const titleEl = sec.querySelector('.section-title');
                                const title = titleEl ? titleEl.textContent.trim() : '(untitled section)';
                                const r = sec.getBoundingClientRect();
                                const topPx = r.top - rootTop;
                                const bottomPx = r.bottom - rootTop;
                                const heightPx = r.height;

                                const shift = shiftBeforeNode(sec);
                                const topEff = topPx + shift;
                                const bottomEff = bottomPx + shift;

                                const startPage = Math.floor(topEff / pageHeightPx) + 1;
                                const endPage = Math.floor((bottomEff - 0.01) / pageHeightPx) + 1;
                                starts[title] = startPage;

                                if (heightPx > pageHeightPx) {
                                    problems.push({ title, startPage, endPage, tooTall: true });
                                    continue;
                                }
                                if (startPage !== endPage) {
                                    problems.push({ title, startPage, endPage, tooTall: false });
                                }
                            }

                            let pageBreakPage = null;
                            if (pageBreaks.length) {
                                const br = pageBreaks[0];
                                const r = br.getBoundingClientRect();
                                const topPx = r.top - rootTop;
                                const shift = shiftBeforeNode(br);
                                const topEff = topPx + shift;
                                pageBreakPage = Math.floor(topEff / pageHeightPx) + 1;
                            }

                            return {
                                problems,
                                starts,
                                pageBreakCount: pageBreaks.length,
                                pageBreakPage,
                            };
            }"""
        )

        if layout.get("error"):
            await browser.close()
            raise RenderError(f"Layout validation failed: {layout['error']}")

        if layout.get("pageBreakCount") != 1:
            await browser.close()
            raise RenderError(
                f"DoD violation: page break mismatch (expected exactly 1, got {layout.get('pageBreakCount')})."
            )

        starts = layout.get("starts", {})
        expected_starts = {
            "Education": 1,
            "Work experience": 1,
            "Further experience / commitment": 2,
            "Language Skills": 2,
            "IT & AI Skills": 2,
            "Interests": 2,
            "References": 2,
        }
        mismatched = []
        for title, expected_page in expected_starts.items():
            actual = starts.get(title)
            if actual is None:
                mismatched.append(f"{title}: missing")
            elif actual != expected_page:
                mismatched.append(f"{title}: p{actual} (expected p{expected_page})")
        if mismatched:
            await browser.close()
            raise RenderError(
                "DoD violation: page break mismatch. " + "; ".join(mismatched)
            )

        problems = layout.get("problems", [])
        too_tall = [p for p in problems if p.get("tooTall")]
        if too_tall:
            await browser.close()
            titles = ", ".join([p["title"] for p in too_tall])
            raise RenderError(
                "DoD violation: section taller than one page (cannot keep together). "
                f"Reduce content for: {titles}"
            )

        if problems:
            await browser.close()
            titles = ", ".join(
                [f"{p['title']} (p{p['startPage']}→p{p['endPage']})" for p in problems]
            )
            raise RenderError(
                "DoD violation: section is split across pages. "
                f"Split sections: {titles}"
            )

        pdf = await page.pdf(format="A4", print_background=True)
        await browser.close()

        # DoD: PDF must have exactly 2 pages.
        pages = _count_pdf_pages(pdf)
        if pages != 2:
            raise RenderError(f"DoD violation: pages != 2 (got {pages}).")

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
