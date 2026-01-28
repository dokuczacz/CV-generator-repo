# Stage Keywords — Quick Reference Card

## 5 Stages + Keywords

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1: BOOTSTRAP                                              │
├─────────────────────────────────────────────────────────────────┤
│ Keywords:  gather, missing, inputs, prompt, required            │
│ Goal:      Collect minimum CV fields (name, email, contact)     │
│ Action:    Ask specific questions; NO tools                     │
│ Tokens:    ~500-800 output                                      │
│ Trigger:   Empty or incomplete CV                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ STAGE 2: REVIEW_SESSION (Iteration Loop)                        │
├─────────────────────────────────────────────────────────────────┤
│ Keywords:  review, propose, concise edits, delta, changed       │
│ Goal:      Analyze CV; suggest improvements (no PDF)            │
│ Action:    Propose edits via update_cv_field(edits=[...])      │
│ Tokens:    ~1800-2500 output                                    │
│ Trigger:   CV data exists; model suggests improvements          │
│ Auto-→:    After 3 turns → APPLY_EDITS (force commit)          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ STAGE 3: APPLY_EDITS (Execution)                               │
├─────────────────────────────────────────────────────────────────┤
│ Keywords:  FIRST ACTION, ONE batch, NO questions, commit        │
│ Goal:      Apply all edits in single call; confirm; NO waiting  │
│ Action:    update_cv_field(edits=[...]) → 1-line confirm       │
│ Tokens:    ~2000 output (mostly tool call)                      │
│ Trigger:   Auto-advanced after 3 REVIEW_SESSION turns          │
│ Constraint: NO follow-up questions or approval requests         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ STAGE 4: GENERATE_PDF (Finalization)                           │
├─────────────────────────────────────────────────────────────────┤
│ Keywords:  user approved, readiness, if readiness allows, short │
│ Goal:      Render 2-page PDF if CV ready                       │
│ Action:    Check readiness → generate_cv(...) or report blockers│
│ Tokens:    ~1500 output                                         │
│ Trigger:   Edits applied; readiness confirmed                   │
│ Output:    PDF blob/link OR list of missing fields              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ STAGE 5: FIX_VALIDATION (Error Recovery)                        │
├─────────────────────────────────────────────────────────────────┤
│ Keywords:  fix validation errors, one pass, schema, blockers    │
│ Goal:      Resolve validation errors in one sweep               │
│ Action:    update_cv_field(edits=[...]) → validate_cv() → PDF  │
│ Tokens:    ~1500 output                                         │
│ Trigger:   Validation errors detected in GENERATE_PDF           │
│ Constraint: NO sequential fixes; batch all in ONE call          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Cross-Stage Keywords

| Keyword | Where | Meaning |
|---------|-------|---------|
| `keep answers short` | All | <100 tokens per response |
| `no PDF` | BOOTSTRAP, REVIEW | Don't generate yet |
| `changed` | REVIEW, APPLY | Section hash changed (delta) |
| `unchanged` | REVIEW, APPLY | Section hash same (delta summary) |
| `ONE batch` | APPLY, FIX | Single tool call, not sequential |
| `FIRST ACTION` | APPLY | Commit edits immediately |
| `NO waiting` | APPLY | Don't ask for approval |
| `auto-advanced` | REVIEW→APPLY | System forces stage change |
| `readiness` | PDF, FIX | All required fields confirmed |
| `concise edits` | REVIEW, APPLY | Small, focused changes |

---

## Token Budget

| Stage | Input | Output | Total |
|-------|-------|--------|-------|
| BOOTSTRAP | ~500 | 500-800 | ~1300 |
| REVIEW | 2500-3000 | 1800-2500 | ~5500 |
| APPLY | 2500-3000 | 2000 | ~5500 |
| PDF | 2000-2500 | 1500 | ~4000 |
| FIX | 2500-3000 | 1500 | ~4500 |

**Total per session:** ~5000-6000 tokens (down from 13k+ baseline) ✓

---

## Decision Flow

```
CV empty?
  YES  → BOOTSTRAP (gather missing)
  
CV exists?
  ITERATION LOOP:
    1. REVIEW_SESSION (propose) × 3 turns max
       ↓
    2. AUTO-ADVANCE → APPLY_EDITS (commit)
       ↓
    3. Validation passed?
       YES  → GENERATE_PDF (render)
       NO   → FIX_VALIDATION (repair) → GENERATE_PDF
```

---

## Use in Prompts

### REVIEW_SESSION example:
```
Stage=review_session. 
Goal: review session data, propose concise edits, no PDF.
[Note: sections marked 'unchanged' contain only summary; 
'changed' sections have full data].
Keep answers short.
```

### APPLY_EDITS example:
```
Stage=apply_edits. 
FIRST ACTION: call update_cv_field(edits=[...]) with ALL proposed 
changes in ONE batch. Then respond with 1-line confirmation. 
NO questions, NO waiting for approval.
```

---

## Key Insight

Each stage **gates** what the model should focus on:

- **BOOTSTRAP** gates: No analysis yet → just gather
- **REVIEW** gates: No PDF → just propose
- **APPLY** gates: No questions → just commit
- **PDF** gates: No errors expected → just render
- **FIX** gates: Errors present → just repair

These keywords enforce **stage discipline** = smaller token budget = faster, better responses ✓
