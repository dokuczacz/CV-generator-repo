# Master Plan: Session Artifact Extraction + Wizard UX Refinements
**Date:** 2026-02-11  
**Scenario ID:** `a15065ac-15e6-4f29-9642-7e1da0da2925`  
**Status:** Planning Gate Complete  

---

## Executive Summary

This plan addresses six critical UX/data issues in the CV Generator:
1. **Session artifact storage consistency** (blob artifacts + Table state)
2. **AI Skills proposal data integrity** (only real data, no fabrication)
3. **Prompt tone for Operational Excellence roles** (production plant style)
4. **UI item reordering/removal** (work exp positions, bullets, skills lists)
5. **Wizard stage navigation reliability** (back/forward transitions)
6. **PDF download button visibility** (before Cover Letter action)

---

## Problem Categories & Requirements

### Category 1: Session Artifact Storage (Deterministic)
**Problem:** Session metadata lives in Table Storage (`cvsessions` table), but artifacts (photos, PDFs, JSON) are scattered across blob containers (`cv-photos`, `cv-pdfs`, `cv-artifacts`). No consistent snapshot or retrieval mechanism.

**Requirements:**
- Session state always lives in Azure Table Storage (`cvsessions` table).
- CV/skills artifacts saved to blob storage with consistent naming and metadata links.
- Session metadata includes artifact references (photo URL, PDF ref, JSON snapshot path).
- Extraction tool recovers all artifacts for a given session ID from both Table + blob sources.

**Observable DoD:**
```bash
# Extract session from Azurite
python scripts/diagnose_session.py --session-id a15065ac-15e6-4f29-9642-7e1da0da2925

# Result: JSON snapshot with all artifacts
docs/scenarios/scenario_a15065ac.json exists
  → Contains: session_id, cv_data, job_posting, photo_blob_path, pdf_refs, skills_artifacts

# Verify artifact references are valid blob paths
ls cv-photos/* | grep -E "(session_id|uuid)"
ls cv-pdfs/a15065ac-15e6-4f29-9642-7e1da0da2925/*

# Freeze scenario pack
docs/scenarios/scenario_a15065ac.json
```



### Category 3: Prompt Tone for Operational Excellence (Semantic)
**Problem:** Skills proposal prompt is generic; does not reflect production plant / operational excellence context for Vibe-X role.

**Requirements:**
- Skills prompt updated to emphasize key words from job offerr.
- Prompt consumes job summary deterministically.
- Output matches tone/business style of job position.

**Observable DoD:**
```bash
# Verify prompt uses job context
grep -r "job_summary\|job_title\|Operational Excellence" src/prompts/

# Test with job posting context
pytest tests/test_skills_proposal_tone.py -v -k "operational_excellence"

# Manual: Generate skills for Vibe-X scenario, verify bullets mention efficiency/quality/KAIZEN
```

---

### Category 4: UI Item Reordering & Removal (Deterministic)
**Problem:** Users cannot move work experience positions up/down, remove bullets, or reorder skills lists.

**Requirements:**
- Work experience positions: move up, move down, remove action buttons.
- Bullets within position: remove bullet, clear all bullets actions.
- Skills lists (IT/AI + Technical/Operational): reorder items, remove item, clear list actions.
- Actions trigger backend handlers that update session state and re-render UI.
- All state changes idempotent and reflected in session metadata.

**Observable DoD:**
```bash
# Verify UI actions dispatch correctly
# (open UI, reach work experience stage, click "Move Up" on position 2)

# Backend receives action
# POST /api/process-cv { action: "MOVE_WORK_EXPERIENCE_UP", payload: { position_index: 1 } }

# Session state updates
pytest tests/test_ui_actions_reorder.py -v

# Manual: Reorder positions, remove bullets, reorder skills; verify session artifact reflects changes
```

---

### Category 5: Wizard Stage Navigation Reliability (Deterministic)
**Problem:** Users cannot reliably navigate back/forward between wizard stages; some transitions break or lose state.

