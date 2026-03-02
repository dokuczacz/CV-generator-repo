from __future__ import annotations

from src.normalize import normalize_cv_data


def test_normalize_truncates_education_details_before_language_heading() -> None:
    cv = {
        "education": [
            {
                "institution": "Politechnika X",
                "title": "Bachelor of Engineering",
                "details": [
                    "Spezialisierung: Mikroprozessorgesteuerte Systeme",
                    "Sprachkenntnisse",
                    "Polnisch (Muttersprache)",
                    "Englisch (fließend)",
                ],
            }
        ]
    }

    out = normalize_cv_data(cv)
    details = out["education"][0]["details"]

    assert details == ["Spezialisierung: Mikroprozessorgesteuerte Systeme"]


def test_normalize_keeps_regular_education_details() -> None:
    cv = {
        "education": [
            {
                "institution": "Uni Y",
                "title": "MSc",
                "details": [
                    "Specialization: Power Systems",
                    "Thesis: Energy optimization in industrial systems",
                ],
            }
        ]
    }

    out = normalize_cv_data(cv)
    details = out["education"][0]["details"]

    assert details == [
        "Thesis: Energy optimization in industrial systems",
    ]
    assert out["education"][0]["specialization"] == "Power Systems"
