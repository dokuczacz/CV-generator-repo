# System Prompt Update Requirements for Session-Based Workflow

**Date:** January 21, 2026  
**Reason:** Migrating from legacy tools (3) to session-based tools (5)  
**Old tools removed:** extract_photo, validate_cv, generate_cv_action  
**New tools available:** extract_and_store_cv, get_cv_session, update_cv_field, generate_cv_from_session, process_cv_orchestrated

---

## 1. Tool List — REPLACE ENTIRELY

**CURRENT (DELETE):**
```
You have access to three tools:
1) extract_photo (DOCX → photo data URI)
2) validate_cv (validates CV content vs strict 2-page constraints)
3) generate_cv_action (renders final PDF)
```

**NEW:**
```
You have access to five tools:
1) extract_and_store_cv — Upload CV, extract photo automatically, create session (returns session_id)
2) get_cv_session — Retrieve CV data from session by session_id
3) update_cv_field — Edit specific CV fields using dot-notation paths (e.g., "full_name", "work_experience[0].employer")
4) generate_cv_from_session — Generate PDF from session data using session_id
5) process_cv_orchestrated — (Optional) Single-call workflow: extract → edit → validate → generate
```

---

## 2. Workflow — MAJOR RESTRUCTURE

### DELETE Entirely:
- All mentions of "Store this JSON internally"
- "Persist and reuse one canonical JSON state across the session"
- "Send this EXACT JSON object to validate_cv and generate_cv_action"
- Any instruction to maintain CV JSON in conversation context

### REPLACE 3-Stage Workflow With:

**Stage 1: Upload & Create Session**
- When user uploads CV, call `extract_and_store_cv(docx_base64, language)`
- Response includes `session_id` — **SAVE THIS** for all subsequent operations
- Photo extracted automatically (no separate tool call needed)
- Show user: `cv_data_summary` (which fields populated vs. empty)
- Do NOT proceed without session_id

**Stage 2: Populate & Edit CV Data**
- Ask user for missing required fields:
  - full_name (required)
  - email (required)
  - phone (required)
  - work_experience (required, min 1 entry with: employer, title, date_range, bullets)
  - education (required, min 1 entry with: institution, title, date_range)
- For each field user provides, call `update_cv_field(session_id, field_path, value)`
- Support nested paths:
  - Simple: `"full_name"`, `"email"`, `"phone"`
  - Arrays: `"languages"`, `"skills"` (set entire array)
  - Nested: `"work_experience[0].employer"`, `"education[1].title"`
- User can request to see current data anytime: call `get_cv_session(session_id)`
- After edits, show updated summary (call `get_cv_session` again)

**Stage 3: Confirm & Generate**
- Show user complete CV data from `get_cv_session(session_id)`
- Ask: "Is this correct? Say 'proceed' to generate your PDF."
- When user confirms "proceed":
  - Call `generate_cv_from_session(session_id)`
  - Response includes `pdf_base64` and validation results
  - Return PDF to user

---

## 3. Session Management Rules — ADD NEW SECTION

**Session Management:**
- Always save `session_id` when received from `extract_and_store_cv`
- Use this `session_id` for ALL subsequent tool calls (get, update, generate)
- Sessions expire after 24 hours
- If you receive error "Session not found or expired":
  - Inform user session expired
  - Create new session via `extract_and_store_cv`
- **NEVER** try to maintain full CV JSON in your conversation context
- Use `get_cv_session(session_id)` whenever you need to show user current CV data

---

## 4. Field Editing Instructions — UPDATE

**DELETE:**
```
If the user provides edits, patch only those fields and re-present JSON for confirmation.
```

**REPLACE WITH:**
```
If user provides edits:
1. Call update_cv_field(session_id, field_path, value) for each change
2. For complex updates (work_experience, education), set entire array in one call
3. After edits complete, call get_cv_session(session_id) to retrieve updated data
4. Show user the updated fields for confirmation
```

**Examples:**
```
# Simple field
update_cv_field(session_id, "full_name", "John Doe")

# Nested field
update_cv_field(session_id, "work_experience[0].employer", "Acme Corp")

# Entire array
update_cv_field(session_id, "work_experience", [
  {
    "date_range": "2020-2024",
    "employer": "Acme Corp",
    "title": "Engineer",
    "bullets": ["Led team", "Improved performance"]
  }
])
```

---

## 5. Error Handling — ADD NEW SECTION

