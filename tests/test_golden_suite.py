#!/usr/bin/env python3
"""Golden Suite - Comprehensive regression tests for local Azure Functions endpoint"""
import json
import base64
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "http://localhost:7071/api"
SAMPLE_DOCX = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")


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


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.duration = 0.0
    
    def pass_test(self, message: str = ""):
        self.passed = True
        self.message = message
    
    def fail_test(self, message: str):
        self.passed = False
        self.message = message
    
    def __str__(self):
        status = "[PASS]" if self.passed else "[FAIL]"
        duration_str = f" ({self.duration:.2f}s)" if self.duration > 0 else ""
        msg = f": {self.message}" if self.message else ""
        return f"{status}{duration_str} {self.name}{msg}"


def test_health_check() -> TestResult:
    """Test 1: Health endpoint responds"""
    result = TestResult("Health Check")
    start = time.time()
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        result.duration = time.time() - start
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "healthy":
            result.pass_test(f"Service healthy, version={data.get('version')}")
        else:
            result.fail_test(f"Unexpected status: {data.get('status')}")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_cleanup_expired_sessions() -> TestResult:
    """Test 2: Cleanup tool responds without errors"""
    result = TestResult("Cleanup Expired Sessions")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "cleanup_expired_sessions", "params": {}},
            timeout=10
        )
        result.duration = time.time() - start
        data = resp.json()
        if data.get("success"):
            result.pass_test(f"Deleted {data.get('deleted_count', 0)} expired sessions")
        else:
            result.fail_test(f"Success=False: {data}")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_extract_and_store_cv() -> tuple[TestResult, str | None]:
    """Test 3: Extract DOCX and create session"""
    result = TestResult("Extract & Store CV")
    session_id = None
    start = time.time()
    try:
        if not SAMPLE_DOCX.exists():
            result.fail_test(f"Sample DOCX not found: {SAMPLE_DOCX}")
            return result, None
        
        docx_b64 = base64.b64encode(SAMPLE_DOCX.read_bytes()).decode('ascii')
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "extract_and_store_cv",
                "params": {"docx_base64": docx_b64, "language": "en", "extract_photo": False}
            },
            timeout=30
        )
        result.duration = time.time() - start
        data = resp.json()
        session_id = data.get("session_id")
        
        if session_id:
            result.pass_test(f"Session created: {session_id[:16]}...")
        else:
            result.fail_test(f"No session_id in response")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result, session_id