**Requirements:**
- `WIZARD_GOTO_STAGE` action validates stage transition (no jumping; only adjacent or declared allowlist).
- Back/forward buttons always present and functional.
- Stage history tracked in session metadata; can step back without data loss.
- State guards prevent invalid transitions (e.g., can't skip to "review_final" without completing prior stages).

**Observable DoD:**
```bash
# Verify stage FSM and transitions
pytest tests/test_wizard_stage_navigation.py -v

# Manual: Start wizard, navigate forward, click back, verify data preserved
# Click back from "Skills Ranking" to "Work Experience", edit, forward again

# Test boundary: try to jump from "Language" to "Review Final" (should be blocked or redirect)
```

---

### Category 6: PDF Download Button Order (Deterministic)
**Problem:** After clicking "Generate PDF", the download button disappears before Cover Letter action. Button order should keep "Pobierz PDF" visible before cover letter.

**Requirements:**
- Action order: `REQUEST_GENERATE_PDF` → `DOWNLOAD_PDF` (always visible) → `GENERATE_COVER_LETTER` (optional, gated).
- Download button remains visible even after PDF generation completes.
- PDF generation does not remove or hide the download action.
- UI action rendering preserves button order from backend.

**Observable DoD:**
```bash
# Verify action ordering in backend
grep -A 20 "REQUEST_GENERATE_PDF\|DOWNLOAD_PDF\|GENERATE_COVER_LETTER" function_app.py | grep -E "ui_action|action_id"

# Manual: Generate CV PDF, verify "Pobierz PDF" button is visible immediately after
# Then check Cover Letter action appears below/after download

# Test with cover letter disabled (CV_ENABLE_COVER_LETTER=0)
# Verify "Pobierz PDF" is the final visible action
```

---

## Implementation Steps

### Step 1: Extract Session Artifacts from Azurite (BLOCKING)
**Files:** `scripts/diagnose_session.py`, `src/session_store.py`, `src/blob_store.py`

1. Start Azurite (if not running): `func start` in terminal or `python scripts/run_local.py`.
2. Run extraction script:
   ```bash
   python scripts/diagnose_session.py --session-id a15065ac-15e6-4f29-9642-7e1da0da2925
   ```
3. Capture output JSON (session state + artifact references).
4. Create scenario pack directory and freeze artifacts:
   ```bash
   mkdir -p docs/scenarios
   # Copy extracted JSON, photos, PDFs, etc. to docs/scenarios/scenario_a15065ac/
   ```
5. Create [docs/scenarios/scenario_a15065ac.json](docs/scenarios/scenario_a15065ac.json):
   - `scenario_id`: `a15065ac-15e6-4f29-9642-7e1da0da2925`
   - `cv_data`: extracted CV JSON
   - `job_posting`: job context (Vibe-X role)
   - `artifacts`: { photo_path, pdf_refs, skills_json_path }
   - `template_version`: current CV template version
   - `dod_commands`: list of commands to reproduce work

**Verification:** `docs/scenarios/scenario_a15065ac.json` exists and all artifact paths resolve.

---

### Step 2: Normalize Blob Artifact Snapshots (Deterministic)
**Files:** `src/session_store.py`, `src/blob_store.py`, `function_app.py`

1. Review [src/session_store.py](src/session_store.py): ensure session metadata includes artifact pointers (photo blob path, PDF refs, JSON snapshot path).
2. Add/verify `_upload_json_blob_for_session()` helper in [function_app.py](function_app.py) that:
   - Saves CV JSON snapshot to `cv-artifacts/{session_id}/cv_<timestamp>.json`
   - Saves skills proposal JSON to `cv-artifacts/{session_id}/skills_proposal_<timestamp>.json`
   - Updates session metadata with blob paths.
3. Add `_download_json_blob()` helper to retrieve snapshots from blob for debugging/audit.
4. Ensure all state-changing operations (after validation, after skills proposal, after PDF gen) write blob snapshots.

**Verification:** Mocked test confirms blob paths are created and session metadata references them.

---

### Step 3: Audit Skills Proposal Pipeline (Semantic)
**Files:** `src/skills_unified_proposal.py`, `src/skills_proposal.py`, `function_app.py`, `tests/test_skills_unified.py`

1. Review [src/skills_unified_proposal.py](src/skills_unified_proposal.py):
   - Identify input sources (CV fields, work experience, education, projects).
   - Ensure no model-invented/fabricated fields are added to proposal.
   - Validate output schema against input fields.
2. Audit [src/skills_proposal.py](src/skills_proposal.py): compare with unified version; merge if needed.
3. Add unit test in [tests/test_skills_unified.py](tests/test_skills_unified.py):
   - Load scenario CV data.
   - Extract skills proposal from CV-only fields.
   - Assert no extra items in proposal.
4. In [function_app.py](function_app.py), locate `it_ai_skills` stage builder: ensure it renders only extracted proposal fields, no AI additions without explicit review step.

**Verification:** `pytest tests/test_skills_unified.py -v` passes; proposal output schema validates; no "unknown" fields.

---

### Step 4: Update Skills Proposal Prompt (Semantic)
**Files:** `src/prompts/`, `src/prompt_registry.py`, `tests/test_skills_proposal_tone.py`

1. Review current skills prompt in `src/prompts/` (e.g., `skills_proposal_prompt.txt` or registry entry).
2. Rewrite prompt to emphasize Operational Excellence / production plant context:
   - Keywords: efficiency, process optimization, quality assurance, KAIZEN, continuous improvement, team leadership, problem-solving, manufacturing.
   - Job summary context: reference job_title (Operational Excellence Manager - Vibe-X) and job_posting text.
   - Expected output: bullet-friendly, production-focused skills.
3. Update [src/prompt_registry.py](src/prompt_registry.py) to register new prompt version.
4. Add test [tests/test_skills_proposal_tone.py](tests/test_skills_proposal_tone.py):
   - Mock OpenAI call with scenario CV data + Vibe-X job context.
   - Assert output tagging/tone includes operational/efficiency keywords.

**Verification:** Prompt text updated; test passes; manual UI flow confirms skills match OE tone.

---

### Step 5: Add UI Actions for Reordering/Removal (Deterministic)
**Files:** `function_app.py`, `ui/app/page.tsx`, `tests/test_ui_actions_reorder.py`

1. In [function_app.py](function_app.py), add action handlers:
   - `MOVE_WORK_EXPERIENCE_UP`: move position at index `i` up one slot.
   - `MOVE_WORK_EXPERIENCE_DOWN`: move position at index `i` down one slot.
   - `REMOVE_WORK_EXPERIENCE`: delete position at index `i`.
   - `REMOVE_WORK_EXPERIENCE_BULLET`: delete bullet at position `i`, bullet `j`.
   - `REORDER_SKILLS_IT_AI`: move skill at index `i` to index `j`.
   - `REMOVE_SKILL_IT_AI`: delete skill at index `i`.
   - Similar for Technical/Operational skills.
2. Each handler:
   - Loads session CV data.
   - Applies transformation (move/remove).
   - Updates session state.
   - Uploads blob snapshot.
   - Returns updated UI action list.
3. In [ui/app/page.tsx](ui/app/page.tsx), add UI controls:
   - "Move Up" / "Move Down" / "Remove" buttons next to each position.
   - "Remove" / "Clear All" for bullets.
   - "Remove" / "Reorder" for skills items (drag or arrow buttons).
4. Add test [tests/test_ui_actions_reorder.py](tests/test_ui_actions_reorder.py):
   - Load scenario CV.
   - Call `MOVE_WORK_EXPERIENCE_UP` action.
   - Assert position order changed.
   - Assert session artifact updated.

**Verification:** Mocked tests pass; UI buttons appear and dispatch actions correctly.

---

### Step 6: Fix Wizard Stage Navigation (Deterministic)
**Files:** `function_app.py` (`WIZARD_GOTO_STAGE` handler), `ui/app/page.tsx` (stepper navigation), `tests/test_wizard_stage_navigation.py`

1. Review `WIZARD_GOTO_STAGE` action in [function_app.py](function_app.py):
   - Validate requested stage is adjacent or in allowlist.
   - Preserve session state across back/forward transitions.
   - Track stage history in session metadata.
2. Ensure stage guards do not skip without completing prior stages (e.g., must complete "contact_info" before "work_experience").
3. In [ui/app/page.tsx](ui/app/page.tsx), verify stepper back/forward buttons always dispatch `WIZARD_GOTO_STAGE` with the correct stage target.
4. Add test [tests/test_wizard_stage_navigation.py](tests/test_wizard_stage_navigation.py):
   - Navigate forward through all stages.
   - Navigate back; assert data preserved.
   - Try invalid transition (e.g., jump two stages forward); assert blocked or redirected.

**Verification:** Test passes; manual flow supports reliable back/forward without data loss.

---

### Step 7: Reorder PDF + Cover Letter Buttons (Deterministic)
**Files:** `function_app.py` (action ordering), `ui/app/page.tsx` (button rendering)

1. In [function_app.py](function_app.py), locate action builders for "Review Final" and "Cover Letter" stages.
2. Ensure action order is:
   ```
   1. REQUEST_GENERATE_PDF (generate CV PDF)
   2. DOWNLOAD_PDF (download generated PDF, always visible)
   3. GENERATE_COVER_LETTER (optional, gated by CV_ENABLE_COVER_LETTER)
   ```
3. Verify `DOWNLOAD_PDF` is not removed or hidden after PDF generation completes.
4. In [ui/app/page.tsx](ui/app/page.tsx), render buttons in order; skip cover letter action if gated.
5. Add test:
   - Mock complete workflow to "review_final" stage.
   - Generate PDF (trigger `REQUEST_GENERATE_PDF`).
   - Assert `DOWNLOAD_PDF` action is still in action list.
   - Assert cover letter action appears after download (if enabled).

**Verification:** Button order correct; download visible before cover letter; tests pass.

---

## Verification & Testing Strategy

### Tier 0: Unit Tests (Deterministic, Always-On)
- `tests/test_skills_unified.py`: Skills input/output schema validation.
- `tests/test_ui_actions_reorder.py`: Move/remove logic for positions, bullets, skills.
- `tests/test_wizard_stage_navigation.py`: Stage FSM transitions and guards.
- Run: `npm run pretest && pytest tests/test_*.py -v`

### Tier 1: Contract Tests (No Real LLM)
- Mock OpenAI calls; verify orchestrator behavior without live AI.
- Load scenario CV from blob; apply reorder/move actions; assert session state consistent.
- Run: `npm run test` (with `MOCK_OPENAI=1` or `OPENAI_PROMPT_ID=mock`).

### Tier 2: Manual Flow (Golden Path)
1. Start Azure Functions + UI: `func start` + `npm run dev`.
2. Load scenario blob/session: use extraction tool or manual upload.
3. Navigate wizard: language → contact → work experience (test move/remove) → skills (test reorder) → review final.
4. Generate PDF: verify button order (download before cover letter).
5. Click download: verify PDF artifact in blob.

### Tier 3: Regression (Optional, Opt-In)
- Run with live OpenAI (if `RUN_LIVE_E2E=1` set).
- Verify skills proposal tone matches Operational Excellence context.
- Keep assertions coarse: "PDF generates", "skills bulleted correctly", not exact wording.

---

## File Manifest

| File | Change Type | Description |
|------|-------------|-------------|
| [docs/scenarios/scenario_a15065ac.json](docs/scenarios/scenario_a15065ac.json) | **NEW** | Frozen scenario pack (CV, job posting, artifacts, DoD) |
| [src/session_store.py](src/session_store.py) | **EDIT** | Add artifact metadata tracking in session state |
| [src/blob_store.py](src/blob_store.py) | **EDIT** | Verify/extend blob helpers for JSON snapshots |
| [function_app.py](function_app.py) | **EDIT** | Add action handlers for reorder/move/remove; fix button order; verify stage guards |
| [src/skills_unified_proposal.py](src/skills_unified_proposal.py) | **EDIT** | Audit input sources; restrict to CV-only data |
| [src/prompts/skills_proposal_prompt.txt](src/prompts/skills_proposal_prompt.txt) | **EDIT** | Update tone to Operational Excellence / production plant |
| [src/prompt_registry.py](src/prompt_registry.py) | **EDIT** | Register updated prompt version |
| [ui/app/page.tsx](ui/app/page.tsx) | **EDIT** | Add UI buttons for move/reorder/remove; ensure button order; stepper navigation |
| [tests/test_skills_unified.py](tests/test_skills_unified.py) | **EDIT** | Add test for input/output validation; verify no fabrication |
| [tests/test_ui_actions_reorder.py](tests/test_ui_actions_reorder.py) | **NEW** | Test move/remove actions and session state updates |
| [tests/test_wizard_stage_navigation.py](tests/test_wizard_stage_navigation.py) | **NEW** | Test FSM transitions, back/forward, guards |
| [tests/test_skills_proposal_tone.py](tests/test_skills_proposal_tone.py) | **NEW** | Test prompt tone/context consumption (mocked OpenAI) |

---

## Success Criteria (DoD)

| Criterion | Verification Command | Target |
|-----------|---------------------|--------|
| **Scenario pack created** | `ls docs/scenarios/scenario_a15065ac.json` | File exists with all artifact refs |
| **Blob snapshots working** | `pytest tests/test_blob_snapshots.py -v` | Mocked test passes |
| **Skills input restricted** | `pytest tests/test_skills_unified.py -v` | No fabricated fields in output |
| **Prompt tone updated** | `grep -r "Operational Excellence\|KAIZEN" src/prompts/` | Keywords present in skills prompt |
| **Reorder actions working** | `pytest tests/test_ui_actions_reorder.py -v` | All move/remove handlers tested |
| **Stage navigation fixed** | `pytest tests/test_wizard_stage_navigation.py -v` | Back/forward transitions reliable |
| **Button order correct** | `pytest tests/test_button_order.py -v` | Download before cover letter in action list |
| **Manual flow passes** | Manual run: wizard flow with reorder + PDF download | PDF button visible; data persists across back/forward |

---

## Decision Log

- **Storage Model:** Table Storage for session state (source of truth); blob containers for artifacts (photos, PDFs, JSON snapshots).
- **Skills Proposal:** Restrict input to CV-only fields; no model-invented skills.
- **Prompt Tone:** Operational Excellence / production plant keywords; job summary consumed deterministically.
- **UI Reordering:** Backend-driven action handlers; UI is thin renderer.
- **Stage Navigation:** Validated transitions with history tracking; no data loss on back/forward.
- **Button Order:** PDF download always visible before cover letter (unless CL disabled).

---

## Addendum (2026-02-14): Wizard Step-by-Step Plan Update

### Agreed Scope Updates

- One operational data mode for wizard decisions: **FULL context from canonical session state** (no quality loss by mini-like reductions in wizard-critical flow).
- Primary issue to fix first: **language/source drift between stages** (mixed translated + untranslated inputs in downstream prompts).
- Keep downstream job context via **JOB_SUMMARY** (no requirement to inject raw job posting into all stages).
- Role titles may be translated/normalized (no strict verbatim-preserve requirement).
- Add explicit CH/EU quality objective for CV stages: **ATS-first, concrete outcomes, formal tone, no fluff**.
- Prompt must be treated as strict runtime input: for each stage we track exactly what prompt was sent and from which source it was built.

### Stage-by-Stage Execution Order (Wizard)

1. Language Selection + Bulk Translation
2. Contact
3. Education
4. Job Posting
5. Work Experience (core)
6. Further Experience
7. Skills (IT/AI + Technical/Operational)
8. Review Final + PDF + Cover Letter

### Per-Stage Verification (must pass before next stage)

#### 1) Language Selection + Bulk Translation
- `target_language` persisted in metadata.
- Canonical translated CV state saved as session source-of-truth.
- No re-translation for unchanged `cv_hash + target_language`.

##### Stage 1 Contract Clarification (Prompt + FSM)

- **Effective prompt for Bulk Translation** = short global base + stage template with `{target_language}` substitution.
- **Base prompt (global, minimal):**
   - `Return JSON only that strictly matches the provided schema.`
   - `Preserve facts, names, and date ranges exactly; do not invent.`
   - `Do not add line breaks inside any JSON string values.`
- **Not global:** candidate/job SoT semantic rules must not live in base; they belong to stage prompts where applicable.
- **Bulk stage prompt:** remains focused on translation only (professional target language, preserve technical terms/dates).

##### Stage 1 FSM State Model (No destructive overwrite)

- Do not treat translated output as destructive replacement of the only CV state.
- Keep immutable state snapshots and explicit active pointer in metadata:
   - `cv_state_original` (initial extracted state)
   - `cv_state_translated_<lang>` (derived translated states)
   - `active_cv_state_id` (currently used state for downstream stages)
- Reuse rule:
   - if `source_cv_hash` unchanged and `target_language` unchanged, switch to existing translated state (no new translation call).

##### Stage 1 Prompt Provenance (Stateless traceability)

- Persist per-call prompt trace metadata:
   - `effective_system_prompt_hash`
   - `stage_prompt_source` (file/prompt_id)
   - `prompt_id_used` (if dashboard prompt was active)
   - `user_payload_hash`
- Goal: stateless requests remain fully auditable in FSM history.

#### 2) Contact
- Lock/unlock behavior stable.
- Back/forward navigation preserves values.

#### 3) Education
- Education payload stable after save/re-open.
- If downstream prompt claims education context, education is present in payload.

#### 4) Job Posting
- One analysis for unchanged job input.
- Prompt output contract matches runtime parser/schema.
- Signature-based reuse works.

#### 5) Work Experience
- Input built from canonical translated state only.
- No mixed-language sections in one payload.
- Prompt-declared sections and runtime payload are aligned 1:1.

#### 6) Further Experience
- Same canonical source policy as Work Experience.
- No fallback to untranslated data if translated state exists.

#### 7) Skills
- Skills input from canonical state (no mixed fallback source).
- Deterministic validation: cardinality + no duplication + language consistency.

#### 8) Review Final + PDF + Cover Letter
- Final render uses same canonical state/hash as prior stages.
- Action order remains stable (`DOWNLOAD_PDF` visible after generation).
- Cover letter language/facts consistent with final CV state.

### Prompt Quality Baseline (CH/EU “Perfect CV”) — Mandatory

- Add a reusable CH/EU quality layer for CV stages (while keeping safety base generic).
- Stage outputs must satisfy: ATS readability, measurable impact phrasing, formal CH/EU tone, factual grounding.
- Enforce with deterministic post-checks (not prompt text only).

### Prompt Layering Rules (applies to all next stages)

- Global base prompt must remain short and schema/safety-focused.
- Domain semantics (SoT scope, job-evidence limits, style constraints) belong to stage prompts.
- Every stage must expose the exact runtime prompt input for debugging (prompt text/hash + source).

---

## Addendum (2026-02-14): Stateless UI MVP (Feature Sections in Main Window)

### Objective

Refactor UI to be more stateless and modular while keeping backend as the sole orchestrator.
Steps are rendered as feature sections in the main window; UI does not implement workflow logic.

### Non-Negotiable Boundaries

- Backend remains single source of truth for `stage`, `ui_action`, `stage_updates`, `readiness`.
- UI may only send: `session_id`, `user_action`, optional upload payload, and render backend response.
- No client-side FSM, no client-side stage skipping rules, no business gating in React.
- Keep existing stable selectors (`data-testid`) where possible to avoid E2E churn.

### MVP Scope (No Behavior Change)

1. Extract transport/session logic from `ui/app/page.tsx` into hooks:
    - `useSessionBootstrap`
    - `useProcessCvClient`
    - `useCvPreview`
2. Split monolithic UI into feature sections rendered in the main window:
    - `UploadStartSection`
    - `WizardStageSection`
    - `CvPreviewSection`
    - `OpsSection`
3. Keep `ui/app/page.tsx` as a thin composition layer wiring state + callbacks.
4. Preserve current UX behavior and API payload semantics in this phase.

### Proposed State Ownership (MVP)

- **Container (`page.tsx`) owns canonical UI state:**
   `sessionId`, `uiAction`, `lastStage`, `stageUpdates`, preview payload, notices, loading flags.
- **Feature sections are mostly presentational:**
   receive state + callbacks, avoid owning workflow state.
- **Hooks own side effects only:**
   fetch, resume, preview refresh, action dispatch.

### Incremental Implementation Plan

1. Extract hooks with zero JSX movement (safest first).
2. Extract `WizardStageSection` (largest block, highest readability gain).
3. Extract `CvPreviewSection`.
4. Extract `UploadStartSection` and `OpsSection`.
5. Final cleanup: shared types and import order normalization.

### Test / Verification Gate

- `cd ui && npm run lint`
- `cd ui && npm run build`
- `npm test -- tests/e2e/smoke-test.spec.ts`
- `npm test -- tests/e2e/wizard_no_ghost_controls.spec.ts`
- `npm test -- tests/e2e/wizard_profile_cache_per_language.spec.ts`

### Risks

- Selector drift in extracted JSX blocks can break Playwright tests.
- Hidden coupling in `page.tsx` side effects (resume + preview refresh) can regress if moved too aggressively.
- Mixed concerns in existing handlers (e.g., optimistic notices + mutation refresh) require careful extraction order.

### Exit Criteria

- `page.tsx` primarily composes feature sections and passes callbacks.
- No regression in wizard flow and action rendering.
- Backend contract unchanged (`/api/process-cv` proxy + `ui_action` rendering path intact).
- E2E selectors and key smoke flows remain green.

---

## Timeline & Effort Estimate

| Step | Effort | Dependencies |
|------|--------|--------------|
| 1. Extract & freeze scenario | 15 min | Azurite running |
| 2. Normalize blob snapshots | 30 min | Step 1 complete |
| 3. Audit skills pipeline | 20 min | Parallel with Step 2 |
| 4. Update prompt tone | 20 min | Step 3 complete |
| 5. Add reorder UI actions | 1 hr | Steps 2, 3 complete |
| 6. Fix stage navigation | 45 min | Parallel with Step 5 |
| 7. Reorder buttons | 15 min | Parallel with Steps 5–6 |
| **Testing (Tier 0/1)** | 1 hr | All steps complete |
| **Manual flow (Tier 2)** | 30 min | Tier 0/1 pass |
| **Total** | ~4 hrs | N/A |

---

## Blockers & Risks

| Risk | Mitigation |
|------|-----------|
| Azurite not running or corrupted | Start fresh: `func kill` + `func start`. Inspect `__azurite_db_*.json` files. |
| Session artifacts scattered or missing | Run `scripts/diagnose_session.py` to audit all references; confirm blob containers exist. |
| Skills proposal prompt change breaks live chat | Test with mocked LLM first (Tier 1); roll out to live only after Tier 2 passes. |
| Stage navigation loses state | Ensure session metadata includes stage history; test back/forward with data preservation. |
| Button order regression | Pin action order in test; verify before/after button placement in e2e. |

---

## Next Steps

1. **Start execution at Stage 1: Bulk Translation** (canonical translated SoT + reuse/cache rules).
2. **Implement Stage 1 prompt split** (short base + stage-specific semantics only).
3. **Implement Stage 1 state snapshots + active pointer** (no destructive overwrite).
4. **Validate Stage 1 gates** (language persistence, hash/reuse, no duplicate translation, prompt provenance persisted).
5. **Proceed stage-by-stage only after gate pass** (Contact → Education → Job Posting → Work Experience ...).
6. **Review with operator after each stage gate** before implementing next stage changes.

---

## Status Update (2026-02-14) — Session/Prompt vs Final CV Audit

### Investigated IDs

- User-provided identifier: `trace_id = c5e13931-752b-49aa-942d-fd41de0e5f24`
- Resolved session: `session_id = 2ec0fd55-72fc-40a4-a97c-e7616ac3d8e2`

### Evidence Collected

- Session snapshot: `docs/scenarios/scenario_2ec0fd55.json`
- OpenAI trace rows (all for session): `tmp/session_2ec0fd55_trace_entries.json`
- Downloaded OpenAI dashboard responses:
   - `tmp/openai_dashboard_exports/session_2ec0fd55/resp_0bf824f43a724ff100699068f78d2881a3a400c584b435951b.response.json` (bulk translation)
   - `tmp/openai_dashboard_exports/session_2ec0fd55/resp_006364a593222aa00069906912a8288196be2ad6bc8f3ad201.response.json` (job posting #1)
   - `tmp/openai_dashboard_exports/session_2ec0fd55/resp_026b685a8a4653d5006990692d6d608197b70c3186c69fcd2c.response.json` (job posting #2)
   - `tmp/openai_dashboard_exports/session_2ec0fd55/resp_0bf2a7684cb8afe50069906933f58481978ce37c509ad71271.response.json` (work experience)
   - `tmp/openai_dashboard_exports/session_2ec0fd55/resp_0dc2ff9e04edb3f1006990695decdc819e8e762f98af5d0baa.response.json` (skills)
- Final PDF + extracted text:
   - `tmp/session_2ec0fd55_final.pdf`
   - `tmp/session_2ec0fd55_final_pdf_text.txt`

### Findings

1. **Model calls recovered completely** for this session (`bulk_translation`, `job_posting` x2, `work_experience`, `it_ai_skills`).
2. **`work_experience` output was largely preserved** in final `cv_data`; one role (Sumitomo) persisted from prior state while proposal covered 4 roles.
3. **`it_ai_skills` output was applied 1:1** into final `cv_data` and appears in generated PDF.
4. **`job_posting` had two responses; second one is the effective final state** (first was superseded).
5. **Final PDF content matches final `cv_data`** for work experience and skills sections.

### Detected Defect (High Priority)

- During PDF generation, backend logs show Azure Table write failure:
   - `PropertyValueTooLarge` while persisting PDF metadata.
- Consequence:
   - PDF blob is generated successfully, but session metadata persistence is partially inconsistent (`pdf_generated` / refs can be stale or incomplete in table state).

### Deterministic Follow-up Actions

1. Add metadata-size guard before table writes in PDF generation path.
2. Move oversized metadata fields to blob snapshot (`cv-artifacts`) and store only compact references in table.
3. Add regression test for table-entity size limits in PDF persistence path.
4. Add post-write verification that `pdf_generated` + `pdf_refs` are persisted and reloadable from `get_session`.

---

## Addendum (2026-02-18) — Token Limits, Work Overwrite, Cover Letter Contract

### Scope of This Update

This update consolidates operator-reported runtime and UX issues from 2026-02-18 and sets a deterministic implementation sequence:

1. Local Azure Functions startup reliability when CDN host resolution fails.
2. Excessive retries due to `incomplete(max_output_tokens)` on key stages.
3. Work Experience acceptance semantics: old roles persist after accepting shortened proposal.
4. Cover Letter generation semantics: generate action must always regenerate.
5. Session consistency around cover-letter action execution and observability.

### Confirmed Decisions

- `WORK_TAILOR_ACCEPT` must **overwrite** `work_experience` (replace-all), not preserve unmatched prior roles.
- `COVER_LETTER_GENERATE` must **always regenerate** (new model call + new PDF ref), not fallback to existing PDF download.
- Token policy update scope includes `job_posting`, `work_experience`, and `cover_letter`.
- Retry multiplier remains `1.6x` in this wave.
- A compact correction payload is required for work-experience shortening/fix path (first-pass prompt remains full).

### Deterministic Requirements

#### A) Work Experience Accept = Replace-All

**Requirement:** When user accepts work proposal, final `cv_data.work_experience` equals accepted proposal roles only.

**DoD:**
- No unmatched legacy role remains after `WORK_TAILOR_ACCEPT`.
- Preview panel and persisted session show exactly accepted roles.

#### B) Cover Letter Generate = Always Regenerate

**Requirement:** `COVER_LETTER_GENERATE` always triggers fresh generation/render path.

**DoD:**
- Existing `cover_letter_pdf_ref` does not short-circuit generation.
- New PDF reference is stored after every successful generate click.

#### C) Token Budgets and Retry Pressure

**Requirement:** Reduce truncation/retry chains on high-pressure stages.

**Planned budget adjustments:**
- `job_posting`: start from 1200 minimum in stage callsites.
- `work_experience`: increase by 40% (1600 → 2240) in all relevant callsites.
- `cover_letter`: increase stage budget consistent with longer reasoning payloads.

**DoD:**
- Fewer `attempt_2/schema_repair_2` chains in logs for target stages.

#### D) Compact Correction Payload (Work Experience)

**Requirement:** Correction/fix path uses minimal input payload (violations + affected roles + compact job anchor), not full capsules.

**DoD:**
- Correction requests are materially smaller than first-pass requests.
- Alignment and bullet constraints remain validated deterministically.

#### E) Action Observability and Session Consistency

**Requirement:** Each critical action emits explicit execution trace (action id, stage before/after, session id before/after).

**DoD:**
- If session reset happens, logs identify exact source branch/action.

### Implementation Order (WU sequence)

1. Update master plan (this section) and freeze decisions.
2. Implement `WORK_TAILOR_ACCEPT` replace-all semantics.
3. Implement `COVER_LETTER_GENERATE` always-regenerate semantics.
4. Apply token budget updates to `job_posting`, `work_experience`, `cover_letter`.
5. Add targeted action/session observability logs.
6. Add/adjust deterministic tests for overwrite + cover regenerate + token retry behavior.

### Verification Commands (Post-Implementation)

```bash
# Focused Python tests for changed behavior
pytest tests/test_work_role_locking.py tests/test_work_alignment_policy.py tests/test_work_experience_validation_payload.py -q

# Run targeted E2E/specs related to wizard stage behavior
npx playwright test tests/e2e/wizard-stage-gated.spec.ts --project=chromium --workers=1 --retries=0
```

### Failure Policy

- If any deterministic gate fails (overwrite contract, cover regenerate contract, or stage stability), stop rollout and keep previous behavior behind explicit branch/flag only until fixed.
- No further optimization work proceeds before these contract fixes are green.

---

## Addendum (2026-02-18) — Cover Letter Generation Crash Fix + Session Read Consistency

### Incident Summary

- Runtime production-like failure observed during `COVER_LETTER_GENERATE`:
   - OpenAI call succeeded (`stage=cover_letter`, valid response id logged).
   - Cover letter PDF render/upload completed.
   - Function failed while persisting session with Azure Table error:
      - `PropertyValueTooLarge` (64KB property limit).

### Root Cause (Deterministic)

1. Wizard `_persist(...)` path used direct `update_session(...)` without resilient size fallback in some large metadata states.
2. After offload writes, some session reads used raw `get_session(...)` instead of blob-aware retrieval, causing:
    - empty `cv_data`-derived prompt sections (`[WORK_EXPERIENCE]`, `[SKILLS]`),
    - false readiness “missing” badges in UI,
    - perceived no-op behavior after cover-letter actions.

### Implemented Fixes

#### A) Blob-aware session reads for orchestrator/session API

- Updated orchestrator/session fetches to prefer `get_session_with_blob_retrieval(...)` when available.
- Keeps canonical `cv_data` available even when table row stores offload pointer (`__offloaded__`).

#### B) Resilient wizard persistence (`_persist`)

- `_persist` now attempts, in order:
   1. `update_session_with_blob_offload(...)`
   2. fallback `update_session(...)`
   3. on `PropertyValueTooLarge`: `_shrink_metadata_for_table(...)` + retry offload update
- If persistence still fails, logs structured error and returns safe in-memory outputs (prevents hard crash of function invocation).

#### C) Existing action passthrough hardening kept

- Action-only requests preserve empty `message` and do not force synthetic `"start"`.

### Verification Status

- Targeted backend regression suite: `pytest tests/test_import_gate_stage_guard.py -q` → pass.
- Deterministic Playwright action path: `tests/e2e/cover-letter-generate-action.spec.ts` → pass.
- Commit with focused scope pushed to `main`:
   - commit: `a529856`
   - branch: `main`
   - remote: `origin/main`

### New/Updated Regression Coverage

- `tests/test_import_gate_stage_guard.py`
   - stale import-gate cannot hijack late cover stage,
   - early import-gate still enforces confirmation,
   - blob-aware cover-letter input path,
   - persistence fallback path for `PropertyValueTooLarge`.
- `tests/e2e/cover-letter-generate-action.spec.ts`
   - verifies browser action dispatch and response update semantics for cover letter generate.

### Remaining Risks / Next Validation

- One real-session Playwright spec with hardcoded stable session id can fail if that session expires; this is environmental, not logic regression.
- Recommended next deterministic real-flow check:
   1. create fresh session,
   2. drive to `cover_letter_review`,
   3. click `COVER_LETTER_GENERATE`,
   4. confirm no function crash and valid PDF response.

