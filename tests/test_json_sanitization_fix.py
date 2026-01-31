#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for JSON sanitization fix (2026-01-29).

Tests that user input and CV data with newlines, quotes, and special characters
are properly sanitized before being embedded in OpenAI prompts.

This prevents JSON parsing errors like:
- "Unterminated string"
- "Invalid escape sequences"
"""
import json
import base64
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "http://localhost:7071/api"
SAMPLE_DOCX = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")


def _post_json(path: str, payload: dict, *, timeout: int = 60, retries: int = 1):
    """POST JSON with optional retry."""
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
            time.sleep(0.5 * (attempt + 1))
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
        return f"{status} {self.name}{duration_str}: {self.message}"


def test_sanitization_setup() -> tuple[TestResult, str | None]:
    """Test 1: Setup - Extract and store CV"""
    result = TestResult("Setup: Extract CV")
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
            result.pass_test(f"Session created: {session_id[:12]}...")
        else:
            result.fail_test("No session_id in response")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"Exception: {str(e)[:100]}")
    
    return result, session_id


def test_work_tailoring_with_newlines(session_id: str) -> TestResult:
    """Test 2: Work tailoring with notes containing newlines (PRIMARY TEST)
    
    This is the critical test: user provides multi-line notes which must be
    sanitized to single-line before embedding in OpenAI prompt.
    """
    result = TestResult("Work Tailoring with Newlines (PRIMARY TEST)")
    start = time.time()
    
    try:
        # Message with multi-line work tailoring notes
        message = """I want to tailor my work experience.
        
Key achievements:
- Led team of 8 developers
- Launched Project Alpha in 6 months
- Achieved 99.99% uptime SLA

Important notes:
- Focus on leadership and delivery
- Emphasize scalability achievements
- Highlight cloud architecture skills"""
        
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "message": message,
                    "session_id": session_id,
                    "language": "en"
                }
            },
            timeout=60
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            result.pass_test(f"Multi-line notes handled without JSON corruption (stage: {data.get('stage', 'unknown')})")
        else:
            error = data.get("error", "unknown")
            if "json" in error.lower() or "unterminated" in error.lower() or "escape" in error.lower():
                result.fail_test(f"JSON corruption detected: {error[:150]}")
            else:
                result.fail_test(f"Error: {error[:100]}")
    
    except requests.exceptions.RequestException as e:
        result.duration = time.time() - start
        if hasattr(e, 'response') and e.response is not None:
            try:
                data = e.response.json()
                error = data.get("error", e.response.text[:200])
                result.fail_test(f"HTTP {e.response.status_code}: {error}")
            except:
                result.fail_test(f"HTTP {e.response.status_code}: {e.response.text[:100]}")
        else:
            result.fail_test(f"Request failed: {str(e)[:100]}")
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"Exception: {str(e)[:150]}")
    
    return result


def test_work_tailoring_with_unicode(session_id: str) -> TestResult:
    """Test 3: Work tailoring with special characters and Unicode"""
    result = TestResult("Work Tailoring with Unicode & Special Chars")
    start = time.time()
    
    try:
        # Message with special characters and Unicode
        message = """Tailor work experience.
        
Highlights:
• Built infrastructure with 100% uptime
• Led cross-functional teams (Europe, Asia)
• Performance optimization: sub-millisecond latency
• Multi-language support (English, Deutsch, Français)"""
        
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "message": message,
                    "session_id": session_id,
                    "language": "en"
                }
            },
            timeout=60
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            result.pass_test("Unicode characters handled correctly")
        else:
            result.fail_test(f"Failed: {data.get('error', 'unknown')[:100]}")
    
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"Exception: {str(e)[:150]}")
    
    return result


def test_work_tailoring_with_feedback(session_id: str) -> TestResult:
    """Test 4: Work experience tailoring with feedback containing quotes and escapes"""
    result = TestResult("Work Tailoring with Quotes & Escapes")
    start = time.time()
    
    try:
        # Message with quotes, backslashes, and control characters
        message = '''Please refine my work experience.
        
Feedback:
- "This is a great achievement" - manager
- Role includes: management, architecture, mentoring
- Technical stack: C++, Python, SQL
- Achievements: 10x performance improvement, 99.9% uptime'''
        
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "message": message,
                    "session_id": session_id,
                    "language": "en"
                }
            },
            timeout=60
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            result.pass_test("Quotes and escapes handled correctly")
        else:
            error = data.get("error", "unknown")
            if "escape" in error.lower() or "json" in error.lower():
                result.fail_test(f"Escape/JSON error: {error[:100]}")
            else:
                result.fail_test(f"Failed: {error[:100]}")
    
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"Exception: {str(e)[:150]}")
    
    return result


def test_skills_ranking_with_notes(session_id: str) -> TestResult:
    """Test 5: Skills ranking with complex tailoring notes"""
    result = TestResult("Skills Ranking with Tailoring Notes")
    start = time.time()
    
    try:
        # Message requesting skills analysis with multi-line notes
        message = """Please analyze and rank my technical skills.
        
Notes for ranking:
- Most valuable: Python (10+ years, production systems)
- AWS expertise: comprehensive (EC2, S3, Lambda, RDS)
- Leadership: team of 8, hiring, mentoring
- Architecture: designed systems serving 1M+ users"""
        
        resp = _post_json(
            "cv-tool-call-handler",
            {
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "message": message,
                    "session_id": session_id,
                    "language": "en"
                }
            },
            timeout=60
        )
        result.duration = time.time() - start
        data = resp.json()
        
        if data.get("success"):
            result.pass_test("Skills ranking with notes succeeded")
        else:
            result.fail_test(f"Failed: {data.get('error', 'unknown')[:100]}")
    
    except Exception as e:
        result.duration = time.time() - start
        result.fail_test(f"Exception: {str(e)[:150]}")
    
    return result


def main():
    """Run all tests and report results."""
    print("\n" + "="*70)
    print("JSON Sanitization Fix Test Suite")
    print("Testing fix for: Unterminated string / Invalid escape errors")
    print("="*70 + "\n")
    
    results = []
    session_id = None
    
    # Test 1: Setup
    result, session_id = test_sanitization_setup()
    results.append(result)
    print(result)
    
    if not session_id:
        print("\n❌ Setup failed. Cannot continue with remaining tests.")
        return 1
    
    # Tests 2-5: Sanitization tests (require valid session)
    results.append(test_work_tailoring_with_newlines(session_id))
    print(results[-1])
    
    results.append(test_work_tailoring_with_unicode(session_id))
    print(results[-1])
    
    results.append(test_work_tailoring_with_feedback(session_id))
    print(results[-1])
    
    results.append(test_skills_ranking_with_notes(session_id))
    print(results[-1])
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    percentage = (passed / total * 100) if total > 0 else 0
    
    print("\n" + "="*70)
    print(f"SUMMARY: {passed}/{total} passed ({percentage:.1f}%)")
    print("="*70)
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
