## CV Generator Orchestration

This document describes how the CV generation workflow is orchestrated end‑to‑end. It covers the backend Azure Functions, the UI request pipeline, the contextual capsule, and the system/stage prompts that steer the model. All major participants are described so you can review how data flows and how stages are guarded.

### 1. Entry point (UI `/api/process-cv`)

- **Request handling** (`ui/app/api/process-cv/route.ts`):
  1. Parses the HTTP body (`message`, `docx_base64`, `session_id`, `job_posting_url/text`).
  2. If the request carries a DOCX, the UI extracts its text once (bounded to 12 000 chars) for diagnostics (not used for orchestration when a session exists).
  3. Determines `stage` based on existing session and intent (`generate_pdf` only when user explicitly asks for PDF; otherwise defaults to `review_session` or `extract`).
  4. Pulls `ContextPackV2` if a session exists; otherwise skips the pack (bootstrap/extract is driven by tools).
  5. Builds prompts for the OpenAI request:
     * **Dashboard prompt mode (default in prod/dev):** when `OPENAI_PROMPT_ID` is set, the request uses `promptId=...` and `systemPrompt` is sent as an empty string.
     * **Local fallback mode:** when `OPENAI_PROMPT_ID` is missing, the request sends `systemPrompt=CV_SYSTEM_PROMPT` from `ui/lib/prompts.ts`.
     * The **stage prompt** always comes from `CV_STAGE_PROMPT(stage)` in `ui/lib/prompts.ts` and is included in the request.
  6. Controls tool availability per stage:
     * Blocks all generation tools until `required_present` (contact + education + work) is true.
     * Once `canGenerate` is true, enables `generate_cv_from_session` only once per iteration; duplicate attempts are rejected.
     * `extract_and_store_cv` is automatically blocked whenever a session already exists to prevent deterministic loops.
  7. Iteratively calls OpenAI Responses with up to 10 iterations, passing:
     * `inputList` (user + tool outputs).
     * `tools` (filtered per iteration, stage, and generate attempts).
     * Stage prompt + system prompt.
  8. After every iteration:
     * Checks returned function calls (tools), executes them via `callAzureFunction`, and appends outputs for the next iteration.
     * Updates stage via `stageFromTool`.
     * Blocks generation after the first successful PDF.
  9. Non-OK tool responses log the HTTP status + body snippet to the UI console (makes backend errors visible).

### 2. Backend Azure Functions

- **Session reset + extraction** (`extract-and-store-cv`):
  * Creates a fresh session and ensures the session’s persisted artifacts start from zero (no carry-over from prior runs).
  * Decodes the DOCX and runs `prefill_cv_from_docx_bytes`.
  * **First major change:** only metadata is populated. `cv_data` is initialized as a canonical empty object (blank name, contact, lists).
  * Metadata now stores:
    * `prefill_summary` (counts / lengths for logging).
    * `docx_prefill_unconfirmed` (bounded snapshot of contact, education, work, skills, interests, etc. with a note that it is **UNCONFIRMED**).
  * The blank `cv_data` is saved via `CVSessionStore`.

- **Session store** (`src/session_store.py`):
  * Uses Azure Table Storage; each session keeps serialized `cv_data` and metadata with `event_log`.
  * `update_field` now auto-expands list indexes (e.g., writing `work_experience[0].employer` on an empty array will append an entry and set the field).

- **Context packs** (`/generate-context-pack-v2`, `src/context_pack.py`):
  * `ContextPackV2` contains phase-specific data + the capsule sent to the model.
  * Key sections:
    * `preparation`: compact CV, proposal history, and `docx_prefill_unconfirmed` reference.
    * `confirmation`: summary + diff vs original metadata (if present).
    * `execution`: `approved_cv_data`, hard limits, checklist.
    * `completeness`: `required_present` booleans, counts, `next_missing_section`.
    * `hard_limits`/`self_validation_checklist`: DoD guards and warnings.
  * The capsule is capped (default 12k chars). When needed, `ContextPackV2` compacts large sections (e.g., trims bullet text and list lengths) **in the pack only**; it does not mutate the stored session `cv_data`.

- **Tool dispatcher** (`/cv-tool-call-handler`, `function_app.py`):
  * Single endpoint for “extra” tools to keep the public surface small.
  * Current tool(s):
    * `cv_session_search` — searches across `cv_data`, `docx_prefill_unconfirmed`, and recent `event_log` entries and returns bounded previews.

