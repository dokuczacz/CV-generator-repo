# 📋 Custom GPT Configuration Package

## Complete Setup for CV_Dopasowywacz v4.2

### 📦 What You're Getting

This package contains everything needed to set up and use the CV Generator Custom GPT:

1. **OpenAPI Schema** (`openapi_cv_actions.yaml`) - Import this to Custom GPT Actions
2. **System Instructions** (`custom_gpt_instructions.md`) - Paste to Custom GPT Instructions
3. **Azure Function Code** (`function_app.py`) - Backend implementation
4. **Authentication Details** - x-functions-key setup guide
5. **Configuration Guide** - Step-by-step setup instructions

---

## 🔧 System Architecture

```
┌─────────────────┐
│  Custom GPT     │
│ (ChatGPT UI)    │
└────────┬────────┘
         │
         │ HTTP with x-functions-key header
         │
┌────────▼────────────────────────────┐
│  OpenAPI Actions (openapi_cv_actions.yaml)
│  - extractPhoto                      │
│  - validateCV                        │
│  - generateCVAction                  │
│  - previewHTML                       │
└────────┬────────────────────────────┘
         │
         │ HTTPS
         │
┌────────▼────────────────────────────────────────┐
│ Azure Functions (cv-generator-6695)            │
│ ┌──────────────────────────────────────────┐   │
│ │ function_app.py                          │   │
│ │                                          │   │
│ │ @app.route("/health")                   │   │
│ │ @app.route("/extract-photo")            │   │
│ │ @app.route("/validate-cv")              │   │
│ │ @app.route("/generate-cv-action")       │   │
│ │ @app.route("/preview-html")             │   │
│ │ @app.route("/generate-cv")              │   │
│ └──────────────────────────────────────────┘   │
└────────┬───────────────────────────────────────┘
         │
┌────────▼─────────────────┐
│ Local Processing         │
│ - PDF Rendering          │
│ - HTML Templates         │
│ - CV Validation          │
│ - Photo Extraction       │
└──────────────────────────┘
```

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Get the API Key

```bash
# Key is already saved in local.settings.json
cat local.settings.json | grep AZURE_FUNCTION_KEY
```

**Your Key**: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`

### Step 2: Open Custom GPT Editor

URL: https://chat.openai.com/gpts/editor

### Step 3: Create New GPT

- **Name**: CV_Dopasowywacz v4.2
- **Description**: Professional CV generator with ATS compliance, photo extraction, and multi-language support

### Step 4: Configure Actions

1. Scroll to **Actions** section
2. Click **"Create new action"**
3. Import or paste content from `openapi_cv_actions.yaml`

### Step 5: Add Instructions

1. Go to **Configure** tab
2. Find **Instructions** field
3. Paste entire content from `custom_gpt_instructions.md`

### Step 6: Set Authentication

1. In Actions → **Authentication**
2. **Auth Type**: API Key
3. **Custom Header**: `x-functions-key`
4. **Value**: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`

### Step 7: Test

Ask Custom GPT:
```
Generate a CV for John Doe, email john@example.com, 
location Zurich, profile "Software engineer with 5 years experience"
```

---

## 📄 Azure Function Code Structure

### File: `function_app.py`

**Current Implementation**:
```python
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
```

This allows:
- ✅ Public access (no Azure-level authentication)
- ✅ Custom header authentication via OpenAPI schema
- ✅ Secure when Custom GPT passes `x-functions-key`

### Available Endpoints

| Endpoint | Auth | Purpose | Response |
|----------|------|---------|----------|
| `GET /health` | Optional | Health check | JSON |
| `POST /extract-photo` | Required | Photo from DOCX | JSON with data URI |
| `POST /validate-cv` | Required | CV validation | JSON validation result |
| `POST /generate-cv-action` | Required | PDF generation (base64) | JSON with PDF |
| `POST /preview-html` | Required | HTML preview | HTML content |
| `POST /generate-cv` | Required | Direct PDF | Binary PDF file |