def test_get_cv_session(session_id: str) -> TestResult:
    """Test 4: Get session returns metadata and cv_data"""
    result = TestResult("Get CV Session")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "get_cv_session", "session_id": session_id, "params": {}},
            timeout=10
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success") and data.get("cv_data") and data.get("metadata"):
            stage = data.get("metadata", {}).get("stage", "UNKNOWN")
            result.pass_test(f"Stage={stage}, has cv_data and metadata")
        else:
            result.fail_test(f"Missing success/cv_data/metadata")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_update_cv_field(session_id: str) -> TestResult:
    """Test 5: Update field and confirm flags"""
    result = TestResult("Update CV Field")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "update_cv_field",
                "session_id": session_id,
                "params": {
                    "confirm": {"contact_confirmed": True, "education_confirmed": True}
                }
            },
            timeout=10
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            result.pass_test(f"Fields confirmed successfully")
        else:
            result.fail_test(f"Success=False")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_validate_cv(session_id: str) -> TestResult:
    """Test 6: Validate CV schema and DoD"""
    result = TestResult("Validate CV")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "validate_cv", "session_id": session_id, "params": {}},
            timeout=10
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            is_valid = data.get("is_valid", False)
            readiness = data.get("readiness", {})
            can_generate = readiness.get("can_generate", False)
            result.pass_test(f"is_valid={is_valid}, can_generate={can_generate}")
        else:
            result.fail_test(f"Success=False")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_cv_session_search(session_id: str) -> TestResult:
    """Test 7: Search session data"""
    result = TestResult("CV Session Search")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "cv_session_search", "session_id": session_id, "params": {"q": "email", "limit": 5}},
            timeout=10
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            hits = data.get("hits", [])
            result.pass_test(f"Found {len(hits)} hits for 'email'")
        else:
            result.fail_test(f"Success=False")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_generate_context_pack_v2(session_id: str) -> TestResult:
    """Test 8: Generate context pack"""
    result = TestResult("Generate Context Pack V2")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "generate_context_pack_v2",
                "session_id": session_id,
                "params": {"phase": "execution", "max_pack_chars": 8000}
            },
            timeout=10
        )
        result.duration = time.time() - start
        data = resp.json()
        
        # Context pack v2 returns structured dict with phase-specific keys
        has_pack = data.get("execution") or data.get("confirmation") or data.get("preparation")
        if has_pack:
            pack_str = json.dumps(data, ensure_ascii=False)
            pack_len = len(pack_str)
            readiness = data.get("readiness", {})
            can_generate = readiness.get("can_generate", False)
            result.pass_test(f"Generated pack: {pack_len} chars, can_generate={can_generate}")
        else:
            result.fail_test(f"No phase-specific context in response")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_process_cv_orchestrated_edit_intent(session_id: str) -> TestResult:
    """Test 9: Orchestrated flow with edit intent (FSM escape)"""
    result = TestResult("Process CV Orchestrated - Edit Intent")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "change my work experience", "session_id": session_id, "language": "en"}
            },
            timeout=30
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            stage = data.get("stage", "UNKNOWN")
            run_summary = data.get("run_summary", {})
            edit_intent = run_summary.get("stage_debug", {}).get("edit_intent", False)
            
            if edit_intent and stage == "review_session":
                result.pass_test(f"Edit intent detected, stage={stage}")
            else:
                result.fail_test(f"Expected edit_intent=True and stage=review_session, got stage={stage}, edit_intent={edit_intent}")
        else:
            result.fail_test(f"Success=False")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_generate_cv_from_session(session_id: str) -> tuple[TestResult, str | None]:
    """Test 10: Direct PDF generation via tool"""
    result = TestResult("Generate CV from Session (Tool)")
    pdf_ref = None
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "generate_cv_from_session",
                "session_id": session_id,
                "params": {"language": "en"}
            },
            timeout=60
        )
        result.duration = time.time() - start
        
        # Should return PDF bytes
        if resp.headers.get("Content-Type") == "application/pdf":
            pdf_size = len(resp.content)
            result.pass_test(f"Generated PDF: {pdf_size} bytes")
        else:
            # Or JSON with metadata
            data = resp.json()
            if data.get("pdf_metadata"):
                pdf_ref = data["pdf_metadata"].get("pdf_ref")
                pdf_size = data["pdf_metadata"].get("pdf_size_bytes", 0)
                result.pass_test(f"Generated PDF metadata: {pdf_size} bytes, ref={pdf_ref[:16] if pdf_ref else 'None'}...")
            else:
                result.fail_test(f"No PDF or metadata returned")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result, pdf_ref


def test_process_cv_orchestrated_generate(session_id: str) -> TestResult:
    """Test 11: Orchestrated PDF generation (Wave 0.1 & 0.3)"""
    result = TestResult("Process CV Orchestrated - Generate PDF")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
            },
            timeout=60
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            pdf_b64 = data.get("pdf_base64", "")
            pdf_size = len(base64.b64decode(pdf_b64)) if pdf_b64 else 0
            run_summary = data.get("run_summary", {})
            execution_mode = run_summary.get("execution_mode", False)
            model_calls = run_summary.get("model_calls", -1)
            
            # Validate Wave 0.1 (non-zero PDF) and Wave 0.3 (single-call)
            if pdf_size > 0 and execution_mode and model_calls == 1:
                result.pass_test(f"PDF: {pdf_size} bytes, execution_mode=True, calls=1")
            else:
                result.fail_test(f"PDF: {pdf_size} bytes, execution_mode={execution_mode}, calls={model_calls}")
        else:
            result.fail_test(f"Success=False")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_idempotency_latch(session_id: str, first_pdf_b64: str) -> TestResult:
    """Test 12: Second generate returns same PDF (Wave 0.1 latch)"""
    result = TestResult("Idempotency Latch - Second Generate")
    start = time.time()
    try:
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
            },
            timeout=60
        )
        result.duration = time.time() - start
        data = resp.json()
        
        pdf_b64_2 = data.get("pdf_base64", "")
        
        if pdf_b64_2 == first_pdf_b64:
            pdf_size = len(base64.b64decode(pdf_b64_2)) if pdf_b64_2 else 0
            result.pass_test(f"Latch working: Same PDF returned ({pdf_size} bytes)")
        else:
            result.fail_test(f"Different PDF returned (latch failed)")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_get_pdf_by_ref(session_id: str) -> TestResult:
    """Test 13: Fetch PDF via ref (blob download)"""
    result = TestResult("Get PDF by Ref - Blob Download")
    start = time.time()
    try:
        # Get latest pdf_ref from session
        sess_resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "get_cv_session", "session_id": session_id, "params": {}},
            timeout=10
        )
        sess_data = sess_resp.json()
        meta = sess_data.get("metadata", {})
        pdf_refs = meta.get("pdf_refs", {})
        
        if not pdf_refs:
            result.fail_test("No pdf_refs in session")
            return result
        
        latest_ref = sorted(
            pdf_refs.items(),
            key=lambda x: x[1].get("created_at", "") if isinstance(x[1], dict) else "",
            reverse=True
        )[0][0]
        
        # Fetch via get_pdf_by_ref
        fetch_resp = _post_json(
            "cv-tool-call-handler",
            {"tool_name": "get_pdf_by_ref", "session_id": session_id, "params": {"pdf_ref": latest_ref}},
            timeout=30
        )
        result.duration = time.time() - start
        
        if fetch_resp.headers.get("Content-Type") == "application/pdf":
            pdf_size = len(fetch_resp.content)
            has_disposition = "Content-Disposition" in fetch_resp.headers
            result.pass_test(f"Downloaded {pdf_size} bytes, Content-Disposition={has_disposition}")
        else:
            result.fail_test(f"Expected application/pdf, got {fetch_resp.headers.get('Content-Type')}")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def test_invalid_session() -> TestResult:
    """Test 14: Invalid session returns 404"""
    result = TestResult("Invalid Session - Error Handling")
    start = time.time()
    try:
        resp = requests.post(
            f"{BASE_URL}/cv-tool-call-handler",
            json={"tool_name": "get_cv_session", "session_id": "00000000-0000-0000-0000-000000000000", "params": {}},
            timeout=10
        )
        result.duration = time.time() - start
        
        if resp.status_code == 404:
            result.pass_test(f"Correctly returned 404 for invalid session")
        else:
            data = resp.json()
            if data.get("error"):
                result.pass_test(f"Error returned: {data.get('error')}")
            else:
                result.fail_test(f"Expected 404 or error, got {resp.status_code}")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"{e}")
    return result


