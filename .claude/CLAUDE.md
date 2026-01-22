# CV Generator - Claude Code Context

Welcome to the CV Generator project. This file auto-loads into every Claude conversation to provide essential context.

---

## What This Project Does

Generates ATS-compliant, 2-page PDF CVs from uploaded DOCX/PDF files via a Next.js chat interface backed by Azure Functions (Python).

**Key workflow:** Upload CV → Extract data → Validate schema → Generate 2-page PDF → Visual regression test

---

## Tech Stack

**Frontend:**
- Next.js 14 + React 18 + TypeScript + Tailwind CSS
- Chat interface: [ui/app/page.tsx](ui/app/page.tsx)
- API orchestration: [ui/app/api/process-cv/route.ts](ui/app/api/process-cv/route.ts)

**Backend:**
- Azure Functions (Python 3.11)
- Function router: [function_app.py](function_app.py)
- PDF generation: WeasyPrint
- Photo extraction: python-docx

**Testing:**
- Playwright visual regression (baselines in `test-results/`)
- Test runner: `npm test`

**AI Integration:**
- OpenAI GPT-4+ with tool calling
- Tools: extract_photo, validate_cv, generate_cv_action

---

## Essential Commands

### Development
```bash
# Frontend dev server
cd ui && npm run dev         # http://localhost:3000

# Backend (Azure Functions)
func start                   # http://localhost:7071

# Install dependencies
cd ui && npm install
pip install -r requirements.txt
```

### Testing
```bash
# Run all Playwright tests
npm test                     # Generates test artifacts first

# Interactive/headed modes
npm run test:headed
npm run test:ui

# View test report
npm run show-report
```

### Build & Validation
```bash
# Frontend build
cd ui && npm run build
cd ui && npm run lint

# Python smoke tests
python scripts/smoke_local_session.py
pwsh scripts/smoke_prod.ps1
```

---

## File Organization

### Key Entry Points
- **Chat UI:** [ui/app/page.tsx](ui/app/page.tsx)
- **API route:** [ui/app/api/process-cv/route.ts](ui/app/api/process-cv/route.ts)
- **Azure Functions:** [function_app.py](function_app.py)
- **CV template:** [templates/html/cv_template_2pages_2025.html](templates/html/cv_template_2pages_2025.html)

### Configuration Files
- **OpenAI setup:** [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md), [TOOLS_CONFIG.md](TOOLS_CONFIG.md)
- **Workflow guide:** [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md)
- **Data schema:** [DATA_DICTIONARY.md](DATA_DICTIONARY.md)

### DO NOT COMMIT
- `local.settings.json` (use `local.settings.template.json` as reference)
- `ui/.env.local`
- Any file with secrets/API keys

---

## Claude-Specific Workflow Patterns

### Test-Driven Development (Preferred)
When implementing new features:
1. Write failing test first based on expected behavior
2. Run test to verify failure
3. Implement minimal code to pass test
4. Refactor while keeping tests green
5. Commit with meaningful message

**Example:**
```bash
# Add test for new validation rule
# File: tests/test_schema_validator.py
def test_photo_url_size_limit():
    assert validate_photo_url_size("data:image/png;base64,..." * 50000) == False

# Run test (should fail)
pytest tests/test_schema_validator.py::test_photo_url_size_limit -v

# Implement validation
# File: src/schema_validator.py
def validate_photo_url_size(photo_url, max_bytes=32000):
    # Implementation here
    pass

# Re-run test (should pass)
pytest tests/test_schema_validator.py::test_photo_url_size_limit -v
```

### Visual Iteration for Template Changes
When updating CV templates:
1. Edit CSS/HTML in [templates/html/](templates/html/)
2. Generate preview via API
3. Use Playwright to screenshot preview
4. Compare with baseline
5. Iterate until pixel-perfect

### Extended Thinking Modes
Use thinking modes for complex tasks:
- **"think"** - Standard complexity (schema validation)
- **"think hard"** - Complex logic (layout calculations, multi-language edge cases)
- **"ultrathink"** - Critical decisions (architecture changes, security reviews)

---

## Code Style Guidelines

### TypeScript
- Strict mode enabled
- Explicit return types for functions
- No `any` types unless absolutely necessary
- Use functional components with hooks

### Python
- Type hints for function signatures
- Docstrings for public functions (not private helpers)
- Use pathlib for file operations
- Follow Azure Functions patterns

### General
- Keep functions small and focused
- Prefer composition over inheritance
- Write self-documenting code (clear names > comments)
- Add comments only for "why", not "what"

---

## Git Etiquette

### Commits
- Meaningful commit messages (conventional commits style)
- Include Co-Authored-By trailer:
  ```
  feat: add photo URL size validation

  Validate that photo URLs don't exceed 32KB to prevent
  Azure Table Storage property limit errors.

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
  ```