**Error Handling:**

**Schema Validation Errors (Phase 1 Fix):**
- If backend returns `"wrong_keys_detected"`, you sent wrong schema
- Rebuild using **canonical schema only**:
  - ✅ USE: `full_name`, `email`, `phone`, `work_experience`, `education`, `skills`, `languages`, `certifications`, `summary`, `photo_url`
  - ❌ NEVER USE: `personal_info`, `employment_history`, `personal`, `cv_source`, `contact`, `profiles`, `metadata`, `employment`, `headline`
- Backend error message shows correct schema example — use it to rebuild

**Session Expired:**
- Error: `"Session not found or expired"`
- Action: Inform user, create new session via `extract_and_store_cv`

**Missing Required Fields:**
- Error: `"CV data validation failed"` with list of missing fields
- Action: Ask user for missing data, use `update_cv_field` to populate
- Required fields: full_name, email, phone, work_experience (min 1), education (min 1)

---

## 6. Tool Call Examples — REPLACE

**DELETE all old examples like:**
```
Tool: extract_photo with { "docx_base64": "..." }
Tool: validate_cv (payload: { "cv_data": <the confirmed JSON> })
Tool: generate_cv_action: { "cv_data": <confirmed JSON>, "source_docx_base64": "..." }
```

**REPLACE WITH:**
```
# Step 1: Create session
extract_and_store_cv({
  "docx_base64": "UEsDBBQACAgI...",
  "language": "en",
  "extract_photo": true
})
→ Returns: { "session_id": "abc-123-def", "cv_data_summary": {...}, "photo_extracted": true }

# Step 2: Update fields
update_cv_field({
  "session_id": "abc-123-def",
  "field_path": "full_name",
  "value": "John Doe"
})

update_cv_field({
  "session_id": "abc-123-def",
  "field_path": "work_experience",
  "value": [{ "date_range": "2020-2024", "employer": "Acme", "title": "Engineer", "bullets": ["Achievement"] }]
})

# Step 3: Check data
get_cv_session({
  "session_id": "abc-123-def"
})
→ Returns: { "cv_data": {...}, "metadata": {...}, "expires_at": "..." }

# Step 4: Generate PDF
generate_cv_from_session({
  "session_id": "abc-123-def"
})
→ Returns: { "pdf_base64": "...", "validation": {...} }
```

---

## 7. Canonical Schema Reminder — ADD

**CRITICAL: Use Canonical Schema Only**

When populating CV data via `update_cv_field`, use these keys:

**Top-level fields:**
- `full_name` (string, required)
- `email` (string, required)
- `phone` (string, required)
- `photo_url` (string, optional — auto-extracted from DOCX)
- `summary` (string, optional)
- `language` (string: "en", "de", or "pl")

**Arrays (required):**
- `work_experience` (array, min 1 entry)
  - Each entry: `{ date_range, employer, location, title, bullets }`
- `education` (array, min 1 entry)
  - Each entry: `{ date_range, institution, title, details }`

**Arrays (optional):**
- `skills` (array of strings)
- `languages` (array of strings or objects)
- `certifications` (array of strings)

**WRONG KEYS (Backend will reject):**
- ❌ `personal_info`, `employment_history`, `personal`, `cv_source`, `contact`, `profiles`, `metadata`, `employment`, `headline`

If backend returns schema error, it provides correct example — use it.

---

## 8. Optional: Single-Call Orchestrated Workflow — ADD

**Alternative Workflow (Power Users):**

If user provides all CV data in one message, use single-call workflow:

```
process_cv_orchestrated({
  "docx_base64": "UEsDBBQACAgI...",
  "language": "en",
  "edits": [
    { "field_path": "full_name", "value": "John Doe" },
    { "field_path": "email", "value": "john@example.com" },
    { "field_path": "phone", "value": "+1234567890" },
    {
      "field_path": "work_experience",
      "value": [
        {
          "date_range": "2020-2024",
          "employer": "Acme Corp",
          "title": "Senior Engineer",
          "bullets": ["Led team of 5", "Improved performance by 40%"]
        }
      ]
    },
    {
      "field_path": "education",
      "value": [
        {
          "date_range": "2016-2020",
          "institution": "MIT",
          "title": "BSc Computer Science",
          "details": []
        }
      ]
    }
  ],
  "extract_photo": true
})
```

This handles: extract → apply edits → validate → generate in one call.

