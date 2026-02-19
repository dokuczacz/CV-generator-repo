from src.validator import CV_LIMITS, _hard_limit
from src.work_experience_proposal import get_work_experience_bullets_proposal_response_format


def test_work_experience_validator_hard_cap_is_200():
    base = CV_LIMITS["work_experience"]["per_entry"]["bullets"]["max_chars_per_bullet"]
    assert base == 200
    assert _hard_limit(base) == 400


def test_work_experience_proposal_schema_enforces_200_maxlen():
    rf = get_work_experience_bullets_proposal_response_format()
    schema = rf.get("schema") if isinstance(rf, dict) else None
    assert isinstance(schema, dict)

    # Find any bullets.items.maxLength in the schema (injected by _apply_bullet_max_length).
    found = []

    def walk(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict) and isinstance(props.get("bullets"), dict):
                bullets = props.get("bullets")
                items = bullets.get("items") if isinstance(bullets, dict) else None
                if isinstance(items, dict) and items.get("type") == "string":
                    found.append(items.get("maxLength"))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    assert 200 in found
