from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default).strip()


def _http_json(method: str, url: str, *, headers: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(url, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200))
            data = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            return status, data if isinstance(data, dict) else {"data": data}
    except Exception as e:
        # Best-effort parse error body (if any)
        status = getattr(getattr(e, "code", None), "__int__", lambda: None)()
        try:
            body = getattr(e, "read", None)
            if callable(body):
                raw = body()
                parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
                return int(status or 0), parsed if isinstance(parsed, dict) else {"data": parsed}
        except Exception:
            pass
        return int(status or 0), {"error": str(e)}


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2))


def _extract_message_text(item: Dict[str, Any]) -> str:
    # input_items tend to be message-like objects with content=[{type: 'input_text', text: '...'}]
    content = item.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for c in content:
        if isinstance(c, dict):
            t = c.get("text")
            if isinstance(t, str) and t.strip():
                parts.append(t)
    return "\n".join(parts).strip()


def _summarize_inputs(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    roles: Dict[str, List[int]] = {}
    role_texts: Dict[str, str] = {}
    for idx, it in enumerate(items or []):
        if not isinstance(it, dict):
            continue
        role = str(it.get("role") or it.get("author") or "").strip() or "unknown"
        roles.setdefault(role, []).append(idx)
    for role, idxs in roles.items():
        texts: List[str] = []
        for i in idxs:
            txt = _extract_message_text(items[i])
            if txt:
                texts.append(txt)
        role_texts[role] = "\n\n".join(texts)
    dev_txt = role_texts.get("developer") or role_texts.get("system") or ""
    user_txt = role_texts.get("user") or ""
    return {
        "roles_present": sorted(list(roles.keys())),
        "developer_len": len(dev_txt),
        "user_len": len(user_txt),
        "developer_has_limit_notes": ("LIMIT NOTES" in dev_txt),
        "developer_has_work_limits": ("Hard max: 180" in dev_txt or "Soft cap: 160" in dev_txt),
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fetch OpenAI Responses artifacts by response_id (response + input_items).")
    ap.add_argument("response_id", help="Response id, e.g. resp_...")
    ap.add_argument("--out-dir", default="tmp/openai_dashboard_exports", help="Output directory")
    ap.add_argument("--base-url", default=_env("OPENAI_BASE_URL", "https://api.openai.com/v1"), help="OpenAI base URL")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Env var name containing the API key")
    ap.add_argument("--limit", type=int, default=200, help="Max input_items to fetch")
    args = ap.parse_args(argv)

    api_key = _env(args.api_key_env)
    if not api_key:
        print(f"ERROR: missing API key env var {args.api_key_env}", file=sys.stderr)
        return 2

    rid = str(args.response_id).strip()
    base = str(args.base_url).rstrip("/")
    out_dir = str(args.out_dir).strip()
    _ensure_dir(out_dir)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 1) Fetch response object
    url_resp = f"{base}/responses/{urllib.parse.quote(rid)}"
    st1, resp_obj = _http_json("GET", url_resp, headers=headers)
    _write_json(os.path.join(out_dir, f"{rid}.response.json"), {"status": st1, "url": url_resp, "data": resp_obj})

    # 2) Fetch input items (paginated)
    items: List[Dict[str, Any]] = []
    after = None
    remaining = max(1, int(args.limit))
    while remaining > 0:
        q = {"limit": str(min(100, remaining))}
        if after:
            q["after"] = str(after)
        url_items = f"{base}/responses/{urllib.parse.quote(rid)}/input_items?{urllib.parse.urlencode(q)}"
        st2, page = _http_json("GET", url_items, headers=headers)
        if st2 and st2 >= 400:
            _write_json(
                os.path.join(out_dir, f"{rid}.input_items.error.json"),
                {"status": st2, "url": url_items, "data": page},
            )
            break
        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list) or not data:
            break
        for it in data:
            if isinstance(it, dict):
                items.append(it)
        remaining = int(args.limit) - len(items)
        after = page.get("last_id") or page.get("after") or None
        if not after:
            break
        time.sleep(0.05)

    _write_json(os.path.join(out_dir, f"{rid}.input_items.json"), {"count": len(items), "data": items})
    summary = _summarize_inputs(items)
    _write_json(os.path.join(out_dir, f"{rid}.summary.json"), summary)

    print(json.dumps({"response_status": st1, "input_items": len(items), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

