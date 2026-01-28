# Structured Output Implementation Summary

**Date:** 2026-01-25
**Status:** COMPLETED (Experimental Feature)
**Feature Flag:** `USE_STRUCTURED_OUTPUT`

---

## Overview

Implemented JSON structured outputs for the CV Generator backend following OpenAI best practices. This feature enables the model to return responses in a strict JSON schema that separates:

1. **User-facing content** - messages, sections, questions for the UI
2. **System metadata** - validation status, confidence, reasoning
3. **Backend actions** - tool calls, workflow stages, confirmation flags

---

## Changes Made

### 1. New Files Created

#### [STRUCTURED_RESPONSE_SCHEMA.md](STRUCTURED_RESPONSE_SCHEMA.md)
- Complete JSON schema definition
- Response type routing guide
- Example responses for all scenarios (question, proposal, error, completion)
- Backend processing flow diagram
- Implementation checklist

#### [src/structured_response.py](src/structured_response.py)
- Pydantic models for type-safe response handling
- Enums for response types, section types, tool names, workflow stages
- JSON schema export for OpenAI API
- Helper functions:
  - `get_response_format()` - Returns response_format parameter for API calls
  - `parse_structured_response()` - Validates and parses model output
  - `format_user_message_for_ui()` - Formats response for UI display

#### [STRUCTURED_OUTPUT_PROMPT_GUIDE.md](STRUCTURED_OUTPUT_PROMPT_GUIDE.md)
- Comprehensive guide for OpenAI model on how to generate structured responses
- Guidelines for each response type
- Tool call format specifications
- Validation status computation rules
- Common patterns and testing checklist

### 2. Modified Files

#### [function_app.py](function_app.py)
**Lines modified:** Import statement (line 39), `_run_responses_tool_loop_v2()` function

**Key changes:**
1. Added imports:
   ```python
   from src.structured_response import CVAssistantResponse, get_response_format, parse_structured_response, format_user_message_for_ui
   ```

2. Added feature flag (line ~663):
   ```python
   use_structured_output = str(os.environ.get("USE_STRUCTURED_OUTPUT", "0")).strip() == "1"
   ```

3. Conditional `response_format` parameter (lines ~704-715):
   ```python
   if use_structured_output:
       req_base["response_format"] = get_response_format()
   else:
       req_base["tools"] = tools
   ```

4. Response parsing logic (lines ~782-810):
   - Parses structured JSON when `use_structured_output=True`
   - Falls back to raw text output if parsing fails
   - Logs metadata (response_type, confidence, validation_status)

5. Tool call extraction (lines ~814-830):
   - Extracts tool calls from `system_actions.tool_calls` array (structured mode)
   - Falls back to traditional function_call items (traditional mode)
   - Checks `confirmation_required` flag before executing

#### [local.settings.template.json](local.settings.template.json)
- Added `USE_STRUCTURED_OUTPUT: "0"` to default configuration
- Updated comment to reference `STRUCTURED_RESPONSE_SCHEMA.md`

#### [.claude/CLAUDE.md](.claude/CLAUDE.md)
- Added experimental features section
- Documented `USE_STRUCTURED_OUTPUT` environment variable
- Added benefits and current status

### 3. Updated Checklist

Original checklist from [STRUCTURED_RESPONSE_SCHEMA.md](STRUCTURED_RESPONSE_SCHEMA.md):

- [x] Add `response_format` parameter to OpenAI API calls
- [x] Create Pydantic models matching schema (for type safety)
- [x] Update `_run_responses_tool_loop_v2()` to enforce structured output
- [x] Add response parser in backend
- [ ] Update UI to handle multi-section responses (FUTURE WORK)
- [x] Add logging for metadata tracking
- [ ] Test all response types (PENDING)
- [ ] Update OpenAI prompt to use structured format (GUIDE CREATED)

---

## How It Works

### Traditional Mode (Default: `USE_STRUCTURED_OUTPUT=0`)

```
User Request → OpenAI API (with tools=[...]) → Model returns function_call
                                               ↓
Backend executes tool → Returns result to model → Model returns text
                                                  ↓
                                    UI displays text
```

### Structured Mode (Experimental: `USE_STRUCTURED_OUTPUT=1`)

