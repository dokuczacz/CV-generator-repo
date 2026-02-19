# Agent Skills Reference (full runbooks)

This file exists to keep the always-loaded instructions (AGENTS.md, copilot-instructions.md) small.

If you are using a skill system (e.g., `.codex/skills/*/SKILL.md`) these sections mirror that “thin router, thick skills” approach.

## Policy status (Copilot-primary)

- Source of truth for implementation behavior: repo Copilot instructions (`AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.md`).
- Optional Codex overlays allowed in this repo: `omniflow-execplan`, `omniflow-llm-orchestration`, `omniflow-test-operator`.
- All other Codex operational instructions are reflected below as core behavior or deprecated overlays rerouted to core docs.

## Codex operational mapping matrix

| Codex operational instruction | Status in this repo | Canonical location |
|---|---|---|
| `omniflow-execplan` | Active optional overlay | `AGENTS.md` (Intent triggers), `.github/instructions/planning-gate.instructions.md` |
| `omniflow-llm-orchestration` | Active optional overlay | `AGENTS.md` (Intent triggers), `.github/instructions/llm-orchestration.instructions.md` |
| `omniflow-test-operator` | Active optional overlay | `AGENTS.md` (Intent triggers), `.github/instructions/tests.instructions.md` |
| `omniflow-stall-escalation` | Core built-in behavior (not optional overlay) | `AGENTS.md` (Safety gates), `.github/instructions/planning-gate.instructions.md` |
| `omniflow-progress-table-strict` | Core reporting convention | `AGENTS.md` (Intent triggers), this file (`PROGRESS_TABLE_STRICT`) |
| `omniflow-step-endcap` | Core reporting convention | `AGENTS.md` (Intent triggers), this file (`STEP_ENDCAP`) |
| `omniflow-operator-commands` | Deprecated overlay, rerouted to core operator guidance | `AGENTS.md` (Intent triggers), this file (`OPERATOR_COMMANDS`) |
| `omniflow-github-operator` | Deprecated overlay, rerouted to core operator guidance | `AGENTS.md` (Intent triggers), this file (`GIT_HYGIENE`) |
| `omniflow-data-operator` | Deprecated overlay, rerouted to core operator guidance | this file (`DATA_OPERATOR`) |
| `omniflow-azure-blob-ops` | Deprecated overlay, rerouted to core operator guidance | this file (`AZURE_BLOB_OPS`) |
| `omniflow-self-learner-mini` | Deprecated overlay, rerouted to concise core explanation style | `AGENTS.md` (Defaults), this file (`CONTEXT_MODE`) |
| Unknown Sea protocol | Core built-in behavior | `AGENTS.md` (Safety gates), this file (`UNKNOWN_SEA_PROTOCOL`) |
| Efficiency guard | Core built-in behavior | `AGENTS.md` (Efficiency guard), this file (`EFFICIENCY_GUARD`) |
| Context mode (`hot_only`) | Core built-in behavior | `AGENTS.md` (Defaults), this file (`CONTEXT_MODE`) |

---

## STALL_ESCALATION
When evidence is missing or scope exceeds 3 files/commands, stop and offer a choice:

1) **Blocker:** One sentence describing the missing evidence or scope issue.
2) **Option A - Split:** 1-3 smallest next steps (can be done with ≤3 files/commands).
3) **Option B - Escalate:** What extra input/tool/model capability is needed.
4) **Operator question:** Direct yes/no question to decide.

Triggers:
- Missing file path, missing outputs, or correctness depends on missing inputs.
- Touching auth, tokens, OAuth, credentials, publishing profiles.
- Requires broad repo scanning or >3 files/commands.
- Scope expands beyond the smallest next step.

Rule: never invent results to “push through” — default to Split if doable.

---

## PROGRESS_TABLE_STRICT
Use when user asks for: status / progress / counts / “czy skończone” / workstream reporting.

Output: one markdown table only:

| Workstream/Task | Done/Total | Progress | Status | Source |
|---|---|---|---|---|
| Task A | 5/10 | 50% | ⚙️ In progress | cmd output line 23 |
| Task B | N/A | N/A (baseline) | 🟡 Needs input | not yet scanned |

Hard rules:
- FORBIDDEN: placeholders (`???`, `TBD`), guesses, random totals.
- Every number must have a Source.
- Keep 3–7 rows, current scope only.

After table: max 2 bullets for anomalies, then stop.

---

## STEP_ENDCAP
Append after any completed step (3 lines only):

- **WU target:** What should be delivered when this work unit is complete.
- **Done now:** What was actually accomplished in this step.
- **Next:** 1–3 next actions (concrete files/commands/artifacts).

---

## EXECPLAN
Use when task is multi-hour / multi-step (>3 steps) OR Unknown Sea triggered OR user asks for “plan/execplan”.

Output:
1) Create/update `tmp/<task>_execplan.md` (stable slug: lowercase, underscores)
2) In chat: link the file and summarize only the delta (don’t paste the whole plan)

ExecPlan structure:
- Goal
- Inputs and Context
- Acceptance (observable signals + exact commands)
- Plan (3–7 steps, smallest first)
- Commands
- Validation
- Recovery
- Notes (append-only)

---

## GIT_HYGIENE
Use when user asks: commit/push/PR/end-of-work.

Safety rules:
- Never remove or rewrite local settings (`local.settings.json`, `.env.local`).
- Never stage secrets (avoid `git add -A`; stage explicitly).

Template (PowerShell-first):
```powershell
# Inspect
git status -sb
git diff --stat

# Stage explicitly
git add -- <space-separated files>
git status --porcelain

# Commit
git commit -m "message"

# Push
git push
```

---

## OPERATOR_COMMANDS
Use when user asks for commands or to run something in the background.

Prefer PowerShell `Start-Job` with an explicit workdir, monitoring loop, and a 1-line success signal. No secrets inline.

---

## DATA_OPERATOR
Use when user asks to run batch/pipeline/progress monitoring/sample validation.

Prefer one command + one monitoring command over adding new scripts.

---

## AZURE_BLOB_OPS
Use when user asks about Azure/Azurite blob checks, counts, sample downloads.

No secrets inline (use `AZURE_STORAGE_CONNECTION_STRING`). Prefer small, deterministic checks.

---

## UNKNOWN_SEA_PROTOCOL
Stop and output this structure when evidence is weak or risk is high:

1) **We are about to work on an unknown sea; be careful.**
2) **State the top 1–2 assumptions and what evidence is missing.**
3) **Offer the smallest safe verification step (command/file) before proceeding.**

---

## EFFICIENCY_GUARD
Ask before broad scans, long test suites, or destructive operations when a cheaper L0/L1 check exists.

---

## CONTEXT_MODE
Default: hot_only (current narrow task). Prefer deterministic micro-checks. Prefer referencing file paths over pasting long logs.
