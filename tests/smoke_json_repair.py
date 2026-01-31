"""Deterministic smoke tests for JSON repair helpers.

Runs in < 1s and has no external deps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    # Ensure repo root is importable when running as a script.
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from src.json_repair import extract_first_json_value, sanitize_json_text, strip_markdown_code_fences

    # 1) Code fences
    fenced = """```json
{\n  \"a\": 1\n}\n```"""
    inner = strip_markdown_code_fences(fenced)
    assert inner.strip().startswith("{"), "expected inner JSON from fenced block"
    assert json.loads(inner)["a"] == 1

    # 2) Leading/trailing prose
    prose = "Here you go: {\"ok\": true, \"msg\": \"hi\"} thanks!"
    extracted = extract_first_json_value(prose)
    assert extracted is not None
    assert json.loads(extracted)["ok"] is True

    # 3) Braces inside strings shouldn't break extraction
    tricky = 'prefix {"a": "{ not a brace }", "b": 2} suffix'
    extracted2 = extract_first_json_value(tricky)
    assert extracted2 is not None
    obj = json.loads(extracted2)
    assert obj["b"] == 2

    # 4) Literal newline inside a string should be escaped
    bad = '{"a": "line1\nline2"}'
    try:
        json.loads(bad)
        raise AssertionError("expected json.loads to fail on literal newline")
    except Exception:
        pass
    fixed = sanitize_json_text(bad)
    assert json.loads(fixed)["a"] == "line1\nline2"

    # 5) Arrays are extractable too (even if some stages disallow them)
    arr = "junk [1, 2, 3] junk"
    extracted3 = extract_first_json_value(arr)
    assert extracted3 is not None
    assert json.loads(extracted3) == [1, 2, 3]

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
