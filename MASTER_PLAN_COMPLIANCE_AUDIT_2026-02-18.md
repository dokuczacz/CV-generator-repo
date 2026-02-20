# Master Plan Compliance Audit (Doc + Code)
Date: 2026-02-18
Scope: `MASTER_PLAN_SESSION_EXTRACTION_AND_UI_REFINEMENTS.md` (including 2026-02-14 + 2026-02-18 addenda) vs repository implementation + `HANDOFF_SESSION_2026-02-18.md`.

## Executive Summary
- Implemented: 11
- Partial: 9
- Not Implemented: 3
- Superseded: 1
- Unverifiable: 1

Top-level conclusion:
- The 2026-02-18 crash-fix/addendum work is mostly implemented (blob-aware reads, persistence fallback, cover action flow).
- Core Step 1/2/3/4/6/7 are substantially present in code.
- Main gaps are test-plan drift (planned test files not present), UI-surface drift for reorder/remove controls, and partial contract coverage for addendum token/observability requirements.

## Status Table
| plan_item_id | master_requirement | expected_evidence | found_evidence | status | diff_type | notes |
|---|---|---|---|---|---|---|
| MP-STEP1-SCENARIO-PACK | Scenario pack for `a15065ac` exists with artifacts and DoD commands | `docs/scenarios/scenario_a15065ac.json` | File exists with `scenario_id`, `artifacts`, `dod_commands` (`docs/scenarios/scenario_a15065ac.json:2`, `docs/scenarios/scenario_a15065ac.json:535`, `docs/scenarios/scenario_a15065ac.json:545`) | Implemented | None | Requirement met. |
| MP-STEP1-DIAGNOSE-SCRIPT | Extraction tool available (`scripts/diagnose_session.py`) | Script + usage for session extraction | Script exists and includes `--session-id` extraction usage (`scripts/diagnose_session.py:9`) | Implemented | None | Requirement met. |
| MP-STEP2-BLOB-HELPERS | Blob snapshot helpers for JSON upload/download exist | `_upload_json_blob_for_session`, `_download_json_blob` + blob container usage | Helpers exist (`function_app.py:9986`, `function_app.py:9998`), artifact container usage in store (`src/session_store.py:433`) | Implemented | None | Requirement met. |
| MP-STEP2-PERSIST-FALLBACK | Persistence resilient to `PropertyValueTooLarge` with shrink+offload retry | `_persist` fallback chain + shrink helper | Implemented (`function_app.py:5741`, `function_app.py:5759`, `function_app.py:5763`, `function_app.py:2211`) | Implemented | None | Matches 2026-02-18 addendum. |
| MP-STEP2-STATE-SNAPSHOTS-COVERAGE | All state-changing operations persist blob snapshots | Snapshot/persist behavior across validation/skills/pdf paths | Snapshot calls exist for work/skills accept (`function_app.py:7642`, `function_app.py:8357`), but not clearly uniform across every state-changing path | Partial | Behavior Drift | Broad intent present; "all operations" not strictly evidenced. |
| MP-STEP2-BLOB-SNAPSHOT-TEST | `tests/test_blob_snapshots.py` per plan DoD | Planned test file exists and validates behavior | Planned file missing; alternative coverage exists in `tests/test_pdf_metadata_blob_offload.py` | Partial | Test Drift | Coverage exists but not via planned test contract. |
| MP-STEP3-SKILLS-INTEGRITY | Skills proposal restricted to grounded input/no fabrication | Skills schema + integrity tests | Schema strictness present (`src/skills_unified_proposal.py:38`), explicit no-fabrication test exists (`tests/test_skills_unified.py:462`) | Implemented | None | Requirement intent met. |
| MP-STEP3-SKILLS-STAGE-APPLY | Skills stage applies only proposal fields deterministically | `function_app.py` skills apply logic | `SKILLS_TAILOR_ACCEPT` applies proposal lists directly (`function_app.py:8342` onward) | Implemented | None | Requirement met. |
| MP-STEP4-PROMPT-TONE | Prompt emphasizes Operational Excellence / manufacturing keywords | Prompt text includes OE keywords and job context cues | Prompt includes KAIZEN/OE/efficiency/manufacturing directives (`src/prompts/it_ai_skills.txt:9`, `src/prompts/it_ai_skills.txt:12`, `src/prompts/it_ai_skills.txt:27`) | Implemented | None | Requirement intent met. |
| MP-STEP4-TONE-TEST | `tests/test_skills_proposal_tone.py` exists | Planned test file | File missing | Not Implemented | Test Drift | No direct named-tone test artifact from plan. |
| MP-STEP5-BACKEND-REORDER-HANDLERS | Reorder/remove handlers exist for work + skills | Action handlers in backend | Implemented for work and skills (`function_app.py:7775`, `function_app.py:7832`, `function_app.py:8366`, `function_app.py:8429`) | Implemented | None | Backend side is present. |
| MP-STEP5-UI-CONTROLS | UI exposes move/down/remove controls for users | UI buttons/dispatch for reorder actions | Generic action renderer exists, but no explicit UI controls for these actions found in UI sections (`ui/app/cv/sections/WizardStageSection.tsx`) | Partial | Behavior Drift | Backend handlers may exist without clear dedicated UI affordances requested by plan. |
| MP-STEP5-REORDER-TEST | `tests/test_ui_actions_reorder.py` exists | Planned test file | File missing | Not Implemented | Test Drift | No file with planned name. |
| MP-STEP6-GOTO-STAGE-GUARD | `WIZARD_GOTO_STAGE` validates transitions, blocks invalid jumps | Handler with transition guard | Implemented major-step guard + forward-jump block (`function_app.py:6679`, `function_app.py:6707`, `function_app.py:6716`) | Partial | Behavior Drift | Guard is major-step based, not strictly adjacent/allowlist as written in plan. |
| MP-STEP6-STAGE-HISTORY | Stage history tracked for back/forward | Metadata `stage_history` update | Implemented (`function_app.py:6722` onward) | Implemented | None | Requirement met. |
| MP-STEP6-NAV-TEST | `tests/test_wizard_stage_navigation.py` exists | Planned test file | File missing; alternative signals in `ui/tests/wizard_stepper_navigation.test.ts` and `tests/e2e/wizard-stage-gated.spec.ts` | Partial | Test Drift | Coverage exists but deviates from planned test artifact. |
| MP-STEP7-BUTTON-ORDER | Review-final action order keeps download visible before cover flow | Ordered action list in backend | Implemented in `review_final` stage (`function_app.py:5455`-`function_app.py:5480`) | Implemented | None | Download-first behavior implemented after PDF generation. |
| MP-STEP7-BUTTON-ORDER-TEST | `tests/test_button_order.py` exists | Planned test file | File missing; indirect e2e coverage present (`tests/e2e/wizard-stage-gated.spec.ts`) | Partial | Test Drift | Planned deterministic unit test artifact missing. |
| MP-ADD18A-WORK-OVERWRITE | `WORK_TAILOR_ACCEPT` must replace-all roles | Overwrite helper + usage in accept path | Implemented (`function_app.py:774`, `function_app.py:7520`) | Implemented | None | Aligns with addendum contract. |
| MP-ADD18B-COVER-ALWAYS-REGENERATE | `COVER_LETTER_GENERATE` must always regenerate | Generate path no shortcut via existing ref | Implemented with explicit comment/log mode (`function_app.py:8512`, `function_app.py:8513`, `function_app.py:8518`) | Implemented | None | Aligns with addendum contract. |
| MP-ADD18C-TOKEN-BUDGET-UPDATES | Increase budgets for job_posting/work_experience/cover_letter | Call sites use updated token limits | `job_posting=1200`, `work_experience=2240`, `cover_letter=1680` present (`function_app.py:2645`, `function_app.py:7608`, `function_app.py:2706`) | Partial | Scope Drift | Implemented values found; no explicit evidence of retry-pressure KPI reduction in repo artifacts. |
| MP-ADD18D-COMPACT-CORRECTION-PAYLOAD | Correction path uses compact payload (violations+affected roles) | Compact payload builder usage | Implemented via violation payload and bad-role subset (`function_app.py:7570`, `function_app.py:7585`) | Implemented | None | Matches addendum direction. |
| MP-ADD18E-ACTION-OBSERVABILITY | Critical actions log action id + stage before/after + session id | Structured logs around action lifecycle | Partial: action-stage logs exist for cover and wizard (`function_app.py:5923`, `function_app.py:8518`, `function_app.py:8593`) but not uniformly stage-before/after for every critical action | Partial | Behavior Drift | Good progress, not yet uniform coverage. |
| MP-ADD18F-CRASH-FIX-BLOB-READS | Blob-aware read consistency + crash fix for persistence | Blob-aware getters + fallback persist + tests | Implemented (`function_app.py:3563`, `function_app.py:5607`, `function_app.py:5741`); tests exist (`tests/test_import_gate_stage_guard.py:287`, `tests/e2e/cover-letter-generate-action.spec.ts:70`) | Implemented | None | Strongly aligned with addendum and handoff. |
| MP-BASELINE-ORDERING-NOTE | Initial Step-7 wording says `GENERATE_COVER_LETTER` in review stage | Action naming from early section | Later flow uses `COVER_LETTER_PREVIEW` then `COVER_LETTER_GENERATE` stage (`function_app.py:5484`, `function_app.py:5522`) | Superseded | Scope Drift | Later addendum + implemented flow supersede early wording. |
| MP-HANDOFF-COMMIT-VERIFY | Handoff commit/push claim verifiable from repo | git metadata present in workspace | Workspace here is not a git root (`git rev-parse` failed earlier), commit claim not locally verifiable | Unverifiable | Doc Drift | Handoff likely correct but cannot prove from current workspace metadata. |

