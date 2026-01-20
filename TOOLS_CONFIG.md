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
  "description": "Validates extracted CV data structure and content",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "full_name": {
        "type": "string",
        "description": "Full name"
      },
      "email": {
        "type": "string",
        "description": "Email address"
      },
      "phone": {
        "type": "string",
        "description": "Phone number"
      },
      "address_lines": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Address lines"
      },
      "profile": {
        "type": "string",
        "description": "Professional profile/summary"
      },
      "work_experience": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "company": { "type": "string" },
            "position": { "type": "string" },
            "start_date": { "type": "string" },
            "end_date": { "type": "string" },
            "description": { "type": "string" }
          }
        },
        "description": "Work experience"
      },
      "education": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "school": { "type": "string" },
            "degree": { "type": "string" },
            "field": { "type": "string" },
            "start_date": { "type": "string" },
            "end_date": { "type": "string" }
          }
        },
        "description": "Education"
      }
    },
    "required": ["full_name", "email", "phone", "address_lines", "profile"],
    "additionalProperties": false
  }
}
```

---

## Tool 3: generate_cv_action

```json
{
  "name": "generate_cv_action",
  "description": "Generates a professional PDF CV from extracted and validated data",
  "strict": false,
  "parameters": {
    "type": "object",
    "properties": {
      "full_name": {
        "type": "string",
        "description": "Full name"
      },
      "email": {
        "type": "string",
        "description": "Email address"
      },
      "phone": {
        "type": "string",
        "description": "Phone number"
      },
      "address_lines": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Address lines"
      },
      "profile": {
        "type": "string",
        "description": "Professional profile/summary"
      },
      "work_experience": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "company": { "type": "string" },
            "position": { "type": "string" },
            "start_date": { "type": "string" },
            "end_date": { "type": "string" },
            "description": { "type": "string" }
          }
        },
        "description": "Work experience"
      },
      "education": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "school": { "type": "string" },
            "degree": { "type": "string" },
            "field": { "type": "string" },
            "start_date": { "type": "string" },
            "end_date": { "type": "string" }
          }
        },
        "description": "Education"
      },
      "language": {
        "type": "string",
        "enum": ["pl", "en", "de"],
        "description": "Output language for CV"
      },
      "source_docx_base64": {
        "type": "string",
        "description": "Optional: Base64 encoded DOCX file for photo extraction"
      }
    },
    "required": ["full_name", "email", "phone", "address_lines", "profile", "language"],
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
extract_photo → POST /api/extract-photo
validate_cv → POST /api/validate-cv  
generate_cv_action → POST /api/generate-cv-action
```

All requests include `x-functions-key` header with the Azure Functions key.
Backend returns results which OpenAI uses to continue the conversation.
