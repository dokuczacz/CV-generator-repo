#!/usr/bin/env python3
"""
Integration test script: Wave 0 features against local Azure Functions endpoint
Tests: Idempotency (0.1), FSM transitions (0.2), Single-call execution (0.3)

Usage:
  cd "c:/AI memory/CV-generator-repo"
  python tests/integration_wave0_local.py
"""

import json
import base64
import time
from pathlib import Path
import requests
from datetime import datetime
import sys

BASE_URL = "http://localhost:7071/api"

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def log_header(msg):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{msg:^70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")

def log_step(msg):
    print(f"{Colors.OKBLUE}[*] {msg}{Colors.ENDC}")

def log_ok(msg):
    print(f"{Colors.OKGREEN}[OK] {msg}{Colors.ENDC}")

def log_warn(msg):
    print(f"{Colors.WARNING}[!] {msg}{Colors.ENDC}")

def log_error(msg):
    print(f"{Colors.FAIL}[ERROR] {msg}{Colors.ENDC}")

def log_data(msg):
    print(f"{Colors.OKCYAN}{msg}{Colors.ENDC}")

# ============================================================================
# TEST DATA
# ============================================================================

def get_sample_docx_base64():
    """Get sample DOCX for testing from samples or create via test data"""
    # Try to find existing DOCX files
    for sample_path in [
        Path("samples/sample_cv.docx"),
        Path("tests/samples/sample_cv.docx"),
        Path("work/sample.docx"),
        Path("artifacts/sample.docx")
    ]:
        if sample_path.exists():
            log_ok(f"Found sample DOCX: {sample_path}")
            return base64.b64encode(sample_path.read_bytes()).decode('ascii')
    
    # If no sample found, we'll create a minimal DOCX
    log_warn("No sample DOCX found; will attempt to generate one from test data")
    try:
        # Try to import test data generator
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tests.aline_keller_cv_data import CV_DATA
        from src.render import render_html, render_pdf
        from docx import Document
        from docx.shared import Pt
        import io
        
        log_step("Generating minimal DOCX from CV data...")
        doc = Document()
        for line in str(CV_DATA).split('\n')[:20]:
            doc.add_paragraph(line)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode('ascii')
    except Exception as e:
        log_error(f"Could not generate test DOCX: {e}")
        return None

# ============================================================================
# TEST 1: Extract & Store CV (create session)
# ============================================================================

def test_health_check():
    """Verify local function is running"""
    log_header("Pre-flight: Health Check")
    
    log_step("Checking API endpoint...")
    try:
        # Try the cleanup endpoint (no auth required)
        payload = {"tool_name": "cleanup_expired_sessions", "params": {}}
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=5)
        if resp.status_code == 200:
            log_ok("Function is running OK")
            return True
        else:
            log_warn(f"Function returned: {resp.status_code}")
            return False
    except Exception as e:
        log_error(f"Function not reachable: {e}")
        log_error("Make sure Azure Functions emulator is running:")
        log_error("  func start")
        return False

def test_extract_and_store_cv():
    log_header("TEST 1: Extract & Store CV (Create Session)")
    
    docx_b64 = get_sample_docx_base64()
    if not docx_b64:
        log_error("Sample DOCX not available; skipping test")
        return None
    
    payload = {
        "tool_name": "extract_and_store_cv",
        "params": {
            "docx_base64": docx_b64,
            "language": "en",
            "extract_photo": False
        }
    }
    
    log_step("POST /cv-tool-call-handler with extract_and_store_cv")
    try:
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        session_id = data.get("session_id")
        if session_id:
            log_ok(f"Session created: {session_id}")
            log_data(f"Response keys: {list(data.keys())}")
            return session_id
        else:
            log_error(f"No session_id in response: {json.dumps(data, indent=2)}")
            return None
    except Exception as e:
        log_error(f"Failed: {e}")
        return None

# ============================================================================
# TEST 2: Get CV Session (baseline state)
# ============================================================================

def test_get_cv_session(session_id):
    log_header("TEST 2: Get CV Session (Baseline)")
    
    payload = {
        "tool_name": "get_cv_session",
        "session_id": session_id,
        "params": {}
    }
    
    log_step(f"GET session {session_id}")
    try:
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        readiness = data.get("readiness", {})
        can_generate = readiness.get("can_generate")
        log_data(f"Readiness: can_generate={can_generate}")
        log_data(f"Stage: {data.get('metadata', {}).get('stage', 'unknown')}")
        
        return data
    except Exception as e:
        log_error(f"Failed: {e}")
        return None

# ============================================================================
# TEST 3: Wave 0.1 - Idempotency Latch
# ============================================================================

def test_idempotency_latch(session_id):
    log_header("TEST 3 (Wave 0.1): Idempotency Latch - First PDF Generation")
    
    # Confirm fields first
    log_step("1. Confirm contact and education")
    confirm_payload = {
        "tool_name": "update_cv_field",
        "session_id": session_id,
        "params": {
            "confirm": {
                "contact_confirmed": True,
                "education_confirmed": True
            }
        }
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=confirm_payload, timeout=10)
        resp.raise_for_status()
        log_ok("Fields confirmed")
    except Exception as e:
        log_error(f"Confirmation failed: {e}")
        return None
    
    # Request PDF generation
    log_step("2. Request PDF generation (first time)")
    gen_payload = {
        "tool_name": "process_cv_orchestrated",
        "params": {
            "message": "generate pdf",
            "session_id": session_id,
            "language": "en"
        }
    }
    
    try:
        t1 = time.time()
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=gen_payload, timeout=30)
        t1_elapsed = time.time() - t1
        resp.raise_for_status()
        data = resp.json()
        
        pdf_base64 = data.get("pdf_base64", "")
        pdf_size = len(base64.b64decode(pdf_base64)) if pdf_base64 else 0
        
        log_ok(f"PDF generated: {pdf_size} bytes in {t1_elapsed:.2f}s")
        log_data(f"Response stage: {data.get('stage')}")
        
        return {
            "session_id": session_id,
            "pdf_size_first": pdf_size,
            "time_first": t1_elapsed,
            "pdf_base64_first": pdf_base64
        }
    except Exception as e:
        log_error(f"First generation failed: {e}")
        return None

