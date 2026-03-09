from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import function_app
from src import product_config


DEFAULT_ALIASES = ["5.0 medium", "5.2 medium", "5.4 medium"]


def _load_cv_data(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("cv_data"), dict):
        cv_data = dict(data.get("cv_data") or {})
        if bool(cv_data.get("__offloaded__")) or str(cv_data.get("__blob_ref__") or "").strip():
            raise ValueError(
                "Input contains offloaded cv_data placeholder (__offloaded__/__blob_ref__) and not real CV content. "
                "Use a fully materialized CV JSON (real fields like work_experience/education/skills) for parity runs."
            )
        return cv_data
    if isinstance(data, dict):
        return data
    raise ValueError(f"Unsupported CV JSON shape in: {path}")


def _list_models(api_key: str) -> list[str]:
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    out: list[str] = []
    for item in payload.get("data") or []:
        mid = str(item.get("id") or "").strip()
        if mid:
            out.append(mid)
    return sorted(set(out))


def _alias_patterns(alias: str) -> list[str]:
    norm = alias.strip().lower()
    if norm == "5.0 medium":
        return [r"^gpt-5$", r"^gpt-5-", r"^gpt-5-mini", r"^gpt-5-medium"]
    if norm == "5.2 medium":
        return [r"^gpt-5\.2", r"^gpt-5-2", r"^gpt-5\.2-"]
    if norm == "5.4 medium":
        return [r"^gpt-5\.4", r"^gpt-5-4", r"^gpt-5\.4-"]
    return [rf"^{re.escape(alias)}$"]


def _is_disallowed_variant(model_id: str) -> bool:
    low = model_id.lower()
    # Cost guard: never auto-resolve to premium/pro variants in parity runs.
    return any(x in low for x in ["search-api", "chat", "codex", "mini", "nano", "pro"])


def _priority_score(alias: str, model_id: str) -> int:
    low = model_id.lower()
    if _is_disallowed_variant(low):
        return -100

    norm = alias.strip().lower()
    if norm == "5.0 medium":
        if low == "gpt-5":
            return 100
        if re.match(r"^gpt-5-\d{4}-\d{2}-\d{2}$", low):
            return 90
        if low.startswith("gpt-5-pro"):
            return 70
    if norm == "5.2 medium":
        if low == "gpt-5.2":
            return 100
        if re.match(r"^gpt-5\.2-\d{4}-\d{2}-\d{2}$", low):
            return 90
        if low.startswith("gpt-5.2-pro"):
            return 70
    if norm == "5.4 medium":
        if low == "gpt-5.4":
            return 100
        if re.match(r"^gpt-5\.4-\d{4}-\d{2}-\d{2}$", low):
            return 90
        if low.startswith("gpt-5.4-pro"):
            return 70
    return 10


def _resolve_model_id(alias: str, available: list[str]) -> str:
    if alias in available:
        return alias

    pats = _alias_patterns(alias)
    matches: list[str] = []
    for mid in available:
        low = mid.lower()
        for pat in pats:
            if re.search(pat, low):
                matches.append(mid)
                break

    if not matches:
        raise RuntimeError(
            "Cannot resolve alias "
            f"'{alias}'. Available gpt-5-like models: {', '.join([m for m in available if 'gpt-5' in m.lower()][:30])}"
        )

    ranked = sorted(matches, key=lambda m: (_priority_score(alias, m), m), reverse=True)
    best = ranked[0]
    if _priority_score(alias, best) < 0:
        raise RuntimeError(f"Resolved alias '{alias}' only to disallowed variants: {matches}")
    return best


def _hash_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _fetch_input_items(api_key: str, response_id: str) -> dict[str, Any]:
    url = f"https://api.openai.com/v1/responses/{response_id}/input_items"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    body = resp.json()

    user = ""
    developer = ""
    for item in body.get("data") or []:
        role = str(item.get("role") or "")
        content = item.get("content") if isinstance(item.get("content"), list) else []
        for c in content:
            if str(c.get("type") or "") != "input_text":
                continue
            txt = str(c.get("text") or "")
            if role == "user":
                user += txt
            elif role == "developer":
                developer += txt

    return {
        "user_len": len(user),
        "developer_len": len(developer),
        "user_sha256": _hash_text(user),
        "developer_sha256": _hash_text(developer),
    }


