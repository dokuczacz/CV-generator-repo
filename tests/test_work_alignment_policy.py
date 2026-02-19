import pytest

from src.work_experience_proposal import parse_work_experience_bullets_proposal


def test_parse_work_role_requires_3_4_bullets():
    payload = {
        "roles": [
            {
                "title": "Independent Technical Development",
                "company": "Self-employed",
                "date_range": "2023-01 - 2025-01",
                "location": "Remote",
                "bullets": [
                    "Built internal tooling.",
                    "Maintained CI pipelines.",
                ],
            }
        ],
        "notes": "test",
    }

    with pytest.raises(Exception):
        parse_work_experience_bullets_proposal(payload)


def test_parse_work_role_accepts_no_alignment_fields():
    payload = {
        "roles": [
            {
                "title": "Operations Manager",
                "company": "Sumitomo",
                "date_range": "2019-01 - 2022-12",
                "location": "Zurich, Switzerland",
                "bullets": [
                    "Led quality governance for multi-plant operations.",
                    "Reduced customer claims by 70% through corrective actions.",
                    "Standardized workflows and cut warehouse process steps by half.",
                ],
            }
        ],
        "notes": "test",
    }

    parsed = parse_work_experience_bullets_proposal(payload)
    assert len(parsed.roles) == 1
    assert parsed.roles[0].company == "Sumitomo"
    assert len(parsed.roles[0].bullets) == 3
