from __future__ import annotations


def _role(n: int) -> dict:
    return {
        "employer": "X",
        "title": "Y",
        "date_range": "2020-01 - 2021-01",
        "bullets": [f"b{i}" for i in range(n)],
    }


def test_drops_last_role_first_and_keeps_floor() -> None:
    import function_app as app

    cv = {"work_experience": [_role(4), _role(4), _role(5)]}
    cv2, change = app._drop_one_work_bullet_bottom_up(cv_in=cv, min_bullets_per_role=3)
    assert change == "work_drop_bullet[2]"
    work = cv2["work_experience"]
    assert len(work[0]["bullets"]) == 4
    assert len(work[1]["bullets"]) == 4
    assert len(work[2]["bullets"]) == 4

    # Once a role hits the floor, it won't drop further at that floor.
    cv3, change2 = app._drop_one_work_bullet_bottom_up(cv_in=cv2, min_bullets_per_role=4)
    assert change2 is None
    assert cv3 == cv2