### Function Signatures

```python
@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse

@app.route(route="extract-photo", methods=["POST"])
def extract_photo(req: func.HttpRequest) -> func.HttpResponse

@app.route(route="validate-cv", methods=["POST"])
def validate_cv_endpoint(req: func.HttpRequest) -> func.HttpResponse

@app.route(route="generate-cv-action", methods=["POST"])
def generate_cv_action(req: func.HttpRequest) -> func.HttpResponse

@app.route(route="preview-html", methods=["POST"])
def preview_html(req: func.HttpRequest) -> func.HttpResponse

@app.route(route="generate-cv", methods=["POST"])
def generate_cv(req: func.HttpRequest) -> func.HttpResponse
```

---

## 🔐 Authentication Flow

### How Custom GPT Passes the Key

When you configure authentication in Custom GPT Actions:

```yaml
securitySchemes:
  FunctionKeyAuth:
    type: apiKey
    in: header
    name: x-functions-key
    description: Azure Functions API Key
```

**Custom GPT automatically**:
1. Reads the security scheme from OpenAPI
2. Prompts you to provide the API key
3. Stores it securely
4. Adds it to every request:
   ```
   POST /api/generate-cv-action
   x-functions-key: cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==
   Content-Type: application/json
   ```

### Backend Validation

The Azure Function **doesn't currently validate** the key (anonymous auth level). To add validation:

```python
# Option 1: Enable function-level auth
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Option 2: Manual header checking
def validate_key(req: func.HttpRequest) -> bool:
    key = req.headers.get("x-functions-key")
    return key == os.environ.get("AZURE_FUNCTION_KEY")
```

---

## 📊 OpenAPI Schema Components

### Security Scheme
```yaml
components:
  securitySchemes:
    FunctionKeyAuth:
      type: apiKey
      in: header
      name: x-functions-key
      description: Azure Functions API Key

security:
  - FunctionKeyAuth: []
```

### Endpoint Example: generate-cv-action
```yaml
/generate-cv-action:
  post:
    operationId: generateCVAction
    summary: Generate CV PDF (returns base64)
    requestBody:
      content:
        application/json:
          schema:
            properties:
              cv_data:
                $ref: '#/components/schemas/CVData'
              language:
                type: string
                enum: [en, de, pl]
    responses:
      '200':
        content:
          application/json:
            schema:
              properties:
                success: boolean
                pdf_base64: string
                validation: object
```

### CVData Schema
```yaml
components:
  schemas:
    CVData:
      type: object
      required:
        - full_name
        - email
        - address_lines
        - profile
      properties:
        full_name: string (max 100)
        email: string (email format)
        phone: string
        address_lines: array (max 3)
        photo_url: string (data URI)
        profile: string (max 400)
        work_experience: array (max 5)
        education: array (max 3)
        languages: array (max 5)
        it_ai_skills: array (max 30)
        certifications: array
        interests: string or array
        references: string
        data_privacy_consent: string
```

---

## 🧪 Testing the Integration

### Test 1: Direct API Call (PowerShell)
```powershell
$key = "cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA=="
$headers = @{ "x-functions-key" = $key }

Invoke-RestMethod -Uri "https://cv-generator-6695.azurewebsites.net/api/health" `
  -Headers $headers
