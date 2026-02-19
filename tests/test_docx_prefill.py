from pathlib import Path

import src.docx_prefill as docx_prefill
from src.docx_contact_extract import ContactExtract
from src.docx_prefill import prefill_cv_from_docx_bytes


def test_prefill_extracts_contact_and_required_sections():
    sample = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
    assert sample.exists(), "Missing sample DOCX"

    cv = prefill_cv_from_docx_bytes(sample.read_bytes())

    assert cv.get("full_name"), "full_name should be extracted"
    assert "Horodecki" in cv.get("full_name", ""), "unexpected full_name"
    assert cv.get("email") and "@" in cv.get("email", ""), "email should be extracted"
    assert cv.get("phone"), "phone should be extracted"

    # Required sections should not be empty for this sample.
    assert isinstance(cv.get("work_experience"), list) and len(cv.get("work_experience")) >= 1
    assert isinstance(cv.get("education"), list) and len(cv.get("education")) >= 1

    languages = cv.get("languages")
    assert isinstance(languages, list) and len(languages) >= 1
    assert all(isinstance(x, str) for x in languages)
    assert any("Polnisch" in x for x in languages), "expected 'Polnisch' in languages"
    assert len(languages) <= 5

    skills = cv.get("it_ai_skills")
    assert isinstance(skills, list) and len(skills) >= 1
    assert all(isinstance(x, str) for x in skills)
    assert len(skills) <= 20

    interests = cv.get("interests")
    assert isinstance(interests, str)


def test_prefill_extracts_inline_skills_heading_tail(monkeypatch):
    fake_lines = [
        "Mariusz Horodecki",
        "horodecki@example.com",
        "+41 77 111 22 33",
        "Sprachen",
        "Polnisch (Muttersprache)",
        "Englisch (fluent)",
        "FÄHIGKEITEN & KOMPETENZENIndependent Technical Development, GitHub: https://github.com/dokuczacz/",
        "Technisches Projektmanagement (CAPEX/OPEX)",
        "Ursachenanalysen & Prozessverbesserungen (FMEA, 5 Why, PDCA)",
        "Interessen",
        "Cycling",
    ]

    monkeypatch.setattr(docx_prefill, "_lines_from_docx", lambda _bytes: fake_lines)
    monkeypatch.setattr(
        docx_prefill,
        "extract_contact_from_docx_bytes",
        lambda _bytes: ContactExtract(
            full_name="Mariusz Horodecki",
            email="horodecki@example.com",
            phone="+41 77 111 22 33",
            address_lines=("Zer Chirchu 20", "3933 Staldenried"),
        ),
    )

    cv = prefill_cv_from_docx_bytes(b"fake")
    merged_skills = list(cv.get("it_ai_skills") or []) + list(cv.get("technical_operational_skills") or [])

    assert any("Independent Technical Development" in s for s in merged_skills)
    assert any("CAPEX/OPEX" in s for s in merged_skills)
    assert any("FMEA" in s for s in merged_skills)
    assert all("FÄHIGKEITEN" not in x for x in (cv.get("languages") or []))
    raw_lines = cv.get("skills_raw_lines") if isinstance(cv.get("skills_raw_lines"), list) else []
    assert any("github.com/dokuczacz" in x.lower() for x in raw_lines)


def test_prefill_preserves_long_skill_lines(monkeypatch):
    long_skill = (
        "Designed and developed OmniFlow Beta, a multi-user AI agent backend built on Azure Functions "
        "and Azure Blob Storage, providing deterministic tool orchestration, user-isolated data storage, "
        "and semantic JSON pipelines for LLM-driven workflows"
    )
    fake_lines = [
        "Mariusz Horodecki",
        "horodecki@example.com",
        "+41 77 111 22 33",
        "FÄHIGKEITEN & KOMPETENZEN",
        "Independent Technical Development, GitHub: https://github.com/dokuczacz/",
        long_skill,
        "WEITERBILDUNGEN",
        "04/2018 – Core Tools (APQP, FMEA, MSA, SPC, PPAP) – RQM Certification",
    ]

    monkeypatch.setattr(docx_prefill, "_lines_from_docx", lambda _bytes: fake_lines)
    monkeypatch.setattr(
        docx_prefill,
        "extract_contact_from_docx_bytes",
        lambda _bytes: ContactExtract(
            full_name="Mariusz Horodecki",
            email="horodecki@example.com",
            phone="+41 77 111 22 33",
            address_lines=("Zer Chirchu 20", "3933 Staldenried"),
        ),
    )

    cv = prefill_cv_from_docx_bytes(b"fake")
    raw_lines = cv.get("skills_raw_lines") if isinstance(cv.get("skills_raw_lines"), list) else []
    assert any(("omni" in x.lower() and "azure functions" in x.lower()) for x in raw_lines)
    assert any(len(x) > 180 for x in raw_lines)
