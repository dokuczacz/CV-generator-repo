"""Deterministic JSON cleanup helpers.

The LLM sometimes returns JSON surrounded by prose or markdown fences, or emits
invalid JSON due to literal newlines inside strings.

These helpers are intentionally conservative and deterministic:
- They never execute any content.
- They only attempt to *extract* and *sanitize* JSON text.

Used by backend orchestration to improve schema-parse robustness.
"""

from __future__ import annotations

def strip_markdown_code_fences(text: str) -> str:
    """If the entire text is a fenced code block, return the inner content.

    Supports:
      ```json\n...\n```
      ```\n...\n```

    Otherwise returns the input unchanged.
    """
    if not text:
        return ""

    s = text.strip()
    if not s.startswith("```"):
        return text

    lines = s.splitlines()
    if len(lines) < 2:
        return text

    first = lines[0].strip()
    if not first.startswith("```"):
        return text

    # Find a closing fence on its own line.
    end_idx = None
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip() == "```":
            end_idx = i
            break
    if end_idx is None or end_idx <= 0:
        return text

    inner = "\n".join(lines[1:end_idx])
    return inner.strip("\n")

def _extract_first_json_span(text: str) -> tuple[int, int] | None:
    """Return (start, end_inclusive) span of the first JSON object/array.

    This scans for the first '{' or '[' and then finds the matching closing
    bracket while respecting JSON strings.

    Returns None if no balanced span is found.
    """
    if not text:
        return None

    start = None
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            start = i
            break

    if start is None:
        return None

    stack: list[str] = []
    in_string = False
    escape = False

    for j in range(start, len(text)):
        ch = text[j]

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        # not in string
        if ch == '"':
            in_string = True
            continue


        if ch in ("{", "["):
            stack.append(ch)
            continue

        if ch in ("}", "]"):
            if not stack:
                return None
            opener = stack[-1]
            expected = "}" if opener == "{" else "]"
            if ch != expected:
                return None
            stack.pop()
            if not stack:
                return start, j
            continue

    return None


def extract_first_json_value(text: str) -> str | None:
    """Extract the first top-level JSON object/array from text.

    Returns the extracted JSON substring, or None if not found.
    """
    span = _extract_first_json_span(text)
    if not span:
        return None
    start, end = span
    return text[start : end + 1]


def sanitize_json_text(raw: str) -> str:
    """Escape unescaped newlines inside JSON strings.

    JSON strings cannot contain literal newline characters; they must be escaped
    as "\\n". Models sometimes emit literal newlines, which causes parse errors.

    This function preserves all other characters and only converts:\n\r -> \\n/\\r
    when they occur inside a JSON string.
    """
    if not raw:
        return ""

    out: list[str] = []
    in_string = False
    escape = False

    for ch in raw:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            out.append(ch)
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            continue

        out.append(ch)

    return "".join(out)
