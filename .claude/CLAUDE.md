# CV Generator - Claude Code Context

**Goal:** Generate ATS-compliant, 2-page PDF CVs from uploaded DOCX/PDF files.

---

## Stack

- **Frontend:** Next.js 14 + React 18 + TypeScript ([ui/app/page.tsx](ui/app/page.tsx))
- **Backend:** Azure Functions Python 3.11 ([function_app.py](function_app.py))
- **PDF:** WeasyPrint (float-based layouts, no Grid/Flexbox)
- **Testing:** Playwright visual regression (baselines in `test-results/`)

---

## Commands

```bash
# Development
cd ui && npm run dev              # Frontend: http://localhost:3000
func start                        # Backend: http://localhost:7071

# Testing
npm test                          # Run all Playwright tests
npm run test:headed               # Interactive mode
npm run test:ui                   # UI mode
npm run show-report               # View test report

# Build
cd ui && npm run build
cd ui && npm run lint
```

---

## Key Files

- **Template:** [templates/html/cv_template_2pages_2025.html](templates/html/cv_template_2pages_2025.html)
- **Schema:** [DATA_DICTIONARY.md](DATA_DICTIONARY.md)
- **Workflow:** [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md)
- **System prompt:** [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md)
- **Tools config:** [TOOLS_CONFIG.md](TOOLS_CONFIG.md)

---

## Skills (on-demand)

- `/execplan [task]` - Create execution plan in tmp/ to reduce context
- `/progress-tracker` - Show verified progress with source attribution
- `/validate-cv` - Validate CV JSON against schema
- `/visual-regression` - Run visual tests and compare baselines
- `/multi-claude-review` - Launch parallel review session

Skills loaded automatically when relevant (see [.claude/skills/](.claude/skills/))

---

## Architecture Principles

- **Backend-first:** Python owns orchestration, state, retries, validation, limits
- **UI is thin:** Next.js proxies inputs/outputs only; no workflow logic
- **AI is semantic:** Model proposes tool calls; backend enforces allowlists
- **JSON-only:** All contracts use strict JSON with `schema_version`
- **Single source of truth:** One dict/schema per project; avoid drift

---

## Critical Constraints

1. **2-page limit:** CVs MUST fit strict template (see [templates/html/CV_template_2pages_2025.spec.md](templates/html/CV_template_2pages_2025.spec.md))
2. **No fabricated data:** Preserve user CV content exactly
3. **Azure Table limits:** Properties <64KB; photo URLs <32KB
4. **Test before commit:** Always run `npm test` and `cd ui && npm run lint`
5. **No secrets in code:** Use `local.settings.json` (see `local.settings.template.json`)

---

## DO NOT COMMIT

- `local.settings.json`
- `ui/.env.local`
- Any files with secrets/API keys

---

## Extended Context

Load on-demand only:

- **Code style:** [.claude/CODE_STYLE.md](.claude/CODE_STYLE.md)
- **Git workflow:** [.claude/GIT_GUIDE.md](.claude/GIT_GUIDE.md)
- **Troubleshooting:** [.claude/TROUBLESHOOTING.md](.claude/TROUBLESHOOTING.md)
- **Deployment:** [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md)
- **Session storage:** [SESSION_STATUS_2026_01_21.md](SESSION_STATUS_2026_01_21.md)

---

## Workflow Patterns

### When Blocked
Use stall-escalation pattern:
- Missing inputs? Stop and ask (Split vs Escalate)
- No progress after 2 turns? Stop and ask
- Scope unclear? Stop and ask
- Never invent placeholder data

### Multi-Step Tasks
Use `/execplan [task]` to create working file in `tmp/` and keep conversation short.

### Visual Changes
1. Edit CSS/HTML in [templates/html/](templates/html/)
2. Generate preview via API
3. Run Playwright screenshot
4. Compare with baseline (5% threshold)
5. Iterate until pixel-perfect

### Extended Thinking
Use for complex tasks:
- `think` - Standard (schema validation)
- `think hard` - Complex (layout calculations)
- `ultrathink` - Critical (architecture, security)

---

## Environment Variables

Required in `local.settings.json` (local) or Azure App Settings (prod):

```json
{
  "FUNCTIONS_WORKER_RUNTIME": "python",
  "AzureWebJobsStorage": "UseDevelopmentStorage=true",
  "OPENAI_API_KEY": "sk-...",
  "STORAGE_CONNECTION_STRING": "...",
  "USE_STRUCTURED_OUTPUT": "0"
}
```

---

## MCP Servers (Available)

- **Filesystem:** `npx -y @modelcontextprotocol/server-filesystem "c:\AI memory\CV-generator-repo"`
- **Azure Blob:** Subscription `3bb75fb7-e75f-4e75-8ff0-473d72d82c79`
- **GitHub:** Requires `GITHUB_TOKEN` env var
- **Playwright:** `npx -y @modelcontextprotocol/server-playwright`

---

**Last updated:** 2026-01-27
**Compatible with:** Claude Sonnet 4.5+