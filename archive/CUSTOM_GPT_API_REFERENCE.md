# CV_Dopasowywacz v4.2 - API Reference

Complete API documentation for Custom GPT integration.

---

## Base URL

```
https://cv-generator-6695.azurewebsites.net/api
```

---

## Endpoint 1: Health Check

**Test if backend is running**

```http
GET /health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "CV Generator API",
  "version": "1.0"
}
```

**Usage**:
```python
response = requests.get("https://cv-generator-6695.azurewebsites.net/api/health")
if response.status_code == 200:
    print("✓ Backend is operational")
```

---

## Endpoint 2: Validate CV

**Validate CV data structure before rendering**

```http
POST /validate-cv
Content-Type: application/json

{
  "cv_data": {
    "full_name": "John Doe",
    "email": "john@example.com",
    "address_lines": ["Zurich, Switzerland"],
    "profile": "Professional summary...",
    "work_experience": [...],
    "education": [...]
  }
}
```

**Response** (200 OK):
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": [
    "Profile is quite long (350 chars, recommended: 250)"
  ],
  "estimated_pages": 2
}
```

**Response** (400 Bad Request):
```json
{
  "error": "Validation failed",
  "details": [
    "Missing required field: email",
    "Profile too short (80 chars, minimum: 100)"
  ]
}
```

**Usage**:
```python
import requests

cv_data = {
    "full_name": "John Doe",
    "email": "john@example.com",
    "address_lines": ["Zurich, Switzerland"],
    "profile": "Software engineer with 10+ years experience..."
}

response = requests.post(
    "https://cv-generator-6695.azurewebsites.net/api/validate-cv",
    json={"cv_data": cv_data}
)

validation = response.json()
if validation["is_valid"]:
    print("✓ CV is valid")
    print(f"  Pages: {validation['estimated_pages']}")
else:
    print("✗ Validation failed:")
    for error in validation["errors"]:
        print(f"  - {error}")
```

---

## Endpoint 3: Extract Photo

**Extract photo from DOCX file (standalone)**

```http
POST /extract-photo
Content-Type: application/json

{
  "docx_base64": "UEsDBBQABgAIAAAAIQ..."
}
```

**Response** (200 OK):
```json
{
  "photo_data_uri": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA..."
}
```

**Response** (400 Bad Request):
```json
{
  "error": "Photo extraction failed",
  "details": ["No images found in DOCX", "Invalid base64 encoding"]
}
```

**Usage**:
```python
import base64

# Read DOCX file
with open('CV.docx', 'rb') as f:
    docx_bytes = f.read()

docx_base64 = base64.b64encode(docx_bytes).decode('utf-8')

response = requests.post(
    "https://cv-generator-6695.azurewebsites.net/api/extract-photo",
    json={"docx_base64": docx_base64}
)

if response.status_code == 200:
    photo_uri = response.json()["photo_data_uri"]
    print(f"✓ Photo extracted: {len(photo_uri)} chars")
```

---

## Endpoint 4: Generate CV (Main Endpoint)

**Generate PDF CV from CV data**

```http
POST /generate-cv-action
Content-Type: application/json

{
  "cv_data": {
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "+41 76 123 4567",
    "address_lines": ["Zurich, Switzerland"],
    "profile": "Senior software engineer with 10+ years experience in full-stack development",
    "work_experience": [
      {
        "title": "Senior Developer",
        "company": "TechCorp",
        "location": "Zurich, Switzerland",
        "dates": "01/2020 - Present",
        "bullets": [
          "Led team of 5 engineers on microservices migration",
          "Reduced API latency by 40% through optimization",
          "Managed AWS infrastructure for 2M+ daily users"
        ]
      }
    ],
    "education": [
      {
        "degree": "Bachelor in Computer Science",
        "institution": "ETH Zurich",
        "location": "Zurich",
        "dates": "2012"
      }
    ],
    "languages": [
      {"name": "English", "level": "C2 (Native)"},
      {"name": "German", "level": "B2 (Professional)"}
    ],
    "it_ai_skills": ["Python", "Go", "AWS", "Kubernetes", "Docker"],
    "interests": "Open-source, hiking, photography",
    "data_privacy_consent": "I agree to data processing per EU GDPR"
  },
  "language": "en",
  "source_docx_base64": "UEsDBBQABgAI..." (optional)
}
```

**Parameters**:
- `cv_data` (required): CV data object
- `language` (optional): "en", "de", or "pl" (default: "en")
- `source_docx_base64` (optional): DOCX with photo for extraction

**Response** (200 OK):
```json
{
  "success": true,
  "pdf_base64": "JVBERi0xLjQK\nCiXref\n...",
  "validation": {
    "warnings": [],
    "estimated_pages": 2
  }
}
```

**Response** (400 Bad Request):
```json
{
  "error": "PDF generation failed",
  "details": [
    "Missing required field: full_name",
    "Profile must be 100-400 characters"
  ]
}
```

**Usage**:
```python
import requests
import base64

