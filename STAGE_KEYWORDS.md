# CV Generator — Stage Keywords & Guidance

## Overview

Each stage has specific **keywords** and **behavioral anchors** that guide the model. These are embedded in stage prompts and context packs to keep responses focused and token-efficient.

---

## Stage 1: **BOOTSTRAP** (Initial Gathering)

### Keywords
- `gather`, `missing`, `inputs`, `prompt`, `confirm`, `required`
- `what`, `please provide`, `need`, `short answers`

### Behavioral Anchors
- **Goal**: Collect minimum required fields (name, email, contact)
- **Tone**: Polite, guiding, not prescriptive
- **Action**: Ask specific questions for empty critical fields
- **Token Constraint**: Ultra-compact responses (~50 tokens)
- **Output**: Plain text questions, no tools called

### Example Keywords in Use
> "What is your **full name** for the CV header? Please keep it to one line."

---

## Stage 2: **REVIEW_SESSION** (Analysis & Proposals)

### Keywords
- `review`, `propose`, `concise edits`, `no PDF`, `brief`, `short answers`
- `sections marked 'unchanged'`, `sections marked 'changed'`, `delta`, `summary`
- `after 3 turns`, `auto-enabled`

### Behavioral Anchors
- **Goal**: Analyze CV data, identify improvement opportunities, propose edits
- **Tone**: Professional, advisory, non-intrusive
- **Action**: Suggest edits via `update_cv_field(edits=[...])` tool
- **Token Constraint**: ~1800-2500 output tokens max
- **Delta Awareness**: Only work with sections marked "changed"; summarize unchanged
- **Timeout**: After 3 user interactions, auto-advance to apply_edits

### Example Keywords in Use
> "I suggest improving your **profile** section. The `work_experience` section (marked 'changed') shows recent promotions that we should highlight..."

---

## Stage 3: **APPLY_EDITS** (Execution)

### Keywords
- `FIRST ACTION`, `call update_cv_field`, `ONE batch`, `NO questions`, `NO waiting`
- `commit`, `immediately`, `confirmation`, `auto-advanced`, `best proposals`
- `sections marked 'unchanged'`, `sections marked 'changed'`, `delta`

### Behavioral Anchors
- **Goal**: Apply all proposed edits in a single tool call, confirm once
- **Tone**: Decisive, action-oriented, no second-guessing
- **Action**: 
  1. Call `update_cv_field(edits=[...])` with ALL changes at once
  2. Respond with 1-line confirmation (e.g., "✓ Applied 5 edits to profile & work_experience")
  3. No follow-up questions or approval requests
- **Token Constraint**: ~2000 output tokens max (mostly tool call + 1-line confirm)
- **Delta Awareness**: Unchanged sections = summaries only; use "changed" sections for edits
- **Safety**: System has already validated readiness; commit immediately

### Example Keywords in Use
```
FIRST ACTION: call update_cv_field(edits=[
  {field_path: "profile", value: "Improved profile text..."},
  {field_path: "work_experience.0.title", value: "Principal Engineer"}
])
✓ Applied 2 edits. Ready for PDF generation.
```

---

## Stage 4: **GENERATE_PDF** (Finalization)

### Keywords
- `user approved`, `generate once`, `readiness`, `short answers`
- `if readiness allows`, `PDF`, `final`

### Behavioral Anchors
- **Goal**: Render PDF if CV is ready; report any blockers
- **Tone**: Factual, brief, action-complete
- **Action**:
  1. Check readiness (contact, education confirmed + essential fields)
  2. Call `generate_cv(language=...)` tool if ready
  3. Report completion or blockers
- **Token Constraint**: ~1500 output tokens max
- **Output**: Confirmation of PDF + link/blob, OR list of missing fields

### Example Keywords in Use
> "✓ CV ready. Generated 2-page ATS-compliant PDF. All contact & education confirmed."
>
> OR
> 
> "❌ Missing required field: **phone number**. Please add before PDF generation."

---

## Stage 5: **FIX_VALIDATION** (Error Recovery)

### Keywords
- `fix validation errors`, `one pass`, `generate once`, `short answers`
- `blockers`, `errors`, `schema`, `missing required`

### Behavioral Anchors
- **Goal**: Resolve validation errors in single sweep, then generate PDF
- **Tone**: Problem-solving, efficient
- **Action**:
  1. Identify validation errors (from `validate_cv` tool or previous stage report)
  2. Propose fixes via `update_cv_field(edits=[...])` in ONE batch
  3. Call `generate_cv(...)` if readiness achieved
- **Token Constraint**: ~1500 output tokens max
- **Output**: List of fixes applied + PDF or remaining blockers

### Example Keywords in Use
> "Validation errors found: missing phone, email format invalid. Fixing in one pass..."
> `update_cv_field(edits=[...])` → call `validate_cv()` → `generate_cv()`

---

