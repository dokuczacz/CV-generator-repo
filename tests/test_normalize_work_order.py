from __future__ import annotations

from src.normalize import normalize_cv_data


def test_normalize_preserves_work_experience_order() -> None:
    cv = {
        "work_experience": [
            {
                "date_range": "2019-01 - 2020-01",
                "employer": "Older Co",
                "title": "Role A",
                "bullets": ["A"],
            },
            {
                "date_range": "2023-01 - 2024-01",
                "employer": "Newer Co",
                "title": "Role B",
                "bullets": ["B"],
            },
        ]
    }

    out = normalize_cv_data(cv)
    work = out.get("work_experience") if isinstance(out.get("work_experience"), list) else []

    assert len(work) == 2
    assert str(work[0].get("employer") or "") == "Older Co"
    assert str(work[1].get("employer") or "") == "Newer Co"
