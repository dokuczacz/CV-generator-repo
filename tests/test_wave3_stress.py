#!/usr/bin/env python3
"""Wave 3 Stress Test - N=5 rapid-fire generate requests to confirm latch + single-call hold"""
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


def test_wave3_stress():
    print("\n" + "="*70)
    print("Wave 3 Stress Test - 5 Rapid Generate Requests")
    print("="*70 + "\n")
    
    # Load real DOCX
    docx_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
    if not docx_path.exists():
        print(f"[ERROR] Sample DOCX not found: {docx_path}")
        return 1
    
    docx_b64 = base64.b64encode(docx_path.read_bytes()).decode('ascii')
    print(f"[OK] Loaded sample DOCX: {docx_path.name} ({docx_path.stat().st_size} bytes)")
    
    # Create session
    print("\n[*] Creating session...")
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
    
    # Confirm fields
    print("\n[*] Confirming fields...")
    try:
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
    except Exception as e:
        print(f"[ERROR] Confirm failed: {e}")
        return 1
    
    # Stress test: N=5 rapid generate requests
    N = 5
    print(f"\n[*] STRESS TEST: {N} rapid-fire generate requests...")
    results = []
    
    for i in range(1, N + 1):
        try:
            start = time.time()
            resp = _post_json(
                "cv-tool-call-handler",
                {
                    "tool_name": "process_cv_orchestrated",
                    "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
                },
                timeout=60,
            )
            elapsed = time.time() - start
            data = resp.json()
            
            pdf_b64 = data.get("pdf_base64", "")
            pdf_size = len(base64.b64decode(pdf_b64)) if pdf_b64 else 0
            run_summary = data.get("run_summary", {})
            execution_mode = run_summary.get("execution_mode", False)
            model_calls = run_summary.get("model_calls", -1)
            
            results.append({
                "index": i,
                "pdf_size": pdf_size,
                "elapsed_s": round(elapsed, 2),
                "execution_mode": execution_mode,
                "model_calls": model_calls,
            })
            
            print(f"  [{i}/{N}] PDF: {pdf_size} bytes, elapsed: {elapsed:.2f}s, exec_mode={execution_mode}, calls={model_calls}")
        except Exception as e:
            print(f"  [{i}/{N}] ERROR: {e}")
            results.append({"index": i, "error": str(e)})
    
    # Verify latch + single-call consistency
    print("\n[*] Analyzing stress test results...")
    
    pdf_sizes = [r["pdf_size"] for r in results if "pdf_size" in r]
    unique_sizes = set(pdf_sizes)
    
    if len(unique_sizes) == 1 and list(unique_sizes)[0] > 0:
        print(f"[OK] LATCH STABLE - All {len(pdf_sizes)} requests returned same PDF size: {list(unique_sizes)[0]} bytes")
    else:
        print(f"[!] LATCH VARIANCE - Different sizes: {unique_sizes}")
    
    execution_modes = [r["execution_mode"] for r in results if "execution_mode" in r]
    model_calls_list = [r["model_calls"] for r in results if "model_calls" in r]
    
    if all(execution_modes) and all(c == 1 for c in model_calls_list):
        print(f"[OK] SINGLE-CALL STABLE - All {len(execution_modes)} requests had execution_mode=True, calls=1")
    else:
        print(f"[!] SINGLE-CALL VARIANCE - execution_modes: {set(execution_modes)}, calls: {set(model_calls_list)}")
    
    elapsed_times = [r["elapsed_s"] for r in results if "elapsed_s" in r]
    if elapsed_times:
        avg_elapsed = sum(elapsed_times) / len(elapsed_times)
        print(f"[*] Average response time: {avg_elapsed:.2f}s")
    
    print("\n" + "="*70)
    print("Wave 3 Stress Test Complete")
    print("="*70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(test_wave3_stress())