## Handoff vs Repo Cross-Check
- Verified in repo (matches handoff):
  - Blob-aware session retrieval used in orchestrator paths (`function_app.py:3563`, `function_app.py:5607`).
  - Persistence fallback with shrink retry for `PropertyValueTooLarge` (`function_app.py:5759`, `function_app.py:5763`).
  - Action-only passthrough in UI API route (`ui/app/api/process-cv/route.ts:47`).
  - Test artifacts referenced in handoff exist (`tests/test_import_gate_stage_guard.py`, `tests/e2e/cover-letter-generate-action.spec.ts`).
- Not locally verifiable:
  - Commit/push provenance (`a529856` on `main`) from this workspace snapshot.

## Top 3 Highest-Risk Gaps
1. **Missing planned deterministic test artifacts** (`test_blob_snapshots.py`, `test_ui_actions_reorder.py`, `test_wizard_stage_navigation.py`, `test_skills_proposal_tone.py`, `test_button_order.py`).
   - Risk: regression blind spots and plan-compliance ambiguity.
2. **UI affordance drift for reorder/remove actions**.
   - Risk: backend capability exists but may remain inaccessible or inconsistent in UX.
3. **Observability not uniformly normalized for all critical actions**.
   - Risk: hard-to-diagnose session/state anomalies outside cover-letter path.

