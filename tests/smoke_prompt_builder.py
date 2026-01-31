"""Smoke-check backend prompt builder.

This catches regressions where prompt templates include literal `{...}` blocks (e.g., JSON examples)
and would crash if the builder uses `str.format()`.

Runs in < 1s and has no external deps.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Ensure repo root is importable when running as a script.
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from function_app import _AI_PROMPT_BY_STAGE, _build_ai_system_prompt

    failures: list[str] = []
    for stage in sorted(_AI_PROMPT_BY_STAGE.keys()):
        try:
            prompt = _build_ai_system_prompt(stage=stage, target_language="en")
        except Exception as exc:  # pragma: no cover
            failures.append(f"stage={stage}: exception={type(exc).__name__}: {exc}")
            continue

        if not isinstance(prompt, str) or not prompt.strip():
            failures.append(f"stage={stage}: produced empty/non-string prompt")
            continue

        if "{target_language}" in prompt:
            failures.append(f"stage={stage}: left placeholder {{target_language}} unexpanded")

    if failures:
        raise AssertionError("Prompt builder smoke check failed:\n" + "\n".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
