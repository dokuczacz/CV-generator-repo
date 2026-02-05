from function_app import _build_work_bullet_violation_payload


def test_build_work_bullet_violation_payload_contains_indices():
    roles = [
        {
            "title": "Engineer",
            "company": "Acme",
            "bullets": ["This bullet is too long"],
        }
    ]
    payload = _build_work_bullet_violation_payload(roles=roles, hard_limit=10, min_reduction_chars=30)

    assert payload.get("error_code") == "VALIDATION:WORK_EXPERIENCE_BULLET_TOO_LONG"
    violations = payload.get("violations")
    assert isinstance(violations, list)
    assert len(violations) == 1

    v0 = violations[0]
    assert v0.get("role_index") == 0
    assert v0.get("bullet_index") == 0
    assert v0.get("max_chars") == 10
    assert v0.get("min_reduction_chars") == 30
    assert isinstance(v0.get("bullet"), str)
