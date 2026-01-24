"""
Azure Functions app for CV Generator.

Public surface area (intentionally minimal):
  - GET  /api/health
  - POST /api/cv-tool-call-handler

All workflow operations are routed through the tool dispatcher to keep the API surface small and the UI thin.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import azure.functions as func
from openai import OpenAI

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.blob_store import BlobPointer, CVBlobStore
from src.context_pack import build_context_pack_v2, format_context_pack_with_delimiters
from src.docx_photo import extract_first_photo_from_docx_bytes
from src.docx_prefill import prefill_cv_from_docx_bytes
from src.normalize import normalize_cv_data
from src.render import render_html, render_pdf
from src.schema_validator import validate_canonical_schema
from src.session_store import CVSessionStore
from src.validator import validate_cv


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _json_response(payload: dict, *, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        mimetype="application/json; charset=utf-8",
        status_code=status_code,
    )


def _serialize_validation_result(validation_result) -> dict:
    """Convert ValidationResult to JSON-safe dict."""
    return {
        "is_valid": validation_result.is_valid,
        "errors": [asdict(err) for err in validation_result.errors],
        "warnings": validation_result.warnings,
        "estimated_pages": validation_result.estimated_pages,
        "estimated_height_mm": validation_result.estimated_height_mm,
        "details": validation_result.details,
    }


def _compute_required_present(cv_data: dict) -> dict:
    return {
        "full_name": bool(cv_data.get("full_name", "").strip()) if isinstance(cv_data.get("full_name"), str) else False,
        "email": bool(cv_data.get("email", "").strip()) if isinstance(cv_data.get("email"), str) else False,
        "phone": bool(cv_data.get("phone", "").strip()) if isinstance(cv_data.get("phone"), str) else False,
        "work_experience": bool(cv_data.get("work_experience")) and isinstance(cv_data.get("work_experience"), list),
        "education": bool(cv_data.get("education")) and isinstance(cv_data.get("education"), list),
    }


def _compute_readiness(cv_data: dict, metadata: dict) -> dict:
    required_present = _compute_required_present(cv_data)
    confirmed_flags = (metadata or {}).get("confirmed_flags") or {}
    contact_ok = bool(confirmed_flags.get("contact_confirmed"))
    education_ok = bool(confirmed_flags.get("education_confirmed"))
    missing: list[str] = []
    for k, v in required_present.items():
        if not v:
            missing.append(k)
    if not contact_ok:
        missing.append("contact_not_confirmed")
    if not education_ok:
        missing.append("education_not_confirmed")
    can_generate = all(required_present.values()) and contact_ok and education_ok
    return {
        "can_generate": can_generate,
        "required_present": required_present,
        "confirmed_flags": {
            "contact_confirmed": contact_ok,
            "education_confirmed": education_ok,
            "confirmed_at": confirmed_flags.get("confirmed_at"),
        },
        "missing": missing,
    }

def _responses_max_output_tokens(stage: str) -> int:
    # Keep bounded. Hard target: <=5 total model turns; typical 1-3.
    if stage == "draft_proposal":
        return 1440
    if stage == "fix_validation":
        return 960
    if stage == "generate_pdf":
        return 720
    return 720


def _stage_prompt(stage: str) -> str:
    # Keep short; the main system prompt lives in the OpenAI Dashboard prompt (OPENAI_PROMPT_ID).
    common = (
        "You are operating in a staged workflow (stateless). "
        "Ask at most 3–4 concise questions per turn. "
        "Finish in <=3 turns when possible (hard max 5)."
    )
    if stage == "review_session":
        return f"{common}\n[STAGE=review_session]\nGoal: review session data + propose edits (no PDF)."
    if stage == "apply_edits":
        return f"{common}\n[STAGE=apply_edits]\nGoal: persist user-provided content using update_cv_field(edits=[...])."
    if stage == "generate_pdf":
        return f"{common}\n[STAGE=generate_pdf]\nGoal: user approved; generate PDF once if readiness allows."
    if stage == "fix_validation":
        return f"{common}\n[STAGE=fix_validation]\nGoal: fix validation errors in one pass then generate once."
    return f"{common}\n[STAGE=bootstrap]\nGoal: establish a session or ask for missing inputs."


def _looks_truncated(text: str) -> bool:
    t = (text or "").rstrip()
    if not t:
        return False
    return not any(t.endswith(x) for x in (".", "!", "?", "…"))


def _tool_schemas_for_responses() -> list[dict]:
    # Provide explicit tool schemas (even with dashboard prompt) to ensure tool calling works.
    return [
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
        },
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
        {
            "type": "function",
            "name": "generate_cv_from_session",
            "strict": False,
            "description": "Generate final PDF from stored session data (requires readiness).",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}, "language": {"type": "string", "enum": ["en", "de", "pl"]}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        },
    ]


def _sanitize_tool_output_for_model(tool_name: str, payload: Any) -> str:
    try:
        if tool_name == "generate_cv_from_session":
            if isinstance(payload, dict):
                return json.dumps(
                    {
                        "ok": payload.get("success") is True and bool(payload.get("pdf_base64_length") or payload.get("pdf_bytes")),
                        "success": payload.get("success"),
                        "error": payload.get("error"),
                        "readiness": payload.get("readiness"),
                        "pdf_base64_length": payload.get("pdf_base64_length"),
                    },
                    ensure_ascii=False,
                )
        if isinstance(payload, dict):
            out = dict(payload)
            for k in ("pdf_base64", "docx_base64", "photo_data_uri"):
                out.pop(k, None)
            return json.dumps(out, ensure_ascii=False)
        return json.dumps({"ok": True, "value": str(payload)[:2000]}, ensure_ascii=False)
    except Exception:
        return json.dumps({"ok": False, "error": "sanitize_failed"}, ensure_ascii=False)


def _run_responses_tool_loop(
    *,
    user_message: str,
    session_id: str,
    stage: str,
    job_posting_text: str | None,
    trace_id: str,
    max_turns: int,
) -> tuple[str, list[dict], dict, str | None, bytes | None]:
    """
    Backend-owned, stateless Responses tool-loop.
    Returns: (assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes)
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt_id = (os.environ.get("OPENAI_PROMPT_ID") or "").strip() or None
    model_override = (os.environ.get("OPENAI_MODEL") or "").strip() or None
    # Tool-loop requires persisted response items for follow-up calls; default ON.
    store_flag = str(os.environ.get("OPENAI_STORE", "1")).strip() == "1"

    run_summary: dict = {"trace_id": trace_id, "timestamps": {}, "steps": [], "max_turns": max_turns, "model_calls": 0}
    turn_trace: list[dict] = []
    pdf_bytes: bytes | None = None
    last_response_id: str | None = None

    store = CVSessionStore()
    session = store.get_session(session_id)
    if not session:
        return (
            "Your session is no longer available. Please re-upload your CV DOCX to start a new session.",
            [],
            run_summary,
            None,
            None,
        )

    # Build capsule once per turn (phase depends on stage).
    phase = "execution" if stage == "generate_pdf" else "preparation"

    for turn_idx in range(1, max_turns + 1):
        run_summary["timestamps"][f"turn_{turn_idx}_start"] = time.time()
        # Refresh session for each turn (tools mutate it).
        session = store.get_session(session_id) or {}
        cv_data = session.get("cv_data") or {}
        readiness = _compute_readiness(cv_data, session.get("metadata") or {})

        # Build context pack text for the model.
        pack = build_context_pack_v2(
            phase=phase,
            cv_data=cv_data,
            job_posting_text=job_posting_text,
            session_metadata=(session.get("metadata") or {}) if isinstance(session.get("metadata"), dict) else {},
            max_pack_chars=12000,
        )
        capsule_text = format_context_pack_with_delimiters(pack)

        # Compose user content (bounded, explicit markers).
        user_content = (
            f"{user_message}\n\n"
            f"[SESSION_ID]\n{session_id}\n\n"
            f"[CONTEXT_PACK_V2]\n{capsule_text}\n"
        )
        input_list = [{"role": "user", "content": user_content}, {"role": "system", "content": _stage_prompt(stage)}]

        req: dict = {
            "input": input_list,
            "tools": _tool_schemas_for_responses(),
            "store": store_flag,
            "truncation": "disabled",
            "max_output_tokens": _responses_max_output_tokens(stage),
            "metadata": {
                "app": "cv-generator-backend",
                "workflow": "backend_orchestrator_v1",
                "trace_id": trace_id,
                "stage": stage,
                "turn": str(turn_idx),
            },
        }
        if prompt_id:
            req["prompt"] = {"id": prompt_id}
        else:
            req["instructions"] = "You are a CV assistant operating in a stateless API. Use tools to persist edits."
        if model_override:
            req["model"] = model_override

        # Model call
        resp = client.responses.create(**req)
        last_response_id = getattr(resp, "id", None) or last_response_id
        out_text = getattr(resp, "output_text", "") or ""

        # Collect tool calls
        tool_calls = [item for item in (getattr(resp, "output", None) or []) if getattr(item, "type", None) == "function_call"]
        tool_names: list[str] = []
        for call in tool_calls:
            name = getattr(call, "name", None) or getattr(getattr(call, "function", None), "name", None)
            args_raw = getattr(call, "arguments", None) or getattr(getattr(call, "function", None), "arguments", None) or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw or {})
            except Exception:
                args = {}
            tool_names.append(str(name))

            tool_start = time.time()
            tool_payload: Any = {}
            tool_output_for_model = "{}"
            try:
                if name == "get_cv_session":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {
                            "success": True,
                            "session_id": sid,
                            "readiness": _compute_readiness(cv, s.get("metadata") or {}),
                            "cv_data": cv,
                            "metadata": s.get("metadata"),
                        }
                elif name == "update_cv_field":
                    sid = args.get("session_id") or session_id
                    # Reuse the same update logic as dispatcher by calling CVSessionStore.update_field and metadata confirm update.
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        # Confirmation flags
                        confirm_flags = args.get("confirm")
                        if isinstance(confirm_flags, dict) and confirm_flags:
                            meta = s.get("metadata") or {}
                            if isinstance(meta, dict):
                                meta = dict(meta)
                                cf = meta.get("confirmed_flags") or {}
                                if not isinstance(cf, dict):
                                    cf = {}
                                cf = dict(cf)
                                for k in ("contact_confirmed", "education_confirmed"):
                                    if k in confirm_flags:
                                        cf[k] = bool(confirm_flags.get(k))
                                if cf.get("contact_confirmed") and cf.get("education_confirmed") and not cf.get("confirmed_at"):
                                    cf["confirmed_at"] = _now_iso()
                                meta["confirmed_flags"] = cf
                                store.update_session(str(sid), (s.get("cv_data") or {}), meta)
                        client_context = args.get("client_context")
                        edits = args.get("edits")
                        field_path = args.get("field_path")
                        value = args.get("value")
                        cv_patch = args.get("cv_patch")
                        applied = 0
                        if isinstance(edits, list):
                            for e in edits:
                                fp = e.get("field_path")
                                if not fp:
                                    continue
                                store.update_field(str(sid), fp, e.get("value"), client_context=client_context if isinstance(client_context, dict) else None)
                                applied += 1
                        if field_path:
                            store.update_field(str(sid), str(field_path), value, client_context=client_context if isinstance(client_context, dict) else None)
                            applied += 1
                        if isinstance(cv_patch, dict):
                            for k, v in cv_patch.items():
                                store.update_field(str(sid), str(k), v, client_context=client_context if isinstance(client_context, dict) else None)
                                applied += 1
                        tool_payload = {"success": True, "session_id": sid, "edits_applied": applied}
                elif name == "validate_cv":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {
                            "success": True,
                            "session_id": sid,
                            **_validate_cv_data_for_tool(cv),
                            "readiness": _compute_readiness(cv, s.get("metadata") or {}),
                        }
                elif name == "cv_session_search":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        q = str(args.get("q") or "")
                        limit = int(args.get("limit") or 20)
                        result = _cv_session_search_hits(session=s, q=q, limit=limit)
                        tool_payload = {"success": True, "session_id": sid, "hits": result["hits"], "truncated": result["truncated"]}
                elif name == "generate_context_pack_v2":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, pack2 = _tool_generate_context_pack_v2(
                            session_id=str(sid),
                            phase=str(args.get("phase") or "preparation"),
                            job_posting_text=str(args.get("job_posting_text") or "") or None,
                            max_pack_chars=int(args.get("max_pack_chars") or 12000),
                            session=s,
                        )
                        tool_payload = pack2 if status == 200 else {"error": pack2.get("error") if isinstance(pack2, dict) else "pack_failed"}
                elif name == "preview_html":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {"success": True, "session_id": sid, **_render_html_for_tool(cv, inline_css=bool(args.get("inline_css", True)))}
                elif name == "generate_cv_from_session":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, payload, content_type = _tool_generate_cv_from_session(
                            session_id=str(sid),
                            language=str(args.get("language") or "").strip() or None,
                            client_context=None,
                            session=s,
                        )
                        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)) and status == 200:
                            pdf_bytes = bytes(payload)
                            tool_payload = {"success": True, "session_id": sid, "pdf_base64_length": len(base64.b64encode(pdf_bytes))}
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "generate_failed"}
                else:
                    tool_payload = {"error": f"Unknown tool: {name}"}

                tool_output_for_model = _sanitize_tool_output_for_model(str(name), tool_payload)
            except Exception as e:
                tool_payload = {"error": f"tool_exec_failed: {e}"}
                tool_output_for_model = _sanitize_tool_output_for_model(str(name), tool_payload)
            tool_end = time.time()
            run_summary["steps"].append(
                {
                    "step": "tool",
                    "tool": str(name),
                    "duration_ms": int((tool_end - tool_start) * 1000),
                    "ok": isinstance(tool_payload, dict) and not tool_payload.get("error"),
                }
            )

            # Feed tool output back to the model in a follow-up call (stateless continuation).
            # We append the function result as an assistant tool message.
            try:
                resp = client.responses.create(
                    **{
                        **req,
                        "input": input_list
                        + [
                            {"type": "function_call_output", "call_id": getattr(call, "call_id", None) or getattr(call, "id", ""), "output": tool_output_for_model}
                        ],
                        "tools": _tool_schemas_for_responses(),
                    }
                )
                last_response_id = getattr(resp, "id", None) or last_response_id
                out_text = getattr(resp, "output_text", "") or out_text
            except Exception:
                # If follow-up fails, continue; we still return what we have.
                pass

        turn_trace.append(
            {
                "turn": turn_idx,
                "stage": stage,
                "phase": phase,
                "tools_called": tool_names,
                "tool_calls_count": len(tool_names),
                "readiness": readiness,
                "assistant_text_chars": len(out_text),
            }
        )
        run_summary["timestamps"][f"turn_{turn_idx}_end"] = time.time()

        # Stop criteria: no tool calls and we have a non-empty assistant response.
        if not tool_calls and out_text.strip():
            # If output looks truncated near cap, do one continuation (no tools).
            if _looks_truncated(out_text):
                try:
                    cont = client.responses.create(
                        **{
                            **req,
                            "input": input_list + [{"role": "user", "content": "Continue from where you stopped. Do not repeat."}],
                            "tools": [],
                            "max_output_tokens": min(1024, _responses_max_output_tokens(stage)),
                        }
                    )
                    cont_text = getattr(cont, "output_text", "") or ""
                    if cont_text:
                        out_text = f"{out_text.rstrip()}\n\n{cont_text.lstrip()}"
                        last_response_id = getattr(cont, "id", None) or last_response_id
                except Exception:
                    pass
            return out_text, turn_trace, run_summary, last_response_id, pdf_bytes

        # If PDF was generated, stop.
        if pdf_bytes:
            return out_text or "PDF generated.", turn_trace, run_summary, last_response_id, pdf_bytes

    # Max turns reached; return last output.
    return out_text or "I need one more message to continue.", turn_trace, run_summary, last_response_id, pdf_bytes