## Next Implementation Batch (Ordered by dependency/risk)
1. **Testing parity batch (smallest/highest ROI):**
   - Add/alias planned test files to existing coverage (or explicitly update master plan to accepted replacements).
   - Minimum: `test_ui_actions_reorder.py`, `test_wizard_stage_navigation.py`, `test_button_order.py`, `test_skills_proposal_tone.py`, blob snapshot regression file.
2. **UI wiring batch for reorder/remove controls:**
   - Expose deterministic controls in wizard UI for work-role and skills reorder/remove actions.
   - Add focused UI tests for action dispatch.
3. **Observability normalization batch:**
   - Standardize one log schema for all critical actions: `aid`, `session`, `stage_before`, `stage_after`, `result`, `trace_id`.

## Repro Commands Used
- `rg -n "Step [1-7]|Success Criteria|Addendum" C:\AI memory\CV-generator-repo\MASTER_PLAN_SESSION_EXTRACTION_AND_UI_REFINEMENTS.md`
- `rg -n "get_session_with_blob_retrieval|update_session_with_blob_offload|PropertyValueTooLarge|_shrink_metadata_for_table|WORK_TAILOR_ACCEPT|COVER_LETTER_GENERATE|WIZARD_GOTO_STAGE|DOWNLOAD_PDF" C:\AI memory\CV-generator-repo\function_app.py`
- `rg -n "COVER_LETTER_GENERATE|PropertyValueTooLarge" C:\AI memory\CV-generator-repo\tests\test_import_gate_stage_guard.py C:\AI memory\CV-generator-repo\tests\e2e\cover-letter-generate-action.spec.ts`
- `Test-Path` matrix for expected planned test files and artifacts.

## Addendum (2026-02-19) - Deep `function_app.py` Modularization Plan

### Objective
Reduce orchestration complexity in `function_app.py` (current: 9874 LOC) by extracting stable, deterministic modules without changing external API contracts.

Primary outcomes:
- smaller files and lower cognitive load for human/agent editing,
- lower merge-conflict surface,
- faster targeted testing and safer incremental refactors.

