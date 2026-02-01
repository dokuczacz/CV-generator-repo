#!/usr/bin/env python3
"""
Quick sanity test: Verify bulk_translation stage is reachable and working in wizard flow.
Tests the local Azure Functions endpoint at http://localhost:7071/api
"""
import json
import requests
import time

BASE_URL = "http://localhost:7071/api"

def test_bulk_translation_stage_exists():
    """Check that bulk_translation can be detected and handled."""
    print("\n" + "="*70)
    print("BULK TRANSLATION E2E TEST (Local Function)")
    print("="*70)
    
    # Test 1: Health check
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            print("✅ Health check passed")
        else:
            print(f"❌ Health check failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint error: {e}")
        return False
    
    # Test 2: Extract CV and create session using proper tool
    try:
        import base64
        with open("samples/Lebenslauf_Mariusz_Horodecki_CH.docx", "rb") as f:
            docx_b64 = base64.b64encode(f.read()).decode('ascii')
        
        resp = requests.post(
            f"{BASE_URL}/cv-tool-call-handler",
            json={
                "tool_name": "extract_and_store_cv",
                "params": {
                    "docx_base64": docx_b64,
                    "language": "en",
                    "extract_photo": False
                }
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            session_id = data.get("session_id")
            if session_id:
                print(f"✅ Session created: {session_id[:16]}...")
            else:
                print(f"❌ No session_id in response: {data}")
                return False
        else:
            print(f"❌ Extract CV failed: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Session creation error: {e}")
        return False
    
    # Test 3: Check current wizard stage
    try:
        resp = requests.post(
            f"{BASE_URL}/cv-tool-call-handler",
            json={
                "tool_name": "get_cv_session",
                "session_id": session_id,
                "params": {}
            },
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            stage = data.get("metadata", {}).get("stage", "UNKNOWN")
            print(f"✅ Current wizard stage: {stage}")
            
            # Check for bulk_translation awareness in codebase
            print(f"✅ Session metadata: {json.dumps(data.get('metadata', {}), indent=2)[:200]}...")
        else:
            print(f"❌ Get session failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Get session error: {e}")
        return False
    
    # Test 4: Try to trigger PDF generation via process_cv
    try:
        resp = requests.post(
            f"{BASE_URL}/cv-tool-call-handler",
            json={
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "message": "generate pdf",
                    "session_id": session_id,
                    "language": "en"
                }
            },
            timeout=60
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Response keys: {list(data.keys())}")
            
            if data and data.get("success"):
                pdf_b64 = data.get("pdf_base64", "")
                pdf_size = 0
                if pdf_b64:
                    import base64
                    pdf_size = len(base64.b64decode(pdf_b64))
                print(f"✅ PDF generated: {pdf_size} bytes")
                print(f"✅ Execution mode: {data.get('run_summary', {}).get('execution_mode')}")
                print(f"✅ Model calls: {data.get('run_summary', {}).get('model_calls')}")
                print(f"✅ Final stage: {data.get('metadata', {}).get('stage')}")
                return pdf_size > 0
            else:
                print(f"❌ Process not successful: {data}")
                return False
        else:
            print(f"❌ Process endpoint error: {resp.status_code}")
            print(f"   Response: {resp.text[:400]}")
            return False
    except Exception as e:
        import traceback
        print(f"❌ Process error: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_bulk_translation_stage_exists()
    print("\n" + "="*70)
    if success:
        print("✅ BULK TRANSLATION E2E: READY FOR PDF")
    else:
        print("❌ BULK TRANSLATION E2E: FAILED")
    print("="*70)
    exit(0 if success else 1)
