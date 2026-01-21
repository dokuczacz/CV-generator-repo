# CV Generator - Tools Configuration for OpenAI Dashboard

**UPDATED:** Session-based workflow (Phases 1-3 implemented)

Dodaj te tools do prompta w OpenAI: https://platform.openai.com/assistants

**Instrukcja:** 
1. Otwórz swój prompt/asystenta
2. Wejdź w sekcję "Tools"
3. Kliknij "Add tool" → "Function"
4. Skopiuj cały JSON każdego tool-a poniżej i wklej

---

## **NEW SESSION-BASED WORKFLOW** (Recommended)

### Tool 1: extract_and_store_cv

```json
{
  "name": "extract_and_store_cv",
  "description": "Extracts CV data from uploaded DOCX and stores it in a session. This is the FIRST tool to call when user uploads a CV. Returns a session_id that you use for all subsequent operations. The CV data persists in the session, so you don't need to maintain it in conversation context.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "docx_base64": {
        "type": "string",
        "description": "Base64 encoded DOCX file content"
      },
      "language": {
        "type": "string",
        "enum": ["en", "de", "pl"],
        "description": "CV language (default: en)"
      },
      "extract_photo": {
        "type": "boolean",
        "description": "Whether to extract photo from DOCX (default: true)"
      }
    },
    "required": ["docx_base64"],
    "additionalProperties": false
  }
}
```

### Tool 2: get_cv_session

```json
{
  "name": "get_cv_session",
  "description": "Retrieves CV data from session. Use this to check what CV data is currently stored, or to show user a summary of extracted data.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "Session identifier returned by extract_and_store_cv"
      }
    },
    "required": ["session_id"],
    "additionalProperties": false
  }
}
```

### Tool 3: update_cv_field

```json
{
  "name": "update_cv_field",
  "description": "Updates a specific field in the CV session. Use this when user wants to edit CV data (e.g., fix a name, add work experience, change language level). Supports nested paths like 'work_experience[0].employer'.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "Session identifier"
      },
      "field_path": {
        "type": "string",
        "description": "Dot-notation path to field (e.g., 'full_name', 'work_experience[0].employer', 'languages[2].proficiency')"
      },
      "value": {
        "description": "New value for the field (can be string, number, array, object)"
      }
    },
    "required": ["session_id", "field_path", "value"],
    "additionalProperties": false
  }
}
```

### Tool 4: generate_cv_from_session

```json
{
  "name": "generate_cv_from_session",
  "description": "Generates PDF from CV data stored in session. This replaces the old generate_cv_action tool. Call this after user confirms the CV data is correct.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "Session identifier"
      },
      "language": {
        "type": "string",
        "enum": ["en", "de", "pl"],
        "description": "Optional: Override language from session metadata"
      }
    },
    "required": ["session_id"],
    "additionalProperties": false
  }
}
```

### Tool 5: process_cv_orchestrated (Phase 3 - Single-Call Workflow)

```json
{
  "name": "process_cv_orchestrated",
  "description": "Orchestrated CV processing - handles extraction, edits, validation, and PDF generation in a single call. Use this for streamlined workflow when you have all the information ready.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "Optional: Use existing session instead of creating new one"
      },
      "docx_base64": {
        "type": "string",
        "description": "Required if no session_id: Base64 encoded DOCX file"
      },
      "language": {
        "type": "string",
        "enum": ["en", "de", "pl"],
        "description": "CV language (default: en)"
      },
      "edits": {
        "type": "array",
        "description": "Optional: Array of field edits to apply before generating PDF",
        "items": {
          "type": "object",
          "properties": {
            "field_path": {
              "type": "string",
              "description": "Field path (e.g., 'full_name', 'work_experience[0].title')"
            },
            "value": {
              "description": "New value for the field"
            }
          },
          "required": ["field_path", "value"]
        }
      },
      "extract_photo": {
        "type": "boolean",
        "description": "Whether to extract photo (default: true)"
      }
    },
    "additionalProperties": false
  }
}
```

---

## **LEGACY WORKFLOW** (Still supported, but session-based is preferred)

### Tool 1: extract_photo

```json
{
  "name": "extract_photo",
  "description": "Extracts the first embedded photo from a DOCX CV file. You MUST copy the returned photo_data_uri into cv_data.photo_url (data URI) before calling validate_cv or generate_cv_action.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "docx_base64": {
        "type": "string",
        "description": "Base64 encoded DOCX file content"
      }
    },
    "required": ["docx_base64"],
    "additionalProperties": false
  }
}
```

---

### Legacy Tool 2: validate_cv

