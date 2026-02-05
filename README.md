# CV Generator

Professional CV generator with chat interface and OpenAI prompt integration. Transforms CVs into ATS-compliant, 2-page PDFs following Swiss/European standards.

## 🎯 Production Status

**Version:** 1.0 (Production-Ready)  
**Test Coverage:** 14/14 golden suite tests passing (100%)  
**Performance:** ~10.5s avg response time, 110KB 2-page PDFs  
**Stability:** Latch idempotency ✓, Single-call execution ✓, FSM gating ✓

### Recent Milestones (Waves 0-3)
- ✅ **Wave 0:** Critical correctness fixes (PDF latch, FSM gating, single-call enforcement)
- ✅ **Wave 1:** Stability enhancements (retry wrapper, blob download verification)
- ✅ **Wave 2:** Resilience improvements (download validation, error logging)
- ✅ **Wave 3:** Observability (sampled metrics, stress testing)

See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment guide.

---

## Architecture

```
┌─────────────────┐
│   Next.js UI    │ ← User uploads CV, sends messages
│  (localhost:3000)│
└────────┬────────┘
         │ POST /api/process-cv
         ▼
┌─────────────────┐
│  OpenAI Prompt  │ ← Configured in dashboard with tools
│  + Tool Calling │
└────────┬────────┘
         │ Tool calls (extract_and_store_cv, get_cv_session, update_cv_field, validate_cv, generate_cv_from_session, ...)
         ▼
┌─────────────────┐
│  Backend (Node) │ ← Routes tool calls to Azure Functions
│  Tool Handler   │
└────────┬────────┘
         │ HTTP requests
         ▼
┌─────────────────┐
│ Azure Functions │ ← Python backend (CV processing)
│  (cv-generator) │
└─────────────────┘
```

**Flow:**
1. User uploads CV → UI converts to base64
2. UI sends to `/api/process-cv` with message
3. Backend calls OpenAI with `store: false` by default (uses prompt from dashboard via `OPENAI_PROMPT_ID`)
4. OpenAI decides which tools to call (session workflow; PDF generation is gated by readiness + confirmations)
5. Backend executes tool calls via Azure Functions
6. Returns results to OpenAI, continues conversation
7. Final PDF returned to user

---

## Project Structure

```
cv-generator-repo/
├── ui/                          # Next.js frontend
│   ├── app/
│   │   ├── page.tsx            # Chat interface with file upload
│   │   └── api/process-cv/     # API route (tool orchestration)
│   ├── lib/
│   │   ├── prompts.ts          # CV_SYSTEM_PROMPT
│   │   └── tools.ts            # CV_TOOLS definitions (reference only)
│   └── package.json
│
├── src/                         # Azure Functions (Python)
│   ├── cv-tool-call-handler/   # Tool dispatcher (search/validate/preview via tool_name)
│
├── templates/                   # CV template
│   ├── CV_template_2pages_2025.spec.md
│   └── html/                   # HTML/CSS for rendering
│
├── TOOLS_CONFIG.md             # (legacy/lab) Tools JSON for OpenAI dashboard
├── PROMPT_SYSTEM_REVISED.md    # Current system prompt (dashboard)
├── docs/CV_GENERATION_PROMPTS.md # Prompt reference for all stages
└── README.md                   # This file
```

---

## Setup

### 1. Install Dependencies

**Frontend (Next.js):**
```bash
cd ui
npm install
```