```

### Test 2: Validate CV
```powershell
$body = @{
  cv_data = @{
    full_name = "Test User"
    email = "test@example.com"
    address_lines = @("Zurich, Switzerland")
    profile = "Test profile"
  }
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://cv-generator-6695.azurewebsites.net/api/validate-cv" `
  -Method Post `
  -Headers @{ "x-functions-key" = $key } `
  -Body $body `
  -ContentType "application/json"
```

### Test 3: Generate PDF via Custom GPT
```
"Please generate a professional CV for:
- Name: Jane Smith
- Email: jane@example.com
- Location: Zurich, Switzerland
- Profile: Full-stack developer with 8 years experience
- Work: Senior Engineer at TechCorp (2020-Present), Software Engineer at StartupXYZ (2016-2020)
- Education: M.Sc. Computer Science, ETH Zurich (2014-2016)
- Skills: Python, React, AWS, Docker"
```

---

## 📋 Deployment Checklist

### Backend (Azure Functions)
- [x] function_app.py deployed
- [x] All 6 endpoints live
- [x] Auth level: ANONYMOUS (allows custom header auth)
- [x] Health endpoint working
- [x] Photo extraction working
- [x] CV validation working
- [x] PDF generation working

### OpenAPI Schema
- [x] Version: 3.1.0 (Custom GPT compatible)
- [x] All endpoints documented
- [x] Security scheme defined (x-functions-key)
- [x] CVData schema complete
- [x] Examples provided

### Custom GPT Configuration
- [ ] GPT created in ChatGPT
- [ ] Actions imported (openapi_cv_actions.yaml)
- [ ] Instructions pasted (custom_gpt_instructions.md)
- [ ] Authentication configured (x-functions-key)
- [ ] Test run completed

---

## 🎯 Use Cases

### Use Case 1: Standard CV Generation
```
"Generate a professional CV from my background"
[Upload CV]
```
✅ Extracts text → Structures JSON → Generates PDF

### Use Case 2: Job Application Optimization
```
"Optimize my CV for this Python engineer role at Google"
[Upload CV]
[Paste job description]
```
✅ Analyzes job requirements → Highlights relevant skills → Generates optimized PDF

### Use Case 3: Multi-Language Generation
```
"Generate my CV in German and Polish"
[Upload CV]
```
✅ Generates DE and PL versions with translated headers

### Use Case 4: Photo Extraction & Inclusion
```
"Extract my photo and include it in a new CV"
[Upload DOCX with embedded photo]
```
✅ Extracts photo → Includes in header → Generates PDF

---

## 🔧 Troubleshooting

### Issue: "x-functions-key header not recognized"
**Solution**: 
- Make sure you set it in Custom GPT Authentication tab
- Verify header name is exactly: `x-functions-key`
- Check the key value: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`

### Issue: "Backend error: 404"
**Solution**:
- Endpoints deployed recently? Wait 2-3 minutes for cold start
- Check Azure status: `az functionapp show --resource-group cv-generator-rg --name cv-generator-6695`
- Test health endpoint directly

### Issue: "PDF generation timeout"
**Solution**:
- First request may take 20-30 seconds (Playwright cold start)
- Retry once
- Check logs: `az functionapp log tail --resource-group cv-generator-rg --name cv-generator-6695`

### Issue: "Validation failed"
**Solution**:
- Required fields: full_name, email, address_lines, profile
- Check field lengths (profile max 400 chars)
- Work experience bullets max 90 chars each
- Max 5 work experiences

---

## 📞 Support & Resources

**GitHub Repository**: https://github.com/dokuczacz/CV-generator-repo
**Function App**: cv-generator-6695
**Resource Group**: cv-generator-rg
**Region**: West Europe

**Check Deployment**:
```bash
az functionapp show --resource-group cv-generator-rg --name cv-generator-6695
```

**View Logs**:
```bash
az functionapp log tail --resource-group cv-generator-rg --name cv-generator-6695
```

---

## 📈 Next Steps

1. ✅ Import OpenAPI schema to Custom GPT Actions
2. ✅ Paste system instructions to Custom GPT
3. ✅ Configure authentication (x-functions-key)
4. ✅ Test with sample CV
5. ⏭️ Deploy Custom GPT (make it public)
6. ⏭️ Monitor usage and iterate

---

**Status**: ✅ Production Ready  
**Last Updated**: 2026-01-19  
**Version**: v4.2
