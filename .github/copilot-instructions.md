# CV Generator — Copilot Instructions

This is a **Next.js 14 UI + Azure Functions (Python) backend** project that generates ATS-compliant, 2-page PDF CVs from uploaded DOCX/PDF files.

## Project Overview

**What it does:**
- Next.js chat interface for CV upload & processing
- Azure Functions extract photos, validate CV data, generate PDFs
- Multi-language support (EN, DE, PL)
- Playwright visual regression tests

**Tech stack:**
- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS
- Backend: Azure Functions, Python 3.11, WeasyPrint (PDF generation)
- Testing: Playwright (visual regression, artifacts in `test-results/`)
- AI: OpenAI GPT-4+ with tool calling (configured in OpenAI dashboard)

---

## Repository Structure

```
cv-generator-repo/
├── ui/                           # Next.js frontend
│   ├── app/
│   │   ├── page.tsx             # Chat interface, file upload
│   │   ├── api/process-cv/      # API route (tool orchestration)
│   │   └── layout.tsx           # Root layout
│   ├── lib/
│   │   ├── prompts.ts           # System prompt (for reference)
│   │   └── tools.ts             # Tool definitions (reference)
│   └── package.json
│
├── src/                          # Azure Functions (Python)
│   ├── extract-photo/           # Extract photo from DOCX → base64
│   ├── validate-cv/             # Validate CV structure
│   └── generate-cv-action/      # Generate 2-page PDF
│
├── templates/                    # CV template (HTML/CSS)
│   ├── CV_template_2pages_2025.spec.md
│   └── html/
│
├── tests/                        # Playwright tests
│   ├── test-cv-generation.spec.ts
│   └── generate_test_artifacts.py
│
├── AGENTS.md                     # Agent operating rules (general)
├── SYSTEM_PROMPT.md             # System prompt for OpenAI dashboard
├── PROMPT_INSTRUCTIONS.md       # Detailed workflow (upload to OpenAI)
├── TOOLS_CONFIG.md              # Tool JSON schemas for dashboard
├── requirements.txt             # Python dependencies
├── playwright.config.ts         # Playwright configuration
└── package.json                 # Root package.json (Playwright tests)
```

---

## How to Build & Test

### Frontend (Next.js)

```bash
cd ui
npm install                       # Install dependencies (do this first)
npm run dev                       # Start dev server (http://localhost:3000)
npm run build                     # Production build
npm run start                     # Run production build
npm run lint                      # Run ESLint
```

### Backend (Azure Functions — Python)

**Setup:**
```bash
pip install -r requirements.txt  # Install Python dependencies
# Set up local.settings.json with OPENAI_API_KEY and AZURE_FUNCTIONS_STORAGE_CONNECTION_STRING
```

**Test locally:**
```bash
func start                        # Start Azure Functions emulator (http://localhost:7071)
# Test endpoints:
# POST http://localhost:7071/api/validate-cv
# POST http://localhost:7071/api/generate-cv-action
# POST http://localhost:7071/api/extract-photo
```

### Tests (Playwright)

```bash
npm test                          # Run all tests (runs pretest: python tests/generate_test_artifacts.py)
npm run test:headed              # Run with visible browser
npm run test:ui                  # Interactive UI mode
npm run test:debug               # Debug mode
npm run show-report              # View HTML report (test-results/)
```

**Pre-test step:** `npm run pretest` runs `python tests/generate_test_artifacts.py` to generate test fixtures.

---

## Key Entry Points

### Frontend
- **Chat UI:** [ui/app/page.tsx](ui/app/page.tsx) — file upload, message loop
- **API orchestration:** [ui/app/api/process-cv/route.ts](ui/app/api/process-cv/route.ts) — calls OpenAI with tool definitions