```
User Request → OpenAI API (with response_format={...}) → Model returns JSON
                                                         ↓
Backend parses JSON:
  - user_message → Format for UI
  - system_actions.tool_calls → Execute tools
  - metadata → Log for debugging
                   ↓
UI displays formatted message + sections + questions
```

**Key Difference:** In structured mode, the model doesn't directly call tools. Instead, it returns JSON **describing** what tools should be called, and the backend executes them.

---

## Response Schema Structure

```json
{
  "response_type": "question|proposal|confirmation|status_update|error|completion",
  "user_message": {
    "text": "Main message",
    "sections": [{"title": "...", "content": "...", "type": "info|warning|success"}],
    "questions": [{"id": "q1", "question": "...", "options": ["...", "..."]}]
  },
  "system_actions": {
    "tool_calls": [{"tool_name": "...", "parameters": {...}, "reason": "..."}],
    "expected_next_stage": "review_session|apply_edits|generate_pdf|...",
    "confirmation_required": true
  },
  "metadata": {
    "response_id": "...",
    "timestamp": "...",
    "model_reasoning": "...",
    "confidence": "high|medium|low",
    "validation_status": {
      "schema_valid": true,
      "page_count_ok": true,
      "required_fields_present": true,
      "issues": []
    }
  },
  "refusal": null
}
```

---

## Benefits

### 1. Separation of Concerns
- **User content** (displayed in chat) is separate from **system metadata** (used for tracking)
- Backend can route responses based on `response_type`
- UI can render multi-section messages with proper styling

### 2. Validation Status Tracking
- Model reports current CV validation state with each response
- `issues` array lists specific problems
- UI can show validation status before user confirms changes

### 3. Explicit Tool Calls
- Model describes **why** each tool call is needed (`reason` field)
- Backend logs tool execution for debugging
- `confirmation_required` flag prevents destructive actions without user approval

### 4. Confidence & Reasoning
- Model reports confidence level (high/medium/low)
- `model_reasoning` explains decision-making process
- Useful for debugging and improving prompts

---

## Testing Plan

### Unit Tests (Recommended)

1. **Test Pydantic models**
   ```python
   from src.structured_response import CVAssistantResponse, parse_structured_response

   # Test valid response
   valid_json = {...}
   response = parse_structured_response(valid_json)
   assert response.response_type == ResponseType.QUESTION

   # Test invalid response (should raise ValidationError)
   invalid_json = {"response_type": "invalid"}
   with pytest.raises(ValidationError):
       parse_structured_response(invalid_json)
   ```

2. **Test response formatting**
   ```python
   from src.structured_response import format_user_message_for_ui

   response = CVAssistantResponse(...)
   ui_data = format_user_message_for_ui(response)
   assert ui_data["text"] == "Expected text"
   assert len(ui_data["sections"]) == 2
   ```

### Integration Tests (Recommended)

1. **Test with real OpenAI API**
   - Set `USE_STRUCTURED_OUTPUT=1` in `local.settings.json`
   - Upload a CV
   - Verify model returns valid JSON
   - Check that tool calls are extracted and executed
   - Verify UI receives formatted response

2. **Test each response type**
   - Question: Model asks clarifying questions
   - Proposal: Model suggests CV changes
   - Error: Validation fails, model reports issues
   - Completion: PDF generation succeeds

3. **Test confirmation flow**
   - Model sets `confirmation_required: true`
   - Backend should **not** execute tool calls until user confirms
   - After confirmation, backend executes queued tool calls

### Manual Testing Checklist

- [ ] Start Azure Functions locally (`func start`)
- [ ] Set `USE_STRUCTURED_OUTPUT=1` in `local.settings.json`
- [ ] Upload CV via UI
- [ ] Verify model asks questions (response_type=question)
- [ ] Answer questions
- [ ] Verify model proposes changes (response_type=proposal)
- [ ] Approve changes
- [ ] Verify model updates CV data (tool_calls executed)
- [ ] Request PDF generation
- [ ] Verify PDF generated (response_type=completion)
- [ ] Check Azure Functions logs for metadata logging

---

## Rollout Strategy

### Phase 1: Experimental (CURRENT)
- Feature flag defaulted to OFF (`USE_STRUCTURED_OUTPUT=0`)
- Documentation complete
- Code changes merged but inactive
- Internal testing required