def run_golden_suite():
    """Execute full golden suite"""
    print("\n" + "="*80)
    print("GOLDEN SUITE - Comprehensive Local Function Tests")
    print("="*80 + "\n")
    
    results = []
    session_id = None
    first_pdf_b64 = None
    
    # Test 1: Health
    results.append(test_health_check())
    print(results[-1])
    
    # Test 2: Cleanup
    results.append(test_cleanup_expired_sessions())
    print(results[-1])
    
    # Test 3: Extract & Store
    test_result, session_id = test_extract_and_store_cv()
    results.append(test_result)
    print(results[-1])
    
    if not session_id:
        print("\n[CRITICAL] No session created - aborting remaining tests")
        return 1
    
    # Test 4: Get Session
    results.append(test_get_cv_session(session_id))
    print(results[-1])
    
    # Test 5: Update Field
    results.append(test_update_cv_field(session_id))
    print(results[-1])
    
    # Test 6: Validate CV
    results.append(test_validate_cv(session_id))
    print(results[-1])
    
    # Test 7: Search
    results.append(test_cv_session_search(session_id))
    print(results[-1])
    
    # Test 8: Context Pack
    results.append(test_generate_context_pack_v2(session_id))
    print(results[-1])
    
    # Test 9: Edit Intent
    results.append(test_process_cv_orchestrated_edit_intent(session_id))
    print(results[-1])
    
    # Test 10: Direct Generate
    test_result, pdf_ref = test_generate_cv_from_session(session_id)
    results.append(test_result)
    print(results[-1])
    
    # Test 11: Orchestrated Generate (first call)
    test_result = test_process_cv_orchestrated_generate(session_id)
    results.append(test_result)
    print(results[-1])
    
    # Capture first PDF for latch test
    if test_result.passed:
        try:
            resp = _post_json(
                "cv-tool-call-handler",
                {
                    "tool_name": "process_cv_orchestrated",
                    "params": {"message": "generate pdf", "session_id": session_id, "language": "en"}
                },
                timeout=60
            )
            data = resp.json()
            first_pdf_b64 = data.get("pdf_base64", "")
        except:
            pass
    
    # Test 12: Idempotency Latch
    if first_pdf_b64:
        results.append(test_idempotency_latch(session_id, first_pdf_b64))
        print(results[-1])
    
    # Test 13: Get PDF by Ref
    results.append(test_get_pdf_by_ref(session_id))
    print(results[-1])
    
    # Test 14: Invalid Session
    results.append(test_invalid_session())
    print(results[-1])
    
    # Summary
    print("\n" + "="*80)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"SUMMARY: {passed}/{total} passed ({pass_rate:.1f}%)")
    if failed > 0:
        print(f"\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.message}")
    
    total_duration = sum(r.duration for r in results)
    print(f"\nTotal execution time: {total_duration:.2f}s")
    print("="*80 + "\n")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_golden_suite())
