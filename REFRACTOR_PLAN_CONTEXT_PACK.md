# Refactor Plan: JSON-first Context Pack (minimize model effort)

Date: 2026-01-20

## Assumptions
- Goal: reduce LLM “effort” by moving CV parsing + structuring into backend code, so the model mostly applies user-requested deltas and calls tools with ready JSON.
- Keep multi-turn continuity via Responses API `previous_response_id` / `last_response_id` (already implemented).
- Avoid re-sending large blobs (DOCX/PDF base64, full CV text) to the model.

## Current State (baseline)
- UI persists `last_response_id` and sends `previous_response_id` on next request.
- Backend extracts DOCX text via `mammoth` and injects bounded text into the model input on first turn.
- Tools exist: `extract_photo`, `validate_cv`, `generate_cv_action`.
- Tool outputs are sanitized to avoid feeding base64 back into the model.

## Problem
- The model currently does a lot of work: it must parse semi-structured CV text into the JSON schema required by `validate_cv`/`generate_cv_action`.
- This increases cost and increases probability of: missing fields, re-asking for info, token bloat, and context-window failures.

## Target Outcome
- Backend produces a compact, bounded JSON “context pack” (source of truth).
- Model input becomes: user message + `[CONTEXT_PACK_JSON] ...` + minimal system rules.
- Model is instructed to:
  1) only apply user-requested modifications to the JSON,
  2) then call `validate_cv`,
  3) then call `generate_cv_action`.

## Acceptance Criteria
1) First turn: server builds `ContextPackV1` within size cap (e.g., ≤ 12k chars JSON).
2) Model receives only the pack (not raw DOCX base64, not full CV text).
3) Tool calls contain complete JSON arguments (no “re-parsing” required).
4) Multi-turn: follow-ups reuse the same context pack until CV changes.
5) No context-window regressions in typical flows.

## Work Unit Boundary (estimate)
- Files: 3–5
- Diff: ~200–450 LOC
- Classification: GREEN→YELLOW (GREEN if we keep it to route + 1 helper + UI; YELLOW if adding tests)

## Design: `ContextPackV1`

### Schema (high level)
```json
{
  "schema_version": "cvgen.context_pack.v1",
  "language": "pl|en|de",
  "cv_fingerprint": "sha256:...",
  "inputs": {
    "has_docx": true,
    "job_url": "https://...",
    "skip_photo": false
  },
  "cv_structured": {
    "full_name": "...",
    "email": "...",
    "phone": "...",
    "address_lines": ["..."],
    "profile": "...",
    "work_experience": [ ... ],
    "education": [ ... ],
    "languages": [ ... ],
    "it_ai_skills": [ ... ],
    "certifications": [ ... ],
    "interests": "..."
  },
  "job_posting": {
    "url": "https://...",
    "text_snippet": "...",
    "fingerprint": "sha256:..."
  },
  "user_preferences": {
    "target_role": "...",
    "seniority": "...",
    "location_preference": "...",
    "omit_photo": false
  },
  "limits": {
    "max_pack_chars": 12000,
    "cv_text_max_chars": 0,
    "job_text_max_chars": 6000
  }
}
```

### Size and safety rules
- Never include base64 (`docx_base64`, `pdf_base64`, `photo_data_uri`) in the pack.
- Pack JSON must be bounded and stable (deterministic field ordering where possible).
- Store only *snippets* of job posting text (already bounded to ~6000 chars).

## Implementation Plan (PDCA)

### Phase 1 — Backend context pack builder (deterministic)
**Goal:** build `ContextPackV1` without LLM.

- Create helper `buildContextPackV1({ userMessage, cvText, jobText, url })`.
- Extract deterministic fields:
  - email / phone / links (regex)
  - name candidate (first non-empty line heuristics)
  - sections by headings (PL/EN/DE keywords)
  - date ranges (best-effort normalization to `YYYY-MM` when possible)
- Output `cv_structured` matching the JSON schema expected by `validate_cv`.
- Compute `cv_fingerprint` as hash of normalized CV text.

### Phase 2 — Prompt contract: JSON-in → tools-out
**Goal:** minimize model reasoning.

- Replace injected `[CV text extracted...]` with `[CONTEXT_PACK_JSON]`.
- Update system prompt rules:
  - “Do not parse CV text; treat `context_pack.cv_structured` as truth.”
  - “Only apply changes explicitly requested by the user.”
  - “Then call validate_cv, then generate_cv_action.”

### Phase 3 — Persistence/reuse across turns
**Option A (minimal):** store pack in the browser.
- Persist `context_pack` in `localStorage` alongside `last_response_id`.
- Send pack to backend on each request.
- Reset pack when a new CV file is uploaded or fingerprint changes.

**Option B (server-side):** persist per user/thread (more infra; avoid unless required).

### Phase 4 — OmniFlow-style resilience (recommended hardening)
- “Safe persist” for `last_response_id`: return/persist only when the run ended terminally (no pending tool calls, not max-iteration).
- Self-heal: if OpenAI returns “No tool output found …”, retry once without `previous_response_id` and clear stored pointer.
- Add env-controlled `max_output_tokens` and downgrade on “request too large/TPM/context” errors.

## Rollback Strategy
- Gate new behavior behind `CV_USE_CONTEXT_PACK=1` (default off until stable).
- Keep old bounded CV-text injection available while iterating.

## Verification
### Manual
1) Upload DOCX + message “generate CV” → ensure tools called in order `validate_cv` → `generate_cv_action`.
2) Follow-up “remove photo / change summary” → ensure pack reused and no CV text re-sent.

### Automated (optional but recommended)
- Unit test for `buildContextPackV1()`:
  - stable schema
  - respects max chars
  - extracts email/phone

## Notes
- The tool-side schema requirements are documented in PROMPT_INSTRUCTIONS.md; the builder should output that structure to reduce model work.
