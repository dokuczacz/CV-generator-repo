# Model Selection Guide

Claude Code supports three models with different cost/capability tradeoffs.

## Cost Comparison

| Model | Input $/1M tokens | Output $/1M tokens | Speed | Best for |
|-------|-------------------|-------------------|-------|----------|
| **Haiku** | $0.25 | $1.25 | Fastest | Quick tasks, file searches, status checks |
| **Sonnet** | $3 | $15 | Fast | Most coding tasks (default) |
| **Opus** | $15 | $75 | Slowest | Complex architecture, critical decisions |

## When to Use Each Model

### Haiku (60x cheaper than Opus)

Use for:
- File reads and searches
- Running tests
- Status checks (`/progress-tracker`)
- Git operations
- Lint/format operations
- Simple edits (typos, variable renames)

**Start Claude with Haiku:**
```bash
claude --model haiku
```

### Sonnet (Default - 5x cheaper than Opus)

Use for:
- Feature implementation
- Bug fixes
- Test writing
- Refactoring
- Most coding tasks

**Start Claude with Sonnet:**
```bash
claude --model sonnet
# OR just:
claude
```

### Opus (Most capable, most expensive)

Use ONLY for:
- Architecture decisions (new system design)
- Security reviews (identifying vulnerabilities)
- Complex debugging (multi-system interactions)
- Critical path optimization
- When Sonnet fails after multiple attempts

**Start Claude with Opus:**
```bash
claude --model opus
```

## Switching Models Mid-Session

You can't switch models during a session. To change models:

1. Complete or `/clear` your current task
2. Exit Claude Code
3. Restart with desired model: `claude --model <haiku|sonnet|opus>`

## Token Optimization Tips

Beyond model selection, reduce token usage:

1. **Use skills** - Skills load on-demand instead of bloating every message
2. **Use `/clear`** - Reset context between unrelated tasks
3. **Use subagents** - Research in separate context: "use subagents to investigate X"
4. **Reference files** - Link to docs instead of copying them into CLAUDE.md
5. **Trim context** - Keep CLAUDE.md under 200 lines

## Cost Calculation Example

For a typical coding session:
- **Input:** ~50K tokens (10 messages × 5K tokens avg)
- **Output:** ~10K tokens (2K tokens per response)

| Model | Session Cost | Notes |
|-------|--------------|-------|
| Haiku | $0.025 | Perfect for simple tasks |
| Sonnet | $0.30 | Recommended default |
| Opus | $1.50 | Only when necessary |

**Rule of thumb:** Use the cheapest model that can do the job well.

## Project-Specific Recommendations

For CV Generator project:

- **Schema validation:** Haiku or Sonnet
- **Template CSS changes:** Sonnet (visual reasoning needed)
- **PDF generation logic:** Sonnet
- **Architecture changes:** Opus
- **Security review:** Opus
- **File searches:** Haiku
- **Test writing:** Sonnet
- **Bug fixes:** Start with Sonnet, escalate to Opus if stuck

## Current Session Model

To check which model you're using, ask:
```
What model are you?
```

Response will indicate: `claude-haiku-...`, `claude-sonnet-...`, or `claude-opus-...`
