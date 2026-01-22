# Claude Code Configuration

This directory contains Claude Code-specific configuration and resources.

---

## Quick Start

### 1. Auto-Context
**[CLAUDE.md](CLAUDE.md)** is automatically loaded into every Claude conversation.

No action needed - just start chatting with Claude Code!

### 2. Custom Slash Commands
Use these shortcuts for common workflows:

- `/validate-cv` - Validate CV JSON against schema
- `/visual-regression` - Run visual regression tests
- `/multi-claude-review` - Launch parallel code review

**Implementation:** See [commands/](commands/) directory

### 3. MCP Servers
Claude Code can access external tools via Model Context Protocol (MCP).

**Configured servers** (see [../.vscode/mcp.json](../.vscode/mcp.json)):
- ✅ OpenAI Developer Docs (HTTP)
- ✅ Filesystem (stdio)
- ✅ Playwright (stdio)
- ✅ GitHub (stdio) - requires `GITHUB_TOKEN`
- ✅ Azure Blob Storage (stdio) - requires `AZURE_STORAGE_CONNECTION_STRING`

**Setup required:**
```powershell
# Set environment variables (PowerShell)
$env:GITHUB_TOKEN = "ghp_your_token_here"
$env:AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;..."

# Or add to .env file (DO NOT COMMIT)
echo "GITHUB_TOKEN=ghp_..." >> .env
echo "AZURE_STORAGE_CONNECTION_STRING=..." >> .env
```

---

## Directory Structure

```
.claude/
├── CLAUDE.md                    # Auto-loaded context (✅ Complete)
├── README.md                    # This file
├── commands/                    # Custom slash commands
│   ├── validate-cv.md           # CV validation workflow
│   ├── visual-regression.md     # Visual testing workflow
│   └── multi-claude-review.md   # Parallel review workflow
└── skills/                      # Claude Agent Skills (Phase 2)
    ├── cv-validation/           # CV validation skill
    └── pdf-generation/          # PDF generation skill
```

---

## File Descriptions

### CLAUDE.md (Auto-Context)
**Purpose:** Loaded automatically at conversation start
**Size:** ~450 lines (~3500 tokens)
**Content:**
- Project overview
- Tech stack
- Essential commands
- Code style guidelines
- Git etiquette
- MCP servers reference
- Common gotchas

**Edit when:** Project structure changes, new tools added, key commands updated

**Keep concise:** Every line costs tokens. Challenge: "Does Claude really need this?"

---

### Custom Slash Commands

**Location:** [commands/](commands/)
**Format:** Markdown files with workflow instructions
**Usage:** `/command-name <arguments>`

#### validate-cv.md
**Purpose:** Validate CV JSON and generate preview
**Workflow:**
1. Load CV data (file or inline JSON)
2. Pre-validate locally (required fields, size constraints)
3. Call API validation endpoint
4. Generate preview HTML
5. Optional: Screenshot with Playwright

**Key features:**
- Two-tier validation (fast local + comprehensive API)
- Visual preview before PDF generation
- Error reporting with suggested fixes

#### visual-regression.md
**Purpose:** Run Playwright visual tests
**Workflow:**
1. Generate test artifacts (EN/DE/PL CVs)
2. Run Playwright tests
3. Compare screenshots with baselines
4. Display diffs if >5% difference
5. Accept baselines or investigate

**Key features:**
- Multi-language testing (EN/DE/PL)
- Pixel-perfect comparison
- Diff visualization with Playwright MCP
- Baseline management

#### multi-claude-review.md
**Purpose:** Parallel code review (Phase 3 advanced)
**Workflow:**
1. Save current context
2. Launch background Claude instance
3. Continue main work
4. Merge review feedback when complete

**Key features:**
- Non-blocking review process
- Focus areas: security, performance, type-safety
- TDD-based fix workflow
- Git worktree alternative if CLI unavailable

---

### Claude Agent Skills (Phase 2)

**Location:** [skills/](skills/)
**Format:** SKILL.md + bundled resources (scripts, references, assets)

#### Skills Structure
```
skills/
├── cv-validation/
│   ├── SKILL.md                 # Skill definition (triggers, workflow)
│   ├── scripts/
│   │   ├── validate_schema.py   # Deterministic validation
│   │   └── count_template_space.py
│   └── references/
│       ├── DATA_DICTIONARY.md   # Schema reference
│       └── ATS_COMPLIANCE.md    # ATS requirements
└── pdf-generation/
    ├── SKILL.md
    ├── scripts/
    │   └── print_pdf_playwright.mjs
    └── references/
        ├── TEMPLATE_SPEC.md     # 2-page constraints
        └── WEASYPRINT_QUIRKS.md # CSS compatibility
```

**Progressive disclosure:**
1. **Metadata** (name + description) - Always in context
2. **SKILL.md body** - Loaded when skill triggers
3. **Bundled resources** - Loaded as needed

---

## MCP Server Details

### Filesystem Server
**Package:** `@modelcontextprotocol/server-filesystem`
**Type:** stdio
**Purpose:** Read/write project files with progressive disclosure
**Scope:** `c:\AI memory\CV-generator-repo`