cv_data = {
    "full_name": "John Doe",
    "email": "john@example.com",
    "address_lines": ["Zurich, Switzerland"],
    "profile": "Software engineer...",
    # ... more fields
}

response = requests.post(
    "https://cv-generator-6695.azurewebsites.net/api/generate-cv-action",
    json={
        "cv_data": cv_data,
        "language": "en"
    },
    timeout=60
)

if response.status_code == 200:
    result = response.json()
    pdf_base64 = result["pdf_base64"]
    
    # Decode and save
    pdf_bytes = base64.b64decode(pdf_base64)
    with open('CV.pdf', 'wb') as f:
        f.write(pdf_bytes)
    
    print("✓ PDF generated successfully")
    print(f"  Pages: {result['validation']['estimated_pages']}")
else:
    errors = response.json()["details"]
    print("✗ Generation failed:")
    for error in errors:
        print(f"  - {error}")
```

---

## Endpoint 5: Preview HTML

**Generate HTML preview (debugging)**

```http
POST /preview-html
Content-Type: application/json

{
  "cv_data": { ... }
}
```

**Response** (200 OK):
```html
<!DOCTYPE html>
<html>
<head>
  <title>CV Preview</title>
  <style>/* Swiss template CSS */</style>
</head>
<body>
  <!-- CV HTML -->
</body>
</html>
```

**Usage**:
```python
response = requests.post(
    "https://cv-generator-6695.azurewebsites.net/api/preview-html",
    json={"cv_data": cv_data}
)

if response.status_code == 200:
    html = response.text
    with open('preview.html', 'w') as f:
        f.write(html)
    print(f"✓ HTML preview: {len(html)} chars")
```

---

## CV Data Schema

**Recommended fields** (backend will validate strict limits for 2 pages):
```json
{
  "full_name": "string (1-100 chars)",
  "email": "string (valid email)",
  "address_lines": ["City, Country"],
  "work_experience": [
    {
      "date_range": "YYYY-MM – Present",
      "employer": "string",
      "location": "City, Country",
      "title": "string",
      "bullets": ["string", "string", "string"]
    }
  ],
  "education": [
    {
      "date_range": "YYYY - YYYY",
      "institution": "string",
      "title": "string",
      "details": ["string"]
    }
  ],
  "languages": [
    {"name": "string", "level": "string"}
  ],
  "it_ai_skills": ["string", "string"],
  "interests": "string",
  "data_privacy_consent": "I agree..."
}
```

**Optional fields**:
```json
{
  "phone": "+41 76 123 4567",
  "photo_url": "data:image/png;base64,...",
  "further_experience": [
    {
      "date_range": "since 2023-01",
      "title": "Volunteer Mentor",
      "organization": "Open Source Community",
      "bullets": ["..."],
      "details": ["..."]
    }
  ],
  "certifications": ["string"],
  "publications": ["string"]
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Error title",
  "details": ["Specific error 1", "Specific error 2"]
}
```

**Common errors**:
- `400 Bad Request`: Validation or structure errors
- `500 Internal Server Error`: Backend processing failure (retry once)

**Handling errors**:
```python
try:
    response = requests.post(...)
    response.raise_for_status()
    result = response.json()
except requests.exceptions.HTTPError as e:
    error_data = e.response.json()
    print(f"Error: {error_data['error']}")
    for detail in error_data['details']:
        print(f"  - {detail}")
```

---

## Response Times

**Typical performance**:
- Health check: < 100ms
- Validation: 150-300ms
- Photo extraction: 200-400ms
- HTML preview: 2-3 seconds
- PDF generation: 2-4 seconds (WeasyPrint rendering)

**Cold start vs warm start**:
- First request after idle: 8-15 seconds
- Subsequent requests: 2-4 seconds

---

## Timeout Settings

**Recommended timeouts**:
```python
# Quick operations
requests.post(..., timeout=30)  # Health, validate, extract

# Slow operations
requests.post(..., timeout=60)  # PDF generation, preview
```

---

## Rate Limiting

Currently no rate limiting. Subject to change.

---

## Authentication

Use `x-functions-key` header (Azure Functions API key) when calling the production endpoint.

---

## CORS

CORS is enabled. Safe for browser-based requests.