### Structural Baseline (evidence)
- `function_app.py` LOC: `9874`
- `if aid ==` action branches in orchestrator flow: `69`
- Top size hotspots:
  - `_tool_process_cv_orchestrated`: `3663` LOC
  - `_build_ui_action`: `962` LOC
  - `_run_responses_tool_loop_v2`: `768` LOC
  - `_run_responses_tool_loop`: `574` LOC
  - `_openai_json_schema_call`: `500` LOC
  - `_tool_generate_cv_from_session`: `494` LOC

### Planning Gate Classification (semantic vs deterministic)
- Deterministic work:
  - module boundaries and imports,
  - action router extraction,
  - persistence wrappers,
  - response/tool loop extraction,
  - tests and LOC KPI reporting.
- Semantic work:
  - none required in this modularization wave (no prompt/behavior redesign as objective).

### Contract Delta Summary
- Request/response JSON contract: **no intended changes**.
- Endpoint surface (`/api/health`, `/api/cv-tool-call-handler`): **no intended changes**.
- Any contract change discovered during extraction is stop-the-line and must be approved before merge.

### Target Module Map (combined plan)
Create a backend package for orchestration extraction (paths are target paths):

1. `src/orchestrator/openai_client.py`
- Move: `_schema_repair_instructions`, `_friendly_schema_error_message`, `_openai_json_schema_call`, helper token logic.
- Goal: isolate OpenAI call policy/retry/repair.

2. `src/orchestrator/wizard/ui_builder.py`
- Move: `_build_ui_action` and UI action composition helpers.
- Goal: separate display/action assembly from execution logic.

3. `src/orchestrator/wizard/persistence.py`
- Move: `_snapshot_session`, `_shrink_metadata_for_table`, persist helper logic used by wizard action handling.
- Goal: single persistence policy layer.

4. `src/orchestrator/wizard/action_handlers/`
- Files:
  - `contact_education.py`
  - `job_posting_interests.py`
  - `work_experience.py`
  - `further_experience.py`
  - `skills.py`
  - `cover_letter_pdf.py`
  - `navigation.py`
- Move: grouped `if aid == ...` branches from `_tool_process_cv_orchestrated`.
- Goal: one handler module per stage domain with explicit dispatch table.

5. `src/orchestrator/responses_loop.py`
- Move: `_tool_schemas_for_responses`, `_sanitize_tool_output_for_model`, `_run_responses_tool_loop`, `_run_responses_tool_loop_v2`.
- Goal: isolate assistant/tool orchestration engine.

6. `src/orchestrator/tools/`
- Files:
  - `cv_session_tools.py`
  - `pdf_tools.py`
  - `context_pack_tools.py`
- Move: `_tool_extract_and_store_cv`, `_tool_generate_cv_from_session`, `_tool_generate_cover_letter_from_session`, `_tool_get_pdf_by_ref`, related helpers.
- Goal: isolate callable backend tools from HTTP wiring.

7. `src/orchestrator/entrypoints.py`
- Move: `cv_tool_call_handler` internals and thin app adapter logic.
- Keep `function_app.py` as Azure Functions bootstrap + imports + route registration only.

### Extraction Waves (decision-complete sequence)

#### Wave 0 - Safety baseline (no behavior change)
- Freeze baseline metrics and smoke tests.
- Add temporary adapter imports from new modules back into `function_app.py`.
- Acceptance:
  - all existing focused tests pass,
  - endpoint behavior unchanged for golden scenarios.

#### Wave 1 - OpenAI + shared helpers extraction
- Extract OpenAI/repair/token helper cluster.
- Replace local definitions with imports.
- Acceptance:
  - schema/repair/retry behavior parity on existing tests.

#### Wave 2 - UI builder extraction
- Extract `_build_ui_action` and related UI assembly logic.
- Keep same returned shape and action IDs.
- Acceptance:
  - UI action payload snapshots unchanged for key stages.

#### Wave 3 - Wizard action handler decomposition
- Introduce dispatch map: `action_id -> handler`.
- Move branches in stage-domain files listed above.
- Keep `_tool_process_cv_orchestrated` as coordinator only.
- Acceptance:
  - parity on all existing action-focused tests.

#### Wave 4 - Responses loop extraction
- Move both responses loops + tool schema builder into dedicated module.
- Keep exact tool contract and stage routing.
- Acceptance:
  - no regression in tool-call paths and response parsing tests.

#### Wave 5 - Tool function extraction (CV/PDF/context pack)
- Move `_tool_*` functions to `src/orchestrator/tools/*`.
- Keep function names re-exported or imported in `function_app.py` for compatibility.
- Acceptance:
  - document/PDF generation and blob ref flows unchanged.

