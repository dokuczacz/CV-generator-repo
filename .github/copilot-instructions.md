# CV Generator — Copilot Instructions (Lean)

This repository is a Next.js 14 UI + Azure Functions (Python) backend that generates ATS‑compliant, 2‑page PDF CVs from uploaded DOCX/PDF files.

For agent behavior rules, see `AGENTS.md` (kept intentionally short).

## LLM / Orchestration (read-first)

Follow `.github/instructions/llm-orchestration.instructions.md` for risk controls (mocking/gating), JSON contracts, and the LLM test pyramid.

## Key Entry Points

Frontend:
- Chat UI: `ui/app/page.tsx`
- Orchestration route: `ui/app/api/process-cv/route.ts`

Backend:
- Azure Functions router: `function_app.py`
- Functions: `src/extract-photo/`, `src/validate-cv/`, `src/generate-cv-action/`

## How to Build & Test (copy/paste)

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

Pre-test step: `npm run pretest` runs `python tests/generate_test_artifacts.py` to generate fixtures.

## Deeper docs (when needed)
- Orchestration notes: `ORCHESTRATION.md`
- OpenAI prompt/workflow: `SYSTEM_PROMPT.md`, `PROMPT_INSTRUCTIONS.md`, `TOOLS_CONFIG.md`
- Template spec: `templates/CV_template_2pages_2025.spec.md`
cp local.settings.template.json local.settings.json
# Edit with your actual values (OPENAI_API_KEY, AZURE_FUNCTIONS_STORAGE_CONNECTION_STRING)
```

---

## Trust the Instructions

- Refer to [AGENTS.md](AGENTS.md) for agent operating rules (plan discipline, Unknown Sea protocol, efficiency guard).
- Refer to [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) for detailed CV processing workflow.
- Only search/explore if you suspect these documents are incomplete or incorrect.
- **Don't invent results** — if blocked, ask for the smallest missing artifact.

