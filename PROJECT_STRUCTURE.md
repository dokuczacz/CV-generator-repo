# Project Structure - Clean Organization

## Active Files (Production)

### Core Configuration
```
README.md                    # Main documentation (setup, usage, architecture)
SYSTEM_PROMPT.md            # System prompt for OpenAI dashboard
PROMPT_INSTRUCTIONS.md      # Knowledge file for prompt (detailed workflow)
TOOLS_CONFIG.md             # 3 tools JSON definitions for dashboard
```

### Frontend (Next.js)
```
ui/
├── app/
│   ├── page.tsx                    # Chat interface with file upload
│   ├── api/process-cv/route.ts     # Tool orchestration endpoint
│   ├── layout.tsx                  # Root layout
│   └── globals.css                 # Global styles
├── lib/
│   ├── prompts.ts                  # CV_SYSTEM_PROMPT
│   ├── tools.ts                    # Tool definitions (reference)
│   └── utils.ts                    # PDF download helper
├── package.json                    # Dependencies
└── .env.local                      # Environment variables (not in git)
```

### Backend (Azure Functions - Python)
```
src/
├── extract-photo/
│   ├── __init__.py                 # Extract photo from DOCX
│   └── function.json
├── validate-cv/
│   ├── __init__.py                 # Validate CV structure
│   └── function.json
└── generate-cv-action/
    ├── __init__.py                 # Generate 2-page PDF
    └── function.json

function_app.py                     # Azure Functions entry point
requirements.txt                    # Python dependencies
host.json                           # Azure Functions config
local.settings.json                 # Local dev settings (not in git)
```

### CV Template
```
templates/
├── CV_template_2pages_2025.spec.md  # Template specification
└── html/
    ├── cv_template_2pages_2025.html # HTML structure
    └── cv_template_2pages_2025.css  # Styles (Swiss layout)
```

### Testing & Samples
```
samples/                    # Sample CV files for testing
tests/                      # E2E tests (Playwright)
scripts/                    # Utility scripts
```

---

## Archive (Moved to archive/)

### Old Documentation
- CUSTOM_GPT_*.md - Custom GPT instructions (replaced by SYSTEM_PROMPT)
- INTEGRATION_GUIDE.md - Custom GPT integration (no longer needed)
- UPLOAD_PACKAGE.md - Custom GPT setup (obsolete)
- UI_MIGRATION_PLAN.md - Migration notes (completed)
- UI_IMPLEMENTATION_COMPLETE.md - Implementation report (completed)
- TEST_REPORT.md - Old test results
- TESTING*.md - Old testing strategies
- IMPLEMENTATION_COMPLETE.md - Old milestones
- IMPROVEMENT_PLAN.md - Old plans
- PHASED_IMPLEMENTATION.md - Old phases
- PLANNING_SUMMARY.md - Old planning docs
- PACKAGE_SUMMARY.md - Old package docs
- VIOLATIONS_AND_FIXES.md - Old debugging
- SYSTEM_SUMMARY.md - Old system docs
- QUICK_START.md - Replaced by new README
- README_OLD.md - Old README

### Azure/Deployment Docs
- AZURE_*.md - Old Azure setup docs
- DEPLOYMENT_*.md - Old deployment guides
- DETAILED_PLANNING.md - Old planning
- ENDPOINT_TESTING_REPORT.md - Old test reports
- FINAL_PROCESS.md - Old process docs
- GOLDEN_RULES.md - Old rules
- GPT_SYSTEM_PROMPT.md - Old prompt
- openapi_cv_actions.yaml - Custom GPT actions schema
- setup-azure.ps1 - Old setup script

### Test Artifacts
- *.pdf - Test PDF outputs
- cv-generator-publish-profile.xml - Azure publish profile
- extracted_images_from_pdf/ - Test images
- wzory/ - Old template files

---

## Current Architecture Summary

**What changed:**
- ❌ Custom GPT → ✅ OpenAI Prompt with tools (dashboard)
- ❌ Actions schema → ✅ Tool calling (function definitions)
- ❌ Custom GPT instructions → ✅ SYSTEM_PROMPT.md + PROMPT_INSTRUCTIONS.md
- ❌ Hardcoded model config → ✅ Dashboard configuration
- ❌ Backend generates PDF directly → ✅ Tool orchestration (extract → validate → generate)

**What stayed:**
- ✅ Azure Functions backend (Python)
- ✅ WeasyPrint PDF rendering
- ✅ Swiss template (2-page, ATS-compliant)
- ✅ Multi-language support (EN/DE/PL)
- ✅ Photo extraction from DOCX

**New features:**
- ✅ Chat interface (Next.js UI)
- ✅ Tool calling workflow
- ✅ Real-time conversation with AI
- ✅ Prompt stored in dashboard (not code)
- ✅ Orchestrated multi-step processing

---

## Quick Reference

**Start development:**
```bash
cd ui
npm run dev
# Opens http://localhost:3000
```

**Configure OpenAI:**
1. Copy `SYSTEM_PROMPT.md` to dashboard "System Prompt"
2. Upload `PROMPT_INSTRUCTIONS.md` as knowledge file
3. Add 3 tools from `TOOLS_CONFIG.md`

**Deploy frontend:**
```bash
cd ui
vercel deploy --prod
```

**Deploy backend:**
Already deployed at: https://cv-generator-6695.azurewebsites.net

---

**Status:** ✅ Production-ready, clean structure, archived legacy docs