def _run_responses_tool_loop_v2(
    *,
    user_message: str,
    session_id: str,
    stage: str,
    job_posting_text: str | None,
    trace_id: str,
    max_model_calls: int,
) -> tuple[str, list[dict], dict, str | None, bytes | None]:
    """
    Backend-owned, stateless Responses tool-loop.

    Design goals:
    - One backend HTTP request can include multiple model calls + tool calls (hard cap <= 5 model calls).
    - Session persistence is deterministic via tools; the model never "assumes" updates without calling tools.

    Returns: (assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes)
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt_id = (os.environ.get("OPENAI_PROMPT_ID") or "").strip() or None
    model_override = (os.environ.get("OPENAI_MODEL") or "").strip() or None
    # Responses API requires an explicit model; prompts do not automatically provide it.
    model_name = model_override or "gpt-5-mini"
    # Tool-loop requires persisted response items for follow-up calls; default ON.
    store_flag = str(os.environ.get("OPENAI_STORE", "1")).strip() == "1"

    run_summary: dict = {"trace_id": trace_id, "steps": [], "max_model_calls": max_model_calls, "model_calls": 0}
    turn_trace: list[dict] = []
    pdf_bytes: bytes | None = None
    last_response_id: str | None = None

    store = CVSessionStore()
    session = store.get_session(session_id)
    if not session:
        return (
            "Your session is no longer available. Please re-upload your CV DOCX to start a new session.",
            [],
            run_summary,
            None,
            None,
        )

    phase = "execution" if stage == "generate_pdf" else "preparation"
    cv_data = session.get("cv_data") or {}
    meta = session.get("metadata") or {}
    readiness = _compute_readiness(cv_data, meta if isinstance(meta, dict) else {})

    pack = build_context_pack_v2(
        phase=phase,
        cv_data=cv_data,
        job_posting_text=job_posting_text,
        session_metadata=meta if isinstance(meta, dict) else {},
        max_pack_chars=12000,
    )
    capsule_text = format_context_pack_with_delimiters(pack)

    out_lang = str(meta.get("language") or "").strip() if isinstance(meta, dict) else ""
    user_content = (
        f"{user_message}\n\n"
        f"[OUTPUT_LANGUAGE]\n{out_lang}\n\n"
        f"[SESSION_ID]\n{session_id}\n\n"
        f"[READINESS]\n{json.dumps(readiness, ensure_ascii=False)}\n\n"
        f"[CONTEXT_PACK_V2]\n{capsule_text}\n"
    )

    tools = _tool_schemas_for_responses()
    req_base: dict = {
        "tools": tools,
        "store": store_flag,
        "truncation": "disabled",
        "max_output_tokens": _responses_max_output_tokens(stage),
        "metadata": {
            "app": "cv-generator-backend",
            "workflow": "backend_orchestrator_v2",
            "trace_id": trace_id,
            "stage": stage,
        },
    }
    if prompt_id:
        req_base["prompt"] = {"id": prompt_id}
    else:
        req_base["instructions"] = "You are a CV assistant operating in a stateless API. Use tools to persist edits."
    req_base["model"] = model_name

    # Context is stateful within this single HTTP request.
    context: list[Any] = [
        {"role": "system", "content": _stage_prompt(stage)},
        {"role": "user", "content": user_content},
    ]

    out_text = ""
    for model_call_idx in range(1, max_model_calls + 1):
        model_start = time.time()
        try:
            resp = client.responses.create(**{**req_base, "input": context})
        except Exception as e:
            model_end = time.time()
            err = str(e)
            run_summary["steps"].append(
                {
                    "step": "model_call_error",
                    "index": model_call_idx,
                    "duration_ms": int((model_end - model_start) * 1000),
                    "error": err[:800],
                }
            )
            return (
                f"Backend error while calling the model. Please retry. If it persists, check OPENAI_API_KEY / OPENAI_PROMPT_ID.\n\nError: {err}",
                turn_trace,
                run_summary,
                last_response_id,
                pdf_bytes,
            )
        model_end = time.time()

        run_summary["model_calls"] += 1
        last_response_id = getattr(resp, "id", None) or last_response_id
        out_text = getattr(resp, "output_text", "") or out_text

        outputs = getattr(resp, "output", None) or []
        for item in outputs:
            context.append(item)

        tool_calls = [item for item in outputs if getattr(item, "type", None) == "function_call"]
        run_summary["steps"].append(
            {
                "step": "model_call",
                "index": model_call_idx,
                "duration_ms": int((model_end - model_start) * 1000),
                "tool_calls": len(tool_calls),
            }
        )

        if not tool_calls:
            break

        tool_names: list[str] = []
        for call in tool_calls:
            name = getattr(call, "name", None) or getattr(getattr(call, "function", None), "name", None)
            args_raw = getattr(call, "arguments", None) or getattr(getattr(call, "function", None), "arguments", None) or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw or {})
            except Exception:
                args = {}
            tool_names.append(str(name))

            tool_start = time.time()
            tool_payload: Any = {}
            try:
                if name == "get_cv_session":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {
                            "success": True,
                            "session_id": sid,
                            "readiness": _compute_readiness(cv, s.get("metadata") or {}),
                            "cv_data": cv,
                            "metadata": s.get("metadata"),
                        }
                elif name == "update_cv_field":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        confirm_flags = args.get("confirm")
                        confirm_applied = 0
                        if isinstance(confirm_flags, dict) and confirm_flags:
                            meta2 = s.get("metadata") or {}
                            if isinstance(meta2, dict):
                                meta2 = dict(meta2)
                                cf = meta2.get("confirmed_flags") or {}
                                if not isinstance(cf, dict):
                                    cf = {}
                                cf = dict(cf)
                                for k in ("contact_confirmed", "education_confirmed"):
                                    if k in confirm_flags:
                                        cf[k] = bool(confirm_flags.get(k))
                                if cf.get("contact_confirmed") and cf.get("education_confirmed") and not cf.get("confirmed_at"):
                                    cf["confirmed_at"] = _now_iso()
                                meta2["confirmed_flags"] = cf
                                store.update_session(str(sid), (s.get("cv_data") or {}), meta2)
                                confirm_applied = 1

                        edits = args.get("edits")
                        field_path = args.get("field_path")
                        value = args.get("value")
                        cv_patch = args.get("cv_patch")
                        applied = 0
                        if isinstance(edits, list):
                            for e in edits:
                                fp = e.get("field_path")
                                if not fp:
                                    continue
                                store.update_field(str(sid), fp, e.get("value"))
                                applied += 1
                        if isinstance(cv_patch, dict) and cv_patch:
                            for fp, v in cv_patch.items():
                                store.update_field(str(sid), str(fp), v)
                                applied += 1
                        if field_path:
                            store.update_field(str(sid), str(field_path), value)
                            applied += 1

                        total_applied = applied + confirm_applied
                        if total_applied == 0:
                            tool_payload = {
                                "error": "no_op",
                                "message": "No updates were applied. Provide at least one of: field_path+value, edits[], cv_patch, or confirm{}.",
                            }
                        else:
                            s2 = store.get_session(str(sid)) or s
                            cv2 = s2.get("cv_data") or {}
                            meta3 = s2.get("metadata") or {}
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "edits_applied": applied,
                                "confirm_applied": bool(confirm_applied),
                                "readiness": _compute_readiness(cv2, meta3 if isinstance(meta3, dict) else {}),
                            }
                elif name == "validate_cv":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        out = _validate_cv_data_for_tool(cv)
                        tool_payload = {"success": True, "session_id": sid, **out, "readiness": _compute_readiness(cv, s.get("metadata") or {})}
                elif name == "cv_session_search":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        q = str(args.get("q") or "")
                        try:
                            limit = int(args.get("limit") or 20)
                        except Exception:
                            limit = 20
                        limit = max(1, min(limit, 50))
                        tool_payload = {"success": True, "session_id": sid, **_cv_session_search_hits(session=s, q=q, limit=limit)}
                elif name == "generate_context_pack_v2":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, pack2 = _tool_generate_context_pack_v2(
                            session_id=str(sid),
                            phase=str(args.get("phase") or "preparation"),
                            job_posting_text=str(args.get("job_posting_text") or "") or None,
                            max_pack_chars=int(args.get("max_pack_chars") or 12000),
                            session=s,
                        )
                        tool_payload = pack2 if status == 200 else {"error": pack2.get("error") if isinstance(pack2, dict) else "pack_failed"}
                elif name == "preview_html":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        cv = s.get("cv_data") or {}
                        tool_payload = {"success": True, "session_id": sid, **_render_html_for_tool(cv, inline_css=bool(args.get("inline_css", True)))}
                elif name == "generate_cv_from_session":
                    sid = args.get("session_id") or session_id
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, payload, content_type = _tool_generate_cv_from_session(
                            session_id=str(sid),
                            language=str(args.get("language") or "").strip() or None,
                            client_context=None,
                            session=s,
                        )
                        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)) and status == 200:
                            pdf_bytes = bytes(payload)
                            tool_payload = {"success": True, "session_id": sid, "pdf_base64_length": len(base64.b64encode(pdf_bytes))}
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "generate_failed"}
                else:
                    tool_payload = {"error": f"Unknown tool: {name}"}
            except Exception as e:
                tool_payload = {"error": f"tool_exec_failed: {e}"}

            tool_end = time.time()
            run_summary["steps"].append(
                {
                    "step": "tool",
                    "tool": str(name),
                    "duration_ms": int((tool_end - tool_start) * 1000),
                    "ok": isinstance(tool_payload, dict) and not tool_payload.get("error"),
                }
            )

            tool_output_for_model = _sanitize_tool_output_for_model(str(name), tool_payload)
            call_id = getattr(call, "call_id", None) or getattr(call, "id", None) or ""
            context.append({"type": "function_call_output", "call_id": call_id, "output": tool_output_for_model})

        turn_trace.append(
            {
                "turn": model_call_idx,
                "stage": stage,
                "phase": phase,
                "tools_called": tool_names,
                "tool_calls_count": len(tool_names),
                "readiness": readiness,
                "assistant_text_chars": len(out_text),
            }
        )

    # If output looks truncated near cap, do one continuation (no tools).
    if out_text and _looks_truncated(out_text):
        try:
            cont = client.responses.create(
                **{
                    **req_base,
                    "input": context + [{"role": "user", "content": "Continue from where you stopped. Do not repeat."}],
                    "tools": [],
                    "max_output_tokens": min(1024, _responses_max_output_tokens(stage)),
                }
            )
            cont_text = getattr(cont, "output_text", "") or ""
            if cont_text:
                out_text = f"{out_text.rstrip()}\n\n{cont_text.lstrip()}"
                last_response_id = getattr(cont, "id", None) or last_response_id
        except Exception:
            pass

    return out_text or "Done.", turn_trace, run_summary, last_response_id, pdf_bytes


def _tool_process_cv_orchestrated(params: dict) -> tuple[int, dict]:
    """
    Backend-owned orchestration entrypoint (thin UI client).
    """
    trace_id = str(params.get("trace_id") or uuid.uuid4())
    message = str(params.get("message") or "").strip()
    docx_base64 = str(params.get("docx_base64") or "")
    session_id = str(params.get("session_id") or "").strip()
    job_posting_text = (str(params.get("job_posting_text") or "").strip() or None)
    job_posting_url = (str(params.get("job_posting_url") or "").strip() or None)
    language = str(params.get("language") or "en").strip() or "en"
    client_context = params.get("client_context") if isinstance(params.get("client_context"), dict) else None

    if not message:
        return 400, {"success": False, "error": "message is required", "trace_id": trace_id}

    # Intent detection: only look at the first couple lines (users paste job ads that can contain "final/pdf").
    intent_header = "\n".join(message.splitlines()[:3]).lower()
    wants_generate = any(x in intent_header for x in ("generate", "go ahead", "provide me cv", "pdf", "proceed", "final"))

    if (job_posting_url and not job_posting_text) and not wants_generate:
        return 200, {
            "success": True,
            "trace_id": trace_id,
            "session_id": session_id or None,
            "assistant_text": "I could not fetch the job posting text. Please paste the full job description (responsibilities + requirements + title/company).",
            "run_summary": {"trace_id": trace_id, "steps": [{"step": "ask_for_job_text"}]},
            "turn_trace": [],
        }

    # Ensure session exists if docx provided.
    if not session_id and docx_base64:
        status, created = _tool_extract_and_store_cv(
            docx_base64=docx_base64,
            language=language,
            extract_photo_flag=bool(params.get("extract_photo", True)),
            job_posting_url=job_posting_url,
            job_posting_text=job_posting_text,
        )
        if status != 200:
            return status, {"success": False, "trace_id": trace_id, "error": created.get("error") if isinstance(created, dict) else "extract_failed"}
        session_id = str(created.get("session_id") or "")

    if not session_id:
        return 200, {"success": True, "trace_id": trace_id, "assistant_text": "Please upload your CV DOCX to start.", "run_summary": {"trace_id": trace_id, "steps": [{"step": "ask_for_docx"}]}, "turn_trace": []}

    # Validate session exists
    store = CVSessionStore()
    sess = store.get_session(session_id)
    if not sess:
        return 200, {"success": True, "trace_id": trace_id, "assistant_text": "Your session is no longer available. Please re-upload your CV DOCX to start a new session.", "session_id": None, "run_summary": {"trace_id": trace_id, "steps": [{"step": "session_missing"}]}, "turn_trace": []}

    # Keep metadata language in sync with user preference (stateless calls).
    if isinstance(sess.get("metadata"), dict) and language:
        meta = dict(sess.get("metadata") or {})
        if meta.get("language") != language:
            meta["language"] = language
            store.update_session(session_id, (sess.get("cv_data") or {}), meta)
            sess = store.get_session(session_id) or sess

    readiness = _compute_readiness(sess.get("cv_data") or {}, sess.get("metadata") or {})
    # If the user asked to generate, run in generate_pdf stage; deterministic gating prevents premature PDF creation.
    stage = "generate_pdf" if wants_generate else "review_session"

    max_model_calls = int(os.environ.get("CV_MAX_MODEL_CALLS", os.environ.get("CV_MAX_TURNS", "5")) or 5)
    max_model_calls = max(1, min(max_model_calls, 5))

    # Best-effort: append user event (for semantic debugging).
    try:
        store.append_event(session_id, {"type": "user_message", "trace_id": trace_id, "stage": stage, "text": message[:6000]})
    except Exception:
        pass

    assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes = _run_responses_tool_loop_v2(
        user_message=message,
        session_id=session_id,
        stage=stage,
        job_posting_text=job_posting_text,
        trace_id=trace_id,
        max_model_calls=max_model_calls,
    )

    # Best-effort: append assistant event (pairs user+assistant in event_log).
    try:
        store.append_event(
            session_id,
            {
                "type": "assistant_message",
                "trace_id": trace_id,
                "stage": stage,
                "text": (assistant_text or "")[:9000],
                "run_summary": {"model_calls": run_summary.get("model_calls"), "steps": run_summary.get("steps")[-10:] if isinstance(run_summary.get("steps"), list) else []},
            },
        )
    except Exception:
        pass

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else ""
    return 200, {
        "success": True,
        "trace_id": trace_id,
        "session_id": session_id,
        "stage": stage,
        "assistant_text": assistant_text,
        "pdf_base64": pdf_base64,
        "last_response_id": last_response_id,
        "run_summary": run_summary,
        "turn_trace": turn_trace,
        "client_context_keys": list(client_context.keys())[:20] if client_context else None,
    }


def _cv_session_search_hits(*, session: dict, q: str, limit: int) -> dict:
    """Pure helper: build bounded search hits from a session dict (no storage I/O)."""
    q = (q or "").lower().strip()
    limit = max(1, min(int(limit or 20), 50))

    hits: list[dict] = []

    def _add_hit(source: str, field_path: str, value: Any) -> None:
        preview = ""
        if isinstance(value, str):
            preview = value[:240]
        elif isinstance(value, (int, float)):
            preview = str(value)
        elif isinstance(value, list):
            preview = json.dumps(value[:2], ensure_ascii=False)[:240]
        elif isinstance(value, dict):
            preview = json.dumps(value, ensure_ascii=False)[:240]
        if q and q not in preview.lower():
            return
        hits.append({"source": source, "field_path": field_path, "preview": preview})

    meta = session.get("metadata") or {}
    docx_prefill = meta.get("docx_prefill_unconfirmed") or {}
    cv_data = session.get("cv_data") or {}

    for fp in ["full_name", "email", "phone"]:
        if fp in docx_prefill:
            _add_hit("docx_prefill_unconfirmed", fp, docx_prefill[fp])
        if fp in cv_data:
            _add_hit("cv_data", fp, cv_data.get(fp))

    def _walk_list(lst: Any, base: str, source: str) -> None:
        if not isinstance(lst, list):
            return
        for idx, item in enumerate(lst):
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                _add_hit(source, f"{base}[{idx}].{k}", v)

    _walk_list(docx_prefill.get("education"), "docx.education", "docx_prefill_unconfirmed")
    _walk_list(cv_data.get("education"), "education", "cv_data")
    _walk_list(docx_prefill.get("work_experience"), "docx.work_experience", "docx_prefill_unconfirmed")
    _walk_list(cv_data.get("work_experience"), "work_experience", "cv_data")

    events = meta.get("event_log") or []
    if isinstance(events, list):
        for i, e in enumerate(events[-20:]):
            _add_hit("event_log", f"event_log[-{min(20, len(events))}+{i}]", e)

    truncated = False
    if len(hits) > limit:
        hits = hits[:limit]
        truncated = True

    return {"hits": hits, "truncated": truncated}


def _validate_cv_data_for_tool(cv_data: dict) -> dict:
    """Deterministic validation for tool use (no rendering)."""
    cv_data = normalize_cv_data(cv_data or {})
    is_schema_valid, schema_errors = validate_canonical_schema(cv_data, strict=True)
    validation_result = validate_cv(cv_data)
    return {
        "schema_valid": bool(is_schema_valid),
        "schema_errors": schema_errors,
        "validation": _serialize_validation_result(validation_result),
    }


def _render_html_for_tool(cv_data: dict, *, inline_css: bool = True) -> dict:
    """Render HTML for tool use (debug/preview)."""
    cv_data = normalize_cv_data(cv_data or {})
    html_content = render_html(cv_data, inline_css=inline_css)
    return {"html": html_content, "html_length": len(html_content or "")}


def _tool_extract_and_store_cv(*, docx_base64: str, language: str, extract_photo_flag: bool, job_posting_url: str | None, job_posting_text: str | None) -> tuple[int, dict]:
    if not docx_base64:
        return 400, {"error": "docx_base64 is required"}

    try:
        docx_bytes = base64.b64decode(docx_base64)
    except Exception as e:
        return 400, {"error": "Invalid base64 encoding", "details": str(e)}

    # Start-fresh semantics are provided by new session IDs; do not purge global storage.
    # Best-effort: cleanup expired sessions to keep local dev storage tidy.
    store = CVSessionStore()
    try:
        deleted = store.cleanup_expired()
        if deleted:
            logging.info(f"Expired sessions cleaned: {deleted}")
    except Exception:
        pass

    extracted_photo = None
    photo_extracted = False
    photo_storage = "none"
    photo_omitted_reason = None
    if extract_photo_flag:
        try:
            extracted_photo = extract_first_photo_from_docx_bytes(docx_bytes)
            photo_extracted = bool(extracted_photo)
            logging.info(f"Photo extraction: {'success' if extracted_photo else 'no photo found'}")
        except Exception as e:
            photo_omitted_reason = f"photo_extraction_failed: {e}"
            logging.warning(f"Photo extraction failed: {e}")

    prefill = prefill_cv_from_docx_bytes(docx_bytes)

    cv_data = {
        "full_name": "",
        "email": "",
        "phone": "",
        "address_lines": [],
        "photo_url": "",
        "profile": "",
        "work_experience": [],
        "education": [],
        "further_experience": [],
        "languages": [],
        "it_ai_skills": [],
        "interests": "",
        "references": "",
    }

    prefill_summary = {
        "has_name": bool(prefill.get("full_name")),
        "has_email": bool(prefill.get("email")),
        "has_phone": bool(prefill.get("phone")),
        "work_experience_count": len(prefill.get("work_experience", []) or []),
        "education_count": len(prefill.get("education", []) or []),
        "languages_count": len(prefill.get("languages", []) or []),
        "it_ai_skills_count": len(prefill.get("it_ai_skills", []) or []),
        "interests_chars": len(str(prefill.get("interests", "") or "")),
    }

    metadata: dict[str, Any] = {
        "language": (language or "en"),
        "created_from": "docx",
        "prefill_summary": prefill_summary,
        "docx_prefill_unconfirmed": prefill,
        "confirmed_flags": {
            "contact_confirmed": False,
            "education_confirmed": False,
            "confirmed_at": None,
        },
    }
    if job_posting_url:
        metadata["job_posting_url"] = job_posting_url
    if job_posting_text:
        metadata["job_posting_text"] = str(job_posting_text)[:20000]

    try:
        session_id = store.create_session(cv_data, metadata)
        logging.info(f"Session created: {session_id}")
    except Exception as e:
        logging.error(f"Session creation failed: {e}")
        return 500, {"error": "Failed to create session", "details": str(e)}

    if photo_extracted and extracted_photo:
        try:
            blob_store = CVBlobStore()
            ptr = blob_store.upload_photo_bytes(extracted_photo)
            try:
                session = store.get_session(session_id)
                if session:
                    meta2 = session.get("metadata") or {}
                    if isinstance(meta2, dict):
                        meta2 = dict(meta2)
                        meta2["photo_blob"] = {
                            "container": ptr.container,
                            "blob_name": ptr.blob_name,
                            "content_type": ptr.content_type,
                        }
                        store.update_session(session_id, cv_data, meta2)
                        photo_storage = "blob"
            except Exception:
                pass
        except Exception as e:
            logging.warning(f"Photo blob storage failed: {e}")
    elif extract_photo_flag and not photo_extracted:
        photo_omitted_reason = photo_omitted_reason or "no_photo_found_in_docx"

    summary = {
        "has_photo": photo_extracted,
        "fields_populated": [k for k, v in cv_data.items() if v],
        "fields_empty": [k for k, v in cv_data.items() if not v],
    }

    session = store.get_session(session_id)
    return 200, {
        "success": True,
        "session_id": session_id,
        "cv_data_summary": summary,
        "photo_extracted": photo_extracted,
        "photo_storage": photo_storage,
        "photo_omitted_reason": photo_omitted_reason,
        "expires_at": session["expires_at"] if session else None,
    }


def _tool_generate_context_pack_v2(*, session_id: str, phase: str, job_posting_text: str | None, max_pack_chars: int, session: dict) -> tuple[int, dict]:
    if phase not in ["preparation", "confirmation", "execution"]:
        return 400, {"error": "Invalid phase. Must be 'preparation', 'confirmation', or 'execution'"}

    cv_data = session.get("cv_data") or {}
    metadata = session.get("metadata") or {}
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        metadata["session_id"] = session_id

    pack = build_context_pack_v2(
        phase=phase,
        cv_data=cv_data,
        job_posting_text=job_posting_text,
        session_metadata=metadata,
        max_pack_chars=max_pack_chars,
    )
    return 200, pack


def _tool_generate_cv_from_session(*, session_id: str, language: str | None, client_context: dict | None, session: dict) -> tuple[int, dict | bytes, str]:
    meta = session.get("metadata") or {}
    cv_data = session.get("cv_data") or {}
    lang = language or (meta.get("language") if isinstance(meta, dict) else None) or "en"

    readiness = _compute_readiness(cv_data, meta if isinstance(meta, dict) else {})
    run_summary = {
        "stage": "generate_pdf",
        "can_generate": readiness.get("can_generate"),
        "required_present": readiness.get("required_present"),
        "confirmed_flags": readiness.get("confirmed_flags"),
    }
    if not readiness.get("can_generate"):
        return (
            400,
            {
                "error": "readiness_not_met",
                "message": "Cannot generate until required fields are present and confirmed.",
                "readiness": readiness,
                "run_summary": run_summary,
            },
            "application/json",
        )

    # Best-effort: record a generation attempt.
    try:
        store = CVSessionStore()
        store.append_event(
            session_id,
            {
                "type": "generate_cv_from_session_attempt",
                "language": lang,
                "client_context": client_context if isinstance(client_context, dict) else None,
            },
        )
    except Exception:
        pass

    # Inject photo from Blob at render time.
    try:
        photo_blob = meta.get("photo_blob") if isinstance(meta, dict) else None
        if photo_blob and not cv_data.get("photo_url"):
            ptr = BlobPointer(
                container=photo_blob.get("container", ""),
                blob_name=photo_blob.get("blob_name", ""),
                content_type=photo_blob.get("content_type", "application/octet-stream"),
            )
            if ptr.container and ptr.blob_name:
                data = CVBlobStore(container=ptr.container).download_bytes(ptr)
                b64 = base64.b64encode(data).decode("ascii")
                cv_data = dict(cv_data)
                cv_data["photo_url"] = f"data:{ptr.content_type};base64,{b64}"
    except Exception as e:
        logging.warning(f"Failed to inject photo from blob for session {session_id}: {e}")

    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    if not is_valid:
        return 400, {"error": "CV data validation failed", "validation_errors": errors, "run_summary": run_summary}, "application/json"

    cv_data = normalize_cv_data(cv_data)
    validation_result = validate_cv(cv_data)
    if not validation_result.is_valid:
        return (
            400,
            {"error": "Validation failed", "validation": _serialize_validation_result(validation_result), "run_summary": run_summary},
            "application/json",
        )

    try:
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        logging.info(f"PDF generated from session {session_id}: {len(pdf_bytes)} bytes")
        return 200, pdf_bytes, "application/pdf"
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return 500, {"error": "PDF generation failed", "details": str(e), "run_summary": run_summary}, "application/json"


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Health check requested")
    return _json_response({"status": "healthy", "service": "CV Generator API", "version": "1.0"}, status_code=200)


@app.route(route="cv-tool-call-handler", methods=["POST"])
def cv_tool_call_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Single tool dispatcher.

    Request:
      {
        "tool_name": "<tool>",
        "session_id": "<uuid>" (optional for some tools),
        "params": {...}
      }
    """
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON"}, status_code=400)

    tool_name = str(body.get("tool_name") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    params = body.get("params") or {}

    if not tool_name:
        return _json_response({"error": "tool_name is required"}, status_code=400)
    if not isinstance(params, dict):
        return _json_response({"error": "params must be an object"}, status_code=400)

    if tool_name == "cleanup_expired_sessions":
        try:
            store = CVSessionStore()
            deleted = store.cleanup_expired()
            return _json_response({"success": True, "tool_name": tool_name, "deleted_count": deleted}, status_code=200)
        except Exception as e:
            return _json_response({"error": "Cleanup failed", "details": str(e)}, status_code=500)

    if tool_name == "extract_and_store_cv":
        docx_base64 = str(params.get("docx_base64") or "")
        language = str(params.get("language") or "en")
        extract_photo_flag = bool(params.get("extract_photo", True))
        job_posting_url = (str(params.get("job_posting_url") or "").strip() or None)
        job_posting_text = (str(params.get("job_posting_text") or "").strip() or None)
        status, payload = _tool_extract_and_store_cv(
            docx_base64=docx_base64,
            language=language,
            extract_photo_flag=extract_photo_flag,
            job_posting_url=job_posting_url,
            job_posting_text=job_posting_text,
        )
        return _json_response(payload, status_code=status)

    if tool_name == "process_cv_orchestrated":
        status, payload = _tool_process_cv_orchestrated(params)
        return _json_response(payload, status_code=status)

    if not session_id:
        return _json_response({"error": "session_id is required"}, status_code=400)

    # Most tools require session lookup; do it once.
    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        return _json_response({"error": "Failed to retrieve session", "details": str(e)}, status_code=500)

    if not session:
        return _json_response({"error": "Session not found or expired"}, status_code=404)

    if tool_name == "get_cv_session":
        client_context = params.get("client_context")
        try:
            store.append_event(
                session_id,
                {"type": "get_cv_session", "client_context": client_context if isinstance(client_context, dict) else None},
            )
        except Exception:
            pass

        cv_data = session.get("cv_data") or {}
        readiness = _compute_readiness(cv_data, session.get("metadata") or {})

        interaction_history: list[dict] = []
        try:
            meta = session.get("metadata") or {}
            events = meta.get("event_log") if isinstance(meta, dict) else None
            if isinstance(events, list):
                for e in events[-80:]:
                    if not isinstance(e, dict):
                        continue
                    if e.get("type") not in ("user_message", "assistant_message"):
                        continue
                    interaction_history.append(
                        {
                            "type": e.get("type"),
                            "at": e.get("at") or e.get("timestamp"),
                            "trace_id": e.get("trace_id"),
                            "stage": e.get("stage"),
                            "text": e.get("text"),
                        }
                    )
        except Exception:
            interaction_history = []
        payload = {
            "success": True,
            "session_id": session_id,
            "cv_data": cv_data,
            "metadata": session.get("metadata"),
            "expires_at": session.get("expires_at"),
            "readiness": readiness,
            "interaction_history": interaction_history,
            "_metadata": {
                "version": session.get("version"),
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
                "content_signature": {
                    "work_exp_count": len(cv_data.get("work_experience", [])) if isinstance(cv_data, dict) else 0,
                    "education_count": len(cv_data.get("education", [])) if isinstance(cv_data, dict) else 0,
                    "profile_length": len(str(cv_data.get("profile", ""))) if isinstance(cv_data, dict) else 0,
                    "skills_count": len(cv_data.get("it_ai_skills", [])) if isinstance(cv_data, dict) else 0,
                },
            },
        }
        return _json_response(payload, status_code=200)

    if tool_name == "update_cv_field":
        try:
            applied = 0
            client_context = params.get("client_context")
            edits = params.get("edits")
            field_path = params.get("field_path")
            value = params.get("value")
            cv_patch = params.get("cv_patch")
            confirm_flags = params.get("confirm")

            is_batch = isinstance(edits, list) and len(edits) > 0
            is_patch = isinstance(cv_patch, dict) and len(cv_patch.keys()) > 0
            if not is_batch and not field_path and not is_patch and not confirm_flags:
                return _json_response({"error": "field_path/value or edits[] or cv_patch or confirm is required"}, status_code=400)

            if isinstance(confirm_flags, dict) and confirm_flags:
                try:
                    meta = session.get("metadata") or {}
                    if isinstance(meta, dict):
                        meta = dict(meta)
                        cf = meta.get("confirmed_flags") or {}
                        if not isinstance(cf, dict):
                            cf = {}
                        cf = dict(cf)
                        for k in ("contact_confirmed", "education_confirmed"):
                            if k in confirm_flags:
                                cf[k] = bool(confirm_flags.get(k))
                        if cf.get("contact_confirmed") and cf.get("education_confirmed") and not cf.get("confirmed_at"):
                            cf["confirmed_at"] = _now_iso()
                        meta["confirmed_flags"] = cf
                        store.update_session(session_id, (session.get("cv_data") or {}), meta)
                except Exception:
                    pass

            if is_batch:
                for e in edits:
                    fp = e.get("field_path")
                    if not fp:
                        continue
                    store.update_field(session_id, fp, e.get("value"), client_context=client_context)
                    applied += 1

            if field_path:
                store.update_field(session_id, field_path, value, client_context=client_context)
                applied += 1

            if is_patch:
                for k, v in cv_patch.items():
                    store.update_field(session_id, k, v, client_context=client_context)
                    applied += 1

            updated_session = store.get_session(session_id)
            if updated_session:
                return _json_response(
                    {
                        "success": True,
                        "session_id": session_id,
                        **({"field_updated": field_path} if (field_path and not is_batch) else {}),
                        **({"edits_applied": applied} if is_batch else {}),
                        "updated_version": updated_session.get("version"),
                        "updated_at": updated_session.get("updated_at"),
                    },
                    status_code=200,
                )
            return _json_response({"success": True, "session_id": session_id, "edits_applied": applied}, status_code=200)
        except Exception as e:
            return _json_response({"error": "Failed to update field", "details": str(e)}, status_code=500)

    if tool_name == "generate_context_pack_v2":
        phase = str(params.get("phase") or "")
        job_posting_text = params.get("job_posting_text")
        try:
            max_pack_chars = int(params.get("max_pack_chars") or 12000)
        except Exception:
            max_pack_chars = 12000
        status, payload = _tool_generate_context_pack_v2(
            session_id=session_id,
            phase=phase,
            job_posting_text=str(job_posting_text) if isinstance(job_posting_text, str) else None,
            max_pack_chars=max_pack_chars,
            session=session,
        )
        return _json_response(payload, status_code=status)

    if tool_name == "cv_session_search":
        q = str(params.get("q") or "")
        try:
            limit = int(params.get("limit", 20))
        except Exception:
            limit = 20
        limit = max(1, min(limit, 50))
        result = _cv_session_search_hits(session=session, q=q, limit=limit)
        return _json_response(
            {
                "success": True,
                "tool_name": tool_name,
                "session_id": session_id,
                "hits": result["hits"],
                "truncated": result["truncated"],
            },
            status_code=200,
        )

    if tool_name == "validate_cv":
        cv_data = session.get("cv_data") or {}
        out = _validate_cv_data_for_tool(cv_data)
        readiness = _compute_readiness(cv_data, session.get("metadata") or {})
        return _json_response(
            {
                "success": True,
                "tool_name": tool_name,
                "session_id": session_id,
                **out,
                "readiness": readiness,
            },
            status_code=200,
        )

    if tool_name == "preview_html":
        inline_css = bool(params.get("inline_css", True))
        cv_data = session.get("cv_data") or {}
        out = _render_html_for_tool(cv_data, inline_css=inline_css)
        return _json_response({"success": True, "tool_name": tool_name, "session_id": session_id, **out}, status_code=200)

    if tool_name == "generate_cv_from_session":
        client_context = params.get("client_context")
        language = str(params.get("language") or "").strip() or None
        status, payload, content_type = _tool_generate_cv_from_session(
            session_id=session_id,
            language=language,
            client_context=client_context if isinstance(client_context, dict) else None,
            session=session,
        )
        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)):
            return func.HttpResponse(body=payload, mimetype="application/pdf", status_code=status)
        if isinstance(payload, dict):
            return _json_response(payload, status_code=status)
        return _json_response({"error": "Unexpected payload type"}, status_code=500)

    return _json_response({"error": "Unknown tool_name", "tool_name": tool_name}, status_code=400)
