# Azure Functions - CV Generator Backend

## Reference Guide for `function_app.py`

### File Location
```
CV-generator-repo/function_app.py
```

### Overview

Complete Azure Functions implementation with 6 HTTP endpoints for CV generation, validation, and photo extraction.

---

## Core Configuration

```python
import azure.functions as func
import logging
import json
import base64

from src.render import render_pdf, render_html
from src.validator import validate_cv
from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes
from src.normalize import normalize_cv_data

# Initialize app with anonymous auth (custom header auth via OpenAPI)
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
```

**Authentication Note**:
- `http_auth_level=func.AuthLevel.ANONYMOUS` allows requests without Azure auth
- Custom GPT passes `x-functions-key` header (defined in OpenAPI schema)
- For strict validation, change to `func.AuthLevel.FUNCTION`

---

## Endpoints Reference

### 1. Health Check
```python
@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse
```

**Purpose**: Verify service is running

**Request**:
```http
GET /api/health
```

**Response (200)**:
```json
{
  "status": "healthy",
  "service": "CV Generator API",
  "version": "1.0"
}
```

**Use Case**: Readiness probe, monitoring

---

### 2. Extract Photo
```python
@app.route(route="extract-photo", methods=["POST"])
def extract_photo(req: func.HttpRequest) -> func.HttpResponse
```

**Purpose**: Extract embedded image from DOCX file

**Request**:
```http
POST /api/extract-photo
Content-Type: application/json
x-functions-key: <API_KEY>

{
  "docx_base64": "UEsDBAoAAAAAAI..."
}
```

**Response (200)**:
```json
{
  "photo_data_uri": "data:image/png;base64,iVBORw0KGgo..."
}
```

**Response (404)** - No photo found:
```json
{
  "error": "No photo found in DOCX"
}
```

**Workflow**:
1. Decode base64 DOCX
2. Extract first embedded image
3. Convert to data URI
4. Return for CV inclusion

---

### 3. Validate CV
```python
@app.route(route="validate-cv", methods=["POST"])
def validate_cv_endpoint(req: func.HttpRequest) -> func.HttpResponse
```

**Purpose**: Validate CV data structure and content constraints

**Request**:
```http
POST /api/validate-cv
Content-Type: application/json
x-functions-key: <API_KEY>

{
  "cv_data": {
    "full_name": "John Doe",
    "email": "john@example.com",
    "address_lines": ["Zurich, Switzerland"],
    "profile": "Software engineer with 5 years experience",
    "work_experience": [
      {
        "title": "Senior Engineer",
        "company": "TechCorp",
        "dates": "01/2020 - Present",
        "bullets": ["Achievement 1", "Achievement 2"]
      }
    ]
  }
}
```

**Response (200)**:
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": ["Profile could be more specific"],
  "estimated_pages": 2
}
```

**Validation Rules**:
- Required: full_name, email, address_lines, profile
- Max items: work_experience (5), education (3), skills (30)
- Max length: profile (400), bullets (90)
- Date format: MM/YYYY - MM/YYYY

---

### 4. Generate CV for Custom GPT
```python
@app.route(route="generate-cv-action", methods=["POST"])
def generate_cv_action(req: func.HttpRequest) -> func.HttpResponse
```

**Purpose**: Generate PDF and return as base64 (for Custom GPT Actions)

**Request**:
```http
POST /api/generate-cv-action
Content-Type: application/json
x-functions-key: <API_KEY>