- **Update CV field** (`update-cv-field`):
  * Supports single paths, batch `edits[]`, and `cv_patch` (one top-level section at a time).
  * Validates patches via `validate_canonical_schema` + `validate_cv` before persisting.
  * Records `event_log` entries for each edit (used later by `recent_events`).

- **Generation** (`generate-cv-from-session`):
  * Validates session completeness (see `required_present` metadata) before generating; if missing fields, it rejects and returns error details.
  * Logs validation errors so the UI and capsule can display them.
  * The generator uses exactly the stored session data—no hallucinated contact/education.

### 3. System/stage prompts

- **Dashboard system prompt** (OpenAI Prompt ID):
  * When `OPENAI_PROMPT_ID=pmpt_...` is present, the UI sends `promptId` on every Responses API call.
  * This is the authoritative system prompt (managed in the OpenAI dashboard).
  * Local prompts in the repo are **fallback/reference** and should not duplicate long system instructions.

- **Stage prompts** (`ui/lib/prompts.ts`):
  * Provide stage‑specific directives (e.g., `review_session` stage asks for CV job-fit mapping using `completeness.next_missing_section` and no more than 3–4 questions per turn).
  * The `review_session` prompt now explicitly instructs the agent to auto-apply the unconfirmed DOCX snapshot when required sections are missing and to stay in preparation.
  * Prompt also enforces the “speed rule”: populate education/work/contact before asking more than one question.

### 3.1 OpenAI request payload (what is actually sent)

The UI builds the Responses request via `buildResponsesRequest(...)` (`ui/lib/capsule.ts`) and calls `openai.responses.create(...)` (`ui/app/api/process-cv/route.ts`). Shape (example, redacted):

```json
{
  "promptId": "pmpt_…",
  "model": "gpt-5-mini-… (optional override via OPENAI_MODEL)",
  "input": [
    { "role": "user", "content": "…capsule + user message…" }
  ],
  "tools": [
    { "type": "web_search" },
    { "type": "function", "name": "get_cv_session", "parameters": { "type": "object", "properties": { "session_id": { "type": "string" } }, "required": ["session_id"] } }
  ],
  "metadata": { "stage": "review_session", "stage_seq": "1" },
  "store": false
}
```

Notes:
- `store: false` is intentional; it means **tool outputs must be re-sent** each iteration (the UI does this by appending `function_call` items to `inputList`).
- When `promptId` is set, `systemPrompt` is sent as empty and the dashboard prompt defines system behavior.

### 4. Capsule + completeness/ DoD

- **`ContextPackV2` fields**:
  * `template`: renders sections (Education → Work experience → Further experience → Language Skills → IT & AI Skills → Interests → References). The front-end uses this to remind the model what exists.
  * `completeness`: `required_present` indicates whether contact/work/education exist; `next_missing_section` indicates which template section is empty (used in prompts for top-down flow).
  * `docx_prefill_unconfirmed`: the unconfirmed reference data from the uploaded DOCX.
  * `hard_limits`: DoD (2-page) instructions and bullet/section counts.
  * `self_validation_checklist` and `recent_events`: help the model stay aware of previous updates and validation failures (coupled to `event_log` in the session store).

### 5. Iteration / tool gating summary

| Component | Behavior |
|-----------|----------|
| UI `process-cv` | Builds `inputList` ⇒ stage prompt ⇒ tool list; iterates up to 10 rounds; logs usage; passes `client_context` so backend can persist event history. |
| Tool gating | Extract/process disabled when a session exists; generation only enabled in Execution after completeness; once one `generate_cv_from_session` runs, duplicates are blocked. |
| Validation | `validate_cv` enforces page-fit; `generate` ensures required fields are present and returns structured error reasons (propagated back into prompts). |
| Session log | Each `update_cv_field` appends succinct entries; the capsule shows the last ~15 recent events so the model knows what changed. |

### 6. Suggested review steps

1. Upload a new DOCX and watch the log: the JSON response should include `docx_prefill_unconfirmed`. Verify `ContextPackV2.preparation.docx_prefill_unconfirmed.education` is present.
2. Confirm the agent submits one batch `update_cv_field(edits=[...])` with the education/contact entries before asking the user anything else.
3. Generate the PDF once—observe that subsequent `generate_cv_from_session` calls are blocked within the same request.
4. Inspect logs for non-2xx tool calls (the UI now prints status + body).

With this document you have a complete reference of the orchestration and the places to inspect when troubleshooting flow stalls or missing data. Let me know if you'd like an architectural diagram or a shorter operational checklist. 
