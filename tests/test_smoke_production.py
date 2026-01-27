#!/usr/bin/env python3
"""Production smoke test - validates deployed Azure Functions endpoint"""
import argparse
import base64
import sys
import time
from pathlib import Path

import requests


def test_production_health(base_url: str) -> bool:
    """Test 1: Health endpoint"""
    print("[1/3] Testing health endpoint...")
    try:
        resp = requests.get(f"{base_url}/api/health", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "healthy":
            print(f"  ✓ Health check passed (version={data.get('version')})")
            return True
        else:
            print(f"  ✗ Unexpected health status: {data}")
            return False
    except Exception as e:
        print(f"  ✗ Health check failed: {e}")
        return False


def test_production_cleanup(base_url: str) -> bool:
    """Test 2: Cleanup tool"""
    print("[2/3] Testing cleanup endpoint...")
    try:
        resp = requests.post(
            f"{base_url}/api/cv-tool-call-handler",
            json={"tool_name": "cleanup_expired_sessions", "params": {}},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            print(f"  ✓ Cleanup passed (deleted {data.get('deleted_count', 0)} sessions)")
            return True
        else:
            print(f"  ✗ Cleanup returned success=False")
            return False
    except Exception as e:
        print(f"  ✗ Cleanup failed: {e}")
        return False


def test_production_pdf_generation(base_url: str, sample_docx: Path) -> bool:
    """Test 3: End-to-end PDF generation"""
    print("[3/3] Testing PDF generation...")
    
    if not sample_docx.exists():
        print(f"  ✗ Sample DOCX not found: {sample_docx}")
        return False
    
    try:
        # Step 1: Extract and create session
        print("  → Extracting CV...")
        docx_b64 = base64.b64encode(sample_docx.read_bytes()).decode('ascii')
        resp = requests.post(
            f"{base_url}/api/cv-tool-call-handler",
            json={
                "tool_name": "extract_and_store_cv",
                "params": {"docx_base64": docx_b64, "language": "en", "extract_photo": False}
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        session_id = data.get("session_id")
        
        if not session_id:
            print(f"  ✗ No session_id returned")
            return False
        
        print(f"  → Session created: {session_id[:16]}...")
        
        # Step 2: Generate PDF
        print("  → Generating PDF...")
        start = time.time()
        resp = requests.post(
            f"{base_url}/api/cv-tool-call-handler",
            json={
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
            },
            timeout=90
        )
        elapsed = time.time() - start
        resp.raise_for_status()
        data = resp.json()
        
        pdf_b64 = data.get("pdf_base64", "")
        pdf_size = len(base64.b64decode(pdf_b64)) if pdf_b64 else 0
        run_summary = data.get("run_summary", {})
        execution_mode = run_summary.get("execution_mode", False)
        model_calls = run_summary.get("model_calls", -1)
        
        if pdf_size > 0 and execution_mode and model_calls == 1:
            print(f"  ✓ PDF generation passed:")
            print(f"    - Size: {pdf_size} bytes")
            print(f"    - Time: {elapsed:.2f}s")
            print(f"    - Execution mode: True")
            print(f"    - Model calls: 1")
            return True
        else:
            print(f"  ✗ PDF generation failed:")
            print(f"    - Size: {pdf_size} bytes")
            print(f"    - Execution mode: {execution_mode}")
            print(f"    - Model calls: {model_calls}")
            return False
            
    except Exception as e:
        print(f"  ✗ PDF generation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Production smoke test for CV Generator API")
    parser.add_argument(
        "--endpoint",
        default="https://cv-generator-api.azurewebsites.net",
        help="Azure Functions endpoint URL"
    )
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx"),
        help="Sample DOCX file for testing"
    )
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("PRODUCTION SMOKE TEST")
    print(f"Endpoint: {args.endpoint}")
    print("="*70 + "\n")
    
    results = []
    results.append(test_production_health(args.endpoint))
    results.append(test_production_cleanup(args.endpoint))
    results.append(test_production_pdf_generation(args.endpoint, args.sample))
    
    print("\n" + "="*70)
    passed = sum(results)
    total = len(results)
    print(f"RESULT: {passed}/{total} tests passed")
    print("="*70 + "\n")
    
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
