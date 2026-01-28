# Wave 0 Integration Testing Report

## Executive Summary

Integration testing of Wave 0 features against the local Azure Functions endpoint revealed several critical issues that require resolution before the function can be properly tested:

### Key Findings

1. **Azure Functions Startup Issue**
   - Local `func start` doesn't properly bind to port 7071
   - Worker initializes but HTTP listener not fully active
   - Impacts: Cannot test any Wave 0 features live
   - Severity: **CRITICAL** - Blocks all integration testing

2. **Python Version Compatibility**
   - System Python 3.13.2 → NOT supported by Azure Functions Core Tools
   - Virtual environment Python 3.11.9 → SUPPORTED ✓
   - Solution: Must use venv-activated shell for `func start`

3. **Wave 0.1 (Idempotency Latch) - Unit Tests PASS**
   - Unit tests: 4/4 passing
   - Implementation: Checks `meta["pdf_refs"]` for cached PDFs
   - Status: Code is correct, needs live testing

4. **Wave 0.2 (FSM Terminal State) - Unit Tests PASS**
   - Unit tests: 9/9 passing
   - Implementation: `ValidationState(pdf_generated, pdf_failed)` flags
   - Status: Code is correct, needs live testing

5. **Wave 0.3 (Single-Call Execution) - Unit Tests PASS, Live Issue Found**
   - Unit tests: 5/5 passing
   - Early integration test showed: `model_calls=2` (expected 1)
   - Implementation: `execution_mode=(stage == "generate_pdf")` flag
   - Status: **POSSIBLE CODE DEFECT** - Feature flag may not be working

---

## Detailed Findings

### Finding 1: Function Startup Not Responding

**What Happened:**
- Ran `func start` from venv in CV-generator-repo
- Function shows as initialized: "Worker process started and initialized"
- HTTP endpoint listed: `http://localhost:7071/api/cv-tool-call-handler`
- However: Port 7071 refuses connections (WinError 10061)

**Root Cause (Hypothesis):**
- Azure Functions Core Tools 4.0.6821 may have binding issue on Windows
- OR function_app.py has initialization error preventing listener activation

**Evidence:**
```
[2026-01-27T13:45:57.607Z] Worker process started and initialized.
Functions:
  cv_tool_call_handler: [POST] http://localhost:7071/api/cv-tool-call-handler
...
but: HTTPConnectionError - [WinError 10061] Connection refused
```

**Next Steps to Investigate:**
1. Check function_app.py for initialization errors (missing imports, bad config)
2. Try running func with verbose flag: `func start --verbose`
3. Check if port 7071 is in use by other process: `netstat -ano | findstr :7071`
4. Try explicit port binding: `func start --port 7071`

---

### Finding 2: Wave 0.3 - Single-Call Execution Not Working

**What Happened (from early integration test run):**
- Generated PDF for session
- Ran: `process_cv_orchestrated` with `message: "generate pdf"`
- Response showed: `model_calls: 2, max_model_calls: 5`
- Expected: `model_calls: 1` (Wave 0.3 contract)

**Code Review:**
```python
# function_app.py line 2539
execution_mode=(stage == "generate_pdf")

# function_app.py line 1468
def _run_responses_tool_loop_v2(..., execution_mode=False, ...):
    if execution_mode:
        max_model_calls = 1  # Should limit to 1
```

**Possible Issues:**
1. `stage != "generate_pdf"` at execution time (stage is something else)
2. `execution_mode` parameter not being passed correctly
3. `max_model_calls=1` override not taking effect
4. Multiple call sites with different execution_mode values

**Evidence Needed:**
- Logs showing actual `stage` value when PDF generation happens
- Logs showing `execution_mode` value passed to _run_responses_tool_loop_v2
- Trace of model_calls count

---

### Finding 3: PDF Generation Returns 0 Bytes

**What Happened (from early integration test):**
- Generated PDF returned `pdf_base64=""` or 0-byte PDF
- Indicates PDF rendering failed silently

**Possible Root Causes:**
- Template rendering issue (missing CV data, bad Jinja2 template)
- WeasyPrint/PDF generation library issue
- File write permissions to blob storage

**Evidence Needed:**
- Check function logs for PDF rendering errors
- Verify CV_DATA extraction from test DOCX
- Check blob storage access

---

## Recommendations

### Immediate Actions (Order)

1. **Fix Function Startup**
   ```bash
   cd "c:/AI memory/CV-generator-repo"
   & ".venv/Scripts/activate"
   func start --verbose  # Add verbose logging
   ```
   - Check output for errors during initialization
   - Look for port binding errors

2. **Verify Port Not In Use**
   ```powershell
   netstat -ano | findstr :7071
   Get-Process -Id <PID> 2>$null  # If port in use
   ```

3. **Add Diagnostic Logging to Wave 0.3**
   - Log `stage` value when executing PDF generation
   - Log `execution_mode` passed to _run_responses_tool_loop_v2
   - Log `model_calls` count during execution

4. **Re-run Integration Tests**
   - Once function is responding
   - With diagnostic logging enabled
   - Against test_wave0_integration.py

### Medium-Term (After Function Fixes)

5. **Validate All Wave 0 Features**
   - Idempotency latch: Upload CV → Generate PDF → Generate again → Verify same PDF
   - FSM transitions: Generate PDF → Send edit intent → Verify DONE→REVIEW
   - Single-call execution: Monitor `model_calls` count during generation

6. **Test Prompt Integration**
   - User message detection accuracy (generate vs edit intent)
   - Response message quality
   - JSON response schema compliance

7. **Test Orchestration**
   - Session persistence across calls
   - State machine transitions (all 6 stages)
   - Error handling and recovery

---

## Test Scripts Created

### tests/test_wave0_integration.py
- Full integration test with all Wave 0 scenarios
- Requires working Azure Functions endpoint
- Tests: health check, session creation, idempotency, FSM, single-call

### tests/test_wave0_simple.py
- Minimal connectivity test
- Used for debugging endpoint issues
- Can run without full test data

---

## Wave 0 Code Status Summary

| Item | Unit Tests | Code Review | Live Test | Status |
|------|-----------|-------------|-----------|--------|
| 0.1 Idempotency Latch | 4/4 PASS | OK | BLOCKED | Ready for live testing |
| 0.2 FSM Terminal State | 9/9 PASS | OK | BLOCKED | Ready for live testing |
| 0.3 Single-Call Execution | 5/5 PASS | Questionable | FAILED (model_calls=2) | Needs fix or debugging |

---

## Known Constraints

- Azure Functions Core Tools requires Python 3.7-3.12 (not 3.13)
- Local development requires venv activation
- Integration testing blocked until endpoint responds
- Wave 0.3 appears to have a defect in execution_mode parameter handling

---

## Next Session Checklist

- [ ] Run `func start --verbose` and capture full startup log
- [ ] Check if port 7071 is already in use
- [ ] Add logging to _run_responses_tool_loop_v2 to trace execution_mode
- [ ] Re-test Wave 0.3 with diagnostic logs
- [ ] Run full integration test suite once endpoint responds
- [ ] Document findings in separate issue
