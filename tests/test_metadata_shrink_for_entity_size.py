from __future__ import annotations

import json

import function_app


def _meta_size_bytes(obj: dict) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def test_shrink_metadata_for_table_reduces_large_metadata_payload() -> None:
    large_pdf_refs = {}
    for i in range(250):
        ref = f"pdf_{i:04d}"
        large_pdf_refs[ref] = {
            "container": "cv-pdfs",
            "blob_name": f"session/very/long/path/{i}/" + ("x" * 120),
            "created_at": f"2026-03-05T19:{i % 60:02d}:00Z",
            "sha256": "a" * 64,
            "size_bytes": 150000 + i,
            "render_ms": 1200 + i,
            "pages": 2,
            "download_name": "Very_Long_Download_Name_" + ("n" * 120),
            "target_language": "de",
            "job_sig": "b" * 64,
            "extra_debug": "debug_" + ("z" * 200),
        }

    meta = {
        "job_posting_text": "JOB\n" + ("q" * 120000),
        "event_log": [{"text": "t" * 6000, "assistant_text": "a" * 6000} for _ in range(120)],
        "job_data_table_history": [
            {
                "position_name": "Engineer " + ("e" * 120),
                "company_name": "Company " + ("c" * 120),
                "company_address": "Address " + ("d" * 300),
                "company_email": "mail@example.com",
                "company_phone": "+41 00 000 00 00",
                "cv_generated_at": "2026-03-05T19:00:00Z",
                "updated_at": "2026-03-05T19:00:00Z",
            }
            for _ in range(300)
        ],
        "work_experience_proposal_block": {
            "roles": [
                {
                    "title": "Role",
                    "company": "Company",
                    "date_range": "2020-2025",
                    "location": "Zurich",
                    "bullets": ["b" * 600 for _ in range(8)],
                }
                for _ in range(12)
            ],
            "notes": "n" * 9000,
        },
        "pdf_refs": large_pdf_refs,
    }

    before_size = _meta_size_bytes(meta)
    shrunk = function_app._shrink_metadata_for_table(meta)
    after_size = _meta_size_bytes(shrunk)

    assert after_size < before_size
    assert after_size <= 45000
    assert isinstance(shrunk.get("pdf_refs"), dict)
    assert len(shrunk.get("pdf_refs") or {}) >= 1
