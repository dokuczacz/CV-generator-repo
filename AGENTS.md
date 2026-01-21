---
applyTo: "**"
---

# Agent Operating Rules for CV Generator

This repository operates with disciplined, reusable agent patterns. Rules apply to all agents (GitHub Copilot, local, MCP-enabled) working in this codebase.

---

## CORE SKILLS (Always Active)

### ⚙️ STALL_ESCALATION
When evidence is missing or scope exceeds 3 files/commands, **stop and offer a choice:**

1) **Blocker:** One sentence describing the missing evidence or scope issue.
2) **Option A - Split:** 1-3 smallest next steps (can be done with ≤3 files/commands).
3) **Option B - Escalate:** What extra input/tool/model capability is needed.
4) **Operator question:** Direct yes/no question to decide.

**Triggers:**
- Missing file path, missing outputs, or correctness depends on missing inputs.
- Touching auth, tokens, OAuth, credentials, publishing profiles.
- Requires broad repo scanning or >3 files/commands.
- Scope expands beyond the smallest next step.

**Never invented results to "push through"** — default to Split if doable, else Escalate.

### 📊 PROGRESS_TABLE_STRICT
Use when user asks for: status / progress / counts / "czy skończone" / workstream reporting.

**Output:** One markdown table only:
```
| Workstream/Task | Done/Total | Progress | Status | Source |
|---|---|---|---|---|
| Task A | 5/10 | 50% | ⚙️ In progress | cmd output line 23 |
| Task B | N/A | N/A (baseline) | 🟡 Needs input | not yet scanned |
```

**Hard rules:**
- ❌ FORBIDDEN: `{d}/{t}`, `???`, `TBD`, random totals, guesses.
- ✅ REQUIRED: Every number has a Source (command, file line, operator-provided).
- ✅ Keep 3-7 rows, current scope only.
- ✅ Progress = round(100 * Done / Total) or `N/A (baseline)`.

**After table:** Max 2 bullets for anomalies, then stop.

### 📌 STEP_ENDCAP
Append after any completed step (3 lines only, no extra prose):

- **WU target:** What should be delivered when this work unit is complete.
- **Done now:** What was actually accomplished in this step.
- **Next:** 1-3 next actions (concrete files/commands/artifacts).

**Be concrete:** Use verified counts, filenames, command names. If WU target unclear, mark `(?)`.

---

## ON_DEMAND SKILLS (Triggered by Intent)

### 📋 EXECPLAN
Use when task is multi-hour / multi-step (>3 steps) OR Unknown Sea triggered OR user asks for "plan" / "execplan" / "PLANS.md".