**Backend (Azure Functions):**
```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `ui/.env.local`:
```env
OPENAI_API_KEY=sk-proj-...
OPENAI_PROMPT_ID=pmpt_696f593c42148195ab41b3a3aaeaa55d029c2c08c553971f
NEXT_PUBLIC_AZURE_FUNCTIONS_URL=https://cv-generator-6695.azurewebsites.net/api
NEXT_PUBLIC_AZURE_FUNCTIONS_KEY=cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==
```

### 3. Configure OpenAI Prompt

**a) Go to OpenAI Platform:**
```
https://platform.openai.com/assistants
```

**b) Create/Edit Prompt:**
- Paste content from `PROMPT_SYSTEM_REVISED.md` into "System Prompt" field
- (Optional) Use `docs/CV_GENERATION_PROMPTS.md` as prompt reference

 **c) Add Tools:**
 - Tools are exposed directly via OpenAI Responses API in backend orchestration (`_tool_schemas_for_responses()`).
 - Enable built-in `web_search` if you want web lookups.

**d) Model Settings:**
- Model: gpt-4 or higher
- Temperature: 0.7 (optional, can be in dashboard)

---

## Development

### Start Frontend
```bash
cd ui
npm run dev
```

Open: http://localhost:3000

### Local E2E smoke (session workflow)
With Azurite + Functions running locally on `http://127.0.0.1:7071`, run:
```bash
python scripts/smoke_local_session.py
```

### Test Backend (Azure Functions)
```bash
curl -X POST https://cv-generator-6695.azurewebsites.net/api/cv-tool-call-handler \
  -H "x-functions-key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"validate_cv","session_id":"<session_id>","params":{}}'
```

---

## Usage

1. Open http://localhost:3000
2. Upload CV file (DOCX or PDF) in sidebar
3. Type message: "Generate CV in English" or "Dopasuj CV pod ofertę: [URL]"
4. AI will:
   - Extract photo (if DOCX)
   - Analyze CV content
   - Validate structure
   - Generate 2-page PDF
5. Download PDF from chat

---

## Tools (MVP)
The OpenAI prompt uses a session-based workflow and calls backend tools through the dispatcher.
- `extract_and_store_cv` → create a new session from an uploaded DOCX
- `get_cv_session` → retrieve current session data + readiness
- `update_cv_field` → apply edits (supports batching via `edits[]` + `confirm`)
- `validate_cv` → deterministic schema + DoD checks (no PDF render)
- `generate_cv_from_session` → generate the final PDF (requires readiness + confirmations)
- `generate_cover_letter_from_session` → generate 1-page cover letter PDF (EN/DE, optional)
Additional debug tools:
- `generate_context_pack_v2` (capsule builder)
- `cv_session_search` (bounded search across session + docx snapshot)
- `preview_html` (debug HTML)

---

## Tech Stack

- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS
- **Backend:** Node.js (tool orchestration)
- **Azure Functions:** Python 3.11, WeasyPrint (PDF rendering)
- **AI:** OpenAI GPT-4+ with tool calling
- **Deployment:** Vercel (frontend), Azure (backend)

---

## Configuration Files

## Configuration Files

- [PROMPT_SYSTEM_REVISED.md](PROMPT_SYSTEM_REVISED.md) - **Current system prompt** with phase-aware workflow + Wave 0-3 guardrails
- [docs/CV_GENERATION_PROMPTS.md](docs/CV_GENERATION_PROMPTS.md) - **Complete prompts reference** for all 7 CV generation stages (job_posting, bulk_translation, work_experience, further_experience, it_ai_skills, interests)
- [local.settings.template.json](local.settings.template.json) - Environment variables template (OpenAI keys, feature flags)
- `ui/lib/prompts.ts` - CV_SYSTEM_PROMPT (reference, can be used locally)
- `ui/lib/tools.ts` - Tool definitions (reference, not used in code)

**For OpenAI Dashboard:**
1. Copy system prompt from [PROMPT_SYSTEM_REVISED.md](PROMPT_SYSTEM_REVISED.md)
2. Configure tools in dashboard (extract_and_store_cv, get_cv_session, update_cv_field, generate_cv_from_session, etc.)
3. Set `OPENAI_PROMPT_ID` in environment

---

## Key Features

✅ **Chat Interface** - Conversational CV generation  
✅ **File Upload** - Drag & drop DOCX/PDF  
✅ **Tool Calling** - AI orchestrates workflow  
✅ **Photo Extraction** - Automatic from DOCX  
✅ **Validation** - Pre-render checks  
✅ **Cover Letter (optional, EN/DE)**  
✅ **Multi-language** - EN/DE/PL support  
✅ **ATS-Compliant** - Parseable by recruitment systems  
✅ **2-Page Limit** - Professional Swiss template  

---

## Testing

### Local Testing (Development)

