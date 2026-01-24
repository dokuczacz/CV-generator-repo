# CV Generator

Professional CV generator with chat interface and OpenAI prompt integration. Transforms CVs into ATS-compliant, 2-page PDFs following Swiss/European standards.

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
         │ Tool calls (extract_photo, validate_cv, generate_cv_action)
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
3. Backend calls OpenAI with `store: true` (uses prompt from dashboard)
4. OpenAI decides which tools to call (extract_photo → validate_cv → generate_cv_action)
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
├── TOOLS_CONFIG.md             # Tools JSON for OpenAI dashboard
├── SYSTEM_PROMPT.md            # System prompt for dashboard
├── PROMPT_INSTRUCTIONS.md      # Knowledge file (upload to dashboard)
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
- Paste content from `SYSTEM_PROMPT.md` into "System Prompt" field
- Upload `PROMPT_INSTRUCTIONS.md` as knowledge file

**c) Add Tools:**
Open `TOOLS_CONFIG.md` and add 3 tools:
1. Copy JSON for `extract_photo`
2. Copy JSON for `validate_cv`
3. Copy JSON for `generate_cv_action`

Paste each into dashboard "Add Tool" → "Function"

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

## Tools

### extract_photo
**Purpose:** Extract photo from DOCX CV  
**Input:** `{ docx_base64: string }`  
**Output:** `{ photo_data_uri: string }`

### validate_cv
**Purpose:** Validate CV data before rendering  
**Input:** CV data object (full_name, email, phone, etc.)  
**Output:** `{ is_valid: boolean, errors: [], warnings: [] }`

### generate_cv_action
**Purpose:** Generate final 2-page PDF  
**Input:** CV data + language (en/de/pl) + optional photo  
**Output:** `{ success: true, pdf_base64: string }`

---

## Tech Stack

- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS
- **Backend:** Node.js (tool orchestration)
- **Azure Functions:** Python 3.11, WeasyPrint (PDF rendering)
- **AI:** OpenAI GPT-4+ with tool calling
- **Deployment:** Vercel (frontend), Azure (backend)

---

## Configuration Files

- `TOOLS_CONFIG.md` - Complete JSON for 3 tools (copy-paste to dashboard)
- `SYSTEM_PROMPT.md` - System prompt text for dashboard
- `PROMPT_INSTRUCTIONS.md` - Detailed workflow guide (upload as knowledge)
- `ui/lib/prompts.ts` - CV_SYSTEM_PROMPT (can be used locally or in dashboard)
- `ui/lib/tools.ts` - Tool definitions (reference, not used in code)

---

## Key Features

✅ **Chat Interface** - Conversational CV generation  
✅ **File Upload** - Drag & drop DOCX/PDF  
✅ **Tool Calling** - AI orchestrates workflow  
✅ **Photo Extraction** - Automatic from DOCX  
✅ **Validation** - Pre-render checks  
✅ **Multi-language** - EN/DE/PL support  
✅ **ATS-Compliant** - Parseable by recruitment systems  
✅ **2-Page Limit** - Professional Swiss template  

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
