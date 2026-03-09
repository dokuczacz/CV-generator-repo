from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, cast

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_blocks_from_request(req: dict[str, Any]) -> tuple[str, str]:
    input_items = cast(list[dict[str, Any]], req.get("input")) if isinstance(req.get("input"), list) else []
    developer_text = ""
    user_text = ""
    for item in input_items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "")
        if role == "developer" and content:
            developer_text = content
        if role == "user" and content:
            user_text = content
    if not developer_text or not user_text:
        raise ValueError("Request template is missing developer/user text blocks")
    return developer_text, user_text


def _extract_job_meta_from_summary(user_text: str) -> tuple[str, str]:
    marker = "[JOB_SUMMARY]"
    if marker not in user_text:
        return "", ""
    after = user_text.split(marker, 1)[1].strip()
    first_line = ""
    for line in after.splitlines():
        line = line.strip()
        if line:
            first_line = line
            break
    if not first_line:
        return "", ""
    parts = [p.strip() for p in first_line.split("|")]
    role_title = parts[0] if parts else ""
    company = parts[1] if len(parts) >= 2 else ""
    return role_title, company


def _merge_cv(base_cv: dict[str, Any], combined_cv: dict[str, Any], *, language: str) -> dict[str, Any]:
    out = dict(base_cv)
    roles = cast(list[dict[str, Any]], combined_cv.get("roles")) if isinstance(combined_cv.get("roles"), list) else []
    work: list[dict[str, Any]] = []
    for role in roles:
        if not isinstance(role, dict):
            continue
        bullets = cast(list[str], role.get("bullets")) if isinstance(role.get("bullets"), list) else []
        work.append(
            {
                "title": str(role.get("title") or "").strip(),
                "employer": str(role.get("company") or "").strip(),
                "date_range": str(role.get("date_range") or "").strip(),
                "location": str(role.get("location") or "").strip(),
                "bullets": [str(b).strip() for b in bullets if str(b).strip()],
            }
        )
    out["work_experience"] = work
    out["it_ai_skills"] = [str(x).strip() for x in (combined_cv.get("it_ai_skills") or []) if str(x).strip()]
    out["technical_operational_skills"] = [
        str(x).strip() for x in (combined_cv.get("technical_operational_skills") or []) if str(x).strip()
    ]
    out["language"] = language
    return out


