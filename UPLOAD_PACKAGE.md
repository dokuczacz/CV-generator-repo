# Custom GPT Setup Documents

## 📦 Files for Custom GPT Integration

### 1. **OpenAPI Schema (YAML)** - `openapi_cv_actions.yaml`
**Purpose**: Import this into Custom GPT Actions

**How to use**:
1. Open ChatGPT → Create GPT → Actions
2. Click "Import from URL" or paste YAML content
3. Schema defines 4 endpoints:
   - `POST /extract-photo` - Photo extraction from DOCX
   - `POST /validate-cv` - CV validation
   - `POST /generate-cv-action` - PDF generation (base64)
   - `POST /preview-html` - HTML preview

### 2. **System Instructions** - `custom_gpt_instructions.md`
**Purpose**: Complete Custom GPT prompt (6-phase pipeline)

**How to use**:
1. Copy entire content
2. Paste into Custom GPT "Instructions" field
3. Defines behavior for:
   - Phase 1: Ingest (extract CV text + photo)
   - Phase 2: Analysis (parse CV structure)
   - Phase 3: Structure (build JSON)
   - Phase 4: Generation (polish content)
   - Phase 5: Render (call backend API)
   - Phase 6: Export (save PDF to /mnt/data/)

### 3. **Integration Proposal** - `CUSTOM_GPT_INTEGRATION_PROPOSAL.md`
**Purpose**: Architecture alignment analysis

**Content**:
- Current backend capabilities
- Custom GPT requirements
- Integration options (Option A selected)
- Implementation plan

### 4. **Deployment Guide** - `CUSTOM_GPT_DEPLOYMENT.md`
**Purpose**: Step-by-step setup instructions

**Content**:
- 5-minute setup guide
- Testing procedures
- Troubleshooting tips
- Security recommendations

---

## 🔑 Authentication Setup

### Function Key
**Retrieved from Azure**: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`

**Current status**: Endpoints are **public** (no authentication required)

**To enable authentication**:
1. In Custom GPT Actions → Authentication
2. Select: **API Key**
3. Auth Type: **Custom Header**
4. Header Name: `x-functions-key`
5. Value: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`

**Note**: For production use, enable function-level authentication in `function_app.py`:
```python
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
```

---

## 🧪 Endpoint Testing Results

### Test 1: Health Check ✅
```bash
GET https://cv-generator-6695.azurewebsites.net/api/health
```
**Response**:
```json
{
  "status": "healthy",
  "service": "CV Generator API",
  "version": "1.0"
}
```

### Test 2: Validate CV ⏳ (Pending deployment)
```bash
POST https://cv-generator-6695.azurewebsites.net/api/validate-cv
```
**Status**: Endpoint not yet deployed (404)

### Test 3: Extract Photo ⏳ (Pending deployment)
```bash
POST https://cv-generator-6695.azurewebsites.net/api/extract-photo
```
**Status**: Endpoint not yet deployed (404)

### Test 4: Generate CV (base64) ✅ (Already deployed)
```bash
POST https://cv-generator-6695.azurewebsites.net/api/generate-cv-action
```
**Status**: Already working from previous deployment

---

## 📋 Deployment Checklist

- [x] OpenAPI schema created (YAML format)
- [x] Custom GPT instructions written
- [x] Function key retrieved and saved
- [x] Integration documentation created
- [ ] **Commit enhanced function_app.py** (with extract-photo, validate-cv)
- [ ] **Push to trigger CI/CD deployment**
- [ ] Test all 4 endpoints after deployment
- [ ] Import YAML schema to Custom GPT Actions
- [ ] Copy instructions to Custom GPT
- [ ] Test end-to-end workflow

---

## 🚀 Next Steps

### Step 1: Deploy Enhanced Endpoints
```bash
git add function_app.py .github/workflows/deploy-azure.yml src/i18n/
git commit -m "feat: add extract-photo and validate-cv endpoints, multi-language support"
git push origin main
```

### Step 2: Wait for Deployment (~3-5 minutes)
Monitor GitHub Actions: https://github.com/dokuczacz/CV-generator-repo/actions

### Step 3: Test All Endpoints
```bash
.\test_endpoints.ps1
```

### Step 4: Configure Custom GPT
1. Import `openapi_cv_actions.yaml` to Actions
2. Paste `custom_gpt_instructions.md` to Instructions
3. Test with sample CV

---

## 📁 File Locations

| File | Purpose | Status |
|------|---------|--------|
| `openapi_cv_actions.yaml` | OpenAPI schema (YAML) | ✅ Ready |
| `openapi_cv_actions.json` | OpenAPI schema (JSON) | ✅ Ready |
| `custom_gpt_instructions.md` | System prompt | ✅ Ready |
| `CUSTOM_GPT_DEPLOYMENT.md` | Setup guide | ✅ Ready |
| `CUSTOM_GPT_INTEGRATION_PROPOSAL.md` | Architecture analysis | ✅ Ready |
| `function_app.py` | Enhanced endpoints | ⏳ Not deployed |
| `src/i18n/translations.json` | EN/DE/PL support | ⏳ Not deployed |

---

**All documents ready for upload!** 📤
