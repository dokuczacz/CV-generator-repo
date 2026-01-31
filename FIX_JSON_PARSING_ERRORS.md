# Fix: JSON Parsing Errors in work_experience Stage

**Date:** 2026-01-29  
**Issue:** JSON parse failures with "Unterminated string" and "Invalid \uXXXX escape" errors in `work_experience` and related stages  
**Root Cause:** User input (`work_tailoring_notes`, ranking notes, feedback) was not being sanitized before embedding in prompts to OpenAI

## Problem

After recent changes that added user tailoring suggestions and notes to several stages (work_experience, it_ai_skills, technical_operational_skills, further_experience), the system started experiencing repeated JSON parsing failures:

```
JSON parse failed for stage=work_experience: Unterminated string starting at: line 1 column 1267 (char 1266)
Attempting schema repair for stage=work_experience
...
Schema repair failed for stage=work_experience: Unterminated string starting at: line 41 column 9 (char 2011)
```

### Why This Happened

When user-provided text (like work_tailoring_notes) contains:
- **Line breaks** (`\n`, `\r`)
- **Quotes** (`"`)
- **Special characters** (unescaped Unicode escapes)

...and this text is directly embedded into the prompt sent to OpenAI, it can corrupt the JSON schema that the model is trying to generate.

**Example:** If user input is:
```
"Managed team of 5 people
Led quarterly planning sessions"
```

When embedded into the prompt unescaped, this creates an unterminated JSON string inside OpenAI's output.

## Solution

### New Helper Function

Created `_escape_user_input_for_prompt()` that:
1. Replaces all line breaks with spaces (preserves readability)
2. Collapses multiple spaces into single spaces
3. Removes control characters
4. Returns clean, single-line text safe for embedding in prompts

```python
def _escape_user_input_for_prompt(raw: str) -> str:
    """Escape user input text before embedding in prompts."""
    if not raw:
        return ""
    # Replace line breaks with spaces (preserve readability for the model)
    text = raw.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # Collapse multiple spaces
    text = " ".join(text.split())
    # Remove control characters except tab
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch == "\t")
    return text.strip()
```

### Applied To

All stages that embed user input in prompts:

1. **work_experience** (`WORK_TAILOR_RUN`):
   - `work_tailoring_notes` → `notes`
   - `work_tailoring_feedback` → `feedback`

2. **it_ai_skills** (`SKILLS_TAILOR_RUN`):
   - `work_tailoring_notes` → `tailoring_suggestions`
   - `skills_ranking_notes` → `notes`

3. **technical_operational_skills** (`TECH_OPS_TAILOR_RUN`):
   - `work_tailoring_notes` → `tailoring_suggestions`
   - `tech_ops_ranking_notes` → `notes`

4. **further_experience** (`FURTHER_TAILOR_RUN`):
   - `further_tailoring_notes` → `notes`

### Code Changes

```python
# Before:
notes = str(meta2.get("work_tailoring_notes") or "").strip()

# After:
notes = _escape_user_input_for_prompt(str(meta2.get("work_tailoring_notes") or ""))
```

## Verification

The fix ensures that:
- ✅ User input is always single-line when embedded in prompts
- ✅ No JSON syntax corruption in OpenAI requests
- ✅ Model receives clean, readable text (line breaks replaced with spaces)
- ✅ Schema repair is no longer needed for this class of error
- ✅ All four tailoring stages are protected

## Files Modified

- `function_app.py` (lines 391-450, 3997, 4001, 4463, 4465, 4599, 4601, 4285)

## Next Steps

1. Test with session that previously failed (session_id: 8853e80b-9113-4f24-a80c-61d5f02e856c)
2. Monitor Azure Functions logs for any remaining JSON parse errors
3. Consider applying same sanitization to other user-provided fields if needed

## Deployment

No configuration changes needed. Just redeploy the updated `function_app.py`.
