# CV Schema Requirements

Complete JSON schema definition for CV data validation.

**Source:** [../../../DATA_DICTIONARY.md](../../../DATA_DICTIONARY.md)

---

## Quick Reference

### Required Fields
```json
{
  "firstName": "string (1-50 chars)",
  "lastName": "string (1-50 chars)",
  "email": "string (valid email format)",
  "phone": "string (5-30 chars)",
  "address": "string (1-120 chars)",
  "professionalTitle": "string (1-100 chars)"
}
```

### Optional But Recommended
```json
{
  "photo_url": "string (base64 data URI, ≤32KB)",
  "languages": [{"language": "string", "level": "string"}],
  "skills": ["string"],
  "experience": [{"position": "string", "company": "string", ...}],
  "education": [{"degree": "string", "institution": "string", ...}]
}
```

---

## Complete Schema

### Personal Information

**firstName**
- Type: `string`
- Required: YES
- Constraints: 1-50 chars, non-empty
- Example: `"John"`

**lastName**
- Type: `string`
- Required: YES
- Constraints: 1-50 chars, non-empty
- Example: `"Doe"`

**email**
- Type: `string`
- Required: YES
- Constraints: Valid email format (RFC 5322), max 100 chars
- Example: `"john.doe@example.com"`

**phone**
- Type: `string`
- Required: YES
- Constraints: 5-30 chars, international format preferred
- Example: `"+41 77 952 24 37"`

**address**
- Type: `string`
- Required: YES
- Constraints: 1-120 chars
- Example: `"Zer Chirchu 20, Switzerland"`

**professionalTitle**
- Type: `string`
- Required: YES
- Constraints: 1-100 chars
- Example: `"Senior Full-Stack Developer"`

**photo_url**
- Type: `string | null`
- Required: NO
- Constraints: Base64 data URI, ≤32KB (Azure Table Storage limit)
- Format: `"data:image/png;base64,..."`
- Example: `"data:image/png;base64,iVBORw0KGgoAAAANS..."`
- Notes: If exceeds 32KB, store in blob storage instead

---

### Experience

**experience**
- Type: `array[object]`
- Required: NO (but recommended, ≥1 entry)
- Structure:
  ```json
  {
    "position": "string (required, 1-100 chars)",
    "company": "string (required, 1-100 chars)",
    "location": "string (optional, max 50 chars)",
    "startDate": "string (ISO format YYYY-MM-DD) | null",
    "endDate": "string (ISO format YYYY-MM-DD) | null (null = present)",
    "responsibilities": ["string (max 90 chars each)"]
  }
  ```

**Constraints:**
- `responsibilities`: Array of strings, each ≤90 chars
- `startDate` ≤ `endDate` (if both present)
- Dates in ISO 8601 format: `YYYY-MM-DD`

**Example:**
```json
{
  "position": "Senior Backend Developer",
  "company": "Tech Corp",
  "location": "Zurich, Switzerland",
  "startDate": "2020-01-15",
  "endDate": null,
  "responsibilities": [
    "Led team of 5 engineers in microservices migration",
    "Reduced API latency by 40% through caching optimization",
    "Implemented CI/CD pipeline reducing deployment time by 60%"
  ]
}
```

---

### Education

**education**
- Type: `array[object]`
- Required: NO (but recommended, ≥1 entry)
- Structure:
  ```json
  {
    "degree": "string (required, 1-100 chars)",
    "institution": "string (required, 1-100 chars)",
    "location": "string (optional, max 50 chars)",
    "startDate": "string (ISO format YYYY-MM-DD) | null",
    "endDate": "string (ISO format YYYY-MM-DD) | null",
    "description": "string (optional, max 200 chars)"
  }
  ```

**Example:**
```json
{
  "degree": "Master of Science in Computer Science",
  "institution": "ETH Zurich",
  "location": "Zurich, Switzerland",
  "startDate": "2015-09-01",
  "endDate": "2017-08-31",
  "description": "Thesis: Distributed Systems Optimization"
}
```

---

### Skills & Languages

**skills**
- Type: `array[string]`
- Required: NO
- Constraints: Each string ≤50 chars
- Example: `["Python", "TypeScript", "React", "Docker", "AWS"]`

**languages**
- Type: `array[object]`
- Required: NO
- Structure:
  ```json
  {
    "language": "string (required, 1-30 chars)",
    "level": "string (required, 1-20 chars)"
  }
  ```