```json
{
  "name": "validate_cv",
  "description": "[LEGACY] Validates CV data structure. Use generate_cv_from_session instead for new workflows.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "cv_data": {
        "type": "object",
        "description": "REQUIRED: The complete canonical CV JSON object you extracted from the user's CV. Must include all required fields with actual data.",
        "properties": {
          "full_name": { "type": "string" },
          "email": { "type": "string" },
          "phone": { "type": "string" },
          "address_lines": { "type": "array", "items": { "type": "string" } },
          "profile": { "type": "string" },
          "nationality": { "type": "string" },
          "work_experience": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "date_range": { "type": "string" },
                "employer": { "type": "string" },
                "location": { "type": "string" },
                "title": { "type": "string" },
                "bullets": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["date_range", "employer", "title", "bullets"],
              "additionalProperties": false
            }
          },
          "education": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "date_range": { "type": "string" },
                "institution": { "type": "string" },
                "title": { "type": "string" },
                "details": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["date_range", "institution", "title", "details"],
              "additionalProperties": false
            }
          },
          "further_experience": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "date_range": { "type": "string" },
                "organization": { "type": "string" },
                "title": { "type": "string" },
                "bullets": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["date_range", "organization", "title", "bullets"],
              "additionalProperties": false
            }
          },
          "languages": {
            "type": "array",
            "items": {
              "anyOf": [
                { "type": "string" },
                {
                  "type": "object",
                  "properties": {
                    "language": { "type": "string" },
                    "level": { "type": "string" }
                  },
                  "required": ["language", "level"],
                  "additionalProperties": false
                }
              ]
            }
          },
          "it_ai_skills": { "type": "array", "items": { "type": "string" } },
          "certifications": { "type": "array", "items": { "type": "string" } },
          "trainings": { "type": "array", "items": { "type": "string" } },
          "publications": { "type": "array", "items": { "type": "string" } },
          "interests": {
            "anyOf": [
              { "type": "string" },
              { "type": "array", "items": { "type": "string" } }
            ]
          },
          "references": { "type": "array", "items": { "type": "string" } },
          "data_privacy": { "type": "string" },
          "photo_url": { "type": "string" },
          "language": { "type": "string", "enum": ["pl", "en", "de"] }
        },
        "required": [
          "full_name",
          "email",
          "phone",
          "address_lines",
          "profile",
          "work_experience",
          "education",
          "languages",
          "it_ai_skills",
          "certifications",
          "interests",
          "publications",
          "further_experience",
          "references",
          "photo_url",
          "language"
        ],
        "additionalProperties": false
      }
    },
    "required": ["cv_data"],
    "additionalProperties": false
  }
}
```

---

### Legacy Tool 3: generate_cv_action

```json
{
  "name": "generate_cv_action",
  "description": "[LEGACY] Generates PDF from CV data. CRITICAL: cv_data must use canonical schema (full_name, email, phone, work_experience, education). DO NOT send wrong keys like personal_info or employment_history. Use generate_cv_from_session for new workflows.",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "cv_data": {
        "type": "object",
        "description": "REQUIRED: The complete, confirmed canonical CV JSON object (same object you presented to the user in Stage 2). Must include all fields with actual data.",
        "properties": {
          "full_name": { "type": "string", "description": "Full name of the candidate" },
          "email": { "type": "string", "description": "Email address" },
          "phone": { "type": "string", "description": "Phone number" },
          "address_lines": { "type": "array", "items": { "type": "string" }, "description": "Address lines" },
          "profile": { "type": "string", "description": "Professional summary/profile (100-400 chars)" },
          "nationality": { "type": "string", "description": "Nationality" },
          "work_experience": {
            "type": "array",
            "description": "Work experience entries",
            "items": {
              "type": "object",
              "properties": {
                "date_range": { "type": "string" },
                "employer": { "type": "string" },
                "location": { "type": "string" },
                "title": { "type": "string" },
                "bullets": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["date_range", "employer", "title", "bullets"],
              "additionalProperties": false
            }
          },
          "education": {
            "type": "array",
            "description": "Education entries",
            "items": {
              "type": "object",
              "properties": {
                "date_range": { "type": "string" },
                "institution": { "type": "string" },
                "title": { "type": "string" },
                "details": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["date_range", "institution", "title"],
              "additionalProperties": false
            }
          },
          "further_experience": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "date_range": { "type": "string" },
                "organization": { "type": "string" },
                "title": { "type": "string" },
                "bullets": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["date_range", "organization", "title"],
              "additionalProperties": false
            }
          },
          "languages": {
            "type": "array",
            "items": {
              "anyOf": [
                { "type": "string" },
                {
                  "type": "object",
                  "properties": {
                    "language": { "type": "string" },
                    "level": { "type": "string" }
                  },
                  "required": ["language", "level"],
                  "additionalProperties": false
                }
              ]
            }
          },
          "it_ai_skills": { "type": "array", "items": { "type": "string" } },
          "certifications": { "type": "array", "items": { "type": "string" } },
          "trainings": { "type": "array", "items": { "type": "string" } },
          "publications": { "type": "array", "items": { "type": "string" } },
          "interests": {
            "anyOf": [
              { "type": "string" },
              { "type": "array", "items": { "type": "string" } }
            ]
          },
          "references": { "type": "array", "items": { "type": "string" } },
          "data_privacy": { "type": "string" },
          "photo_url": { "type": "string" },
          "language": { "type": "string", "enum": ["pl", "en", "de"] }
        },
        "required": [
          "full_name",
          "email",
          "phone",
          "address_lines",
          "profile",
          "work_experience",
          "education",
          "languages",
          "language"
        ],
        "additionalProperties": true
      },
      "source_docx_base64": {
        "type": "string",
        "description": "Optional: Base64 encoded DOCX file for photo extraction (server will fill photo_url if possible)"
      },
      "debug_allow_pages": {
        "type": "boolean",
        "description": "Optional: Set true to allow PDFs that are not exactly 2 pages (debug only)"
      }
    },
    "required": ["cv_data"],
    "additionalProperties": false
  }
}
```

