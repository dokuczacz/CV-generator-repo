from __future__ import annotations

import json
import logging
import os
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable

from openai import OpenAI


@dataclass(frozen=True)
class SchemaRepairDeps:
    now_iso: Callable[[], str]
    schema_repair_instructions: Callable[..., str]


def sanitize_tool_output_for_model(tool_name: str, payload: Any) -> str:
    try:
        if tool_name == "generate_cv_from_session":
            if isinstance(payload, dict):
                return json.dumps(
                    {
                        "ok": payload.get("success") is True and bool(payload.get("pdf_ref")),
                        "success": payload.get("success"),
                        "error": payload.get("error"),
                        "pdf_ref": payload.get("pdf_ref"),
                        "pdf_sha256": payload.get("pdf_sha256"),
                        "pdf_size_bytes": payload.get("pdf_size_bytes"),
                        "render_ms": payload.get("render_ms"),
                        "validation_passed": payload.get("validation_passed"),
                        "pdf_pages": payload.get("pdf_pages"),
                    },
                    ensure_ascii=False,
                )
        if tool_name == "generate_cover_letter_from_session":
            if isinstance(payload, dict):
                return json.dumps(
                    {
                        "ok": payload.get("success") is True and bool(payload.get("pdf_ref")),
                        "success": payload.get("success"),
                        "error": payload.get("error"),
                        "pdf_ref": payload.get("pdf_ref"),
                        "pdf_size_bytes": payload.get("pdf_size_bytes"),
                    },
                    ensure_ascii=False,
                )
        if tool_name == "get_pdf_by_ref":
            if isinstance(payload, dict):
                return json.dumps(
                    {
                        "ok": payload.get("success") is True and bool(payload.get("pdf_ref")),
                        "success": payload.get("success"),
                        "error": payload.get("error"),
                        "pdf_ref": payload.get("pdf_ref"),
                        "pdf_size_bytes": payload.get("pdf_size_bytes"),
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


def schema_repair_response(
    *,
    client: OpenAI,
    req_base: dict,
    base_context: list[Any],
    trace_id: str,
    stage: str,
    model_call_idx: int,
    deps: SchemaRepairDeps,
) -> Any | None:
    repair_context = list(base_context)
    repair_context.append(
        {
            "role": "developer",
            "content": deps.schema_repair_instructions(stage=stage, parse_error=None),
        }
    )
    logging.warning(
        "Schema repair attempt trace_id=%s stage=%s call_idx=%s",
        trace_id,
        stage,
        model_call_idx,
    )
    try:
        resp_obj = client.responses.create(**{**req_base, "input": repair_context})
        if str(os.environ.get("CV_OPENAI_TRACE", "0")).strip() == "1":
            try:
                trace_dir = str(os.environ.get("CV_OPENAI_TRACE_DIR") or "tmp/openai_trace").strip()
                os.makedirs(trace_dir, exist_ok=True)
                index_path = os.path.join(trace_dir, "openai_trace.jsonl")
                rid = getattr(resp_obj, "id", None)
                with open(index_path, "a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "ts_utc": deps.now_iso(),
                                "trace_id": trace_id,
                                "session_id": None,
                                "stage": stage,
                                "phase": None,
                                "call_seq": f"schema_repair_{model_call_idx}",
                                "request": {
                                    "has_prompt": bool(req_base.get("prompt")),
                                    "prompt_id": (req_base.get("prompt") or {}).get("id")
                                    if isinstance(req_base.get("prompt"), dict)
                                    else None,
                                    "has_instructions": bool(req_base.get("instructions")),
                                    "model": req_base.get("model"),
                                    "store": req_base.get("store"),
                                    "max_output_tokens": req_base.get("max_output_tokens"),
                                    "tools_count": len(req_base.get("tools") or []),
                                    "response_format": "present" if bool(req_base.get("response_format")) else None,
                                },
                                "response": {"id": rid, "output_text_len": len(getattr(resp_obj, "output_text", "") or "")},
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                if rid:
                    logging.info(
                        "openai_response_id=%s trace_id=%s stage=%s call_seq=%s",
                        str(rid),
                        trace_id,
                        stage,
                        f"schema_repair_{model_call_idx}",
                    )
            except Exception:
                pass
        return resp_obj
    except Exception as exc:
        logging.warning(
            "Schema repair API call failed trace_id=%s stage=%s call_idx=%s error=%s",
            trace_id,
            stage,
            model_call_idx,
            exc,
        )
        return None


@dataclass(frozen=True)
class ResponsesLoopDeps:
    use_structured_output: bool
    cv_single_call_execution: bool
    get_openai_prompt_id: Callable[[str], str | None]
    require_openai_prompt_id: Callable[[], bool]
    get_session_store: Callable[[], Any]
    compute_readiness: Callable[[dict, dict], dict]
    build_context_pack_v2: Callable[..., dict]
    format_context_pack_with_delimiters: Callable[[dict], str]
    tool_schemas_for_responses: Callable[..., list[dict]]
    responses_max_output_tokens: Callable[[str], int]
    stage_prompt: Callable[[str], str]
    should_log_prompt_debug: Callable[[], bool]
    describe_responses_input: Callable[[list[Any]], Any]
    parse_structured_response: Callable[[str], Any]
    format_user_message_for_ui: Callable[[Any], dict]
    schema_repair_instructions: Callable[..., str]
    now_iso: Callable[[], str]
    validate_cv_data_for_tool: Callable[[dict], dict]
    cv_session_search_hits: Callable[..., dict]
    tool_generate_context_pack_v2: Callable[..., tuple[int, dict]]
    render_html_for_tool: Callable[..., dict]
    tool_generate_cv_from_session: Callable[..., tuple[int, dict | bytes, str]]
    tool_generate_cover_letter_from_session: Callable[..., tuple[int, dict | bytes, str]]
    tool_get_pdf_by_ref: Callable[..., tuple[int, dict | bytes, str]]
    looks_truncated: Callable[[str], bool]

def run_responses_tool_loop_v2(
    *,
    user_message: str,
    session_id: str,
    stage: str,
    job_posting_text: str | None,
    trace_id: str,
    max_model_calls: int,
    execution_mode: bool = False,
    deps: ResponsesLoopDeps,
) -> tuple[str, list[dict], dict, str | None, bytes | None]:
    """
    Backend-owned, stateless Responses tool-loop.

    Design goals:
    - One backend HTTP request can include multiple model calls + tool calls (hard cap <= 5 model calls).
    - Session persistence is deterministic via tools; the model never "assumes" updates without calling tools.

    Wave 0.3: execution_mode=True enforces single-call execution contract for generate_pdf stage.

    Returns: (assistant_text, turn_trace, run_summary, last_response_id, pdf_bytes)
    """
    _get_openai_prompt_id = deps.get_openai_prompt_id
    _require_openai_prompt_id = deps.require_openai_prompt_id
    _get_session_store = deps.get_session_store
    _compute_readiness = deps.compute_readiness
    build_context_pack_v2 = deps.build_context_pack_v2
    format_context_pack_with_delimiters = deps.format_context_pack_with_delimiters
    _tool_schemas_for_responses = deps.tool_schemas_for_responses
    _responses_max_output_tokens = deps.responses_max_output_tokens
    _stage_prompt = deps.stage_prompt
    _should_log_prompt_debug = deps.should_log_prompt_debug
    _describe_responses_input = deps.describe_responses_input
    parse_structured_response = deps.parse_structured_response
    format_user_message_for_ui = deps.format_user_message_for_ui
    _schema_repair_instructions = deps.schema_repair_instructions
    _now_iso = deps.now_iso
    _validate_cv_data_for_tool = deps.validate_cv_data_for_tool
    _cv_session_search_hits = deps.cv_session_search_hits
    _tool_generate_context_pack_v2 = deps.tool_generate_context_pack_v2
    _render_html_for_tool = deps.render_html_for_tool
    _tool_generate_cv_from_session = deps.tool_generate_cv_from_session
    _tool_generate_cover_letter_from_session = deps.tool_generate_cover_letter_from_session
    _tool_get_pdf_by_ref = deps.tool_get_pdf_by_ref
    _looks_truncated = deps.looks_truncated
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt_id = _get_openai_prompt_id(stage)
    model_override = (os.environ.get("OPENAI_MODEL") or "").strip() or None
    # Tool-loop requires persisted response items for follow-up calls; default ON.
    store_flag = str(os.environ.get("OPENAI_STORE", "1")).strip() == "1"
    # Structured outputs: when enabled, model returns JSON with tool calls embedded (experimental)
    use_structured_output = deps.use_structured_output

    # Wave 0.3: Single-call execution contract
    # Override max_model_calls in execution mode to enforce exactly 1 OpenAI call
    if execution_mode and deps.cv_single_call_execution:
        max_model_calls = 1
        logging.info(f"Execution mode: limiting to 1 OpenAI call (trace_id={trace_id})")

    run_summary: dict = {"trace_id": trace_id, "steps": [], "max_model_calls": max_model_calls, "model_calls": 0, "execution_mode": execution_mode}
    turn_trace: list[dict] = []
    pdf_bytes: bytes | None = None
    last_response_id: str | None = None

    store = _get_session_store()
    session = store.get_session(session_id)
    if not session:
        logging.warning(
            "Session missing before OpenAI call trace_id=%s session_id=%s",
            trace_id,
            session_id,
        )
        return (
            "Your session is no longer available. Please re-upload your CV DOCX to start a new session.",
            [],
            run_summary,
            None,
            None,
        )

    phase = "execution" if stage == "generate_pdf" else "preparation"
    if _require_openai_prompt_id() and not prompt_id:
        return (
            "Backend configuration error: OPENAI_PROMPT_ID is required but not set. "
            "Set OPENAI_PROMPT_ID in local.settings.json (Values) or your environment.",
            [],
            run_summary,
            None,
            None,
        )

    def _openai_trace_enabled() -> bool:
        return str(os.environ.get("CV_OPENAI_TRACE", "0")).strip() == "1"

    def _openai_trace_dir() -> str:
        return str(os.environ.get("CV_OPENAI_TRACE_DIR") or "tmp/openai_trace").strip()

    def _sha256_text(s: str) -> str:
        try:
            return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()
        except Exception:
            return ""

    def _summarize_req_for_trace(req_obj: dict) -> dict:
        try:
            input_items = req_obj.get("input") or []
            summarized_inputs: list[dict] = []
            for item in input_items:
                if not isinstance(item, dict):
                    summarized_inputs.append({"item_type": type(item).__name__})
                    continue
                role = item.get("role") or item.get("type")
                content = item.get("content", "")
                if isinstance(content, str):
                    summarized_inputs.append(
                        {
                            "role": role,
                            "content_len": len(content),
                            "content_sha256": _sha256_text(content),
                        }
                    )
                else:
                    summarized_inputs.append({"role": role, "content_type": type(content).__name__})

            tools = req_obj.get("tools") or []
            tool_names: list[str] = []
            for t in tools:
                if isinstance(t, dict) and t.get("name"):
                    tool_names.append(str(t.get("name")))

            prompt_obj = req_obj.get("prompt")
            prompt_id_local = prompt_obj.get("id") if isinstance(prompt_obj, dict) else None
            return {
                "has_prompt": bool(prompt_obj),
                "prompt_id": prompt_id_local,
                "has_instructions": bool(req_obj.get("instructions")),
                "model": req_obj.get("model"),
                "store": req_obj.get("store"),
                "max_output_tokens": req_obj.get("max_output_tokens"),
                "truncation": req_obj.get("truncation"),
                "tools_count": len(tools),
                "tool_names": tool_names[:40],
                "input_items": summarized_inputs,
                "response_format": "present" if bool(req_obj.get("response_format")) else None,
            }
        except Exception:
            return {"error": "summarize_failed"}

    def _append_openai_trace_record(record: dict) -> None:
        if not _openai_trace_enabled():
            return
        try:
            trace_dir = _openai_trace_dir()
            os.makedirs(trace_dir, exist_ok=True)
            index_path = os.path.join(trace_dir, "openai_trace.jsonl")
            with open(index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _responses_create_with_trace(*, req_obj: dict, call_seq: int) -> Any:
        started_at = time.time()
        resp_obj = client.responses.create(**req_obj)

        response_id = getattr(resp_obj, "id", None)
        out_text_local = getattr(resp_obj, "output_text", "") or ""
        output_items = getattr(resp_obj, "output", None) or []
        tool_calls_local = [item for item in output_items if getattr(item, "type", None) == "function_call"]

        _append_openai_trace_record(
            {
                "ts_utc": _now_iso(),
                "trace_id": trace_id,
                "session_id": session_id,
                "stage": stage,
                "phase": phase,
                "call_seq": call_seq,
                "duration_ms": int((time.time() - started_at) * 1000),
                "request": _summarize_req_for_trace(req_obj),
                "response": {
                    "id": response_id,
                    "output_text_len": len(out_text_local),
                    "tool_calls_count": len(tool_calls_local),
                },
            }
        )
        if _openai_trace_enabled() and response_id:
            logging.info(
                "openai_response_id=%s trace_id=%s stage=%s call_seq=%s",
                str(response_id),
                trace_id,
                stage,
                str(call_seq),
            )
        return resp_obj

    call_seq = 0
    cv_data = session.get("cv_data") or {}
    meta = session.get("metadata") or {}
    readiness = _compute_readiness(cv_data, meta if isinstance(meta, dict) else {})

    pack = build_context_pack_v2(
        phase=phase,
        cv_data=cv_data,
        job_posting_text=job_posting_text,
        session_metadata=meta if isinstance(meta, dict) else {},
        pack_mode="full",
        max_pack_chars=16000,  # Increased for full CV data
    )
    capsule_text = format_context_pack_with_delimiters(pack)

    out_lang = str(meta.get("language") or "").strip() if isinstance(meta, dict) else ""
    readiness_mini = {
        "can_generate": readiness.get("can_generate") if isinstance(readiness, dict) else None,
        "missing": readiness.get("missing") if isinstance(readiness, dict) else None,
        "required_present": readiness.get("required_present") if isinstance(readiness, dict) else None,
    }
    if isinstance(meta, dict) and meta.get("pending_confirmation"):
        readiness_mini["pending_confirmation"] = meta.get("pending_confirmation")

    user_content = (
        f"{user_message}\n\n"
        f"[OUTPUT_LANGUAGE]\n{out_lang}\n\n"
        f"[SESSION_ID]\n{session_id}\n\n"
        f"[READINESS]\n{json.dumps(readiness_mini, ensure_ascii=False)}\n\n"
        f"[CONTEXT_PACK_V2]\n{capsule_text}\n"
        f"\n[STAGE]\n{stage}\n"
        f"[PHASE]\n{phase}\n"
    )

    # Tool permissions are stage-based.
    # - "apply_edits" and "fix_validation" may persist canonical CV changes.
    # - Other stages are read-only.
    allow_persist = stage in ("apply_edits", "fix_validation")
    tools = _tool_schemas_for_responses(allow_persist=allow_persist, stage=stage)
    try:
        tool_names_logged = [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]
        logging.info(
            "trace_id=%s stage=%s phase=%s allow_persist=%s tools=%s store=%s max_tokens=%s",
            trace_id,
            stage,
            phase,
            allow_persist,
            tool_names_logged,
            str(store_flag),
            str(_responses_max_output_tokens(stage)),
        )
    except Exception:
        pass
    req_base: dict = {
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

    # Conditional: structured output (JSON parsing enabled) OR traditional tool calling
    # Note: When using dashboard prompt with structured output, response_format is NOT sent;
    # it's already configured in the dashboard prompt itself.
    if not use_structured_output:
        req_base["tools"] = tools
    if prompt_id:
        req_base["prompt"] = {"id": prompt_id, "variables": {"stage": stage, "phase": phase}}
        # Do not set model when using a dashboard prompt; prompt config owns the model.
    else:
        req_base["instructions"] = "You are a CV assistant operating in a stateless API. Use tools to persist edits."
        # Legacy mode (no dashboard prompt) requires explicit model.
        req_base["model"] = model_override or "gpt-4o-mini"

    # Context is stateful within this single HTTP request.
    # Always include a compact stage hint to anchor the model (even with dashboard prompt).
    context: list[Any] = [
        {"role": "developer", "content": _stage_prompt(stage)},
        {"role": "user", "content": user_content},
    ]

    out_text = ""
    for model_call_idx in range(1, max_model_calls + 1):
        model_start = time.time()
        try:
            if _should_log_prompt_debug():
                try:
                    model_for_log = req_base.get("model") or ""
                    logging.info(
                        "responses.create request trace_id=%s stage=%s phase=%s prompt_id=%s model=%s store=%s call_idx=%s context=%s",
                        trace_id,
                        stage,
                        phase,
                        prompt_id or "",
                        model_for_log,
                        str(store_flag),
                        str(model_call_idx),
                        json.dumps(_describe_responses_input(context), ensure_ascii=False),
                    )
                except Exception:
                    pass
            call_context = list(context)
            call_seq += 1
            resp = _responses_create_with_trace(req_obj={**req_base, "input": call_context}, call_seq=call_seq)
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
        model_elapsed_ms = int((model_end - model_start) * 1000)
        last_response_id = getattr(resp, "id", None) or last_response_id
        
        logging.info(f"Model call {model_call_idx} completed in {model_elapsed_ms}ms (trace_id={trace_id})")
        
        if _should_log_prompt_debug():
            try:
                logging.info(
                    "responses.create response trace_id=%s stage=%s call_idx=%s response_id=%s duration_ms=%s",
                    trace_id,
                    stage,
                    str(model_call_idx),
                    last_response_id or "",
                    model_elapsed_ms,
                )
            except Exception:
                pass

        # Parse structured response (if enabled)
        structured_resp: Any = None
        raw_output_text = ""
        schema_repair_attempted = False

        def _parse_structured_output(text: str) -> CVAssistantResponse | None:
            if not text:
                return None
            # Try direct parse
            try:
                return parse_structured_response(text)
            except Exception:
                pass
            # Try trimming to the outermost JSON object (handles trailing prose)
            try:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    candidate = text[start : end + 1]
                    return parse_structured_response(candidate)
            except Exception:
                pass
            return None

        if use_structured_output:
            raw_output_text = getattr(resp, "output_text", "")
            while raw_output_text:
                structured_resp = _parse_structured_output(raw_output_text)
                if structured_resp:
                    break
                logging.warning(
                    "Failed to parse structured response trace_id=%s stage=%s call_idx=%s error=%s",
                    trace_id,
                    stage,
                    model_call_idx,
                    "parse_failed",
                )
                if not schema_repair_attempted:
                    schema_repair_attempted = True
                    repair_resp = schema_repair_response(
                        client=client,
                        req_base=req_base,
                        base_context=call_context,
                        trace_id=trace_id,
                        stage=stage,
                        model_call_idx=model_call_idx,
                        deps=SchemaRepairDeps(
                            now_iso=_now_iso,
                            schema_repair_instructions=_schema_repair_instructions,
                        ),
                    )
                    if repair_resp:
                        resp = repair_resp
                        run_summary["model_calls"] += 1
                        last_response_id = getattr(resp, "id", None) or last_response_id
                        raw_output_text = getattr(resp, "output_text", "")
                        continue
                    logging.warning(
                        "Schema repair attempt unable to generate a new response trace_id=%s call_idx=%s",
                        trace_id,
                        model_call_idx,
                    )
                raw_output_text = getattr(resp, "output_text", "") or raw_output_text
                break
            if structured_resp:
                # Extract user-facing message
                formatted = format_user_message_for_ui(structured_resp)
                # Convert dict format back to text for backward compatibility (cleaner formatting)
                parts = []
                
                # Main text first
                main_text = formatted.get("text", "").strip()
                if main_text:
                    parts.append(main_text)
                
                # Sections as formatted blocks
                sections = formatted.get("sections") or []
                if sections:
                    for s in sections:
                        section_text = f"### {s['title']}\n{s['content']}"
                        parts.append(section_text)
                
                # Questions as numbered list
                questions = formatted.get("questions") or []
                if questions:
                    q_lines = ["**Please confirm:**"]
                    for idx, q in enumerate(questions, 1):
                        q_lines.append(f"{idx}. {q['question']}")
                        if q.get("options"):
                            for opt in q["options"]:
                                q_lines.append(f"   - {opt}")
                    parts.append("\n".join(q_lines))
                
                out_text = "\n\n".join(parts)
                
                # Log metadata
                if _should_log_prompt_debug():
                    logging.info(
                        "Structured response trace_id=%s response_type=%s confidence=%s validation_status=%s",
                        trace_id,
                        structured_resp.response_type.value,
                        structured_resp.metadata.confidence.value,
                        json.dumps({
                            "schema_valid": structured_resp.metadata.validation_status.schema_valid,
                            "page_count_ok": structured_resp.metadata.validation_status.page_count_ok,
                            "required_fields_present": structured_resp.metadata.validation_status.required_fields_present,
                            "issues": structured_resp.metadata.validation_status.issues
                        })
                    )
                # out_text is already set by formatting above; do not overwrite
        else:
            # Traditional mode: just use raw output text
            out_text = getattr(resp, "output_text", "") or out_text

        outputs = getattr(resp, "output", None) or []
        for item in outputs:
            context.append(item)

        # Handle tool calls from structured response or traditional tool calling
        tool_calls = []
        if use_structured_output and structured_resp and structured_resp.system_actions.tool_calls:
            # Structured response mode: tool calls are embedded in JSON
            for tc in structured_resp.system_actions.tool_calls:
                tool_calls.append({
                    "name": tc.tool_name.value,
                    "arguments": tc.parameters,
                    "reason": tc.reason,
                    "structured": True
                })
            # Check if confirmation is required before executing
            if structured_resp.system_actions.confirmation_required and not tool_calls:
                # Model wants user confirmation before proceeding
                break
        else:
            # Traditional tool calling mode
            tool_calls = [item for item in outputs if getattr(item, "type", None) == "function_call"]

        if len(tool_calls) > 4:
            logging.warning(
                "Trace %s stage %s returned %d tool_calls (max 4); truncating to 4",
                trace_id,
                stage,
                len(tool_calls),
            )
            tool_calls = tool_calls[:4]

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
            # Handle both structured and traditional tool calls
            if isinstance(call, dict) and call.get("structured"):
                name = call["name"]
                args = call["arguments"]
            else:
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
                if name in ("generate_cv_from_session", "generate_cover_letter_from_session", "get_pdf_by_ref") and stage not in ("generate_pdf", "fix_validation"):
                    tool_payload = {"error": "pdf_tool_not_allowed_in_stage", "stage": stage}
                elif name == "get_cv_session":
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
                    logging.info(f"=== TOOL: generate_cv_from_session (v2) === session_id={sid} trace_id={trace_id}")
                    s = store.get_session_with_blob_retrieval(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                        logging.warning(f"=== TOOL: generate_cv_from_session (v2) FAILED === session not found")
                    else:
                        status, payload, content_type = _tool_generate_cv_from_session(
                            session_id=str(sid),
                            language=str(args.get("language") or "").strip() or None,
                            client_context=None,
                            session=s,
                        )
                        if (
                            content_type == "application/pdf"
                            and isinstance(payload, dict)
                            and isinstance(payload.get("pdf_bytes"), (bytes, bytearray))
                            and status == 200
                        ):
                            pdf_bytes = bytes(payload["pdf_bytes"])
                            pdf_meta = payload.get("pdf_metadata") or {}
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_meta.get("pdf_ref"),
                                "pdf_sha256": pdf_meta.get("sha256"),
                                "pdf_size_bytes": pdf_meta.get("pdf_size_bytes"),
                                "render_ms": pdf_meta.get("render_ms"),
                                "validation_passed": pdf_meta.get("validation_passed"),
                                "pdf_pages": pdf_meta.get("pages"),
                            }
                            logging.info(
                                "=== TOOL: generate_cv_from_session (v2) SUCCESS === pdf_size=%d bytes pdf_ref=%s",
                                len(pdf_bytes),
                                pdf_meta.get("pdf_ref"),
                            )
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "generate_failed"}
                            logging.warning(f"=== TOOL: generate_cv_from_session (v2) FAILED === status={status} payload={tool_payload}")
                elif name == "generate_cover_letter_from_session":
                    sid = args.get("session_id") or session_id
                    logging.info(f"=== TOOL: generate_cover_letter_from_session (v2) === session_id={sid} trace_id={trace_id}")
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                        logging.warning("=== TOOL: generate_cover_letter_from_session (v2) FAILED === session not found")
                    else:
                        status, payload, content_type = _tool_generate_cover_letter_from_session(
                            session_id=str(sid),
                            language=str(args.get("language") or "").strip() or None,
                            session=s,
                        )
                        if content_type == "application/pdf" and isinstance(payload, dict) and isinstance(payload.get("pdf_bytes"), (bytes, bytearray)) and status == 200:
                            pdf_bytes = bytes(payload["pdf_bytes"])
                            pdf_meta = payload.get("pdf_metadata") or {}
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_meta.get("pdf_ref") or payload.get("pdf_ref"),
                                "pdf_size_bytes": len(pdf_bytes),
                            }
                            logging.info(
                                "=== TOOL: generate_cover_letter_from_session (v2) SUCCESS === pdf_size=%d bytes pdf_ref=%s",
                                len(pdf_bytes),
                                pdf_meta.get("pdf_ref") or payload.get("pdf_ref"),
                            )
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "generate_failed"}
                            logging.warning(f"=== TOOL: generate_cover_letter_from_session (v2) FAILED === status={status} payload={tool_payload}")
                elif name == "get_pdf_by_ref":
                    sid = args.get("session_id") or session_id
                    pdf_ref = str(args.get("pdf_ref") or "").strip()
                    s = store.get_session(str(sid))
                    if not s:
                        tool_payload = {"error": "Session not found or expired"}
                    else:
                        status, payload, content_type = _tool_get_pdf_by_ref(
                            session_id=str(sid),
                            pdf_ref=pdf_ref,
                            session=s,
                        )
                        if content_type == "application/pdf" and isinstance(payload, (bytes, bytearray)) and status == 200:
                            tool_payload = {
                                "success": True,
                                "session_id": sid,
                                "pdf_ref": pdf_ref,
                                "pdf_size_bytes": len(payload),
                            }
                        else:
                            tool_payload = payload if isinstance(payload, dict) else {"error": "pdf_fetch_failed"}
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

            tool_output_for_model = sanitize_tool_output_for_model(str(name), tool_payload)
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

        # Wave 0.3: Fire-and-forget in execution mode
        # After generate_cv_from_session executes, terminate loop immediately
        if execution_mode and "generate_cv_from_session" in tool_names:
            logging.info(f"Execution mode: generate_cv_from_session executed, terminating loop (fire-and-forget)")
            # Return immediately with PDF if generated
            if pdf_bytes:
                return out_text or "PDF generated.", turn_trace, run_summary, last_response_id, pdf_bytes
            # Otherwise return with tool result
            return out_text or "PDF generation attempted.", turn_trace, run_summary, last_response_id, pdf_bytes

    # If output looks truncated near cap, do one continuation (no tools).
    if out_text and _looks_truncated(out_text):
        try:
            call_seq += 1
            cont = _responses_create_with_trace(
                req_obj={
                    **req_base,
                    "input": context + [{"role": "user", "content": "Continue from where you stopped. Do not repeat."}],
                    "tools": [],
                    "max_output_tokens": min(1024, _responses_max_output_tokens(stage)),
                },
                call_seq=call_seq,
            )
            cont_text = getattr(cont, "output_text", "") or ""
            if cont_text:
                out_text = f"{out_text.rstrip()}\n\n{cont_text.lstrip()}"
                last_response_id = getattr(cont, "id", None) or last_response_id
        except Exception:
            pass

    return out_text or "Done.", turn_trace, run_summary, last_response_id, pdf_bytes

