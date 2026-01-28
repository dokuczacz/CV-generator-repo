#!/usr/bin/env python3
"""Wave 0 Integration Test - Using real sample DOCX"""
import json
import base64
import sys
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:7071/api"


def _post_json(path: str, payload: dict, *, timeout: int = 30, retries: int = 2, backoff: float = 0.75):
    """POST JSON with small retry to smooth local socket hiccups."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(f"{BASE_URL}/{path.lstrip('/')}", json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(backoff * (attempt + 1))
    raise last_exc

def test_wave0_with_real_docx():
    print("\n" + "="*70)
    print("Wave 0 Integration - With Real Sample DOCX")
    print("="*70 + "\n")
    
    # Load real DOCX
    docx_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
    if not docx_path.exists():
        print(f"[ERROR] Sample DOCX not found: {docx_path}")
        return 1
    
    docx_b64 = base64.b64encode(docx_path.read_bytes()).decode('ascii')
    print(f"[OK] Loaded sample DOCX: {docx_path.name} ({docx_path.stat().st_size} bytes)")
    
    # TEST 1: Create session
    print("\n[*] TEST 1: Creating session...")
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "extract_and_store_cv",
                "params": {"docx_base64": docx_b64, "language": "en", "extract_photo": False}
            },
            timeout=30,
        )
        data = resp.json()
        session_id = data.get("session_id")
        
        if not session_id:
            print(f"[ERROR] No session_id: {json.dumps(data)[:100]}")
            return 1
        
        print(f"[OK] Session created: {session_id}")
    except Exception as e:
        print(f"[ERROR] extract_and_store_cv failed: {e}")
        return 1
    
    # TEST 2: Get session state
    print("\n[*] TEST 2: Get session baseline...")
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "get_cv_session", "session_id": session_id, "params": {}},
            timeout=10,
        )
        data = resp.json()
        stage = data.get("metadata", {}).get("stage", "UNKNOWN")
        print(f"[OK] Stage: {stage}")
    except Exception as e:
        print(f"[ERROR] get_cv_session failed: {e}")
    
    # TEST 3: Wave 0.1 - First PDF generation
    print("\n[*] TEST 3a (Wave 0.1): First PDF generation...")
    try:
        # Confirm fields
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "update_cv_field",
                "session_id": session_id,
                "params": {"confirm": {"contact_confirmed": True, "education_confirmed": True}}
            },
            timeout=10,
        )
        print("[OK] Fields confirmed")
        
        # Generate PDF
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
            },
            timeout=60,
        )
        data = resp.json()
        
        pdf_b64 = data.get("pdf_base64", "")
        pdf_size = len(base64.b64decode(pdf_b64)) if pdf_b64 else 0
        stage = data.get("stage", "UNKNOWN")
        
        print(f"[OK] PDF: {pdf_size} bytes, stage={stage}")
        return_data = {"pdf_b64": pdf_b64, "pdf_size": pdf_size, "stage": stage}

        # Fetch latest pdf_ref via get_cv_session and verify get_pdf_by_ref returns same bytes
        sess_resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "get_cv_session", "session_id": session_id, "params": {}},
            timeout=10,
        )
        sess_data = sess_resp.json()
        meta = sess_data.get("metadata", {}) if isinstance(sess_data, dict) else {}
        pdf_refs = meta.get("pdf_refs") if isinstance(meta, dict) else {}
        latest_ref = None
        if isinstance(pdf_refs, dict) and pdf_refs:
            latest_ref = sorted(
                pdf_refs.items(),
                key=lambda x: x[1].get("created_at", "") if isinstance(x[1], dict) else "",
                reverse=True,
            )[0][0]
        if latest_ref:
            fetch_resp = _post_json(
                "cv-tool-call-handler",
                {"tool_name": "get_pdf_by_ref", "session_id": session_id, "params": {"pdf_ref": latest_ref}},
                timeout=30,
            )
            fetched_bytes = fetch_resp.content if fetch_resp.headers.get("Content-Type") == "application/pdf" else b""
            content_disp = fetch_resp.headers.get("Content-Disposition", "")
            download_name_ok = "attachment" in content_disp and "filename=" in content_disp
            
            if fetched_bytes and len(fetched_bytes) == pdf_size:
                print(f"[OK] get_pdf_by_ref returned cached PDF ({len(fetched_bytes)} bytes)")
                if download_name_ok:
                    print(f"[OK] Download headers present (Content-Disposition)")
                else:
                    print(f"[!] Missing Content-Disposition header: {content_disp}")
            else:
                print(f"[!] get_pdf_by_ref size mismatch (got {len(fetched_bytes)} expected {pdf_size})")
    except Exception as e:
        print(f"[ERROR] First PDF generation failed: {e}")
        return 1
    
    # TEST 3b: Wave 0.1 - Second PDF (latch test)
    print("\n[*] TEST 3b (Wave 0.1): Second PDF (idempotency latch)...")
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
            },
            timeout=60,
        )
        data = resp.json()
        
        pdf_b64_2 = data.get("pdf_base64", "")
        pdf_size_2 = len(base64.b64decode(pdf_b64_2)) if pdf_b64_2 else 0
        
        if pdf_b64 == pdf_b64_2:
            print(f"[OK] LATCH WORKING - Same PDF ({pdf_size_2} bytes) returned")
        else:
            print(f"[!] Different PDF ({pdf_size_2} bytes) - latch may not have engaged")
    except Exception as e:
        print(f"[ERROR] Second PDF failed: {e}")
    
    # TEST 4: Wave 0.2 - FSM edit intent
    print("\n[*] TEST 4 (Wave 0.2): FSM edit intent escape...")
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "change work experience", "session_id": session_id, "language": "en"}
            },
            timeout=30,
        )
        data = resp.json()
        
        stage = data.get("stage", "UNKNOWN")
        run_summary = data.get("run_summary", {})
        next_stage = run_summary.get("stage_debug", {}).get("next_stage", "UNKNOWN")
        edit_detected = run_summary.get("stage_debug", {}).get("edit_intent", False)
        
        if next_stage == "REVIEW":
            print(f"[OK] FSM WORKING - Transitioned to REVIEW (edit_intent={edit_detected})")
        else:
            print(f"[!] FSM transitioned to {next_stage} (expected REVIEW)")
    except Exception as e:
        print(f"[ERROR] Edit intent test failed: {e}")
    
    # TEST 5: Wave 0.3 - Single-call execution
    print("\n[*] TEST 5 (Wave 0.3): Single-call execution contract...")
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
            },
            timeout=60,
        )
        data = resp.json()
        
        run_summary = data.get("run_summary", {})
        model_calls = run_summary.get("model_calls", -1)
        max_calls = run_summary.get("max_model_calls", -1)
        execution_mode = run_summary.get("execution_mode", False)
        
        if execution_mode and model_calls == 1:
            print(f"[OK] SINGLE-CALL WORKING - calls={model_calls} (execution_mode={execution_mode})")
        else:
            print(f"[!] calls={model_calls}, max={max_calls}, execution_mode={execution_mode}")
    except Exception as e:
        print(f"[ERROR] Single-call test failed: {e}")
    
    print("\n" + "="*70)
    print("Wave 0 Integration Tests Complete")
    print("="*70 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(test_wave0_with_real_docx())
