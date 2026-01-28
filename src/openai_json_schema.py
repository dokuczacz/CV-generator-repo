"""Helpers for OpenAI Structured Outputs JSON Schema.

The OpenAI Responses API enforces a stricter subset of JSON Schema when `strict=true`.
In particular, object schemas must explicitly set `additionalProperties: false`.

We post-process Pydantic-exported JSON Schema to satisfy these requirements.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def enforce_additional_properties_false(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied schema with `additionalProperties: false` on all object nodes."""

    root = deepcopy(schema)

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            node_type = node.get("type")
            if node_type == "object":
                # Required by OpenAI strict JSON schema validation.
                node["additionalProperties"] = False
                props = node.get("properties")
                if isinstance(props, dict):
                    # OpenAI strict mode requires every property key to be listed in `required`.
                    node["required"] = list(props.keys())
                    for v in props.values():
                        _walk(v)

            for key in ("anyOf", "allOf", "oneOf"):
                value = node.get(key)
                if isinstance(value, list):
                    for item in value:
                        _walk(item)

            if "items" in node:
                _walk(node.get("items"))

            defs = node.get("definitions")
            if isinstance(defs, dict):
                for v in defs.values():
                    _walk(v)

            defs2 = node.get("$defs")
            if isinstance(defs2, dict):
                for v in defs2.values():
                    _walk(v)

        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(root)
    return root