#### Wave 6 - Entrypoint thinning and cleanup
- Reduce `function_app.py` to bootstrap, import wiring, and route registration.
- Remove dead helpers and duplicated logic.
- Acceptance:
  - `function_app.py` below target LOC threshold,
  - all targeted regression tests green.

### LOC Reduction KPI (mandatory reporting)

Baseline:
- `baseline_loc = 9874` (current `function_app.py` lines).

Formula:
- `loc_reduction_ratio = ((baseline_loc - current_loc) / baseline_loc) * 100`

Reporting protocol:
- report `current_loc` and `loc_reduction_ratio` after each wave and at final merge,
- include before/after numbers in PR summary and handoff.

Targets:
- Wave 3 checkpoint: `function_app.py <= 7000` LOC (>= 29.1% reduction).
- Wave 5 checkpoint: `function_app.py <= 5000` LOC (>= 49.4% reduction).
- Final target: `function_app.py <= 3200` LOC (>= 67.6% reduction).

### Validation Matrix (deterministic)
Run minimum relevant tests per wave (smallest-first):
- action gating/cover regression:
  - `pytest tests/test_import_gate_stage_guard.py -q`
- work overwrite and payload contracts:
  - `pytest tests/test_work_role_locking.py tests/test_work_alignment_policy.py tests/test_work_experience_validation_payload.py -q`
- wizard/e2e action routing smoke:
  - `npx playwright test tests/e2e/cover-letter-generate-action.spec.ts --project=chromium --workers=1 --retries=0`

Add modularization parity tests:
- handler dispatch tests for each extracted action module,
- UI action snapshot tests for `review_final`, `cover_letter_review`, `work_experience`, `it_ai_skills`.

### Risks and Controls
- Risk: hidden coupling via shared mutable `meta2`/`cv_data`.
  - Control: enforce typed handler signature and single persist boundary per handler.
- Risk: circular imports after extraction.
  - Control: dependency direction rule (`entrypoints -> orchestrator -> tools`, not reverse).
- Risk: behavior drift during branch moves.
  - Control: move in small slices with parity tests after each slice.

### Rollback Strategy
- Keep extraction commits wave-scoped and reversible.
- If a wave regresses, revert that wave only; do not continue subsequent waves.
- Preserve compatibility adapters in `function_app.py` until final wave is green.

## Normal Route Default Baseline (locked 2026-02-20)

Primary runtime baseline for cleanup/orphan decisions:
- log source: `tmp/logs/func_20260220_110738.log`
- session observed: `e7a328b5-0b84-4336-b204-b482701fea56`

Default click/action sequence:
1. `LANGUAGE_SELECT_EN`
2. `CONFIRM_IMPORT_PREFILL_YES`
3. `CONTACT_CONFIRM`
4. `EDUCATION_CONFIRM`
5. `JOB_OFFER_CONTINUE`
6. `WORK_TAILOR_RUN` (notes/edit loop can repeat)
7. `WORK_TAILOR_ACCEPT`
8. `SKILLS_TAILOR_RUN`
9. `SKILLS_TAILOR_ACCEPT`
10. `REQUEST_GENERATE_PDF`
11. `COVER_LETTER_GENERATE`

Code ownership map for this route:
- `src/orchestrator/wizard/action_dispatch_contact.py`
- `src/orchestrator/wizard/action_dispatch_profile_confirm.py`
- `src/orchestrator/wizard/action_dispatch_job_posting_ai.py`
- `src/orchestrator/wizard/action_dispatch_work_basic.py`
- `src/orchestrator/wizard/action_dispatch_work_tailor_ai.py`
- `src/orchestrator/wizard/action_dispatch_skills.py`
- `src/orchestrator/wizard/action_dispatch_cover_pdf.py`
- `src/orchestrator/wizard/ui_builder.py`
- dispatcher wiring in `function_app.py` (`_tool_process_cv_orchestrated`)

Rule for dead-code/orphan classification:
- treat this normal route as default runtime evidence;
- remove candidates only if they are outside this route, outside fallback contracts, and not required by deterministic tests.

## Execution Scope Update (2026-02-20)

- Full golden suite gate: marked **done** (operator-verified normal run + golden checks completed).
- UX phase timing: moved to **deferred/backlog** by operator decision.
  - Current product behavior is stable and accepted for active usage.
  - UX optimization remains planned but is intentionally paused until a later iteration.
- Immediate focus is now:
  - runtime-backed orphan cleanup,
  - modularization hardening,
  - deterministic route stability.
