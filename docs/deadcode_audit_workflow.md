# Dead-Code Audit Workflow

This repo uses report-first dead-code checks to reduce refactor risk.

## Install tools (local dev)

```powershell
Set-Location "c:\AI memory\CV-generator-repo"
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Run report mode (default)

```powershell
Set-Location "c:\AI memory\CV-generator-repo"
python scripts/deadcode_scan.py
```

Or via npm wrapper (auto-prefers repo `.venv`):

```powershell
npm run deadcode:python
```

Artifacts are written to `tmp/deadcode/`:
- `deadcode-report-<timestamp>.md`
- `ruff-<timestamp>.txt`
- `vulture-<timestamp>.txt`

## Run gate mode (non-zero on findings)

```powershell
Set-Location "c:\AI memory\CV-generator-repo"
python scripts/deadcode_scan.py --fail-on-findings
```

Or:

```powershell
npm run deadcode:python:strict
```

## Conservative removal policy

Only remove code when all are true:
1. No static references in repo (`rg`, dispatch strings, route/tool wiring).
2. Not reachable from known entry points.
3. Not exercised by baseline tests.
4. No scenario/docs dependency.

If uncertain, mark as `Deprecate` and keep until evidence is complete.
