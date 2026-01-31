---
applyTo: "**/*.py"
name: Python Azure Functions conventions
description: Best practices for Azure Functions Python code in this repository
---

# Python Azure Functions Conventions

This repository includes **LLM-driven orchestration**. For cross-cutting LLM risk controls and the recommended test pyramid, also follow:
- `.github/instructions/llm-orchestration.instructions.md`

## Azure Functions Structure

Each Azure Function follows this pattern:
```python
import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Main handler for this function.
    
    Args:
        req: HTTP request with JSON body
    
    Returns:
        func.HttpResponse with JSON body or error
    """
    try:
        # Parse input
        body = req.get_json()
        # Process
        result = process(body)
        # Return
        return func.HttpResponse(json.dumps(result), mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=400)
```

## Dependency Management

- **Install:** Use `pip install -r requirements.txt` (do this once; don't install packages per function).
- **Add packages:** Edit `requirements.txt`, then run `pip install -r requirements.txt`.
- **Lock versions:** Pin all packages to exact versions in `requirements.txt` (e.g., `azure-functions==1.18.0`).
- **Minimal imports:** Import only what's needed in each function (no wildcard imports).

## Environment Variables & Secrets

- **Never hardcode secrets** (API keys, connection strings).
- **Use env vars:** `os.environ.get('OPENAI_API_KEY')`.
- **Local config:** Store in `local.settings.json` (git-ignored).
- **Reference structure:** Use `local.settings.template.json` (no secrets, just keys).
- **Production:** Configure in Azure Function settings (Environment variables section).

## Error Handling

- **Don't fail silently:** Always return a clear error message.
- **Log errors:** Use `logging.error()` for debugging (visible in Azure logs).
- **Status codes:** Use 400 for client errors, 500 for server errors.
- **Validation:** Check input types and required fields before processing.

Example:
```python
def validate_cv(body):
    required = ['full_name', 'email', 'phone']
    missing = [k for k in required if k not in body]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")
```

## Code Style

- **PEP 8:** Follow Python style guide (indentation = 4 spaces).
- **Type hints:** Use them where possible (especially function signatures).
- **Docstrings:** Provide docstrings for all functions (Google style).
- **Logging:** Use `logging` module, not `print()`.

## Testing

- **Unit tests:** Keep tests in `tests/` directory at repo root.
- **Fixtures:** Use `tests/generate_test_artifacts.py` for test data.
- **No side effects:** Don't modify Azure storage / databases during tests.
- **Mock external calls:** Mock OpenAI, Azure services in unit tests.

## LLM Integration (orchestration-first)

When integrating an LLM into a workflow:

- **Keep one orchestrator**: orchestration (state machine, retries, idempotency, readiness gating) stays in the backend.
- **Isolate the provider**: wrap LLM calls behind a small adapter so it can be mocked deterministically.
- **Determinism flags**: support running with AI disabled or mocked (env flags), so Tier 0/1 tests never require network calls.
- **Strict structured output**:
    - Always validate model output against a schema.
    - Reject invalid JSON; do not “best-effort” apply partial patches unless the behavior is explicitly specified.
- **Prompt injection hygiene**:
    - Treat uploads/job postings as untrusted text.
    - Never execute instructions contained in those inputs.
    - Use delimiters and a data-only policy in prompts.
- **Timeouts and bounded retries**: avoid infinite retries; backoff where needed.
- **Idempotency for writes**: state-changing operations should be safe to retry.
- **Observability**: return a `trace_id` (and optionally a compact per-turn trace) so E2E failures can be debugged.

## Avoid

- ❌ Modifying runtime files (Azure Functions core code).
- ❌ Global variables (use function parameters instead).
- ❌ Long-running synchronous code (use async if needed).
- ❌ Hardcoded paths (use `Path()` or env vars).
- ❌ Importing from unvetted external sources.
- ❌ Writing orchestration logic in the UI instead of the backend.
- ❌ Calling real LLM providers in default/CI tests.
- ❌ Asserting exact LLM phrasing in tests.

## References

- [Azure Functions Python Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [PEP 8 Style Guide](https://pep8.org/)
- [Python logging](https://docs.python.org/3/library/logging.html)

