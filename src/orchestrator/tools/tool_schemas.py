from __future__ import annotations


def tool_schemas_for_responses(*, allow_persist: bool, stage: str = "review_session") -> list[dict]:
    # Provide explicit tool schemas (even with dashboard prompt) to ensure tool calling works.
    tools: list[dict] = [
        {"type": "web_search"},
        {
            "type": "function",
            "name": "get_cv_session",
            "strict": False,
            "description": "Retrieves CV data from an existing session for preview or confirmation.",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        },
    ]

    if allow_persist:
        tools.append(
            {
                "type": "function",
                "name": "update_cv_field",
                "strict": False,
                "description": "Updates CV session fields (single update, batch edits[], one-section cv_patch, and/or confirmation flags).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "field_path": {"type": "string"},
                        "value": {},
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"field_path": {"type": "string"}, "value": {}},
                                "required": ["field_path", "value"],
                                "additionalProperties": False,
                            },
                        },
                        "cv_patch": {"type": "object", "additionalProperties": True},
                        "confirm": {
                            "type": "object",
                            "properties": {
                                "contact_confirmed": {"type": "boolean"},
                                "education_confirmed": {"type": "boolean"},
                            },
                            "additionalProperties": False,
                        },
                        "client_context": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            }
        )

    tools.extend(
        [
            {
                "type": "function",
                "name": "validate_cv",
                "strict": False,
                "description": "Runs deterministic schema + DoD validation checks for the current session (no PDF render).",
                "parameters": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "cv_session_search",
                "strict": False,
                "description": "Search session data (cv_data + docx_prefill_unconfirmed + recent events) and return bounded previews.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "q": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "generate_context_pack_v2",
                "strict": False,
                "description": "Build ContextPackV2 for the given session and phase.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "phase": {"type": "string", "enum": ["preparation", "confirmation", "execution"]},
                        "job_posting_text": {"type": "string"},
                        "max_pack_chars": {"type": "integer"},
                    },
                    "required": ["session_id", "phase"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "preview_html",
                "strict": False,
                "description": "Render debug HTML from current session.",
                "parameters": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}, "inline_css": {"type": "boolean"}},
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            },
        ]
    )

    if stage in ("generate_pdf", "fix_validation"):
        tools.append(
            {
                "type": "function",
                "name": "generate_cv_from_session",
                "strict": False,
                "description": "Generate and persist PDF for the current session (execution stage only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "language": {"type": "string"},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            }
        )
        tools.append(
            {
                "type": "function",
                "name": "generate_cover_letter_from_session",
                "strict": False,
                "description": "Generate and persist a 1-page Cover Letter PDF for the current session (execution stage only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "language": {"type": "string"},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
            }
        )
        tools.append(
            {
                "type": "function",
                "name": "get_pdf_by_ref",
                "strict": False,
                "description": "Fetch previously generated PDF by reference (execution stage only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "pdf_ref": {"type": "string"},
                    },
                    "required": ["session_id", "pdf_ref"],
                    "additionalProperties": False,
                },
            }
        )
    return tools
