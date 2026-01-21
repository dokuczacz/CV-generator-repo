# OpenAI Dashboard Manual Update — Step-by-Step

**Date:** 2026-01-21
**Status:** Ready for manual update

---

## What Changed

**Updated TOOLS_CONFIG.md with:**
1. **Tool descriptions** now emphasize `cv_data` is REQUIRED (not optional)
2. **Schema** enforced `strict: false` with all properties in `required` array
3. **Clear warnings** in generate_cv_action: "Do NOT call with only source_docx_base64 + language"

**Important clarification (photo):**
- Photo extraction is a separate tool (`extract_photo`). Its output (`photo_data_uri`) must be placed into `cv_data.photo_url` before calling `validate_cv` / `generate_cv_action`.

---

## Step-by-Step Manual Update

### Step 1: Go to OpenAI Assistants Dashboard
1. Open: https://platform.openai.com/assistants
2. Find your CV Generator assistant/prompt
3. Click **Edit**

### Step 2: Update Tool 0 — `extract_photo`

In the **Functions** section, find or add **extract_photo** function:

1. Click **Add tool** → **Function** (if not already present)
2. **Name:** `extract_photo`
3. **Description:** Replace with:
   ```
   Extracts the first embedded photo from a DOCX CV file.
   Output photo_data_uri MUST be copied into cv_data.photo_url (data URI) for Stage 2 confirmation and Stage 3 PDF generation.
   ```
4. **Strict mode:** OFF (unchecked)
5. **Parameters (JSON Schema):** Copy the entire JSON below:

```json
{
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
```

6. Click **Save**

---

### Step 3: Update Tool 1 — `validate_cv`

In the **Functions** section, find or add **validate_cv** function:

1. Click **Add tool** → **Function** (if not already present)
2. **Name:** `validate_cv`
3. **Description:** Replace with:
   ```
   Validates the extracted CV data structure and content against strict 2-page constraints. 
   Call this BEFORE generate_cv_action to ensure the data will produce a valid PDF. 
   The cv_data parameter MUST contain the complete CV JSON object you extracted from the user's CV.
   ```
4. **Strict mode:** OFF (unchecked)
5. **Parameters (JSON Schema):** Copy the entire JSON below:

```json
{
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
```

6. Click **Save**

---

### Step 4: Update Tool 2 — `generate_cv_action`

In the **Functions** section, find or add **generate_cv_action** function:

1. Click **Add tool** → **Function** (if not already present)
2. **Name:** `generate_cv_action`
3. **Description:** Replace with:
   ```
   Generates a professional PDF CV from the extracted and validated CV data. 
   CRITICAL REQUIREMENT: The cv_data parameter MUST contain the complete CV JSON object 
   (with full_name, email, phone, profile, work_experience, education, languages, etc.) 
   that you presented to the user in Stage 2. Do NOT call this function with only 
   source_docx_base64 and language parameters - you MUST include the cv_data field 
   with all CV content.
   ```
4. **Strict mode:** OFF (unchecked)
5. **Parameters (JSON Schema):** Copy the entire JSON below:

```json
{
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
            "required": ["date_range", "institution", "title", "details"],
            "additionalProperties": false
          }
        },
        "further_experience": {
          "type": "array",
          "description": "Further experience entries",
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
          "description": "Languages and proficiency levels",
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
        "it_ai_skills": {
          "type": "array",
          "description": "IT and AI skills",
          "items": { "type": "string" }
        },
        "certifications": {
          "type": "array",
          "description": "Certifications",
          "items": { "type": "string" }
        },
        "trainings": {
          "type": "array",
          "description": "Trainings",
          "items": { "type": "string" }
        },
        "publications": {
          "type": "array",
          "description": "Publications",
          "items": { "type": "string" }
        },
        "interests": {
          "description": "Personal interests",
          "anyOf": [
            { "type": "string" },
            { "type": "array", "items": { "type": "string" } }
          ]
        },
        "references": {
          "type": "array",
          "description": "References",
          "items": { "type": "string" }
        },
        "data_privacy": {
          "type": "string",
          "description": "Data privacy consent text"
        },
        "photo_url": {
          "type": "string",
          "description": "Photo as data URI (base64)"
        },
        "language": {
          "type": "string",
          "enum": ["pl", "en", "de"],
          "description": "Output language for CV"
        },
        "theme": {
          "type": "string",
          "enum": ["zurich", "default"],
          "description": "Visual theme for CV"
        },
        "debug_allow_pages": {
          "type": "boolean",
          "description": "DEBUG ONLY: Allow PDFs >2 pages (false=strict 2-page requirement)"
        }
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
```

6. Click **Save**

---

### Step 5: Verify System Prompt

1. Go to **System Prompt** section
2. Confirm it includes the 3-stage workflow:
   - **Stage 1:** Extract CV from DOCX
   - **Stage 2:** Confirm extracted data with user
   - **Stage 3:** Validate & generate PDF ONLY after user says "proceed"
3. Confirm instruction: "Store this JSON internally — you will send this EXACT JSON object to validate_cv and generate_cv_action in Stage 3"
4. Click **Save**

---

### Step 6: Verify Knowledge/Instructions Files

1. In **Knowledge** or **Instructions** section, ensure:
   - [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) is uploaded
   - [DATA_DICTIONARY.md](DATA_DICTIONARY.md) is uploaded (newly created)
2. Click **Save**

---

## After Update: Quick Verification

1. **Test in Playground:**
   - Upload a CV file
   - Proceed through Stage 1 → Stage 2
  - In Stage 1, confirm the model calls `extract_photo` (DOCX → photo_data_uri)
  - Confirm Stage 2 JSON includes `photo_url` populated with the returned `photo_data_uri`
   - In Stage 3, verify the model's tool call includes:
     - `cv_data` object with all fields
     - NOT just `source_docx_base64 + language`

2. **Expected Tool Call:**
   ```json
   {
     "name": "generate_cv_action",
     "arguments": {
       "cv_data": {
         "full_name": "John Doe",
         "email": "john@example.com",
         "phone": "+1 555 0123",
         "address_lines": ["123 Main St", "USA"],
         "profile": "...",
         "work_experience": [...],
         "education": [...],
         "languages": [...],
         ...
       }
     }
   }
   ```

3. **If still missing cv_data:**
   - Check that generate_cv_action description was updated with CRITICAL warning
   - Verify `cv_data` is in `required` array (not optional)
   - Regenerate or refresh the prompt in OpenAI dashboard

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Model still omits cv_data | Verify cv_data is in `required` array; check tool description has CRITICAL note |
| PDF generation fails | Check cv_data in tool arguments via Playground test run |
| Schema validation errors | Ensure `"strict": false` on both validate_cv and generate_cv_action |
| Address showing >2 lines | Verify address_lines constraint: max 2 items (not 3) |

---

## Related Documents

- [TOOLS_CONFIG.md](TOOLS_CONFIG.md) — Full tool schema reference
- [DATA_DICTIONARY.md](DATA_DICTIONARY.md) — Field constraints & validation rules
- [PROMPT_INSTRUCTIONS.md](PROMPT_INSTRUCTIONS.md) — Workflow description
- [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md) — System prompt for dashboard
