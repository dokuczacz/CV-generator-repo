from pathlib import Path

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
    assert len(skills) <= 8

    interests = cv.get("interests")
    assert isinstance(interests, str)
