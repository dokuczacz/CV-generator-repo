# Claude Code Token Optimization - Implementation Summary

**Date:** 2026-01-27
**Goal:** Reduce token consumption by 60% through Codex-inspired patterns and Claude Code best practices

---

## Problem

Claude Code (Opus) was consuming 5-6x more tokens than Codex for same work:
- CLAUDE.md: 379 lines (~10KB, ~2,500 tokens per message)
- No skills architecture (everything in one file)
- Using most expensive model (Opus 4.5) by default

---

## Solution Implemented

### 1. Trimmed CLAUDE.md: 60% Reduction

**Before:** 379 lines
**After:** 150 lines
**Savings:** ~1,500 tokens per message

Changes:
- Moved troubleshooting → [.claude/TROUBLESHOOTING.md](.claude/TROUBLESHOOTING.md)
- Moved git workflow → [.claude/GIT_GUIDE.md](.claude/GIT_GUIDE.md)
- Moved code style → [.claude/CODE_STYLE.md](.claude/CODE_STYLE.md)
- Removed verbose examples
- Kept only essential context Claude can't infer from code

### 2. Skills Architecture

Created 3 Codex-inspired skills following Claude Code best practices:

#### [.claude/skills/execplan/SKILL.md](.claude/skills/execplan/SKILL.md)
- **Purpose:** Offload multi-step plans to `tmp/*.md` files
- **Trigger:** `/execplan [task]` (manual invocation only)
- **Benefit:** Keeps conversation thread short, survives compaction
- **Size:** 86 lines (vs embedded in CLAUDE.md)

#### [.claude/skills/stall-escalation/SKILL.md](.claude/skills/stall-escalation/SKILL.md)
- **Purpose:** Stop and ask when blocked (Split vs Escalate pattern)
- **Trigger:** Claude loads automatically when detecting blockers
- **Benefit:** Prevents wasted turns on wrong assumptions
- **Size:** 135 lines (reference material, not loaded every turn)

#### [.claude/skills/progress-tracker/SKILL.md](.claude/skills/progress-tracker/SKILL.md)
- **Purpose:** Strict progress tables with verified numbers only
- **Trigger:** User asks for status/progress, or `/progress-tracker`
- **Benefit:** No placeholder data, source attribution required
- **Size:** 107 lines

**Key changes from Codex patterns:**
- Removed Codex-specific terminology ("Mode: replace", "Composition")
- Added Claude Code frontmatter (`disable-model-invocation`, `user-invocable`)
- Simplified to under 500 lines per skill
- No HTML skill markers (Claude Code doesn't need them)

### 3. Model Selection Guide

Created [.claude/MODEL_SELECTION.md](.claude/MODEL_SELECTION.md) documenting:
- **Haiku:** 60x cheaper than Opus (file searches, status checks, simple edits)
- **Sonnet:** 5x cheaper than Opus (most coding tasks - **recommended default**)
- **Opus:** Most expensive (architecture, security, complex debugging only)

**Action required:** Start Claude with `claude --model sonnet` instead of default Opus

### 4. Supporting Documentation

Created on-demand reference files:
- [.claude/TROUBLESHOOTING.md](.claude/TROUBLESHOOTING.md) - Common fixes
- [.claude/GIT_GUIDE.md](.claude/GIT_GUIDE.md) - Git workflow & safety
- [.claude/CODE_STYLE.md](.claude/CODE_STYLE.md) - Code conventions
- [.claude/MODEL_SELECTION.md](.claude/MODEL_SELECTION.md) - Model cost/capability guide

---

## Expected Savings

### Per-Message Token Reduction

| Component | Before | After | Savings |
|-----------|--------|-------|---------|
| CLAUDE.md | 2,500 tokens | 1,000 tokens | **60%** |
| Skills (loaded on-demand) | N/A (embedded) | 0-500 tokens | **Context-aware loading** |
| Total per message | ~2,500 tokens | ~1,000-1,500 tokens | **40-60%** |

### Model Cost Reduction (if switching to Sonnet)

| Scenario | Opus Cost | Sonnet Cost | Savings |
|----------|-----------|-------------|---------|
| Input (50K tokens) | $0.75 | $0.15 | **80%** |
| Output (10K tokens) | $0.75 | $0.15 | **80%** |
| **Total session** | **$1.50** | **$0.30** | **80%** |

### Combined Optimization

Using **Sonnet + Trimmed CLAUDE.md**:
- Token overhead: 60% reduction (CLAUDE.md trim)
- Model cost: 80% reduction (Opus → Sonnet)
- **Total effective savings: ~85-90%** for typical coding sessions

---

## How to Use

### Start New Sessions with Sonnet

```bash
# Instead of:
claude

# Use:
claude --model sonnet
```

### Use Skills

```bash
# Create execution plan
/execplan cv_validation

# Check progress
/progress-tracker

# Skills load automatically when Claude detects relevant context
```

### Load Extended Context On-Demand

```
Read .claude/TROUBLESHOOTING.md for Azure Functions issue
```

Claude will load only when needed instead of every message.

---

## Files Changed

```
.claude/
├── CLAUDE.md (379 → 150 lines, -60%)
├── CODE_STYLE.md (NEW)
├── GIT_GUIDE.md (NEW)
├── MODEL_SELECTION.md (NEW)
├── OPTIMIZATION_SUMMARY.md (NEW, this file)
├── TROUBLESHOOTING.md (NEW)
└── skills/
    ├── execplan/
    │   └── SKILL.md (NEW, 86 lines)
    ├── progress-tracker/
    │   └── SKILL.md (NEW, 107 lines)
    └── stall-escalation/
        └── SKILL.md (NEW, 135 lines)
```

---

## Next Steps

1. **Test the new structure** with a typical task
2. **Start using Sonnet** by default (`claude --model sonnet`)
3. **Use Opus selectively** for architecture/security only
4. **Monitor token usage** - should see 60% reduction per message
5. **Refine skills** based on usage patterns

---

## Validation

To verify optimization is working:

```bash
# Check CLAUDE.md size
wc -l .claude/CLAUDE.md
# Should show: 150 lines

# Check skills exist
ls .claude/skills/*/SKILL.md
# Should show: execplan, progress-tracker, stall-escalation

# Start Claude with Sonnet and ask:
claude --model sonnet
> What model are you?
# Should respond: claude-sonnet-4-5...
```

---

**References:**
- [Codex AGENTS.md](C:\Users\Mariusz\.codex\AGENTS.md) - Inspiration for minimal global context
- [Claude Code Skills Docs](https://code.claude.com/docs/en/skills)
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)