## Cross-Stage Keywords (All Stages)

| Keyword | Meaning | Context |
|---------|---------|---------|
| `keep answers short` | Max 50-100 tokens per response | All stages |
| `no PDF` | Don't generate PDF yet | BOOTSTRAP, REVIEW_SESSION |
| `ONE batch` | Single tool call, not sequential | APPLY_EDITS, FIX_VALIDATION |
| `changed` / `unchanged` | Delta load markers (P1 feature) | REVIEW_SESSION, APPLY_EDITS |
| `auto-advanced` | Model doesn't wait for permission | REVIEW_SESSION (after 3 turns) → APPLY_EDITS |
| `readiness` | CV has all required fields confirmed | GENERATE_PDF, FIX_VALIDATION |
| `concise edits` | Small, focused changes | REVIEW_SESSION, APPLY_EDITS |
| `commit` | Apply edits without hesitation | APPLY_EDITS, FIX_VALIDATION |

---

## Token Budget Per Stage

| Stage | Input | Output | Notes |
|-------|-------|--------|-------|
| BOOTSTRAP | ~500 | 500-800 | Quick question |
| REVIEW_SESSION | 2500-3000 | 1800-2500 | Analysis + proposals |
| APPLY_EDITS | 2500-3000 | 2000 | Tool call + confirm |
| GENERATE_PDF | 2000-2500 | 1500 | Quick check + generation |
| FIX_VALIDATION | 2500-3000 | 1500 | Error fix + generation |

---

## Decision Tree: Which Keywords to Emphasize

```
START
├─ Empty CV? → BOOTSTRAP keywords: "gather missing"
├─ CV data exists?
│  ├─ First iteration → REVIEW_SESSION: "review, propose, concise"
│  ├─ After 3 turns → APPLY_EDITS: "FIRST ACTION, ONE batch, NO waiting"
│  └─ After edits applied?
│     ├─ Valid + ready → GENERATE_PDF: "user approved, readiness"
│     └─ Validation errors → FIX_VALIDATION: "fix validation, one pass"
```

---

## Implementation Tips

### For Model/Prompts
- **Always include stage name**: "Stage=review_session"
- **Lead with behavioral anchor**: "FIRST ACTION: call..." (for APPLY_EDITS)
- **Mention delta context**: "[Note: sections marked 'unchanged' contain only summary]" (REVIEW_SESSION, APPLY_EDITS)
- **Token budget reminder**: "Keep answers short" (all stages)

### For Context Packs
- **BOOTSTRAP**: Minimal context, just empty fields
- **REVIEW_SESSION**: Full CV data, job posting (if provided), delta markers
- **APPLY_EDITS**: Same as REVIEW_SESSION (just confirming edits)
- **GENERATE_PDF**: Summary context, readiness flags
- **FIX_VALIDATION**: Error list, CV snapshot, readiness blockers

### For Tool Calls
- **REVIEW_SESSION**: Suggest `update_cv_field` edits (model proposes)
- **APPLY_EDITS**: Call `update_cv_field` (model commits), then optional `generate_cv`
- **GENERATE_PDF**: Call `generate_cv` (model finalizes)
- **FIX_VALIDATION**: `update_cv_field` → `validate_cv` → `generate_cv` (model repairs)

---

## Examples: Keywords in Action

### Example 1: REVIEW_SESSION
```
Stage=review_session. Goal: review session data, propose concise edits, no PDF.
[Note: sections marked 'unchanged' contain only summary; 'changed' sections have full data]

Response:
"Your profile mentions 5 years, but work_experience shows 8 years (marked 'changed').
I suggest updating the profile to match. Also, the 'education' section (unchanged) 
looks complete. Shall I apply this edit?"
```

### Example 2: APPLY_EDITS (auto-advanced after 3 turns)
```
Stage=apply_edits. FIRST ACTION: call update_cv_field(edits=[...]) with ALL proposed 
changes in ONE batch. Then respond with 1-line confirmation. NO questions, NO waiting.

Response:
[Tool call: update_cv_field(edits=[{field_path: "profile", value: "..."}])]
✓ Updated profile to align with 8 years experience.
```

### Example 3: GENERATE_PDF (readiness confirmed)
```
Stage=generate_pdf. Goal: user approved; generate once if readiness allows.

Response:
✓ Contact confirmed. Education confirmed. All required fields present.
Generating 2-page ATS-compliant PDF...
```

---

## Key Takeaway

Each stage uses **specific keywords** to anchor the model's behavior:
- **BOOTSTRAP**: Gather
- **REVIEW_SESSION**: Propose (short, delta-aware)
- **APPLY_EDITS**: Commit (one batch, no questions)
- **GENERATE_PDF**: Finalize (readiness check)
- **FIX_VALIDATION**: Repair (one pass)

Use these keywords consistently in prompts, context packs, and tool descriptions to maintain focus and efficiency across the workflow.