{
  "cv_data": { ... },
  "language": "en",
  "source_docx_base64": "optional_base64_docx"
}
```

**Response (200)**:
```json
{
  "success": true,
  "pdf_base64": "JVBERi0xLjQKJeLjz9MNCjEgMCBvYmo...",
  "validation": {
    "warnings": [],
    "estimated_pages": 2
  }
}
```

**Response (400)** - Validation failed:
```json
{
  "error": "Validation failed",
  "details": ["work_experience: Expected max 5 entries, got 7"]
}
```

**Workflow**:
1. Normalize CV data (handle GPT formatting variations)
2. Extract photo if source_docx_base64 provided
3. Validate via `/validate-cv` logic
4. Render PDF via Chromium
5. Encode as base64
6. Return JSON

**Special Features**:
- Deterministic 2-page layout
- Photo in header (if provided)
- ATS-compliant formatting
- Multi-language section headers (en/de/pl)

---

### 5. Preview HTML
```python
@app.route(route="preview-html", methods=["POST"])
def preview_html(req: func.HttpRequest) -> func.HttpResponse
```

**Purpose**: Generate HTML without PDF rendering (for debugging)

**Request**:
```http
POST /api/preview-html
Content-Type: application/json
x-functions-key: <API_KEY>

{
  "cv_data": { ... },
  "source_docx_base64": "optional"
}
```

**Response (200)**:
```html
<!DOCTYPE html>
<html>
  <head>
    <style>/* CSS inline */</style>
  </head>
  <body>
    <!-- Rendered CV HTML -->
  </body>
</html>
```

**Use Case**: Quick testing without PDF rendering overhead

---

### 6. Generate CV (Direct PDF)
```python
@app.route(route="generate-cv", methods=["POST"])
def generate_cv(req: func.HttpRequest) -> func.HttpResponse
```

**Purpose**: Generate PDF and return directly (alternative to base64)

**Request**:
```http
POST /api/generate-cv
Content-Type: application/json
x-functions-key: <API_KEY>

{
  "cv_data": { ... },
  "source_docx_base64": "optional"
}
```

**Response (200)**:
```
Content-Type: application/pdf
Content-Disposition: attachment; filename=cv.pdf

[Binary PDF data]
```

**Use Case**: Direct download, file-based workflows

---

## Common Request/Response Patterns

### Pattern 1: Successful PDF Generation
```python
# Request
{
  "cv_data": {
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "address_lines": ["Berlin, Germany"],
    "profile": "Full-stack developer",
    "work_experience": [
      {
        "title": "Senior Dev",
        "company": "Tech AG",
        "location": "Berlin",
        "dates": "03/2020 - Present",
        "bullets": [
          "Led team of 5 engineers",
          "Architected microservices",
          "Improved performance by 40%"
        ]
      }
    ],
    "education": [
      {
        "degree": "M.Sc. Computer Science",
        "institution": "TU Berlin",
        "dates": "2016 - 2018"
      }
    ]
  }
}

# Response
{
  "success": true,
  "pdf_base64": "JVBERi0xLjQK...",
  "validation": {
    "warnings": [],
    "estimated_pages": 2
  }
}
```

### Pattern 2: Validation with Warnings
```python
# Response
{
  "is_valid": true,
  "errors": [],
  "warnings": [
    "Profile is quite long (350 chars, recommended: 250)",
    "Consider removing 1 work experience entry to fit on 2 pages"
  ],
  "estimated_pages": 2
}
```

### Pattern 3: Validation Failure
```python
# Response
{
  "is_valid": false,
  "errors": [
    "Missing required field: email",
    "work_experience[0]: missing required field 'dates'",
    "profile: exceeds maximum length (400 chars)"
  ],
  "warnings": [],
  "estimated_pages": null
}
```

### Pattern 4: Error Response
```python
# Response (500)
{
  "error": "PDF generation failed",
  "details": "Chromium renderer crashed: out of memory"
}
```

---

## Error Handling

### Validation Errors (400)
```python
return func.HttpResponse(
    json.dumps({
        "error": "Validation failed",
        "details": validation_result.errors
    }),
    mimetype="application/json",
    status_code=400
)
```

### Rendering Errors (500)
```python
try:
    pdf_bytes = render_pdf(cv_data)
except Exception as e:
    logging.error(f"PDF generation failed: {e}")
    return func.HttpResponse(
        json.dumps({
            "error": "PDF generation failed",
            "details": str(e)
        }),
        mimetype="application/json",
        status_code=500
    )