**Response:**
```json
{
  "success": true,
  "session_id": "abc-123-def",
  "pdf_base64": "...",
  "validation": { "is_valid": true },
  "cv_data_summary": { ... }
}
```

**Benefits:**
- Faster for users who provide complete data upfront
- Still creates session for future edits
- Single tool call instead of multiple

**When to use:**
- User provides all CV information in one message
- No iterative editing needed
- Generate PDF immediately

---

## 9. Remove Obsolete Instructions — DELETE

**DELETE these entire sections/phrases:**
- "Store this JSON internally — you will send this EXACT JSON object to validate_cv and generate_cv_action tools"
- "Persist and reuse one canonical JSON state across the session"
- "CRITICAL: You MUST include the cv_data parameter with the EXACT SAME complete JSON object you showed to the user in Stage 2"
- "Do NOT call this tool with only source_docx_base64 and language — the cv_data field is REQUIRED"
- Any instruction about maintaining CV JSON in conversation memory

**Why:** Backend stores CV data in session. Agent only needs to reference `session_id`.

---

## 10. Update Reference to PROMPT_INSTRUCTIONS.md

**CURRENT:**
```
You also have access to PROMPT_INSTRUCTIONS.md (detailed workflow and examples).
```

**UPDATE TO:**
```
You also have access to PROMPT_INSTRUCTIONS_SESSION_BASED.md (detailed session workflow, examples, and error handling).
```

---

## Summary Checklist for Prompt Generator

- [ ] Replace 3 legacy tools → 5 session-based tools
- [ ] Remove "store JSON internally" language throughout
- [ ] Add session_id management rules (save it, use it for all operations)
- [ ] Update Stage 1: extract_and_store_cv instead of extract_photo
- [ ] Update Stage 2: update_cv_field instead of "patch JSON"
- [ ] Update Stage 3: generate_cv_from_session instead of generate_cv_action
- [ ] Add session management section (save session_id, handle expiration)
- [ ] Add error handling section (schema errors, session expired, missing fields)
- [ ] Add canonical schema reminder (Phase 1 fix — wrong keys rejected)
- [ ] Replace all tool call examples with session-based versions
- [ ] Add optional process_cv_orchestrated workflow
- [ ] Update reference: PROMPT_INSTRUCTIONS.md → PROMPT_INSTRUCTIONS_SESSION_BASED.md
- [ ] Delete all mentions of cv_data parameter (agent doesn't send it anymore)
- [ ] Delete all mentions of persisting JSON state in conversation

---

## Key Behavioral Changes

| Old Behavior | New Behavior |
|--------------|--------------|
| Agent maintains full CV JSON in context (~5000 tokens) | Agent maintains only session_id (~50 tokens) |
| File upload lost between turns → data loss | Session persists 24h → no data loss |
| Re-extract photo every turn | Extract once at upload |
| Send cv_data parameter to every tool | Send session_id parameter to every tool |
| Validate with cv_data, generate with cv_data | Validate/generate with session_id only |
| "Store JSON internally" | "Backend stores it, use session_id" |
| 3 tool calls minimum | 1 call (orchestrated) or incremental updates |

---

## Expected Workflow After Update

**User:** "Here's my CV [uploads DOCX]"

**Agent:**
1. Calls `extract_and_store_cv(docx_base64, language="en")`
2. Gets `session_id: abc-123`
3. Shows user summary: "Photo extracted ✓. I need: full_name, email, phone, work_experience, education"

**User:** "John Doe, john@email.com, +123..."

**Agent:**
1. Calls `update_cv_field(session_id, "full_name", "John Doe")`
2. Calls `update_cv_field(session_id, "email", "john@email.com")`
3. Calls `update_cv_field(session_id, "phone", "+123...")`
4. Calls `get_cv_session(session_id)` to verify
5. Shows user: "Current data: [summary]. Provide work_experience..."

**User:** [provides work experience]

**Agent:**
1. Calls `update_cv_field(session_id, "work_experience", [...])`
2. Repeats for education
3. Calls `get_cv_session(session_id)` to show final data
4. Asks: "Is this correct? Say 'proceed'"

**User:** "proceed"

**Agent:**
1. Calls `generate_cv_from_session(session_id)`
2. Returns PDF to user

**Session persists** — if user returns later (within 24h) to edit, agent reuses same session_id.

---

**END OF REQUIREMENTS**
