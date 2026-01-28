import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request


def _read_jsonl(path: pathlib.Path):
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _http_get_json(url: str, api_key: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return json.loads(raw.decode("utf-8", errors="ignore"))


def _safe_write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _filter_func_logs(out_dir: pathlib.Path, needle: str) -> None:
    logs_dir = pathlib.Path("tmp/logs")
    if not logs_dir.exists():
        return
    patt = re.compile(re.escape(needle))
    out_path = out_dir / "func_logs_filtered.log"
    matched = 0
    with out_path.open("w", encoding="utf-8") as out:
        for log_file in sorted(logs_dir.glob("func_*.log"), key=lambda p: p.stat().st_mtime):
            try:
                text = log_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                if patt.search(line):
                    out.write(f"[{log_file.name}] {line}\n")
                    matched += 1
    if matched == 0:
        try:
            out_path.unlink()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch OpenAI Responses API objects for response_ids logged by CV_OPENAI_TRACE.")
    ap.add_argument("--trace-file", default="tmp/openai_trace/openai_trace.jsonl", help="Path to openai_trace.jsonl")
    ap.add_argument("--out-dir", default="tmp/exports/openai_trace", help="Output directory")
    ap.add_argument("--session-id", default=None, help="Filter to a session_id")
    ap.add_argument("--trace-id", default=None, help="Filter to a trace_id")
    ap.add_argument("--limit", type=int, default=50, help="Max unique response_ids to fetch")
    ap.add_argument("--sleep-ms", type=int, default=120, help="Sleep between API calls")
    ap.add_argument("--write-report", action="store_true", help="Write a Markdown report.md summary to out-dir")
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY") or ""
    if not api_key.strip():
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 2

    base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com").rstrip("/")
    trace_path = pathlib.Path(args.trace_file)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect unique response ids, preserving order
    response_ids: list[str] = []
    seen: set[str] = set()
    matching_records: list[dict] = []
    for rec in _read_jsonl(trace_path):
        if args.session_id and str(rec.get("session_id") or "") != args.session_id:
            continue
        if args.trace_id and str(rec.get("trace_id") or "") != args.trace_id:
            continue
        matching_records.append(rec)
        rid = (rec.get("response") or {}).get("id")
        if rid and rid not in seen:
            seen.add(rid)
            response_ids.append(rid)
        if len(response_ids) >= args.limit:
            break

    _safe_write_json(out_dir / "openai_trace_records.json", {"count": len(matching_records), "records": matching_records})
    if args.trace_id:
        _filter_func_logs(out_dir, args.trace_id)
    if args.session_id:
        _filter_func_logs(out_dir, args.session_id)

    fetched = 0
    for rid in response_ids:
        # Response object
        url = f"{base_url}/v1/responses/{rid}"
        try:
            data = _http_get_json(url, api_key=api_key)
            _safe_write_json(out_dir / "responses" / f"{rid}.json", data)
            fetched += 1
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            _safe_write_json(out_dir / "errors" / f"{rid}.json", {"url": url, "status": e.code, "body": body})
        except Exception as e:
            _safe_write_json(out_dir / "errors" / f"{rid}.json", {"url": url, "error": str(e)})

        # Input items (best-effort; may 404 depending on API features)
        url_items = f"{base_url}/v1/responses/{rid}/input_items"
        try:
            items = _http_get_json(url_items, api_key=api_key)
            _safe_write_json(out_dir / "input_items" / f"{rid}.json", items)
        except Exception:
            pass

        time.sleep(max(0, args.sleep_ms) / 1000.0)

    _safe_write_json(out_dir / "summary.json", {"unique_response_ids": len(response_ids), "fetched": fetched, "out_dir": str(out_dir)})
    if args.write_report:
        try:
            report_lines: list[str] = []
            report_lines.append("# OpenAI Trace Report\n")
            report_lines.append(f"- trace_file: `{trace_path}`\n")
            report_lines.append(f"- out_dir: `{out_dir}`\n")
            if args.session_id:
                report_lines.append(f"- session_id filter: `{args.session_id}`\n")
            if args.trace_id:
                report_lines.append(f"- trace_id filter: `{args.trace_id}`\n")
            report_lines.append("\n## Summary\n")
            report_lines.append("| response_id | status | incomplete_reason | prompt_id | instructions? | input_tokens | output_tokens |\n")
            report_lines.append("|---|---|---|---|---:|---:|---:|\n")

            for rid in response_ids:
                resp_path = out_dir / "responses" / f"{rid}.json"
                if not resp_path.exists():
                    continue
                data = json.loads(resp_path.read_text(encoding="utf-8", errors="ignore") or "{}")
                status = data.get("status") or ""
                incomplete_reason = ""
                if isinstance(data.get("incomplete_details"), dict):
                    incomplete_reason = data["incomplete_details"].get("reason") or ""
                prompt_id = ""
                if isinstance(data.get("prompt"), dict):
                    prompt_id = data["prompt"].get("id") or ""
                has_instructions = "yes" if data.get("instructions") else "no"
                usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
                in_tok = usage.get("input_tokens") or ""
                out_tok = usage.get("output_tokens") or ""
                report_lines.append(f"| {rid} | {status} | {incomplete_reason} | {prompt_id} | {has_instructions} | {in_tok} | {out_tok} |\n")

            (out_dir / "report.md").write_text("".join(report_lines), encoding="utf-8")
        except Exception:
            pass
    print(f"Wrote {fetched} responses to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