def test_idempotency_latch_second_call(session_id, first_result):
    log_header("TEST 3b (Wave 0.1): Idempotency Latch - Second PDF Request (Should Use Cache)")
    
    log_step("Request PDF generation again (should use latch)")
    gen_payload = {
        "tool_name": "process_cv_orchestrated",
        "params": {
            "message": "generate pdf",
            "session_id": session_id,
            "language": "en"
        }
    }
    
    try:
        t2 = time.time()
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=gen_payload, timeout=30)
        t2_elapsed = time.time() - t2
        resp.raise_for_status()
        data = resp.json()
        
        pdf_base64 = data.get("pdf_base64", "")
        pdf_size = len(base64.b64decode(pdf_base64)) if pdf_base64 else 0
        
        log_ok(f"PDF returned: {pdf_size} bytes in {t2_elapsed:.2f}s")
        log_data(f"Response stage: {data.get('stage')}")
        
        # Check if same PDF (idempotency)
        if first_result and pdf_base64 == first_result["pdf_base64_first"]:
            log_ok("✓ LATCH WORKING: Same PDF returned (idempotent)")
        else:
            log_warn("⚠ Different PDF returned (latch may not have engaged)")
        
        # Performance: second call should be faster
        if t2_elapsed < first_result["time_first"] * 0.5:
            log_ok(f"✓ Performance improved: {t2_elapsed:.2f}s vs {first_result['time_first']:.2f}s (first)")
        
        return True
    except Exception as e:
        log_error(f"Second generation failed: {e}")
        return False

# ============================================================================
# TEST 4: Wave 0.2 - FSM Transitions with Edit Intent
# ============================================================================

def test_fsm_edit_intent_escape(session_id):
    log_header("TEST 4 (Wave 0.2): FSM Transitions - Edit Intent Escapes DONE")
    
    log_step("Attempting to escape DONE state with edit intent (Polish: zmień)")
    edit_payload = {
        "tool_name": "process_cv_orchestrated",
        "params": {
            "message": "zmień doświadczenie zawodowe",  # "Change work experience" in Polish
            "session_id": session_id,
            "language": "en"
        }
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=edit_payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        stage = data.get("stage")
        run_summary = data.get("run_summary", {})
        stage_debug = run_summary.get("stage_debug", {})
        
        log_data(f"Response stage: {stage}")
        log_data(f"FSM next_stage: {stage_debug.get('next_stage')}")
        log_data(f"Edit intent detected: {stage_debug.get('edit_intent')}")
        
        if stage_debug.get('next_stage') == 'review_session':
            log_ok("✓ FSM WORKING: Escaped DONE → REVIEW with edit intent")
            return True
        else:
            log_warn(f"⚠ FSM may not have transitioned correctly: {stage_debug.get('next_stage')}")
            return False
    except Exception as e:
        log_error(f"Edit intent test failed: {e}")
        return False

# ============================================================================
# TEST 5: Wave 0.3 - Single-Call Execution (Check Logs)
# ============================================================================

def test_single_call_execution(session_id):
    log_header("TEST 5 (Wave 0.3): Single-Call Execution Contract")
    
    log_step("Request PDF generation (should be single OpenAI call)")
    log_warn("Note: Requires CV_OPENAI_TRACE=1 to verify call count")
    
    gen_payload = {
        "tool_name": "process_cv_orchestrated",
        "params": {
            "message": "generate pdf",
            "session_id": session_id,
            "language": "en"
        }
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=gen_payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        run_summary = data.get("run_summary", {})
        model_calls = run_summary.get("model_calls", "?")
        max_calls = run_summary.get("max_model_calls", "?")
        execution_mode = run_summary.get("execution_mode", False)
        
        log_data(f"Execution mode: {execution_mode}")
        log_data(f"Model calls made: {model_calls}")
        log_data(f"Max calls limit: {max_calls}")
        
        if execution_mode and model_calls == 1:
            log_ok(f"✓ SINGLE-CALL WORKING: {model_calls} OpenAI call in execution mode")
            return True
        else:
            log_warn(f"⚠ Check logs for actual call count (reported: {model_calls})")
            return False
    except Exception as e:
        log_error(f"Single-call test failed: {e}")
        return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    log_header("Wave 0 Integration Tests - Local Function Endpoint")
    log_step(f"Target: {BASE_URL}")
    log_step(f"Timestamp: {datetime.now().isoformat()}")
    
    # Pre-flight check
    if not test_health_check():
        log_error("Aborting: Function not available")
        return 1
    
    # Test 1: Create session
    session_id = test_extract_and_store_cv()
    if not session_id:
        log_error("Cannot proceed without session")
        return 1
    
    # Test 2: Baseline state
    session_data = test_get_cv_session(session_id)
    
    # Test 3: Idempotency latch
    first_result = test_idempotency_latch(session_id)
    if first_result:
        test_idempotency_latch_second_call(session_id, first_result)
    
    # Test 4: FSM transitions
    test_fsm_edit_intent_escape(session_id)
    
    # Test 5: Single-call execution
    test_single_call_execution(session_id)
    
    log_header("Integration Tests Complete")
    log_ok(f"Session: {session_id}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