---

## System Prompt

Użyj tej instrukcji w sekcji "System prompt" twojego asystenta:

```
You are a professional CV processing assistant. Your task is to:

1. Extract key information from the CV (full name, email, phone, address, profile, work experience, education)
2. If a DOCX file is provided, use the extract_photo tool to extract any photo
3. Validate the extracted data using the validate_cv tool
4. Generate a professional PDF CV using the generate_cv_action tool

Important workflow:
- First, ALWAYS use extract_photo tool to process the DOCX if provided
- Then extract all text/information from CV content
- Validate the data structure with validate_cv tool  
- Finally, generate the PDF with generate_cv_action tool with ALL extracted information

Extract COMPLETE information:
- Basic information: full name, email, phone, complete address
- Professional profile/summary
- Work experience with company, position, dates, descriptions
- Education with school, degree, field, dates

Be thorough and maintain accuracy. Process step by step using the tools.
```

---

## How to Configure in OpenAI Dashboard

1. Go to: https://platform.openai.com/assistants
2. Create or edit a prompt/assistant
3. Add these 3 tools by clicking "Add Tool" → "Function"
4. For each tool:
   - Copy the **name** (extract_photo, validate_cv, generate_cv_action)
   - Copy the **description**
   - Copy the **webhook URL** (important!)
   - Paste the **parameters schema**
5. Update your system prompt with the workflow instructions above

---

## Backend Implementation

**NEW Session-Based Endpoints:**
```
extract_and_store_cv → POST /api/extract-and-store-cv
get_cv_session → GET/POST /api/get-cv-session
update_cv_field → POST /api/update-cv-field
generate_cv_from_session → POST /api/generate-cv-from-session
process_cv_orchestrated → POST /api/process-cv-orchestrated
```

**Legacy Endpoints (still supported):**
```
extract_photo → POST /api/extract-photo
validate_cv → POST /api/validate-cv
generate_cv_action → POST /api/generate-cv-action
```

**Phase 1 Improvements:** Backend now validates schema and rejects wrong keys (personal_info, employment_history, etc.) with helpful error messages showing canonical schema.

**Phase 2 Benefits:** CV data stored in Azure Table Storage; agent maintains only session_id instead of full CV JSON in conversation context.

**Phase 3 Capabilities:** Single orchestrated endpoint handles full workflow (extract → edit → validate → generate) in one call.

All requests include authentication headers. Backend returns results which OpenAI uses to continue the conversation.

---

## Recommended Workflow

### New Session-Based Workflow (Preferred)

1. **User uploads CV:**
   - Call `extract_and_store_cv(docx_base64, language="en")`
   - Get back `session_id` and summary
   - Show user what was extracted

2. **User makes edits:**
   - Call `update_cv_field(session_id, field_path="full_name", value="John Doe")`
   - Repeat for each field user wants to change

3. **User confirms:**
   - Call `generate_cv_from_session(session_id)`
   - Return PDF to user

**Alternative: One-Shot Workflow (Phase 3)**

- Call `process_cv_orchestrated(docx_base64, edits=[...], language="en")`
- Get back PDF immediately with session_id for future edits