def _build_cover_payload(
    *,
    base_cv: dict[str, Any],
    cover_letter: dict[str, Any],
    language: str,
    recipient_company: str,
    recipient_job_title: str,
) -> dict[str, Any]:
    addr_lines = cast(list[str], base_cv.get("address_lines")) if isinstance(base_cv.get("address_lines"), list) else []
    sender_address = "\n".join([str(x).strip() for x in addr_lines if str(x).strip()])
    signoff = str(cover_letter.get("signoff") or "").strip()
    full_name = str(base_cv.get("full_name") or "").strip()
    if signoff and full_name and full_name not in signoff:
        signoff = f"{signoff}\n{full_name}"

    return {
        "language": language,
        "sender_name": full_name,
        "sender_email": str(base_cv.get("email") or "").strip(),
        "sender_phone": str(base_cv.get("phone") or "").strip(),
        "sender_address": sender_address,
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "recipient_company": recipient_company,
        "recipient_job_title": recipient_job_title,
        "opening_paragraph": str(cover_letter.get("opening_paragraph") or "").strip(),
        "core_paragraphs": [str(p).strip() for p in (cover_letter.get("core_paragraphs") or []) if str(p).strip()],
        "closing_paragraph": str(cover_letter.get("closing_paragraph") or "").strip(),
        "signoff": signoff,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified CV+CL generation for multiple models and render PDFs")
    parser.add_argument(
        "--request-template",
        default="tmp/unified_onecall/runs/5.2_medium/request.json",
        help="Path to a prior request.json used as template",
    )
    parser.add_argument(
        "--base-cv",
        default="samples/extracted_cv.json",
        help="Base CV JSON used to merge model-generated work/skills before rendering",
    )
    parser.add_argument("--models", nargs="+", default=["gpt-5.2", "gpt-5.4"], help="Model IDs to run")
    parser.add_argument("--out-dir", default="tmp/unified_onecall_refresh", help="Output directory")
    parser.add_argument("--reasoning-effort", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--reasoning-summary", default="detailed")
    parser.add_argument("--max-output-tokens", type=int, default=3600)
    args = parser.parse_args()

    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")

    request_template = _load_json(Path(args.request_template))
    developer_text, user_text = _extract_blocks_from_request(request_template)
    job_title, company = _extract_job_meta_from_summary(user_text)

    response_format = (
        ((request_template.get("text") or {}).get("format"))
        if isinstance(request_template.get("text"), dict)
        else None
    )
    if not isinstance(response_format, dict):
        raise ValueError("Request template does not contain text.format schema")

    base_cv = _load_json(Path(args.base_cv))
    language = "en"

    out_dir = Path(args.out_dir)
    runs_dir = out_dir / "runs"
    pdf_dir = out_dir / "pdfs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    client = OpenAI(api_key=api_key, timeout=150.0)

    # Import after path setup to keep script standalone.
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.render import count_pdf_pages, render_cover_letter_pdf, render_pdf  # type: ignore

    rows: list[dict[str, Any]] = []
    pdf_rows: list[dict[str, Any]] = []

    for model_id in args.models:
        alias = model_id.replace("gpt-", "").replace(".", "_")
        run_dir = runs_dir / alias
        run_dir.mkdir(parents=True, exist_ok=True)

        request_payload: dict[str, Any] = {
            "model": model_id,
            "input": [
                {"role": "developer", "content": developer_text},
                {"role": "user", "content": user_text},
            ],
            "text": {"format": response_format},
            "max_output_tokens": int(args.max_output_tokens),
            "reasoning": {"effort": args.reasoning_effort, "summary": args.reasoning_summary},
        }

        _save_json(run_dir / "request.json", request_payload)

        started = time.time()
        resp = client.responses.create(**request_payload)
        elapsed = round(time.time() - started, 2)
        output_text = str(getattr(resp, "output_text", "") or "")

        parsed: dict[str, Any]
        parse_ok = False
        parse_error = ""
        try:
            parsed = json.loads(output_text)
            parse_ok = True
        except Exception as exc:  # pragma: no cover - defensive
            parsed = {}
            parse_error = str(exc)

        (run_dir / "response_text.json").write_text(output_text, encoding="utf-8")
        if parse_ok:
            _save_json(run_dir / "parsed_unified.json", parsed)
            _save_json(run_dir / "cv_combined.json", parsed.get("combined_cv") or {})
            _save_json(run_dir / "cover_letter.json", parsed.get("cover_letter") or {})

            cv_payload = _merge_cv(base_cv, parsed.get("combined_cv") or {}, language=language)
            cover_payload = _build_cover_payload(
                base_cv=base_cv,
                cover_letter=parsed.get("cover_letter") or {},
                language=language,
                recipient_company=company,
                recipient_job_title=job_title,
            )
            _save_json(run_dir / "cv_payload_for_render.json", cv_payload)
            _save_json(run_dir / "cover_payload_for_render.json", cover_payload)

            cv_pdf = render_pdf(cv_payload, enforce_two_pages=False)
            cl_pdf = render_cover_letter_pdf(cover_payload, enforce_one_page=False)
            cv_pdf_path = pdf_dir / f"{alias}_cv.pdf"
            cl_pdf_path = pdf_dir / f"{alias}_cl.pdf"
            cv_pdf_path.write_bytes(cv_pdf)
            cl_pdf_path.write_bytes(cl_pdf)

            pdf_rows.append(
                {
                    "run": alias,
                    "cv_pdf": str(cv_pdf_path),
                    "cv_pages": count_pdf_pages(cv_pdf),
                    "cl_pdf": str(cl_pdf_path),
                    "cl_pages": count_pdf_pages(cl_pdf),
                    "cv_bytes": len(cv_pdf),
                    "cl_bytes": len(cl_pdf),
                }
            )

        response_meta = {
            "response_id": str(getattr(resp, "id", "") or ""),
            "status": str(getattr(resp, "status", "") or ""),
            "elapsed_sec": elapsed,
            "output_chars": len(output_text),
            "parse_ok": parse_ok,
            "parse_error": parse_error,
        }
        _save_json(run_dir / "response_meta.json", response_meta)

        rows.append(
            {
                "alias": alias,
                "model_id": model_id,
                "response_id": response_meta["response_id"],
                "status": response_meta["status"],
                "elapsed_sec": elapsed,
                "parse_ok": parse_ok,
                "output_chars": len(output_text),
            }
        )

    report = {
        "source_request_template": str(args.request_template),
        "base_cv": str(args.base_cv),
        "rows": rows,
    }
    _save_json(out_dir / "multimodel_unified_report.json", report)

    pdf_summary = {
        "out_dir": str(pdf_dir),
        "rows": pdf_rows,
    }
    _save_json(pdf_dir / "pdf_summary.json", pdf_summary)

    print(f"Wrote: {out_dir / 'multimodel_unified_report.json'}")
    print(f"Wrote: {pdf_dir / 'pdf_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
