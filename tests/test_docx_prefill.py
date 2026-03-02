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


def test_parse_work_experience_preserves_import_order():
    lines = [
        "2021-01 - 2023-01 Senior Engineer - Company B, Zurich",
        "- Led delivery",
        "2019-01 - 2020-12 Engineer - Company A, Basel",
        "- Improved process",
    ]

    parsed = docx_prefill._parse_work_experience(lines)

    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert str(parsed[0].get("employer") or "").startswith("Company B")
    assert str(parsed[1].get("employer") or "").startswith("Company A")


def test_prefill_splits_inline_section_leakage_from_education(monkeypatch):
    fake_lines = [
        "Mariusz Horodecki",
        "horodecki@example.com",
        "+41 77 111 22 33",
        "Ausbildung",
        "2012-2015 Poznań University of Technology",
        "Master of Science in Electrical Engineering, Spezialisierung: Industrie- und Fahrzeugsysteme",
        "2008-2012 Poznań University of Technology",
        "Bachelor of Engineering in Electrical Engineering, Spezialisierung: Mikroprozessorgesteuerte Systeme, Sprachkenntnisse,Polnisch (Muttersprache),Englisch (fließend),Deutsch (mittelstufe),Russisch und Rumänisch (Grundkenntnisse),Interessen,Systemdenken & Workflow-Optimierung,Referenzen,Werden auf Anfrage bekanntgegeben.",
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

    education = cv.get("education") if isinstance(cv.get("education"), list) else []
    assert len(education) >= 2
    details_2 = education[1].get("details") if isinstance(education[1], dict) else []
    assert isinstance(details_2, list)
    assert all(len(str(d)) <= 300 for d in details_2)
    assert not any("Interessen" in str(d) or "Referenzen" in str(d) for d in details_2)

    languages = cv.get("languages") if isinstance(cv.get("languages"), list) else []
    assert any("Deutsch" in str(x) for x in languages)

    interests = str(cv.get("interests") or "")
    assert "Workflow-Optimierung" in interests


def test_prefill_splits_inline_language_skills_from_education(monkeypatch):
    fake_lines = [
        "Mariusz Horodecki",
        "horodecki@example.com",
        "+41 77 111 22 33",
        "Education",
        "2012-2015 Poznań University of Technology",
        "Master of Science in Electrical Engineering, specialization: Industrial and automotive systems",
        "2008-2012 Poznań University of Technology",
        "Bachelor of Engineering in Electrical Engineering, specialization: Microprocessor control systems, Language Skills,Polish (native),English (fluent),German (intermediate),Russian and Romanian (basic knowledge),Interests,Systems thinking & Workflow-Optimierung,References,Available upon request.",
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

    education = cv.get("education") if isinstance(cv.get("education"), list) else []
    assert len(education) >= 2
    details_2 = education[1].get("details") if isinstance(education[1], dict) else []
    assert isinstance(details_2, list)
    assert not any("Language Skills" in str(d) or "Interests" in str(d) or "References" in str(d) for d in details_2)

    languages = cv.get("languages") if isinstance(cv.get("languages"), list) else []
    assert any("German" in str(x) for x in languages)

    interests = str(cv.get("interests") or "")
    assert "Workflow-Optimierung" in interests
