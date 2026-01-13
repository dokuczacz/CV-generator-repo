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
        "nationality": "Polnisch",
        "profile": (
            "Projekt- und Betriebsleiter mit über 10 Jahren Erfahrung in Qualitätssystemen, "
            "technischen Prozessverbesserungen und Infrastrukturprojekten. Nachgewiesene "
            "Führung interdisziplinärer Teams, Aufbau von Greenfield-Standorten sowie "
            "Umsetzung komplexer Projekte in öffentlichen und privaten Bereichen. Starker "
            "Hintergrund in der Produktions- und Qualitätsingenieurtechnik mit zunehmender "
            "Spezialisierung auf Automatisierung und KI-gestützte Produktivitätstools (GPT). "
            "Fliessend in Englisch, muttersprachlich Polnisch, Deutschkenntnisse auf "
            "Mittelstufenniveau. Auf der Suche nach neuen Herausforderungen."
        ),
        "work_experience": [
            {
                "date_range": "2025-05",
                "employer": "Imbodden AG",
                "location": "Visp, Schweiz",
                "title": "Bauarbeiter",
                "bullets": [
                    "Ausführung von manuellen Tätigkeiten auf Tiefbau- und Strassenbaustellen",
                    "Unterstützung bei Grabungsarbeiten, Rohrverlegung und Baustellenreinigung",
                    "Mithilfe beim Materialtransport und einfachen Maschinenarbeiten",
                    "Einblick in Schweizer Baustandards und Sicherheitsvorschriften erhalten",
                ],
            },
            {
                "date_range": "2020-01 – 2025-04",
                "employer": "GL Solutions",
                "title": "Direktor",
                "bullets": [
                    "Planung und Koordination von Strassenbau- und Infrastrukturprojekten",
                    "Überwachung von Baustellen, Subunternehmern und Einhaltung gesetzlicher Vorschriften",
                    "Erstellung von Terminplänen, Budgets und Abschlussdokumentationen",
                    "Operatives Management öffentlicher und privater Aufträge",
                    "Einsatz von Planungs- und Kalkulationstools zur Optimierung der Umsetzung vor Ort",
                ],
            },
            {
                "date_range": "2018-11 – 2020-01",
                "employer": "Expondo Polska Sp. z o.o.",
                "title": "Leiter Qualität & Produktservice",
                "bullets": [
                    "Leitung von 3 Abteilungen mit insgesamt 35 Mitarbeitenden",
                    "Sicherstellung der CE-Konformität, Einführung von KPI-Dashboards und Prozessverbesserungen",
                    "Reklamationsmanagement, Produkt- und Prozessoptimierung",
                    "Standardisierung und Verbesserung der internen Abläufe",
                ],
            },
            {
                "date_range": "2016-08 – 2018-11",
                "employer": "SE Bordnetze SRL",
                "location": "Moldawien, Greenfield project",
                "title": "Qualitätsmanager",
                "bullets": [
                    "Leitung eines Bereichs mit 5 Sektionen und 80 Mitarbeitenden",
                    "Aufbau eines Greenfield-Werks, Einführung von Prozessen und Qualitätssystemen",
                    "Implementierung von VDA, Formel-Q und IATF Standards",
                    "Ansprechpartner für OEM-Kunden und Zertifizierungsstellen",
                ],
            },
            {
                "date_range": "2011-03 – 2016-07",
                "employer": "Sumitomo Electric Bordnetze SE",
                "title": "Spezialist für Prozessverbesserung (global)",
                "bullets": [
                    "Optimierung von Arbeitsplätzen und Prozessen, Durchführung von Zeitstudien",
                    "Kostenreduktion durch effiziente Produktionslösungen",
                    "Hauptauditor (PK) – Koordination globaler Audits, Benchmarking, Kundenanforderungsanpassung",
                ],
            },
        ],
        "education": [
            {
                "date_range": "2012–2015",
                "institution": "Poznań University of Technology",
                "title": "Master of Science in Electrical Engineering",
                "details": ["Schwerpunkt: Industrielle und fahrzeugtechnische Systeme"],
            },
            {
                "date_range": "2008–2012",
                "institution": "Poznań University of Technology",
                "title": "Bachelor of Engineering in Electrical Engineering",
                "details": ["Schwerpunkt: Mikroprozessorsteuerungen"],
            },
        ],
        "languages": ["Polnisch (Muttersprache)", "Englisch (fliessend)", "Deutsch (mittelstufe)"],
        "it_ai_skills": [
            "Technisches Projektmanagement (CAPEX/OPEX)",
            "Führung interdisziplinärer Teams",
            "Ursachenanalysen & Prozessverbesserungen (FMEA, 5 Why, PDCA)",
            "Baustellenmanagement (Strassenbau)",
            "Standardisierung & Optimierung auf datenbasierter Grundlage",
            "KI-gestützte Effizienz (GPT / Automatisierung / Reporting)",
        ],
        "trainings": [
            "05/2018 – Formel-Q Anforderungen – TQM Slovakia",
            "04/2018 – Core Tools (APQP, FMEA, MSA, SPC, PPAP) – RQM Certification s.r.l.",
            "12/2017 – Interner Auditor für IATF – RQM Certification s.r.l.",
            "11/2017 – IATF für Führungskräfte – RQM Certification s.r.l.",
            "03/2017 – Produktsicherheitsbeauftragter – TQMsoft Sp. z o.o.",
            "12/2015 – Teamorientierte Kommunikation – Effect Group Sp. z o.o.",
        ],
        "interests": (
            "Systemdenken & Workflow-Optimierung; Prozessautomatisierung & Planungsarchitekturen; "
            "Langstreckenradfahren, Outdoor-Aktivitäten, Wandern; Belletristik (z. B. Fantasy/Sci-Fi) "
            "und Fachliteratur (Entscheidungspsychologie, NLP); Angewandte künstliche Intelligenz "
            "und Sprachmodelle"
        ),
        "data_privacy": (
            "Ich stimme der Verarbeitung meiner personenbezogenen Daten zum Zwecke des "
            "Bewerbungsverfahrens für die ausgeschriebene Stelle zu."
        ),
    }

    pdf_bytes = render_pdf(sample)
    out = Path(__file__).resolve().parents[1] / "preview.pdf"
    out.write_bytes(pdf_bytes)
    print(f"Preview written to {out} ({len(pdf_bytes)} bytes)")