### Backend
- **Function app:** [function_app.py](function_app.py) — Azure Functions router
- **Extract photo:** [src/extract-photo/](src/extract-photo/) → extracts photo from DOCX
- **Validate CV:** [src/validate-cv/](src/validate-cv/) → validates CV structure
- **Generate PDF:** [src/generate-cv-action/](src/generate-cv-action/) → renders 2-page PDF (WeasyPrint)

### Configuration
- **System prompt:** [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md) — paste into OpenAI dashboard
- **Tool definitions:** [TOOLS_CONFIG.md](TOOLS_CONFIG.md) — tool JSON schemas for dashboard
- **Workflow guide:** [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) — detailed instructions (upload to OpenAI)

---

## OpenAI Dashboard Configuration

The CV Generator uses OpenAI tool calling. **Setup (one-time):**

1. Go to https://platform.openai.com/assistants
2. Create or edit a prompt/assistant
3. **System Prompt:** Copy content from [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md)
4. **Tools:** Add 3 functions from [TOOLS_CONFIG.md](TOOLS_CONFIG.md):
   - `extract_photo` (extracts photo from DOCX)
   - `validate_cv` (validates CV structure)
   - `generate_cv_action` (generates PDF)
5. **Knowledge file:** Upload [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md)
6. **Model:** Use GPT-4 or higher

---

## Important Files & Config

| File | Purpose | Edit? |
|------|---------|-------|
| `function_app.py` | Azure Functions router | ✅ For new endpoints/changes |
| `local.settings.json` | Local secrets (DO NOT COMMIT) | ⛔ Use `local.settings.template.json` as reference |
| `local.settings.template.json` | Template for secrets | ✅ Document structure, not values |
| `ui/.env.local` | Frontend env vars (DO NOT COMMIT) | ⛔ Use for local dev only |
| `requirements.txt` | Python dependencies | ✅ Update when adding packages |
| `ui/package.json` | Node dependencies | ✅ Update when adding packages |
| `TOOLS_CONFIG.md` | Tool JSON for OpenAI | ⛔ Don't edit; regenerate if schema changes |

---

## Common Commands for Agents

### Quick Status Check
```bash
# Frontend
cd ui && npm run lint && npm run build

# Backend
pip list | grep -E "(azure|jinja2|weasyprint|flask|python-docx)"

# Tests
npm test 2>&1 | tail -20
```

### Dev Workflow
```bash
# Terminal 1: Frontend dev
cd ui && npm run dev

# Terminal 2: Backend (if running locally)
func start

# Terminal 3: Run tests
npm test --headed
```

### Before Commit
```bash
git status -sb
git diff --stat
npm run lint
npm test
```

---

## Validation Checklist Before PR

- [ ] Frontend lints: `cd ui && npm run lint`
- [ ] Frontend builds: `cd ui && npm run build`
- [ ] Tests pass: `npm test`
- [ ] No secrets in `local.settings.json` or `ui/.env.local`
- [ ] Python dependencies match `requirements.txt`
- [ ] No `TBD`, `TODO`, or placeholder values in code
- [ ] Changes don't touch unrelated code (no accidental refactors)

---

## Troubleshooting

**"Cannot find module" in Next.js:**
```bash
cd ui && npm install && npm run build
```

**Python import error (azure-functions, weasyprint, etc.):**
```bash
pip install -r requirements.txt
```

**Playwright tests fail:**
```bash
npm run pretest  # Generate test artifacts
npm test --headed  # Run with visible browser to debug
```

**Local.settings.json missing or invalid:**
```bash
# Reference structure in local.settings.template.json
cp local.settings.template.json local.settings.json
# Edit with your actual values (OPENAI_API_KEY, AZURE_FUNCTIONS_STORAGE_CONNECTION_STRING)
```

---

## Trust the Instructions

- Refer to [AGENTS.md](AGENTS.md) for agent operating rules (plan discipline, Unknown Sea protocol, efficiency guard).
- Refer to [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) for detailed CV processing workflow.
- Only search/explore if you suspect these documents are incomplete or incorrect.
- **Don't invent results** — if blocked, ask for the smallest missing artifact.