**Golden Suite (14 comprehensive tests):**
```bash
# Prerequisite: Start local Azure Functions
func start

# Run full test suite
python tests/test_golden_suite.py
```

Expected results: 14/14 passed (100%), ~46s execution time

**Wave-Specific Tests:**
```bash
# Wave 0 integration tests (real DOCX sample)
python tests/test_wave0_real_docx.py

# Wave 3 stress tests (5 rapid-fire requests)
python tests/test_wave3_stress.py
```

### Production Testing

**Smoke Test (3 critical paths):**
```bash
python tests/test_smoke_production.py --endpoint https://cv-generator-api.azurewebsites.net
```

Tests:
1. Health check
2. Cleanup expired sessions
3. End-to-end PDF generation

### Performance Benchmarks

| Metric | Expected Value |
|--------|---------------|
| First PDF generation | ~17s |
| Cached PDF (latch) | ~7-12s |
| Average response time | 10.56s |
| PDF size (2-page) | 110KB |
| Latch stability | 100% (identical PDFs) |
| Single-call execution | 100% (execution_mode=True) |

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete production deployment guide including:
- Azure resource provisioning
- Environment variables configuration
- CI/CD setup recommendations
- Monitoring & alerting setup
- Rollback procedures

**Quick deploy:**
```bash
func azure functionapp publish cv-generator-api --python
```

---

## Troubleshooting

### Tools not showing in OpenAI
- Refresh dashboard page
- Re-import JSON from TOOLS_CONFIG.md
- Verify JSON syntax (no trailing commas)

### PDF not generating
- Check Azure Functions logs
- Verify API key in .env.local
- Validate via the tool dispatcher first

### Photo not extracted
- Ensure DOCX file has embedded image
- Check base64 conversion in logs
- Falls back to placeholder if extraction fails

---

## AI Agent Setup

This project supports multiple AI coding agents with tailored configurations:

### Claude Code (Recommended for Complex Tasks)
**Auto-context file:** [.claude/CLAUDE.md](.claude/CLAUDE.md) loads automatically on every conversation

**Quick start:**
1. Open project in VSCode with Claude Code extension
2. Start chatting - context loads automatically
3. Use custom slash commands:
   - `/cv-tool-call-handler` (`tool_name=validate_cv`) - Validate the session CV (schema + layout checks)
   - `/visual-regression` - Run visual tests
   - `/multi-claude-review` - Parallel code review

**Unique features:**
- Extended thinking modes (`think`, `think hard`, `ultrathink`)
- Multi-Claude parallel workflows (code + review simultaneously)
- Visual iteration with Playwright screenshots
- Agent Skills with progressive disclosure
- Headless CI/CD integration

**MCP Servers configured:**
- Filesystem (progressive disclosure)
- Playwright (visual regression)
- GitHub (PR management)
- Azure Blob Storage (session storage)
- OpenAI Developer Docs

**See:** [.claude/README.md](.claude/README.md) for complete setup

### GitHub Copilot (Recommended for Quick Edits)
**Instructions file:** [.github/copilot-instructions.md](.github/copilot-instructions.md)

**Features:**
- Context mentions (`#codebase`, `#file`, `#terminalSelection`)
- Agent modes (Agent/Plan/Ask/Edit)
- Azure MCP integration (default subscription/tenant configured)
- Validation checklist before PR

### Codex (Advanced Users)
**Configuration:** [AGENTS.md](AGENTS.md)

**Features:**
- Modular skills system (omniflow-* skills)
- Progressive disclosure (3-level loading)
- Unknown Sea Protocol (safety-first)
- Tier-based skill composition (CORE vs ON_DEMAND)

**Installed skills:**
- `omniflow-execplan` - Task execution planning
- `omniflow-stall-escalation` - Blocker detection
- `omniflow-azure-blob-ops` - Azure/Azurite operations
- `omniflow-github-operator` - Git hygiene workflows

**See:** [AGENTS.md](AGENTS.md) for full skill documentation

---

## Archive

Old documentation (Custom GPT, migration plans, old tests) moved to `archive/` folder.

---

## License

Private project - Mariusz Sondej 2026