- Common levels: "Native", "Fluent", "Professional", "Intermediate", "Basic"
- Example:
  ```json
  [
    {"language": "English", "level": "Fluent"},
    {"language": "German", "level": "Professional"},
    {"language": "Polish", "level": "Native"}
  ]
  ```

---

### Certifications

**certifications**
- Type: `array[object]`
- Required: NO
- Structure:
  ```json
  {
    "name": "string (required, 1-100 chars)",
    "issuer": "string (optional, max 50 chars)",
    "date": "string (ISO format YYYY-MM-DD) | null"
  }
  ```

**Example:**
```json
{
  "name": "AWS Certified Solutions Architect",
  "issuer": "Amazon Web Services",
  "date": "2023-05-15"
}
```

---

## Size Constraints Summary

| Field | Max Size | Reason |
|-------|----------|--------|
| photo_url | 32KB | Azure Table Storage property limit (64KB, use margin) |
| Experience bullet | 90 chars | Template line limit, readability |
| Skill name | 50 chars | Template space allocation |
| Total content | ~2 pages | Template constraint (see layout estimation) |

---

## Validation Levels

### Level 1: Syntax (JSON validity)
- Valid JSON structure
- No syntax errors
- UTF-8 encoding

### Level 2: Schema (Field types and presence)
- Required fields present
- Field types match expectations
- No unknown fields (warning only)

### Level 3: Constraints (Size and format)
- photo_url ≤32KB
- Bullets ≤90 chars
- Dates in ISO format
- Email format valid

### Level 4: Business Rules (API validation)
- Dates chronologically ordered
- No duplicate entries
- Language-specific constraints
- ATS compliance (if --strict)

### Level 5: Layout (2-page fit)
- Content estimation
- Section overflow detection
- Language-specific spacing

---

## JSON Schema (JSON Schema Draft 7)

For programmatic validation, use this JSON Schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["firstName", "lastName", "email", "phone", "address", "professionalTitle"],
  "properties": {
    "firstName": {"type": "string", "minLength": 1, "maxLength": 50},
    "lastName": {"type": "string", "minLength": 1, "maxLength": 50},
    "email": {"type": "string", "format": "email", "maxLength": 100},
    "phone": {"type": "string", "minLength": 5, "maxLength": 30},
    "address": {"type": "string", "minLength": 1, "maxLength": 120},
    "professionalTitle": {"type": "string", "minLength": 1, "maxLength": 100},
    "photo_url": {"type": ["string", "null"], "maxLength": 32768},
    "skills": {
      "type": "array",
      "items": {"type": "string", "maxLength": 50}
    },
    "languages": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["language", "level"],
        "properties": {
          "language": {"type": "string", "maxLength": 30},
          "level": {"type": "string", "maxLength": 20}
        }
      }
    },
    "experience": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["position", "company"],
        "properties": {
          "position": {"type": "string", "maxLength": 100},
          "company": {"type": "string", "maxLength": 100},
          "location": {"type": "string", "maxLength": 50},
          "startDate": {"type": ["string", "null"], "format": "date"},
          "endDate": {"type": ["string", "null"], "format": "date"},
          "responsibilities": {
            "type": "array",
            "items": {"type": "string", "maxLength": 90}
          }
        }
      }
    },
    "education": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["degree", "institution"],
        "properties": {
          "degree": {"type": "string", "maxLength": 100},
          "institution": {"type": "string", "maxLength": 100},
          "location": {"type": "string", "maxLength": 50},
          "startDate": {"type": ["string", "null"], "format": "date"},
          "endDate": {"type": ["string", "null"], "format": "date"},
          "description": {"type": "string", "maxLength": 200}
        }
      }
    },
    "certifications": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name"],
        "properties": {
          "name": {"type": "string", "maxLength": 100},
          "issuer": {"type": "string", "maxLength": 50},
          "date": {"type": ["string", "null"], "format": "date"}
        }
      }
    }
  }
}
```

---

## Related Files

- [../../../DATA_DICTIONARY.md](../../../DATA_DICTIONARY.md) - Complete field definitions
- [../../../src/schema_validator.py](../../../src/schema_validator.py) - Python validation implementation
- [ats-compliance.md](ats-compliance.md) - ATS-specific requirements
- [layout-constraints.md](layout-constraints.md) - 2-page template constraints