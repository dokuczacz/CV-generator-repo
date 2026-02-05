import re


def _extract_action_ids_from_build_ui_action(src: str) -> set[str]:
    # Only scan the _build_ui_action() body to avoid unrelated action ids.
    m = re.search(r"^def _build_ui_action\(.*?\)\s*(?:->.*?)?\s*:\r?\n", src, flags=re.MULTILINE)
    assert m, "missing _build_ui_action"
    start = m.end()
    m2 = re.search(r"\r?\n\r?\n\s*def _tool_process_cv_orchestrated\(", src[start:])
    assert m2, "missing _tool_process_cv_orchestrated"
    block = src[start : start + m2.start()]

    ids = set(re.findall(r'\"id\"\\s*:\\s*\"([A-Z0-9_]+)\"', block))
    # Filter out obvious non-wizard legacy ids, keep the set strict.
    return {i for i in ids if i and i.upper() == i}


def _extract_handled_action_ids_from_wizard_handler(src: str) -> set[str]:
    # Heuristic: collect ids appearing in `aid == "X"` and in explicit tuples `aid in ("X","Y")`.
    ids = set(re.findall(r'aid\\s*==\\s*\"([A-Z0-9_]+)\"', src))

    for grp in re.findall(r'aid\\s+in\\s+\\(([^\\)]*)\\)', src):
        ids.update(re.findall(r'\"([A-Z0-9_]+)\"', grp))

    return {i for i in ids if i and i.upper() == i}


def test_wizard_ui_actions_are_handled():
    """
    Prevent 'ghost buttons': every action id emitted by _build_ui_action (wizard UI)
    must be handled by the wizard user_action dispatcher.
    """
    with open("function_app.py", "r", encoding="utf-8") as f:
        src = f.read()

    ui_ids = _extract_action_ids_from_build_ui_action(src)
    handled_ids = _extract_handled_action_ids_from_wizard_handler(src)

    missing = sorted(ui_ids - handled_ids)
    assert not missing, f"Ghost action ids (present in UI, missing in handler): {missing}"
