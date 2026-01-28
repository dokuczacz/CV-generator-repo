# Copilot Agent Quickstart (VS Code)

**Note:** This file is not auto-loaded; reference it when you need Copilot-specific features.

## Context Mentions

Use `#` to add context to your Copilot prompt:
- `#codebase` — full workspace context (architecture questions)
- `#file <path>` — specific file
- `#terminalSelection` — terminal output
- `#selection` — current editor selection

**Example:** `#file src/function_app.py Generate a test for this endpoint`

## Agent Modes

- **Agent** — autonomous (default, uses all tools)
- **Plan** — read-only planning
- **Ask** — conversational only
- **Edit** — inline refactoring

Switch mode with `/mode plan` or similar commands.

## Tool Management

- VS Code agents can use up to 128 tools per request
- If too many tools enabled → deselect unused servers in tool picker
- Group related tools into **tool sets** for cleaner UI

## MCP Tools (when available)

Reference tools explicitly:
- `#tool:githubRepo` — search GitHub repositories
- `#tool:azureResources` — query Azure resources
- `#tool:fetchWebpage` — pull live docs

**Example:** `#tool:githubRepo Find similar CV generation projects`

## Best Practices

1. Use `#terminalSelection` to share command output instead of copying text
2. Use `#file` to add specific context before asking for changes
3. Keep prompts focused (hot_only mode) unless you need architecture-level reasoning
4. Prefer deterministic checks over broad scans
