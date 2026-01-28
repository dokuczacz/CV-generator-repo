---
name: stall-escalation
description: Stop and ask for direction when blocked instead of inventing assumptions or placeholder data
user-invocable: false
---

# stall-escalation

When you detect blockers that prevent correct implementation, stop and ask for user direction using this pattern.

## When to stop

Trigger this pattern if **any** of these occur:

- Missing critical inputs (files, logs, schemas, examples)
- No measurable progress after 2+ turns on the same issue
- Scope is too broad for a focused next step
- Would need to scan >5 unknown files to proceed
- Contract/schema is unclear and correctness requires guessing
- About to invent placeholder data or assume behavior

## Response pattern

When blocked, structure your response like this:

```
**Blocker:** <one sentence>

**Option A - Split:**
- <smallest next step with current info>
- <alternative small step>

**Option B - Escalate:**
<what's needed: broader search, Task tool, more files>

**Question:** <direct question to user>
```

## Guidelines

**Default to Split** when possible:
- Can it be done with ≤3 files? → Split
- Is it a focused investigation? → Split
- Just need one clarification? → Split

**Escalate when necessary:**
- Needs repo-wide search → "Use Task tool with Explore agent"
- Requires understanding 10+ components → "Needs architectural context"
- Schema unclear → "Need schema documentation or examples"
- Security implications → "Requires security review"

**No filler:**
- Don't apologize excessively
- Don't invent results to "push through"
- Don't add placeholder comments like "TODO: implement this"

## Examples

### Missing file path

```
**Blocker:** Template file path unknown - cannot modify CSS without knowing which template to edit.

**Option A - Split:**
- Read [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) for template references
- Ask user for specific template path

**Option B - Escalate:**
- Use Task tool with Explore agent to search all templates

**Question:** Do you know which template file needs updating, or should I search the codebase?
```

### Scope too broad

```
**Blocker:** "Optimize CV generation" is too broad - unclear which metrics matter.

**Option A - Split:**
- Profile current performance with sample CV
- Identify top 3 slowest operations
- Propose specific optimizations based on data

**Option B - Escalate:**
- Full performance audit across all CV types
- Requires load testing setup

**Question:** Are you seeing specific performance issues, or should I profile first?
```

### Missing contract

```
**Blocker:** API contract unclear - no request/response schema documented.

**Option A - Split:**
- Read [function_app.py](function_app.py) to extract current API
- Document actual behavior as baseline

**Option B - Escalate:**
- Trace all API calls across frontend/backend
- Create comprehensive schema

**Question:** Should I document current behavior, or do you have a spec?
```

## When NOT to use this pattern

Don't stop if:
- You have all needed information
- Making clear progress (tests passing, code working)
- User explicitly said to proceed
- It's a simple clarification (just ask normally)

## After user responds

Based on their choice:
- **Split chosen**: Proceed with focused next step
- **Escalate chosen**: Use Task tool or broader exploration
- **User clarifies**: Continue with new information
- **User provides files**: Read them and proceed

## Why this matters

Prevents:
- Wasted turns on wrong assumptions
- Invented placeholder data that needs rework
- Solving the wrong problem
- Context pollution from failed approaches

Enables:
- Faster course correction
- Better use of user's time
- Clearer communication of blockers
- Focused problem-solving