import re
from pathlib import Path


def _extract_action_ids(src: str) -> set[str]:
    ids = set(re.findall(r'\"id\"\\s*:\\s*\"([A-Z0-9_]+)\"', src))
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
    ui_builder_path = Path("src/orchestrator/wizard/ui_builder.py")
    if ui_builder_path.exists():
        src = ui_builder_path.read_text(encoding="utf-8")
    else:
        # Backward compatibility for pre-modularized layout.
        src = Path("function_app.py").read_text(encoding="utf-8")

    ui_ids = _extract_action_ids(src)
    handler_src = Path("function_app.py").read_text(encoding="utf-8")
    handled_ids = _extract_handled_action_ids_from_wizard_handler(handler_src)

    missing = sorted(ui_ids - handled_ids)
    assert not missing, f"Ghost action ids (present in UI, missing in handler): {missing}"
