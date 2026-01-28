# CV Generator Structured Response Schema

**Version:** 1.0
**Date:** 2026-01-25
**Purpose:** Define strict JSON schema for model responses with clear user/metadata separation

---

## Design Principles

Based on [OpenAI Structured Outputs](https://cookbook.openai.com/examples/structured_outputs_intro) and [Azure OpenAI documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs):

1. **Strict mode enabled** (`strict: true`) - all fields required, no additional properties
2. **User/Metadata separation** - distinct sections for UI display vs response metadata
3. **Multi-section responses** - organized by purpose (message, actions, validation, etc.)
4. **Refusal handling** - dedicated field for safety-based rejections
5. **Nested validation** - each sub-object enforces its own schema

---

## JSON Schema Definition

```json
{
  "name": "cv_assistant_response",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "response_type": {
        "type": "string",
        "enum": ["question", "proposal", "confirmation", "status_update", "error", "completion"],
        "description": "High-level category of response for UI routing"
      },
      "user_message": {
        "type": "object",
        "description": "Content displayed to user in chat interface",
        "properties": {
          "text": {
            "type": "string",
            "description": "Primary message text (markdown supported)"
          },
          "sections": {
            "type": "array",
            "description": "Organized content sections (optional, for multi-part messages)",
            "items": {
              "type": "object",
              "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "type": {
                  "type": "string",
                  "enum": ["info", "warning", "success", "question", "proposal"]
                }
              },
              "required": ["title", "content", "type"],
              "additionalProperties": false
            }
          },
          "questions": {
            "type": "array",
            "description": "Clarifying questions for user (if response_type=question)",
            "items": {
              "type": "object",
              "properties": {
                "id": {"type": "string"},
                "question": {"type": "string"},
                "options": {
                  "type": "array",
                  "items": {"type": "string"}
                }
              },
              "required": ["id", "question", "options"],
              "additionalProperties": false
            }
          }
        },
        "required": ["text", "sections", "questions"],
        "additionalProperties": false
      },
      "metadata": {
        "type": "object",
        "description": "Response metadata for tracking and debugging",
        "properties": {
          "response_id": {"type": "string"},
          "timestamp": {"type": "string"},
          "model_reasoning": {
            "type": "string",
            "description": "Brief explanation of decision-making process"
          },
          "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Model's confidence in this response"
          },
          "validation_status": {
            "type": "object",
            "description": "Current CV validation state",
            "properties": {
              "schema_valid": {"type": "boolean"},
              "page_count_ok": {"type": "boolean"},
              "required_fields_present": {"type": "boolean"},
              "issues": {
                "type": "array",
                "items": {"type": "string"}
              }
            },
            "required": ["schema_valid", "page_count_ok", "required_fields_present", "issues"],
            "additionalProperties": false
          }
        },
        "required": ["response_id", "timestamp", "model_reasoning", "confidence", "validation_status"],
        "additionalProperties": false
      },
      "refusal": {
        "type": ["string", "null"],
        "description": "Safety-based refusal message (null if no refusal)"
      }
    },
    "required": ["response_type", "user_message", "metadata", "refusal"],
    "additionalProperties": false
  }
}
```

---

## Response Type Routing

| Type | When Used | UI Behavior |
|------|-----------|-------------|
| `question` | Need user input/clarification | Show questions with option buttons |
| `proposal` | Suggesting CV changes | Show preview with accept/reject |
| `confirmation` | Awaiting user approval | Show confirmation dialog |
| `status_update` | Progress update (e.g., "Processing...") | Show status message, no action needed |
| `error` | Validation/processing error | Show error alert with details |
| `completion` | Task finished (PDF ready) | Show success + download button |

---

## Example Responses

### 1. Asking Clarifying Questions

```json
{
  "response_type": "question",
  "user_message": {
    "text": "I need a few details before preparing your CV:",
    "sections": [],
    "questions": [
      {
        "id": "q1",
        "question": "Should I use your contact details from the DOCX?",
        "options": ["Yes", "No, I'll provide different contact info"]
      },
      {
        "id": "q2",
        "question": "Target CV length?",
        "options": ["1 page (concise)", "2 pages (detailed)"]
      }
    ]
  },
  "metadata": {
    "response_id": "resp_abc123",
    "timestamp": "2026-01-25T20:30:00Z",
    "model_reasoning": "Need user confirmation on contact info and CV length before proceeding with data transfer from prefill.",
    "confidence": "high",
    "validation_status": {
      "schema_valid": true,
      "page_count_ok": false,
      "required_fields_present": false,
      "issues": ["work_experience empty", "education empty"]
    }
  },
  "refusal": null
}
```

### 2. Proposing CV Updates

```json
{
  "response_type": "proposal",
  "user_message": {
    "text": "I'll prepare your CV with the following changes:",
    "sections": [
      {
        "title": "Contact Information",
        "content": "Using: Mariusz Horodecki, horodecki.mariusz@gmail.com, +41 77 952 24 37",
        "type": "info"
      },
      {
        "title": "Work Experience",
        "content": "Transferring 5 positions from your DOCX:\n- GL Solutions (2020-2025)\n- Expondo Polska (2018-2020)\n- SE Bordnetze (2016-2018)\n- Sumitomo Electric (2011-2016)\n- Imbodden AG (2025)",
        "type": "proposal"
      },
      {
        "title": "Education",
        "content": "Adding 2 degrees from Poznań University of Technology",
        "type": "proposal"
      }
    ],
    "questions": []
  },
  "metadata": {
    "response_id": "resp_def456",
    "timestamp": "2026-01-25T20:35:00Z",
    "model_reasoning": "User confirmed they want a 2-page CV. Proposing to transfer all prefill data to cv_data.",
    "confidence": "high",
    "validation_status": {
      "schema_valid": true,
      "page_count_ok": true,
      "required_fields_present": false,
      "issues": ["Pending data transfer"]
    }
  },
  "refusal": null
}
```

### 3. PDF Generation Complete

```json
{
  "response_type": "completion",
  "user_message": {
    "text": "Your CV is ready!",
    "sections": [
      {
        "title": "PDF Generated",
        "content": "Successfully created 2-page CV tailored for Project Manager (technical) role",
        "type": "success"
      },
      {
        "title": "Validation",
        "content": "✓ All required fields present\n✓ Fits in 2 pages (1.94 pages estimated)\n✓ ATS-compliant format",
        "type": "success"
      }
    ],
    "questions": []
  },
  "metadata": {
    "response_id": "resp_ghi789",
    "timestamp": "2026-01-25T20:40:00Z",
    "model_reasoning": "All required fields confirmed, validation passed, PDF generation successful.",
    "confidence": "high",
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

### 4. Validation Error

```json
{
  "response_type": "error",
  "user_message": {
    "text": "I found some issues that need fixing before generating your PDF:",
    "sections": [
      {
        "title": "Missing Information",
        "content": "• Work experience is empty\n• Education is empty",
        "type": "warning"
      },
      {
        "title": "Next Steps",
        "content": "Would you like me to transfer the data from your DOCX prefill?",
        "type": "question"
      }
    ],
    "questions": [
      {
        "id": "fix_missing",
        "question": "How should I proceed?",
        "options": [
          "Transfer all data from DOCX",
          "I'll provide the information manually",
          "Let me upload a different CV"
        ]
      }
    ]
  },
  "metadata": {
    "response_id": "resp_jkl012",
    "timestamp": "2026-01-25T20:38:00Z",
    "model_reasoning": "User requested PDF generation but validation failed due to missing required fields.",
    "confidence": "high",
    "validation_status": {
      "schema_valid": true,
      "page_count_ok": false,
      "required_fields_present": false,
      "issues": [
        "work_experience: required but empty",
        "education: required but empty"
      ]
    }
  },
  "refusal": null
}
```

---

## Backend Processing Flow

```
1. Model returns structured JSON (validated against schema)
      ↓
2. Backend parses response
  ↓
3. Route by response_type:
   - question      → Return user_message to UI, wait for answers
   - proposal      → Show preview, wait for confirmation
   - confirmation  → Wait for explicit user approval (backend-owned)
   - status_update → Display progress, continue workflow
   - error         → Show errors, provide recovery options
   - completion    → PDF already generated (or ready) per backend state
      ↓
4. Tools are executed via native tool-calling (not embedded in JSON)
  ↓
5. Update session with metadata
      ↓
6. Return to UI:
   {
     "assistant_text": user_message.text + formatted sections,
     "pdf_base64": (if completion),
     "metadata": response metadata,
     "questions": user_message.questions (if any)
   }
```

---

## Implementation Checklist

- [ ] Add `response_format` parameter to OpenAI API calls
- [ ] Create Pydantic models matching schema (for type safety)
- [ ] Update `_run_responses_tool_loop_v2()` to enforce structured output
- [ ] Add response parser in backend
- [ ] Update UI to handle multi-section responses
- [ ] Add logging for metadata tracking
- [ ] Test all response types
- [ ] Update OpenAI prompt to use structured format

---

**References:**
- [OpenAI Structured Outputs Cookbook](https://cookbook.openai.com/examples/structured_outputs_intro)
- [Azure OpenAI Structured Outputs Guide](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs)
