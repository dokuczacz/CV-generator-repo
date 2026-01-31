---
applyTo: "**"
---

# Copilot Agent Rules (Lean)

This file is intentionally short to reduce prompt load for VS Code Copilot Agents.

If you need the full runbooks/templates, open:
- `docs/agent_skills_reference.md` (not auto-loaded into the agent prompt)

## Defaults
- Stay **hot_only**: solve the current narrow task; don’t broaden scope unless asked.
- Prefer **deterministic micro-checks** over repo-wide scans.
- No secrets inline; use env vars / local settings templates.

## Planning gate (stop-the-line)
- Before executing non-trivial work, follow: `.github/instructions/planning-gate.instructions.md`
- If the gate fails (no stable scenario pack / no DoD / deterministic constraints missing fallback), stop and use the stall-escalation pattern to request the missing artifacts/decisions.
## Architecture baseline (default)
- Backend-first (Python): backend is the only orchestrator (stage/state, retries, timeouts, idempotency, validation, limits).
- UI is minimal: UI is a thin proxy for inputs/outputs; do not implement orchestration/workflow in UI.
- AI is semantics only: model proposes intent/tool_calls; backend enforces allowlists/limits and owns state changes.
- JSON-only contracts: no plaintext; request/response are strict JSON with `schema_version`.
- Contract discipline: aim for one "single source of truth" (one dict/schema) per project/backend; if a change would add a second source or drift risk, stop and confirm the approach with the operator first.
- Contract deltas: whenever you propose changing a JSON contract, explicitly summarize the delta (what changed + why + how to verify) before implementing.
- Pre-agent gate: before prompt/agent integration, ensure backend+orchestration pass a dry-run baseline (health + capabilities + 1–2 golden JSON flows) via test-operator skill (see `docs/skills/test-operator.md`).
## Safety gates

### Unknown sea (mandatory script)
Use when evidence is missing, multiple interpretations exist, scope explodes, or auth/secrets may be touched:
1) **We are about to work on an unknown sea; be careful.**
2) **State the top 1–2 assumptions and what evidence is missing.**
3) **Offer the smallest safe verification step (command/file) before proceeding.**

### Stall escalation (replace)
If blocked or correctness depends on missing inputs, stop and output only:
1) **Blocker:** one sentence
2) **Option A - Split:** 1–3 smallest next steps
3) **Option B - Escalate:** what extra input/tool is needed
4) **Operator question:** yes/no

## Intent triggers (router)
- `status/progress/counts` → strict progress table (verified numbers + Source)
- `plan/execplan` or >3 steps → write `tmp/<task>_execplan.md` and link it
- `run/cmd/background` → copy/paste PowerShell commands (non-blocking)
- `git/commit/push/pr` → safe “inspect → stage explicitly → commit → push” commands- `test/verify/CI/pytest` → route test scope + commands via test-operator skill (see `docs/skills/test-operator.md`); avoid ad-hoc test plans- `done/final/DoD` → 3-line step endcap (WU target / Done now / Next)

## Efficiency guard
Ask before anything likely >2m (broad scans, long test suites, destructive ops) when a cheaper L0/L1 check exists.