### Phase 2: Opt-In Testing
- Enable for internal testing (`USE_STRUCTURED_OUTPUT=1` locally)
- Validate all response types work correctly
- Ensure backward compatibility (traditional mode still works)
- Monitor logs for parsing errors

### Phase 3: Gradual Rollout
- Enable for subset of production users (A/B test)
- Monitor error rates, response quality
- Collect feedback on UI experience

### Phase 4: Default ON
- Once validated, change default to `USE_STRUCTURED_OUTPUT=1`
- Keep traditional mode available as fallback
- Remove flag in future versions (structured becomes standard)

---

## Known Limitations

### 1. UI Not Updated
The UI ([ui/app/page.tsx](ui/app/page.tsx)) still expects plain text responses. To fully leverage structured outputs:
- Update UI to render `sections` array with proper styling
- Display `questions` with option buttons
- Show validation status indicators
- Add confirmation dialogs when `confirmation_required: true`

**Workaround:** Backend converts structured response back to plain text for backward compatibility.

### 2. No Tool Calling in Structured Mode
When `USE_STRUCTURED_OUTPUT=1`, the model cannot use traditional function calling. All tool calls must be described in JSON.

**Implication:** The workflow changes from "model calls tool → backend executes" to "model describes tool call → backend parses JSON → backend executes".

### 3. Pydantic Version Compatibility
Current implementation uses Pydantic v1 methods (`schema()`, `parse_obj()`). If upgrading to Pydantic v2:
- Change `schema()` to `model_json_schema()`
- Change `parse_obj()` to `model_validate()`
- Test thoroughly

---

## Troubleshooting

### Issue: "AttributeError: 'CVAssistantResponse' has no attribute 'model_json_schema'"
**Cause:** Pydantic v1 uses `schema()` not `model_json_schema()`
**Solution:** Already fixed in [src/structured_response.py](src/structured_response.py) line 149

### Issue: Model returns invalid JSON
**Cause:** Model prompt doesn't instruct it to use structured format
**Solution:** Update OpenAI prompt to reference [STRUCTURED_OUTPUT_PROMPT_GUIDE.md](STRUCTURED_OUTPUT_PROMPT_GUIDE.md)

### Issue: Tool calls not executing
**Cause 1:** `confirmation_required: true` but user hasn't confirmed
**Cause 2:** Tool call parameters don't match expected format
**Solution:** Check logs for `system_actions.tool_calls` content, verify parameters match tool schemas

### Issue: UI displays JSON instead of formatted text
**Cause:** UI not updated to handle structured responses
**Workaround:** Backend converts structured → text (lines ~800-803 in function_app.py)
**Permanent Fix:** Update UI to parse and render structured responses

---

## Next Steps

### Immediate (Before Testing)
1. Test import and parsing logic
2. Enable feature flag locally (`USE_STRUCTURED_OUTPUT=1`)
3. Upload CV and verify model returns valid JSON
4. Check Azure Functions logs for metadata

### Short Term (After Initial Testing)
1. Update OpenAI prompt to instruct model to use structured format
2. Add unit tests for Pydantic models
3. Add integration tests for all response types
4. Fix any parsing errors discovered during testing

### Long Term (Future Enhancements)
1. Update UI to render multi-section responses
2. Add visual validation status indicators
3. Implement confirmation dialogs
4. Consider making structured outputs default (after validation)
5. Add response analytics (track confidence levels, common validation issues)

---

## References

**Best Practices:**
- [OpenAI Structured Outputs Cookbook](https://cookbook.openai.com/examples/structured_outputs_intro)
- [Azure OpenAI Structured Outputs Guide](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs)

**Project Files:**
- [STRUCTURED_RESPONSE_SCHEMA.md](STRUCTURED_RESPONSE_SCHEMA.md) - Schema definition and examples
- [STRUCTURED_OUTPUT_PROMPT_GUIDE.md](STRUCTURED_OUTPUT_PROMPT_GUIDE.md) - Model instructions
- [src/structured_response.py](src/structured_response.py) - Pydantic models
- [function_app.py](function_app.py) - Backend integration

---

**Implementation completed:** 2026-01-25
**Ready for testing:** YES (with `USE_STRUCTURED_OUTPUT=1`)
**Production ready:** NO (requires testing + UI updates)