**Use cases:**
- Navigate codebase hierarchically
- Load skill resources on-demand
- Unbounded context via lazy loading

### Playwright Server
**Package:** `@modelcontextprotocol/server-playwright`
**Type:** stdio
**Purpose:** Browser automation and screenshot comparison

**Use cases:**
- Visual regression testing
- Screenshot preview HTML
- Compare baseline images
- Debug layout issues

### GitHub Server
**Package:** `@modelcontextprotocol/server-github`
**Type:** stdio
**Requires:** `GITHUB_TOKEN` environment variable

**Use cases:**
- Create/update issues
- Manage pull requests
- Query commit history
- Search repositories

**Setup:**
```powershell
# Create GitHub token: https://github.com/settings/tokens
# Scopes: repo, workflow

$env:GITHUB_TOKEN = "ghp_your_token_here"
```

### Azure Blob Storage Server
**Package:** `@azure/mcp-server-blob`
**Type:** stdio
**Requires:** `AZURE_STORAGE_CONNECTION_STRING` environment variable

**Use cases:**
- Query blob storage (Azurite local or production)
- Download sample CVs
- Check session storage
- Compare local vs production data

**Setup:**
```powershell
# Get connection string from local.settings.json
$env:AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=..."
```

---

## Environment Variables

**Required for MCP servers:**

```powershell
# GitHub (optional, for GitHub server)
$env:GITHUB_TOKEN = "ghp_..."

# Azure Blob Storage (optional, for Azure server)
$env:AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;..."

# Verify
echo $env:GITHUB_TOKEN
echo $env:AZURE_STORAGE_CONNECTION_STRING
```

**Alternative: .env file**
```bash
# .env (DO NOT COMMIT - already in .gitignore)
GITHUB_TOKEN=ghp_...
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
```

---

## Testing MCP Servers

### Test Filesystem Server
```
Ask Claude: "List all files in the templates/ directory using the filesystem MCP"
```

Expected: Claude uses filesystem server to navigate and list files

### Test Playwright Server
```
Ask Claude: "Take a screenshot of tmp/preview_d03cf26e.html using Playwright"
```

Expected: Claude uses Playwright server to generate screenshot

### Test GitHub Server
```
Ask Claude: "List recent commits on this repo using the GitHub MCP"
```

Expected: Claude uses GitHub server to query commit history

### Test Azure Blob Server
```
Ask Claude: "Count blobs in the 'sessions' container using the Azure Blob MCP"
```

Expected: Claude uses Azure Blob server to query blob storage

---

## Troubleshooting

### CLAUDE.md not loading
**Symptom:** Claude doesn't have project context
**Fix:** Ensure CLAUDE.md exists in `.claude/` directory. Claude Code auto-loads it at conversation start.

### Slash commands not working
**Symptom:** `/validate-cv` not recognized
**Fix:** Ensure command files exist in `.claude/commands/`. Use exact filenames (e.g., `validate-cv.md` not `validate_cv.md`)

### MCP server connection failed
**Symptom:** "Could not connect to MCP server: playwright"
**Fix:**
1. Check `mcp.json` syntax (valid JSON)
2. Verify `npx` is available: `npx --version`
3. Test package availability: `npx -y @modelcontextprotocol/server-playwright --help`

### Environment variable not found
**Symptom:** "GITHUB_TOKEN is not set"
**Fix:**
```powershell
# Set in current session
$env:GITHUB_TOKEN = "ghp_..."

# Or add to PowerShell profile for persistence
Add-Content $PROFILE '$env:GITHUB_TOKEN = "ghp_..."'
```

### Skills not triggering
**Symptom:** Claude doesn't use cv-validation skill
**Fix:**
1. Ensure SKILL.md has proper YAML frontmatter
2. Check `description` field is comprehensive
3. Verify skill directory name matches skill name in frontmatter

---

## Phase Implementation Status

- ✅ **Phase 1: Foundation** (Complete)
  - ✅ `.claude/` directory structure
  - ✅ CLAUDE.md auto-context
  - ✅ Custom slash commands (3)
  - ✅ MCP servers configured (5)

- ⏳ **Phase 2: Skills Migration** (In Progress)
  - ⏳ cv-validation skill
  - ⏳ pdf-generation skill

- 📋 **Phase 3: Advanced Workflows** (Planned)
  - 📋 Multi-Claude workflows documented
  - 📋 Visual iteration workflow
  - 📋 Headless CI/CD integration

---

## Additional Resources

**Claude Code Documentation:**
- [VS Code Extension Guide](https://code.claude.com/docs/en/vs-code)
- [Claude Cookbook](https://platform.claude.com/cookbook/)
- [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

**MCP Protocol:**
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Servers Directory](https://github.com/modelcontextprotocol/servers)

**Project Documentation:**
- [AGENTS.md](../AGENTS.md) - Codex agent rules
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) - Copilot instructions
- [README.md](../README.md) - Project README

---

**Last updated:** 2026-01-22
**Maintained by:** Claude Sonnet 4.5
