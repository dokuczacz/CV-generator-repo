# CV Generator - Tools Configuration for OpenAI Dashboard

Dodaj te tools do prompta w OpenAI: https://platform.openai.com/assistants

**Instrukcja:** 
1. Otwórz swój prompt/asystenta
2. Wejdź w sekcję "Tools"
3. Kliknij "Add tool" → "Function"
4. Skopiuj cały JSON każdego tool-a poniżej i wklej

---

## Tool 1: extract_photo

```json
{
  "name": "extract_photo",
  "description": "Extracts photo from a DOCX CV file",
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

## Tool 2: validate_cv

```json
{
  "name": "validate_cv",
  "description": "Validates the extracted CV data structure and content against strict 2-page constraints. Call this BEFORE generate_cv_action to ensure the data will produce a valid PDF.",
  "strict": true,
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

## Tool 3: generate_cv_action

```json
{
  "name": "generate_cv_action",
  "description": "Generates a professional PDF CV from the extracted and validated CV data. IMPORTANT: You MUST include the complete cv_data object (with all fields: full_name, email, phone, work_experience, education, etc.) that you showed to the user in Stage 2. Do NOT call this function with an empty cv_data or only language/source_docx_base64.",
  "strict": true,
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

Backend receives tool calls from OpenAI and routes them:

```
extract_photo → POST /api/extract-photo (expects `{ docx_base64 }`)
validate_cv → POST /api/validate-cv (expects `{ cv_data: { ... } }`)
generate_cv_action → POST /api/generate-cv-action (expects `{ cv_data: { ... }, source_docx_base64?, debug_allow_pages? }`)
```

All requests include `x-functions-key` header with the Azure Functions key.
Backend returns results which OpenAI uses to continue the conversation.
