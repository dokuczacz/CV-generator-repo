from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable

from openai import OpenAI

from src import product_config
from src.json_repair import extract_first_json_value, sanitize_json_text, strip_markdown_code_fences


@dataclass(frozen=True)
class OpenAIJsonSchemaDeps:
    openai_enabled: Callable[[], bool]
    openai_model: Callable[[], str]
    get_openai_prompt_id: Callable[[str | None], str | None]
    require_openai_prompt_id: Callable[[], bool]
    normalize_stage_env_key: Callable[[str], str]
    bulk_translation_output_budget: Callable[[str, object], int]
    coerce_int: Callable[[object, int], int]
    schema_repair_instructions: Callable[[str | None, str | None], str]
    now_iso: Callable[[], str]


def _extract_openai_output_text(resp: object) -> str:
    text = str(getattr(resp, "output_text", "") or "")
    if text.strip():
        return text

    chunks: list[str] = []
    output_items = getattr(resp, "output", None)
    if not isinstance(output_items, list):
        return ""

    for item in output_items:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            part_text = part.get("text")
            if isinstance(part_text, str) and part_text.strip():
                chunks.append(part_text)
                continue
            if isinstance(part_text, dict):
                val = part_text.get("value")
                if isinstance(val, str) and val.strip():
                    chunks.append(val)
                    continue
            val = part.get("value")
            if isinstance(val, str) and val.strip():
                chunks.append(val)

    return "\n".join(chunks).strip()


