import pytest


def test_apply_work_experience_proposal_respects_locks():
    from function_app import _apply_work_experience_proposal_with_locks

    cv_data = {
        "work_experience": [
            {
                "employer": "A",
                "title": "Role A",
                "date_range": "2020-01 - 2021-01",
                "location": "X",
                "bullets": ["keep-a1", "keep-a2"],
            },
            {
                "employer": "B",
                "title": "Role B",
                "date_range": "2021-02 - 2022-02",
                "location": "Y",
                "bullets": ["keep-b1"],
            },
            {
                "employer": "C",
                "title": "Role C",
                "date_range": "2022-03 - 2023-03",
                "location": "Z",
                "bullets": ["keep-c1"],
            },
        ]
    }

    proposal_roles = [
        {"company": "A", "title": "Role A", "date_range": "2020-01 - 2021-01", "location": "X", "bullets": ["new-a1"]},
        {"company": "B", "title": "Role B", "date_range": "2021-02 - 2022-02", "location": "Y", "bullets": ["new-b1"]},
        {"company": "C", "title": "Role C", "date_range": "2022-03 - 2023-03", "location": "Z", "bullets": ["new-c1"]},
    ]

    meta = {"work_role_locks": {"1": True}}  # lock Role B
    out = _apply_work_experience_proposal_with_locks(cv_data=cv_data, proposal_roles=proposal_roles, meta=meta)

    assert out["work_experience"][0]["bullets"] == ["new-a1"]
    assert out["work_experience"][1]["bullets"] == ["keep-b1"]
    assert out["work_experience"][2]["bullets"] == ["new-c1"]


def test_apply_work_experience_proposal_shorter_than_current_keeps_rest():
    from function_app import _apply_work_experience_proposal_with_locks

    cv_data = {
        "work_experience": [
            {"employer": "A", "title": "Role A", "date_range": "", "location": "", "bullets": ["a"]},
            {"employer": "B", "title": "Role B", "date_range": "", "location": "", "bullets": ["b"]},
            {"employer": "C", "title": "Role C", "date_range": "", "location": "", "bullets": ["c"]},
        ]
    }
    proposal_roles = [{"company": "A", "title": "Role A", "date_range": "", "location": "", "bullets": ["a2"]}]

    out = _apply_work_experience_proposal_with_locks(cv_data=cv_data, proposal_roles=proposal_roles, meta={})
    assert out["work_experience"][0]["bullets"] == ["a2"]
    assert out["work_experience"][1]["bullets"] == ["b"]
    assert out["work_experience"][2]["bullets"] == ["c"]