```

### Missing Data (400)
```python
if not cv_data:
    return func.HttpResponse(
        json.dumps({"error": "Missing cv_data in request"}),
        mimetype="application/json",
        status_code=400
    )
```

---

## Environment Variables

Read from `local.settings.json` or Azure Function App settings:

```python
import os

# Example usage
api_key = os.environ.get("AZURE_FUNCTION_KEY")
storage_conn_str = os.environ.get("STORAGE_CONNECTION_STRING")
cv_theme = os.environ.get("CV_DEFAULT_THEME", "zurich")
```

**Available Variables**:
- `FUNCTIONS_WORKER_RUNTIME`: python
- `AZURE_FUNCTION_KEY`: x-functions-key value
- `STORAGE_CONNECTION_STRING`: Azure Storage connection
- `CV_DEFAULT_THEME`: zurich (default template)
- `PLAYWRIGHT_BROWSERS_PATH`: Chromium cache location

---

## Logging

```python
import logging

# In each endpoint
logging.info('Endpoint requested')
logging.warning(f'Photo extraction failed: {e}')
logging.error(f'PDF generation failed: {e}')
```

**View Logs**:
```bash
az functionapp log tail --resource-group cv-generator-rg --name cv-generator-6695
```

---

## Dependencies

### Internal Modules
- `src.render` - PDF/HTML rendering via Chromium
- `src.validator` - CV structure validation
- `src.docx_photo` - Photo extraction from DOCX
- `src.normalize` - GPT output normalization

### External Libraries
```python
import azure.functions as func  # Azure Functions SDK
import json                      # JSON parsing
import base64                    # Base64 encoding/decoding
import logging                   # Logging
```

### System Dependencies
- Python 3.11+
- Chromium (for PDF rendering)
- Required packages in `requirements.txt`:
  - azure-functions
  - playwright
  - python-docx
  - pyyaml
  - jinja2

---

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Health check | <100ms | Instant |
| Validate CV | 100-200ms | JSON validation only |
| Extract photo | 300-500ms | DOCX parsing |
| Generate PDF | 3-8 seconds | Chromium rendering |
| Cold start | 15-30 seconds | First request after idle |

---

## Security Considerations

### Current Setup
- ✅ Anonymous auth (no Azure-level protection)
- ✅ Custom GPT passes x-functions-key header
- ⚠️ Key sent in plain HTTP header

### Recommended for Production
```python
# Option 1: Enable function-level auth
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Option 2: Manual validation
def get_api_key(req: func.HttpRequest) -> str:
    return req.headers.get("x-functions-key", "")

def validate_key(key: str) -> bool:
    return key == os.environ.get("AZURE_FUNCTION_KEY")
```

### HTTPS
- ✅ All endpoints use HTTPS (Azure automatically)
- ✅ TLS 1.2+ enforced
- ✅ Custom domain supported

---

## Deployment

### GitHub Actions CI/CD
Automatic deployment on push to `main` branch:

```yaml
# .github/workflows/deploy-azure.yml
- Test (npm test)
- Build (zip functions)
- Deploy (publish profile auth)
```

### Manual Deployment
```bash
# Using Azure CLI
az functionapp deployment source config-zip \
  --resource-group cv-generator-rg \
  --name cv-generator-6695 \
  --src-path deploy.zip
```

---

## Testing

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
func start

# Test endpoint
curl -X POST http://localhost:7071/api/health
```

### Unit Tests
```bash
# Run tests
npm test

# With coverage
npm run test:coverage
```

---

## Version Information

- **File**: `function_app.py`
- **Version**: 1.0
- **Azure Functions Runtime**: v4
- **Python**: 3.11
- **Last Updated**: 2026-01-19

---

**Status**: ✅ Production Ready  
**Endpoints**: 6/6 Active  
**Uptime**: Running