**Output:**
1. Create/update `tmp/<task>_execplan.md` (stable slug: lowercase, underscores).
2. In chat, link to file and summarize only the delta (don't paste whole plan).

**File structure:**
```markdown
# Goal
# Inputs and Context
# Acceptance (observable signals + exact commands)
# Plan (3-7 steps, smallest first)
# Commands (exact with working directory)
# Validation (tests / manual checks)
# Recovery (idempotence, retry, rollback)
# Notes (decisions + rationale, append-only)
```

**Progress updates:** Mark steps done/blocked as work proceeds. If you change a decision, write one short note at the bottom.

**Git hygiene:** At end of milestone, add "Git hygiene" subsection with inspection commands (but don't commit/push unless user explicitly asks).

### 🔐 GIT_HYGIENE
Use when user asks: "commit" / "push" / "GitHub" / "PR" / "tidy repo" / end-of-work-unit.

**Safety rules (MUST):**
- ❌ Never remove or rewrite local settings (no `git clean -xfd`, no deleting `.env`).
- ❌ Never stage secrets (avoid `git add -A`; stage files explicitly).
- ✅ Default: "inspect → stage explicitly → commit → push" (copy/paste commands).

**Templates (PowerShell-first):**
```powershell
# Inspect (non-destructive)
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

### 🖥️ OPERATOR_COMMANDS
Use when user asks: "podaj cmd" / "jak odpalić" / "żeby nie blokowało" / "puść w tle".

**Output (copy/paste, non-blocking):**
- PowerShell `Start-Job` for background work (or `Start-Process`).
- Include: job name, monitoring loop, success signal (1 line).
- ❌ No secrets inline → use env vars.
- ✅ Paths explicit.

**Templates (PowerShell):**
```powershell
# Run background job
cd <workdir>
Start-Job -Name <job-name> -ScriptBlock { Set-Location <workdir>; <full-command> }

# Monitor progress
while ((Get-Job -Name <job-name>).State -eq 'Running') {
  Receive-Job -Name <job-name> -Keep
  Start-Sleep -Seconds 20
}

# Cleanup
Receive-Job -Name <job-name> -Keep
Remove-Job -Name <job-name> -ErrorAction SilentlyContinue
```

### 📦 DATA_OPERATOR
Use when: "uruchom pipeline" / "daj monitoring" / "pokaż sample" / "sprawdź kontrakt JSON" / "DoD = stałe pola".

**Prefer:** One cmd + one progress-monitoring cmd over writing new scripts.

**Templates:**
```powershell
# Run in background
cd <workdir>
Start-Job -Name <job> -ScriptBlock { <tool> --progress-file tmp/<task>_progress.json --progress-every 30 }

# Monitor progress (refresh every 30s)
$progress = ConvertFrom-Json (Get-Content tmp/<task>_progress.json)
$handled = $progress.processed + $progress.skipped + $progress.errors
$total = <TTL>
$pct = [math]::Round(100 * $handled / $total)
Write-Host "handled=$handled/$total ($pct%) | rate=$($progress.rate)/s | ETA=$($progress.eta)"

# Sample validation
python -c "import json; d=json.load(open(r'<output>.json','rb')); missing=[k for k in ['field1','field2'] if k not in d]; print('missing', missing)"
```

### ☁️ AZURE_BLOB_OPS
Use when: "sprawdź azurite/azure" / "ile plików" / "pobierz sample" / "compare azurite vs azure".

**Output (copy/paste commands):**
- ❌ No secrets inline → use env vars (`AZURE_STORAGE_CONNECTION_STRING`).
- ✅ PowerShell `python -c` (stable, explicit).
- ✅ Include 1-line success signal.

**Azure MCP Tools:**
When using Azure MCP tools (AppLens, Monitor, etc.), always include:
- `subscription`: `3bb75fb7-e75f-4e75-8ff0-473d72d82c79`
- `tenant`: `dbb16708-62b5-4835-bc82-46b38d1a71d3` (if required)

**Example MCP call:**
```json
{
  "command": "monitor_resource_log_query",
  "parameters": {
    "subscription": "3bb75fb7-e75f-4e75-8ff0-473d72d82c79",
    "resource-id": "/subscriptions/3bb75fb7-e75f-4e75-8ff0-473d72d82c79/resourceGroups/cv-generator-rg/providers/Microsoft.Web/sites/cv-generator-6695",
    "table": "requests",
    "query": "requests | where timestamp > ago(24h) | order by timestamp desc",
    "hours": 24,
    "limit": 10
  }
}
```

**Templates (PowerShell):**
```powershell
# Check if blob exists
python -c "import os; from azure.storage.blob import BlobServiceClient; c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); bc=c.get_blob_client('<blob>'); print('exists', bc.exists())"

# Count blobs with prefix
python -c "import os; from azure.storage.blob import BlobServiceClient; c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); print(sum(1 for b in c.list_blobs(name_starts_with='<prefix/>')))  "

# Download sample
python -c "import os, pathlib; from azure.storage.blob import BlobServiceClient; out=pathlib.Path(r'tmp\\sample.json'); out.parent.mkdir(parents=True, exist_ok=True); c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); data=c.get_blob_client('<blob>').download_blob().readall(); out.write_bytes(data); print('wrote', str(out), 'bytes', len(data))"

# Compare Azurite vs Azure (requires both env vars set)
$old = $Env:AZURE_STORAGE_CONNECTION_STRING
$Env:AZURE_STORAGE_CONNECTION_STRING = $Env:AZURITE_STORAGE_CONNECTION_STRING
python -c "import os; from azure.storage.blob import BlobServiceClient; c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); print('azurite', c.get_blob_client('<blob>').exists())"
$Env:AZURE_STORAGE_CONNECTION_STRING = $Env:AZURE_STORAGE_CONNECTION_STRING_PROD
python -c "import os; from azure.storage.blob import BlobServiceClient; c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); print('azure', c.get_blob_client('<blob>').exists())"
$Env:AZURE_STORAGE_CONNECTION_STRING = $old
```

### 🎓 SELF_LEARNER_MINI
Use ONLY when user asks for clarification: "przypomnij" / "wytłumacz" / "nie rozumiem" / "co to jest" / "jak działa".

**Output (exactly 4 items, no lecture):**
1) **What it is** (1-2 sentences)
2) **Why it matters here** (1 sentence)
3) **Example** (one command OR one tiny snippet)
4) **Gotcha** (one pitfall to watch for)

**Rules:** Stay code-oriented, concise. If unsure: state one assumption OR ask one targeted question.

---

## META RULES

### 🌊 UNKNOWN_SEA_PROTOCOL
Stop and output this structure when:
- Missing file path / missing outputs needed for correctness
- Touching auth, tokens, OAuth, credentials, publishing profiles
- Requires repo-wide scan or broad blob scan (many items)
- High-fidelity work (pixel-perfect, copy 1:1, layout matching)
- Data quality looks inconsistent (impossible dates, null fields)
- Multiple plausible interpretations of the request

**Mandatory output:**
1) **We are about to work on an unknown sea; be careful.**
2) **State the top 1–2 assumptions and what evidence is missing.**
3) **Offer the smallest safe verification step (command/file) before proceeding.**

**Stop conditions:**
- If correctness depends on missing inputs → ask for them (or escalate).
- If operation might touch secrets/credentials → propose safe alternative.
- If scope exceeds 3 files/commands → split into smallest next step and confirm.

### ⚡ EFFICIENCY_GUARD
Ask before broad scans, long suites, destructive ops, or anything likely >2m when a cheaper L0/L1 check exists.

**Confirm before:**
- `git status --porcelain` over `find . -type f`
- Sample-based count (N=5-10) over full-repo scan
- `git log --oneline | head` over `git log`
- Linter on single file vs whole project

### 📊 VALIDATION_LADDER (Pick Lowest Level That Answers)
- **L0:** Metadata only (exists/counts/schema keys)
- **L1:** Sample-based (N=5/10 items)
- **L2:** Focused test (single unit/integration)
- **L3:** Benchmark/repro (timed before/after)

### 🔍 GAP_DRIVEN_COACHING
Before trusting samples: sanity-check invariants (dates, ids, counts, schema).
Before layout/extraction work: request reference artefact + define fidelity tier + validate one vertical slice.
Before changing code: identify 1 entry-point + 1 focused test or minimal repro.

### 🔥 CONTEXT_MODE
- **Default:** "hot_only" — stay on current narrow task.
- **Prefer:** Deterministic micro-checks over broad exploration.
- **Prefer:** File paths (e.g., `tmp/<task>_plan.md`) over pasting long logs.
- **Don't broaden scope** unless explicitly requested.

---

## COPILOT-SPECIFIC FEATURES

### 💬 CONTEXT_MENTIONS
When using Copilot Chat or agents, leverage native context:
- `#codebase` — full workspace context (for architecture questions).
- `#file <path>` — add specific file to context.
- `#terminalSelection` — include terminal output as context.
- Type `#` to see all available mentions.

**Example:** "@file src/function_app.py #codebase Generate a test for this endpoint"

### 🛠️ MCP_TOOLS
When MCP servers are available (GitHub, Azure, OpenAI, etc.), reference tools explicitly:
- `#tool:githubRepo` — search GitHub repositories.
- `#tool:azureResources` — query Azure resources.
- `#tool:fetchWebpage` — pull live documentation.

**Example:** "#tool:githubRepo Find similar CV generation projects"

### 🤖 AGENT_MODES
Copilot supports multiple agent modes; choose based on task:
- **Agent** — autonomous code execution (default, uses all tools).
- **Plan** — read-only planning mode (no execution).
- **Ask** — conversational, retrieves context only.
- **Edit** — inline code refactoring.

**Use Plan mode** for architecture reviews or complex planning before making changes.

### 🧩 TOOL_MANAGEMENT
- VS Code agent can use up to 128 tools per request.
- If too many tools enabled → deselect unused servers in tool picker.
- Group related tools into **tool sets** to keep picker clean.

---

## SKILL ACTIVATION TRIGGERS

| Trigger (User Says) | Skill(s) Activated | Mode |
|---|---|---|
| "status", "progress", "progress" | PROGRESS_TABLE_STRICT | append |
| "plan", "execplan", "multi-hour task" | EXECPLAN | append |
| "commit", "push", "GitHub", "PR" | GIT_HYGIENE | append |
| "run", "cmd", "background", "jak odpalić" | OPERATOR_COMMANDS | append |
| "pipeline", "batch", "progress", "sample" | DATA_OPERATOR | append |
| "azure", "blob", "azurite", "count files" | AZURE_BLOB_OPS | append |
| "blocked", "missing", "can't proceed" | STALL_ESCALATION | replace |
| "explain", "what is", "how does", "why" | SELF_LEARNER_MINI | append |
| "done", "confirmed", "DoD", "final", "next" | STEP_ENDCAP | append (always last) |

---

## PRINCIPLES

1. **Always make a plan before multi-step work** (3-7 steps, acceptance criteria, smallest verification first).
2. **Never emit placeholders** (TBD, ???, estimate unless asked).
3. **Default to Split** (smallest next step) over escalation (unless blocked).
4. **No secrets inline** — use env vars, `.env.template`, docs.
5. **Confirm before expensive operations** (repo-wide scans, destructive commands).
6. **Trust the instructions** — only search/ask if information incomplete or found to be in error.
7. **Verify every number** in progress tables (source must be verifiable).
8. **Prefer copy/paste commands** over prose when operator involvement needed.
9. **Keep git hygiene** — safe staging, meaningful commits, document operations.
10. **Use MCP when available** — prefer `#tool:` references over manual searches.

