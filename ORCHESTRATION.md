# CV Generator Orchestration (MVP)

This is the **current** end‑to‑end orchestration for the MVP after removing lab/legacy endpoints and tools.

## 1) Public API surface

Backend (Azure Functions) exposes only:
- `GET /api/health`
- `POST /api/cv-tool-call-handler`

UI (Next.js) exposes:
- `POST /api/process-cv`

Everything else is internal/private implementation.

## 2) Core loop (UI `/api/process-cv`)

File: `ui/app/api/process-cv/route.ts`

High level:
1. Parse request (`message`, optional `docx_base64`, optional `session_id`, optional `job_posting_url/text`).
2. Best-effort fetch of `job_posting_text` (UI-side). If missing and not generating, short-circuit asking user to paste the posting.
3. **Deterministic extraction**: if `docx_base64` is provided and `session_id` is missing, the UI first calls the backend tool `extract_and_store_cv` via the dispatcher to obtain a new `session_id`.
4. Determine stage:
   - Session present + user asked to generate → `generate_pdf`
   - Session present otherwise → `review_session`
   - No session → `bootstrap`
5. Fetch `ContextPackV2` via dispatcher tool `generate_context_pack_v2` (only when session exists).
6. Prefetch a compact session snapshot via dispatcher tool `get_cv_session` (only when session exists) and inject it into the model input.
7. Call OpenAI Responses API and iterate:
   - Read tool calls from model output
   - Execute each via `processToolCall()` which routes to `/cv-tool-call-handler`
   - Append tool outputs back into the next model input
8. Tool gating:
   - `generate_cv_from_session` is only allowed in execution stage and only once per request.
   - Non-2xx backend responses are logged with HTTP status + body snippet so failures are visible immediately.

## 3) Dispatcher contract (single backend endpoint)

Endpoint: `POST /api/cv-tool-call-handler`

Request shape:
```json
{
  "tool_name": "get_cv_session",
  "session_id": "uuid-...",
  "params": { }
}
```

Response:
- JSON for most tools (`application/json`)
- Raw PDF bytes for `generate_cv_from_session` (`application/pdf`)

OpenAI tool schema for the dispatcher (copy/paste for dashboard if you want the model to call the dispatcher directly):
- `schemas/openai_cv_tool_call_handler_schema.json`

## 4) Backend tools (via dispatcher)

Implementation: `function_app.py`

Tools currently supported:
- `cleanup_expired_sessions` (no session)
- `extract_and_store_cv` (no session) → returns `session_id`
- `get_cv_session` → returns `cv_data`, `metadata`, and `readiness`
- `update_cv_field` → supports `field_path/value`, `edits[]`, `cv_patch`, and `confirm` flags
- `generate_context_pack_v2` → returns capsule for phase (`preparation|confirmation|execution`)
- `cv_session_search` → bounded search across `cv_data`, `docx_prefill_unconfirmed`, recent `event_log`
- `validate_cv` → deterministic schema + DoD checks (no PDF render)
- `preview_html` → debug HTML render
- `generate_cv_from_session` → final PDF (strict 2 pages)

## 5) Sessions + determinism (start-from-zero)

Session store: `src/session_store.py` (Azure Table Storage via Azurite locally)

Creation (`extract_and_store_cv`):
- `cv_data` starts as canonical empty schema (no stale merges)
- `metadata.docx_prefill_unconfirmed` stores extracted DOCX snapshot (reference-only until confirmed)
- `metadata.confirmed_flags` starts `false` (`contact_confirmed`, `education_confirmed`)

Updates (`update_cv_field`):
- Writes to the persisted session (source of truth for the final PDF)
- Auto-expands list indices (`work_experience[0].…` works even when list is empty)
- Appends a bounded `event_log` entry to help stateless continuity

Readiness + gating:
- `get_cv_session` returns `readiness` (`can_generate`, `required_present`, `confirmed_flags`, `missing`)
- `generate_cv_from_session` rejects if readiness is not met (structured `readiness_not_met` error)

## 6) ContextPackV2 (capsule)

Builder: `src/context_pack.py` (called via dispatcher tool `generate_context_pack_v2`)

Key properties:
- Phase-specific capsule (`preparation|confirmation|execution`)
- Includes `<docx_prefill_unconfirmed>` in preparation so the model can recover Education/Contact without asking again
- Enforces a bounded size (default 12k chars); compaction affects only the capsule, not stored session data

## 7) OpenAI request payload (what the UI sends)

Builder: `ui/lib/capsule.ts`

The UI uses:
- Dashboard prompt mode when `OPENAI_PROMPT_ID` is set (system instructions come from OpenAI dashboard)
- Repo fallback system prompt only when `OPENAI_PROMPT_ID` is missing (`ui/lib/prompts.ts`)

`store` default:
- `store: false` by default (ZDR; no CV data retention on OpenAI side)
- Set `OPENAI_STORE=1` only for debugging dashboard logs

## 8) What is NOT used in MVP

- Legacy endpoints for direct tool calls (removed from public surface)
- Legacy V1 “generate-context-pack” endpoint (removed from UI code path)
- Lab-only tool names like `generate_cv_action` / `extract_photo` as standalone tools