def openai_json_schema_call(
    *,
    deps: OpenAIJsonSchemaDeps,
    system_prompt: str,
    user_text: str,
    response_format: dict,
    max_output_tokens: int = 800,
    stage: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
) -> tuple[bool, dict | None, str]:
    """Call OpenAI Responses API with JSON schema formatting."""
    if not deps.openai_enabled():
        return False, None, "OPENAI_API_KEY missing or CV_ENABLE_AI=0"
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=60.0)
        prompt_id = deps.get_openai_prompt_id(stage)
        model_override = (os.environ.get("OPENAI_MODEL") or "").strip() or None

        max_attempts = product_config.OPENAI_JSON_SCHEMA_MAX_ATTEMPTS
        if max_attempts < 1:
            max_attempts = 1

        if deps.require_openai_prompt_id() and not prompt_id:
            stage_key = deps.normalize_stage_env_key(stage or "")
            return (
                False,
                None,
                "Backend configuration error: OpenAI dashboard prompt id is required but not set. "
                f"Set OPENAI_PROMPT_ID_{stage_key} (or OPENAI_PROMPT_ID) in local.settings.json (Values) or your environment.",
            )

        if str(stage or "").strip().lower() == "bulk_translation":
            max_output_tokens = deps.bulk_translation_output_budget(user_text, max_output_tokens)
        else:
            max_output_tokens = deps.coerce_int(max_output_tokens, 800)

        system_prompt = system_prompt or ""
        include_system_with_dashboard = product_config.OPENAI_DASHBOARD_INCLUDE_SYSTEM_PROMPT

        req_input: list[dict] = [{"role": "user", "content": user_text}]
        if not prompt_id:
            req_input = [
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": user_text},
            ]
        else:
            if include_system_with_dashboard and system_prompt.strip():
                req_input.insert(0, {"role": "developer", "content": system_prompt})
            elif system_prompt.strip():
                logging.info(
                    "Omitting system_prompt for dashboard prompt_id (default) stage=%s system_prompt_chars=%s",
                    stage or "json_schema_call",
                    len(system_prompt),
                )

        prompt_source_mode = "legacy_model"
        if prompt_id:
            prompt_source_mode = "dashboard_plus_system" if (include_system_with_dashboard and system_prompt.strip()) else "dashboard_only"

        req: dict = {"input": req_input, "text": {"format": response_format}, "max_output_tokens": max_output_tokens}

        try:
            dev_chars_included = 0
            if req_input and isinstance(req_input[0], dict) and req_input[0].get("role") == "developer":
                dev_chars_included = len(str(req_input[0].get("content") or ""))
            logging.debug(
                "openai_json_schema_call stage=%s prompt_id=%s input_items=%s dev_chars=%s user_chars=%s",
                stage or "json_schema_call",
                bool(prompt_id),
                len(req_input),
                dev_chars_included,
                len(user_text or ""),
            )
        except Exception:
            pass

        if prompt_id:
            req["prompt"] = {"id": prompt_id, "variables": {"stage": stage or "json_schema_call", "phase": "preparation"}}
        else:
            req["model"] = model_override or deps.openai_model()

        logging.info(
            "Calling OpenAI for stage=%s max_output_tokens=%s has_prompt_id=%s prompt_source_mode=%s system_prompt_hash=%s",
            stage,
            str(max_output_tokens),
            bool(prompt_id),
            prompt_source_mode,
            hashlib.sha256((system_prompt or "").encode("utf-8", errors="ignore")).hexdigest()[:16],
        )

        def _openai_trace_enabled() -> bool:
            return product_config.CV_OPENAI_TRACE

        def _openai_trace_dir() -> str:
            return product_config.CV_OPENAI_TRACE_DIR

        def _sha256_text(s: str) -> str:
            try:
                return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()
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
                    role = item.get("role")
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

                prompt_obj = req_obj.get("prompt")
                prompt_id_local = prompt_obj.get("id") if isinstance(prompt_obj, dict) else None

                fmt = req_obj.get("text") if isinstance(req_obj.get("text"), dict) else None
                fmt_name = ""
                try:
                    if isinstance(fmt, dict) and isinstance(fmt.get("format"), dict):
                        fmt_name = str(fmt["format"].get("name") or "")
                except Exception:
                    pass

                return {
                    "has_prompt": bool(prompt_obj),
                    "prompt_id": prompt_id_local,
                    "prompt_source_mode": prompt_source_mode,
                    "include_system_with_dashboard": bool(include_system_with_dashboard),
                    "system_prompt_chars": len(system_prompt or ""),
                    "system_prompt_sha256": _sha256_text(system_prompt or ""),
                    "format_name": fmt_name or None,
                    "max_output_tokens": req_obj.get("max_output_tokens"),
                    "input_items": summarized_inputs,
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

        def _openai_trace_full_enabled() -> bool:
            return product_config.CV_OPENAI_TRACE_FULL

        def _safe_write_trace_artifact(*, response_id: str, kind: str, payload: dict) -> None:
            if not _openai_trace_full_enabled():
                return
            try:
                trace_dir = _openai_trace_dir()
                out_dir = os.path.join(trace_dir, "artifacts", kind)
                os.makedirs(out_dir, exist_ok=True)
                path = os.path.join(out_dir, f"{response_id}.json")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            except Exception:
                pass

        last_err: str = ""
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                logging.info(
                    "OpenAI request attempt stage=%s call_seq=%s max_attempts=%s prompt_source_mode=%s has_prompt_id=%s",
                    str(stage or "json_schema_call"),
                    f"attempt_{attempt}",
                    max_attempts,
                    prompt_source_mode,
                    bool(prompt_id),
                )
                started_at = time.time()
                resp = client.responses.create(**req)
            except Exception as e:
                try:
                    if (
                        str(stage or "").strip().lower() == "bulk_translation"
                        and isinstance(req.get("max_output_tokens"), int)
                        and req.get("max_output_tokens", 0) > 4096
                        and "max_output_tokens" in str(e).lower()
                        and attempt < max_attempts
                    ):
                        req["max_output_tokens"] = 4096
                        logging.warning(
                            "Clamping max_output_tokens to 4096 after OpenAI rejection stage=%s err=%s",
                            stage,
                            str(e)[:300],
                        )
                        continue
                except Exception:
                    pass
                status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
                body = None
                try:
                    body = getattr(getattr(e, "response", None), "text", None)
                except Exception:
                    body = None
                body_preview = (str(body)[:500] + "...") if body else ""
                logging.warning(
                    "OpenAI call failed stage=%s attempt=%s/%s status=%s has_prompt_id=%s prompt_source_mode=%s err=%s body=%s",
                    stage,
                    attempt,
                    max_attempts,
                    status,
                    bool(prompt_id),
                    prompt_source_mode,
                    str(e),
                    body_preview,
                )
                last_err = f"openai error (status={status}): {str(e)}"
                if attempt < max_attempts:
                    continue
                return False, None, last_err

            out = _extract_openai_output_text(resp)
            try:
                rid = getattr(resp, "id", None)
                trace_record = {
                    "ts_utc": deps.now_iso(),
                    "trace_id": str(trace_id or ""),
                    "session_id": str(session_id or ""),
                    "stage": str(stage or "json_schema_call"),
                    "phase": "schema",
                    "call_seq": f"attempt_{attempt}",
                    "duration_ms": int((time.time() - started_at) * 1000) if "started_at" in locals() else None,
                    "request": _summarize_req_for_trace(req),
                    "response": {"id": rid, "status": getattr(resp, "status", None), "output_text_len": len(out or "")},
                }
                _append_openai_trace_record(trace_record)
                if rid:
                    _safe_write_trace_artifact(
                        response_id=str(rid),
                        kind="requests",
                        payload={"request": req, "trace": trace_record},
                    )
                    logging.info(
                        "openai_response_id=%s trace_id=%s stage=%s call_seq=%s prompt_source_mode=%s",
                        str(rid),
                        str(trace_id or ""),
                        str(stage or "json_schema_call"),
                        f"attempt_{attempt}",
                        prompt_source_mode,
                    )
            except Exception:
                pass

            try:
                if str(getattr(resp, "status", "") or "").strip().lower() == "incomplete" and attempt < max_attempts:
                    inc = getattr(resp, "incomplete_details", None)
                    reason = str(inc.get("reason") or "") if isinstance(inc, dict) else str(getattr(inc, "reason", "") or "")
                    if reason.strip().lower() == "max_output_tokens":
                        try:
                            cur = int(req.get("max_output_tokens") or max_output_tokens or 800)
                        except Exception:
                            cur = int(max_output_tokens or 800)
                        bumped = min(8192, max(cur + 400, int(cur * 1.6)))
                        if bumped > cur:
                            req["max_output_tokens"] = bumped
                            logging.warning(
                                "Retrying stage=%s after incomplete(max_output_tokens): bump max_output_tokens %s -> %s",
                                stage,
                                cur,
                                bumped,
                            )
                            continue
            except Exception:
                pass

            if not out.strip():
                resp_id = getattr(resp, "id", "unknown")
                last_err = f"empty model output (response_id={resp_id})"
                output_items = getattr(resp, "output", []) or []
                item_types: list[str] = []
                if output_items:
                    for item in output_items:
                        if isinstance(item, dict):
                            item_types.append(str(item.get("type") or "unknown"))
                        else:
                            item_types.append(str(getattr(item, "type", "unknown") or "unknown"))
                reasoning_tokens = 0
                if resp.usage and hasattr(resp.usage, "output_tokens_details"):
                    reasoning_tokens = getattr(resp.usage.output_tokens_details, "reasoning_tokens", 0)
                elif resp.usage and hasattr(resp.usage, "completion_tokens_details"):
                    reasoning_tokens = getattr(resp.usage.completion_tokens_details, "reasoning_tokens", 0)

                logging.warning(
                    "Empty model output for stage=%s attempt=%s/%s response_id=%s output_items=%s item_types=%s reasoning_tokens=%s",
                    stage,
                    attempt,
                    max_attempts,
                    resp_id,
                    len(output_items),
                    item_types,
                    reasoning_tokens,
                )
                if attempt < max_attempts:
                    continue
                return False, None, last_err

            out_for_parse = strip_markdown_code_fences(out)
            extracted = extract_first_json_value(out_for_parse)
            if extracted:
                out_for_parse = extracted

            parsed = None
            parse_error = None
            try:
                parsed = json.loads(out_for_parse)
            except Exception as e:
                parse_error = str(e)
                logging.warning("JSON parse failed for stage=%s: %s", stage, str(e))
                try:
                    sanitized = sanitize_json_text(out_for_parse)
                    parsed = json.loads(sanitized)
                    parse_error = None
                    logging.info("JSON parse recovered after sanitization for stage=%s", stage)
                except Exception as e2:
                    parse_error = str(e2)

            try:
                resp_id = getattr(resp, "id", None)
                if resp_id and isinstance(parsed, dict):
                    parsed.setdefault("_openai_response_id", str(resp_id))
            except Exception:
                pass

            if parsed is None and parse_error and str(stage or "").strip().lower() == "bulk_translation":
                if "Unterminated string" in str(parse_error) or "EOF" in str(parse_error) or "Expecting" in str(parse_error):
                    try:
                        cur = int(req.get("max_output_tokens") or max_output_tokens or 800)
                    except Exception:
                        cur = max_output_tokens or 800
                    bumped = min(8192, max(cur + 1200, int(cur * 2)))
                    if bumped > cur and attempt < max_attempts:
                        req["max_output_tokens"] = bumped
                        logging.warning(
                            "Retrying bulk_translation with higher max_output_tokens=%s after parse_error=%s",
                            bumped,
                            str(parse_error)[:200],
                        )
                        continue

            if parsed is None and parse_error:
                logging.info("Attempting schema repair for stage=%s", stage)
                try:
                    repair_input = list(req["input"])
                    repair_input.append({"role": "assistant", "content": out})
                    repair_input.append(
                        {
                            "role": "developer",
                            "content": deps.schema_repair_instructions(stage, parse_error),
                        }
                    )
                    repair_req = {**req, "input": repair_input}
                    if str(stage or "").strip().lower() == "bulk_translation":
                        try:
                            cur = int(repair_req.get("max_output_tokens") or max_output_tokens or 800)
                        except Exception:
                            cur = max_output_tokens or 800
                        repair_req["max_output_tokens"] = max(cur, min(8192, int(cur * 2)))
                    logging.info(
                        "OpenAI request attempt stage=%s call_seq=%s max_attempts=%s prompt_source_mode=%s has_prompt_id=%s",
                        str(stage or "json_schema_call"),
                        f"schema_repair_{attempt}",
                        max_attempts,
                        prompt_source_mode,
                        bool(prompt_id),
                    )
                    started_at_repair = time.time()
                    repair_resp = client.responses.create(**repair_req)
                    repair_out = _extract_openai_output_text(repair_resp)
                    try:
                        rid2 = getattr(repair_resp, "id", None)
                        trace_record2 = {
                            "ts_utc": deps.now_iso(),
                            "trace_id": str(trace_id or ""),
                            "session_id": str(session_id or ""),
                            "stage": str(stage or "json_schema_call"),
                            "phase": "schema_repair",
                            "call_seq": f"schema_repair_{attempt}",
                            "duration_ms": int((time.time() - started_at_repair) * 1000),
                            "request": _summarize_req_for_trace(repair_req),
                            "response": {"id": rid2, "status": getattr(repair_resp, "status", None), "output_text_len": len(repair_out or "")},
                        }
                        _append_openai_trace_record(trace_record2)
                        if rid2:
                            _safe_write_trace_artifact(
                                response_id=str(rid2),
                                kind="requests",
                                payload={"request": repair_req, "trace": trace_record2},
                            )
                            logging.info(
                                "openai_response_id=%s trace_id=%s stage=%s call_seq=%s prompt_source_mode=%s",
                                str(rid2),
                                str(trace_id or ""),
                                str(stage or "json_schema_call"),
                                f"schema_repair_{attempt}",
                                prompt_source_mode,
                            )
                    except Exception:
                        pass
                    if repair_out.strip():
                        try:
                            repair_for_parse = strip_markdown_code_fences(repair_out)
                            extracted2 = extract_first_json_value(repair_for_parse)
                            if extracted2:
                                repair_for_parse = extracted2
                            parsed = json.loads(repair_for_parse)
                        except Exception:
                            parsed = json.loads(sanitize_json_text(repair_for_parse))
                        logging.info("Schema repair succeeded for stage=%s", stage)
                except Exception as repair_err:
                    logging.warning("Schema repair failed for stage=%s: %s", stage, str(repair_err))
                    last_err = f"invalid json from model: {parse_error} (repair also failed: {repair_err})"
                    if attempt < max_attempts:
                        continue
                    return False, None, last_err

            if parsed is None:
                last_err = f"invalid json from model: {parse_error}"
                if attempt < max_attempts:
                    continue
                return False, None, last_err
            if not isinstance(parsed, dict):
                last_err = "model returned non-object json"
                if attempt < max_attempts:
                    continue
                return False, None, last_err
            return True, parsed, ""

        return False, None, last_err or "openai error"
    except Exception as e:
        return False, None, str(e)

