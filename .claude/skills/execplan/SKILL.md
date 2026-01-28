---
name: execplan
description: Create and maintain execution plan files in tmp/ to reduce chat context for multi-step tasks
argument-hint: [task-name]
disable-model-invocation: true
---

# execplan

Create a living execution plan document that keeps the conversation thread short.

## Usage

Invoke this skill when:
- Task has >3 steps
- Implementation will span multiple turns
- Context is getting long and needs offloading

```
/execplan cv_validation
/execplan pdf_generation_fix
```

The skill creates `tmp/$ARGUMENTS_execplan.md` with a structured plan template.

## Plan structure

The generated plan file includes:

```markdown
# Goal
One sentence describing what we're building/fixing.

# Acceptance Criteria
Observable behavior with exact verification commands:
- [ ] `npm test -- cv-visual.spec.ts` passes
- [ ] PDF size < 2 pages
- [ ] Visual diff < 5% threshold

# Plan
1. [ ] Smallest next step
2. [ ] Second step
3. [ ] Third step

# Commands
Exact commands with working directory and expected output.

# Validation
How to verify success (tests, manual checks).

# Recovery
Idempotence notes, rollback commands, retry steps.

# Notes
Append-only log of decisions and rationale with timestamps.
```

## Working with plans

**Update as you go:**
- Mark steps `[x]` when completed
- Mark steps `[!]` if blocked
- Append decisions to Notes section with date

**Link in responses:**
Use markdown links: [tmp/cv_validation_execplan.md](tmp/cv_validation_execplan.md)

**Summarize deltas:**
Don't paste the full plan into chat - only summarize what changed.

## Pre-agent gate for AI integration

If the plan involves OpenAI/Claude integration:
- Add acceptance criterion: "Backend dry-run passes (no agent connected)"
- Verify orchestration works before connecting the model
- This prevents debugging agent issues vs backend issues simultaneously

## Safety

- No secrets in plan files (use env var names: `OPENAI_API_KEY`)
- Plans are working files - they don't replace git commits or documentation
- Safe to delete and regenerate if plan becomes stale

## Examples

See [.claude/workflows/execplan-examples.md](.claude/workflows/execplan-examples.md) for complete workflow examples.