def _build_request_components(cv_data: dict[str, Any], target_language: str, schema_mode: str, requested_tokens: int) -> dict[str, Any]:
    cv_payload = function_app._build_bulk_translation_payload(cv_data)
    user_text = json.dumps(cv_payload, ensure_ascii=False)
    system_prompt = function_app._build_ai_system_prompt(stage="bulk_translation", target_language=target_language)
    response_format = function_app._bulk_translation_response_format(mode=schema_mode)
    max_output_tokens = function_app._bulk_translation_output_budget(user_text=user_text, requested_tokens=requested_tokens)
    prompt_id = function_app._get_openai_prompt_id("bulk_translation")
    include_system_with_dashboard = product_config.OPENAI_DASHBOARD_INCLUDE_SYSTEM_PROMPT

    input_items: list[dict[str, str]] = [{"role": "user", "content": user_text}]
    prompt_source_mode = "legacy_model"
    if prompt_id:
        prompt_source_mode = "dashboard_plus_system" if include_system_with_dashboard else "dashboard_only"
        if include_system_with_dashboard:
            input_items.insert(0, {"role": "developer", "content": system_prompt})
    else:
        input_items = [
            {"role": "developer", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

    return {
        "cv_payload": cv_payload,
        "user_text": user_text,
        "system_prompt": system_prompt,
        "response_format": response_format,
        "max_output_tokens": max_output_tokens,
        "prompt_id": prompt_id,
        "prompt_source_mode": prompt_source_mode,
        "input_items": input_items,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run inline parity test across multiple models using production CV payload builders.")
    ap.add_argument("--aliases", nargs="+", default=DEFAULT_ALIASES, help="Model aliases, e.g. '5.0 medium' '5.2 medium' '5.4 medium'")
    ap.add_argument("--cv-json", default="samples/sample_cv.json", help="Path to materialized CV JSON (or session snapshot with concrete cv_data)")
    ap.add_argument("--target-language", default="en", help="Target language used in bulk_translation prompt")
    ap.add_argument("--schema-mode", choices=["storage", "render"], default="render", help="storage=backend contract, render=template-focused contract")
    ap.add_argument("--requested-tokens", type=int, default=6000, help="Requested max output tokens before budget guard")
    ap.add_argument("--reasoning-effort", default="medium", choices=["low", "medium", "high"], help="Reasoning effort for Responses API")
    ap.add_argument("--reasoning-summary", default="detailed", help="Reasoning summary mode")
    ap.add_argument("--out-dir", default="tmp/inline_parity", help="Output directory")
    args = ap.parse_args()

    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")

    available = _list_models(api_key)
    alias_map: dict[str, str] = {}
    for alias in args.aliases:
        alias_map[alias] = _resolve_model_id(alias, available)

    cv_path = Path(args.cv_json)
    cv_data = _load_cv_data(cv_path)

    built = _build_request_components(
        cv_data=cv_data,
        target_language=args.target_language,
        schema_mode=args.schema_mode,
        requested_tokens=args.requested_tokens,
    )

    client = OpenAI(api_key=api_key, timeout=120.0)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for alias, model_id in alias_map.items():
        req: dict[str, Any] = {
            "model": model_id,
            "input": built["input_items"],
            "text": {"format": built["response_format"]},
            "max_output_tokens": built["max_output_tokens"],
            "reasoning": {"effort": args.reasoning_effort, "summary": args.reasoning_summary},
        }
        if built["prompt_id"]:
            req["prompt"] = {
                "id": built["prompt_id"],
                "variables": {"stage": "bulk_translation", "phase": "preparation"},
            }

        started = time.time()
        try:
            resp = client.responses.create(**req)
            elapsed = round(time.time() - started, 2)
            response_id = str(getattr(resp, "id", "") or "")
            output_text = str(getattr(resp, "output_text", "") or "")

            parse_ok = False
            parse_error = ""
            try:
                json.loads(output_text)
                parse_ok = True
            except Exception as e:
                parse_error = str(e)

            input_audit = _fetch_input_items(api_key, response_id) if response_id else {}
            rows.append(
                {
                    "alias": alias,
                    "model_id": model_id,
                    "response_id": response_id,
                    "status": str(getattr(resp, "status", "")),
                    "elapsed_sec": elapsed,
                    "prompt_source_mode": built["prompt_source_mode"],
                    "schema_mode": args.schema_mode,
                    "reasoning_effort": args.reasoning_effort,
                    "reasoning_summary": args.reasoning_summary,
                    "max_output_tokens": built["max_output_tokens"],
                    "parse_ok": parse_ok,
                    "parse_error": parse_error,
                    "output_chars": len(output_text),
                    "input_audit": input_audit,
                }
            )
        except Exception as e:
            rows.append(
                {
                    "alias": alias,
                    "model_id": model_id,
                    "error": str(e),
                    "prompt_source_mode": built["prompt_source_mode"],
                    "schema_mode": args.schema_mode,
                    "reasoning_effort": args.reasoning_effort,
                    "reasoning_summary": args.reasoning_summary,
                    "max_output_tokens": built["max_output_tokens"],
                }
            )

    summary = {
        "aliases": args.aliases,
        "alias_map": alias_map,
        "cv_json": str(cv_path),
        "schema_mode": args.schema_mode,
        "target_language": args.target_language,
        "reasoning_effort": args.reasoning_effort,
        "reasoning_summary": args.reasoning_summary,
        "prompt_id_used": built["prompt_id"],
        "prompt_source_mode": built["prompt_source_mode"],
        "system_prompt_sha256": _hash_text(built["system_prompt"]),
        "user_payload_sha256": _hash_text(built["user_text"]),
        "user_payload_chars": len(built["user_text"]),
        "rows": rows,
    }

    (out_dir / "multimodel_parity_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Inline Multimodel Parity Report\n",
        f"- schema_mode: `{args.schema_mode}`\n",
        f"- target_language: `{args.target_language}`\n",
        f"- prompt_source_mode: `{built['prompt_source_mode']}`\n",
        f"- prompt_id_used: `{built['prompt_id']}`\n",
        f"- reasoning: effort=`{args.reasoning_effort}`, summary=`{args.reasoning_summary}`\n",
        "\n",
        "| alias | model_id | status | response_id | parse_ok | user_len | dev_len | elapsed_sec |\n",
        "|---|---|---|---|---:|---:|---:|---:|\n",
    ]

    for row in rows:
        audit = row.get("input_audit") if isinstance(row.get("input_audit"), dict) else {}
        md_lines.append(
            "| {alias} | {model_id} | {status} | {response_id} | {parse_ok} | {user_len} | {dev_len} | {elapsed_sec} |\n".format(
                alias=row.get("alias", ""),
                model_id=row.get("model_id", ""),
                status=row.get("status", row.get("error", "error")),
                response_id=row.get("response_id", ""),
                parse_ok=str(row.get("parse_ok", False)),
                user_len=audit.get("user_len", ""),
                dev_len=audit.get("developer_len", ""),
                elapsed_sec=row.get("elapsed_sec", ""),
            )
        )

    (out_dir / "multimodel_parity_report.md").write_text("".join(md_lines), encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "alias_map": alias_map, "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