### Before Committing
```bash
# Check status
git status -sb

# Lint frontend
cd ui && npm run lint

# Run tests
npm test

# Verify no secrets
git diff --cached | grep -i "api_key\|secret\|password\|connection"
```

### Branch Workflow
- Main branch: `main`
- No force push to main
- Create feature branches for new work
- Run tests before creating PRs

---

## MCP Servers (Available Tools)

### Filesystem
Access project files with progressive disclosure.
```
npx -y @modelcontextprotocol/server-filesystem "c:\AI memory\CV-generator-repo"
```

### Azure Blob Storage
Query Azurite (local) or production blob storage.
```
Subscription: 3bb75fb7-e75f-4e75-8ff0-473d72d82c79
Tenant: dbb16708-62b5-4835-bc82-46b38d1a71d3
```

### GitHub
Interact with issues, PRs, commits.
```
Requires GITHUB_TOKEN env var
```

### Playwright
Browser automation for visual regression tests.
```
npx -y @modelcontextprotocol/server-playwright
```

### OpenAI Developer Docs
Query OpenAI documentation.
```
https://developers.openai.com/mcp
```

---

## Custom Slash Commands

Use these shortcuts for common workflows:

- **/validate-cv** - Validate CV JSON against schema
- **/visual-regression** - Run visual tests and compare baselines
- **/multi-claude-review** - Launch parallel Claude for code review

See [.claude/commands/](.claude/commands/) for implementation details.

---

## Environment Variables

Required in `local.settings.json` (local dev) or Azure App Settings (production):

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "OPENAI_API_KEY": "sk-...",
    "STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=https;..."
  }
}
```

---

## Session Storage (Phase 1-3 Implementation)

**Current state:** Session-based workflow implemented (Phase 1-3 complete)

**Key files:**
- [src/blob_store.py](src/blob_store.py) - Session storage operations
- [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) - Current deployment state
- [SESSION_STATUS_2026_01_21.md](SESSION_STATUS_2026_01_21.md) - Handoff snapshot

**Session flow:**
1. User uploads CV → creates session in Azure Table Storage
2. Each step updates session state (uploaded → validated → generated)
3. Session persists across browser reloads
4. PDF/HTML stored in blob storage, referenced by session

---

## Common Gotchas

### Azure Table Storage Limits
- Property size: 64KB max
- Photo URLs must be <32KB (base64-encoded)
- Use blob storage for large data

### WeasyPrint CSS Quirks
- Limited CSS support (no Grid, limited Flexbox)
- Use float-based layouts for compatibility
- Test across template languages (EN/DE/PL)

### Playwright Visual Regression
- Baselines stored in `test-results/`
- Update baselines intentionally with `npm test -- --update-snapshots`
- 5% diff threshold (configurable in `playwright.config.ts`)

---

## Troubleshooting

**"Cannot find module" in Next.js:**
```bash
cd ui && rm -rf node_modules package-lock.json
npm install
```

**Azure Functions not starting:**
```bash
# Check Python version (must be 3.11)
python --version

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**Tests failing:**
```bash
# Regenerate test artifacts
npm run pretest

# Run headed to debug
npm run test:headed
```

**Photo extraction fails:**
```bash
# Verify DOCX structure
python -c "from docx import Document; doc = Document('sample.docx'); print([r._element.xml for r in doc.part.rels.values()])"
```

---

## References

**Project Documentation:**
- [AGENTS.md](AGENTS.md) - Agent operating rules (general, applies to Codex)
- [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) - CV processing workflow
- [DATA_DICTIONARY.md](DATA_DICTIONARY.md) - Full schema reference
- [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) - Deployment state

**GitHub Copilot Users:**
- See [.github/copilot-instructions.md](.github/copilot-instructions.md) for Copilot-specific guidance

**Codex Users:**
- See [AGENTS.md](AGENTS.md) for Codex agent rules and omniflow skills

**Claude Code Users:**
- You're reading the right file!
- See [.claude/commands/](.claude/commands/) for custom workflows
- See [.claude/skills/](.claude/skills/) for domain-specific skills (Phase 2)

---

## Key Principles

1. **Test before commit** - Always run `npm test` and `cd ui && npm run lint`
2. **No secrets in code** - Use environment variables
3. **Preserve user data** - Never fabricate CV content
4. **2-page constraint** - CVs must fit strict template (see [templates/html/CV_template_2pages_2025.spec.md](templates/html/CV_template_2pages_2025.spec.md))
5. **Think before coding** - Use extended thinking for complex problems
6. **Verify visually** - Run visual regression tests for template changes

---

**Last updated:** 2026-01-22
**Claude Code version:** Compatible with Claude Sonnet 4.5+