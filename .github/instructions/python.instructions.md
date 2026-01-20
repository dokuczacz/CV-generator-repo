---
applyTo: "**/*.py"
name: Python Azure Functions conventions
description: Best practices for Azure Functions Python code in this repository
---

# Python Azure Functions Conventions

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

## Avoid

- ❌ Modifying runtime files (Azure Functions core code).
- ❌ Global variables (use function parameters instead).
- ❌ Long-running synchronous code (use async if needed).
- ❌ Hardcoded paths (use `Path()` or env vars).
- ❌ Importing from unvetted external sources.

## References

- [Azure Functions Python Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [PEP 8 Style Guide](https://pep8.org/)
- [Python logging](https://docs.python.org/3/library/logging.html)

