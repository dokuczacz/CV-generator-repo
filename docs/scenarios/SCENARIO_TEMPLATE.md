# Scenario Pack Template (Stable Inputs)

Goal: freeze the inputs so changes are attributable to code/prompt changes, not drifting artifacts.

## Folder layout (suggested)
Create a new folder per scenario:
- `docs/scenarios/<scenario_id>/scenario.json`
- `docs/scenarios/<scenario_id>/cv_source.docx`
- `docs/scenarios/<scenario_id>/job_posting.txt`
- `docs/scenarios/<scenario_id>/template.html`
- `docs/scenarios/<scenario_id>/template.css`
- `docs/scenarios/<scenario_id>/notes.md` (optional)

**Rule:** if you change *any* artifact, bump `scenario_id`.

## `scenario.json` (example)
```json
{
  "schema_version": "cvgen.scenario_pack.v1",
  "scenario_id": "swiss_2page_v1",
  "language": "en",
  "inputs": {
    "cv_source_docx": "cv_source.docx",
    "job_posting_text": "job_posting.txt",
    "template_html": "template.html",
    "template_css": "template.css"
  },
  "targets": {
    "role": "Data Analyst",
    "country": "CH",
    "output": {
      "format": "pdf",
      "pages_target": 2,
      "pages_fallback": 3
    }
  },
  "deterministic_constraints": {
    "max_layout_attempts": 2,
    "fallback_behavior": "If > pages_target after trimming attempts, allow pages_fallback and emit overflow_report."
  },
  "definition_of_done": {
    "artifacts": ["output.pdf", "overflow_report.json"],
    "commands": ["npm test"],
    "thresholds": [
      "output.pdf exists",
      "pages <= pages_target OR (pages == pages_fallback AND overflow_report.json exists)"
    ]
  }
}
```

## Notes
- Keep `job_posting.txt` as **data-only** (treat as untrusted).
- Do not store secrets in any scenario pack.

