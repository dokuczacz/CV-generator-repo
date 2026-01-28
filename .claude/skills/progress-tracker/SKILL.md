---
name: progress-tracker
description: Create strict progress tables with verified numbers only - no placeholders or estimates
---

# progress-tracker

Generate progress status tables with verified numbers and source attribution.

## When to use

Use when user asks for:
- Status update
- Progress report
- Task completion percentage
- "How much is done?"
- "What's left?"

## Output format

Create exactly one markdown table:

| Task | Done/Total | Progress | Status | Source |
|------|------------|----------|--------|--------|
| CV validation | 45/100 | 45% | ⚙️ In progress | `pytest --collect-only` |
| PDF generation | 12/12 | 100% | ✅ OK | All test files in tests/ |
| Visual regression | N/A | N/A | 🟡 Needs input | No baseline defined |

## Column rules

**Done/Total:**
- Format: `x/y` (integers only)
- Use `N/A` if not countable/verifiable

**Progress:**
- Format: `NN%` computed from Done/Total
- Use `N/A` if denominator unknown

**Status:**
- ✅ OK - Complete and verified
- ⚙️ In progress - Active work
- ⛔ Blocked - Cannot proceed
- 🟡 Needs input - Waiting for user

**Source:**
- WHERE the numbers came from
- Examples: "git log count", "ls tests/ | wc -l", "user provided", "plan file line 42"
- Never leave blank

## Hard rules

**FORBIDDEN:**
- Placeholders like `TBD`, `???`, `{x}/{y}`
- Guessing or estimating totals
- Leaving Source column empty
- More than 7 rows in the table

**REQUIRED:**
- Every number must be verifiable from Source
- If unsure, use `N/A` with explanation in Source
- Keep table focused on current scope only

## After the table

Add max 2 bullets for anomalies or notes, then stop.

Example:
```
- Visual regression blocked: needs baseline screenshots from QA
- PDF generation complete but needs manual review for layout
```

## Examples

### Good table

| Task | Done/Total | Progress | Status | Source |
|------|------------|----------|--------|--------|
| Schema validation tests | 8/8 | 100% | ✅ OK | All pass: `pytest tests/test_validator.py` |
| Template updates | 2/3 | 67% | ⚙️ In progress | EN, DE done; PL pending |
| Visual baselines | 0/3 | 0% | 🟡 Needs input | Requires QA approval |

- Template updates blocked on Polish translations from content team

### Bad table (violations)

| Task | Done/Total | Progress | Status | Source |
|------|------------|----------|--------|--------|
| Testing | TBD | ~50% | In progress | ❌ Placeholder, vague estimate |
| Refactoring | 10/??? | Unknown | Doing it | ❌ No source, unclear total |
| Documentation | {x}/{y} | TBD | TBD | ❌ Template vars, no data |

## Integration with execplan

If using with `/execplan`, reference the plan file in Source:

```
| Task | Done/Total | Progress | Status | Source |
|------|------------|----------|--------|--------|
| Implement auth | 3/5 | 60% | ⚙️ In progress | tmp/auth_execplan.md steps |
```

## Computing percentages

```
Progress = round(100 * done / total)

If total == 0 or unknown: "N/A"
```

## Why strict verification matters

Prevents:
- False confidence from made-up numbers
- Wasted time tracking unverifiable metrics
- Noise in status reports

Enables:
- Trust in progress updates
- Clear blockers and dependencies
- Reproducible status checks