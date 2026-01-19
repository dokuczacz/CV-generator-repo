# Custom GPT Integration - Deployment Guide

## 🚀 Quick Setup (5 Minutes)

### Step 1: Configure Custom GPT

1. Go to ChatGPT → Create GPT
2. **Name**: CV_Dopasowywacz v4.2
3. **Description**: Premium CV generator with ATS compliance and photo extraction

### Step 2: Add Instructions

Copy entire content from [`custom_gpt_instructions.md`](custom_gpt_instructions.md) into the **Instructions** field.

### Step 3: Configure Actions

1. Click **Actions** → **Create new action**
2. **Import from URL**: 
   ```
   https://cv-generator-6695.azurewebsites.net/api/openapi-schema
   ```
   
   **OR** manually paste content from [`openapi_cv_actions.json`](openapi_cv_actions.json)

3. **Authentication**: None (endpoints are public)
   - Note: For production, add function key authentication

4. **Privacy Policy**: (optional)
   ```
   https://your-domain.com/privacy
   ```

### Step 4: Test Integration

Upload a test CV and ask:
```
"Please generate a professional CV in English"
```

**Expected flow**:
1. GPT extracts text from uploaded file
2. GPT detects photo (if present)
3. GPT builds structured JSON
4. GPT calls `/api/validate-cv` to check constraints
5. GPT calls `/api/generate-cv-action` with JSON
6. GPT decodes base64 PDF
7. GPT provides download link

---

## 📋 Available Endpoints

### Base URL
```
https://cv-generator-6695.azurewebsites.net/api
```

### Endpoints

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/health` | GET | Health check | ✅ Live |
| `/extract-photo` | POST | Photo extraction only | ✅ Live |
| `/validate-cv` | POST | CV validation only | ✅ Live |
| `/generate-cv-action` | POST | PDF generation (base64) | ✅ Live |
| `/preview-html` | POST | HTML preview | ✅ Live |

---

## 🧪 Testing

### Test 1: Health Check
```bash
curl https://cv-generator-6695.azurewebsites.net/api/health
```

**Expected**:
```json
{
  "status": "healthy",
  "service": "CV Generator API",
  "version": "1.0"
}
```

### Test 2: Validation
```bash
curl -X POST https://cv-generator-6695.azurewebsites.net/api/validate-cv \
  -H "Content-Type: application/json" \
  -d '{
    "cv_data": {
      "full_name": "John Doe",
      "email": "john@example.com",
      "address_lines": ["Zurich, Switzerland"],
      "profile": "Test profile"
    }
  }'
```

**Expected**:
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": ["Missing work_experience", "Missing education"],
  "estimated_pages": 1
}
```

### Test 3: Full PDF Generation
```bash
curl -X POST https://cv-generator-6695.azurewebsites.net/api/generate-cv-action \
  -H "Content-Type: application/json" \
  -d @test_cv.json \
  | jq -r '.pdf_base64' \
  | base64 -d > output.pdf
```

---

## 🔧 Troubleshooting

### Issue: "Backend error: 500"

**Check logs**:
```bash
az functionapp log tail \
  --resource-group cv-generator-rg \
  --name cv-generator-6695
```

**Common causes**:
- WeasyPrint font loading (cold start optimization)
- Invalid CV JSON structure
- Photo extraction failed

**Solution**: Retry after 30 seconds (cold start warmup)

### Issue: "Validation failed"

**Check validation response**:
```json
{
  "is_valid": false,
  "errors": [
    "Missing required field: email",
    "work_experience: Expected max 5 entries, got 7"
  ]
}
```

**Solution**: Fix JSON structure per error messages

### Issue: Custom GPT not calling backend

1. Check Actions configuration in GPT settings
2. Verify OpenAPI schema imported correctly
3. Test endpoints manually with curl
4. Check GPT instructions reference correct base URL

---

## 📊 Performance

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| `/health` | <100ms | Instant |
| `/validate-cv` | <200ms | JSON validation only |
| `/extract-photo` | <500ms | DOCX parsing |
| `/generate-cv-action` | 2-4 seconds | WeasyPrint PDF rendering |
| Cold start | 15-30 seconds | First request after idle |

---

## 🔐 Security (Production)

### Current: Public Endpoints ⚠️
All endpoints are currently public (no authentication).

### Recommended: Add Function Key

1. **Get function key**:
   ```bash
   az functionapp keys list \
     --resource-group cv-generator-rg \
     --name cv-generator-6695 \
     --query "functionKeys.default" -o tsv
   ```

2. **Update Custom GPT Actions**:
   - Authentication Type: `API Key`
   - Auth Type: `Custom Header`
   - Header Name: `x-functions-key`
   - Value: `[paste function key]`

3. **Update function_app.py**:
   ```python
   app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
   ```

4. **Redeploy**:
   ```bash
   git commit -am "feat: add function key authentication"
   git push origin main
   ```

---

## 🌍 Multi-Language Support

### Current Implementation
Templates use hardcoded English headers.

### Adding Language Support (Future)

1. **Use translations.json**:
   ```python
   from src.i18n.translations import get_translations
   
   lang = req_body.get("language", "en")
   translations = get_translations(lang)
   ```

2. **Apply to templates**:
   ```python
   html_content = render_html(cv_data, language=lang)
   ```

3. **Custom GPT passes language**:
   ```json
   {
     "cv_data": {...},
     "language": "de"
   }
   ```

---

## 📈 Monitoring

### Application Insights

View logs and metrics:
```
Azure Portal → cv-generator-6695 → Application Insights
```

**Key metrics**:
- Request count
- Average response time
- Failure rate
- Custom events (PDF generated)

### Cost Monitoring

Current plan: **FlexConsumption**
- Pay per execution
- ~$0.000015/GB-second

**Expected costs**:
- 100 CVs/day: $2-3/month
- 1000 CVs/day: $20-30/month

---

## 🚀 Next Steps

1. ✅ **Test Custom GPT** with real CV
2. ✅ **Add authentication** (function keys)
3. ⚠️ **Implement language switching** (EN/DE/PL)
4. ⚠️ **Add DOCX export** (currently PDF only)
5. ⚠️ **Job offer matching** (AI-powered skill alignment)

---

## 📞 Support

- **Backend logs**: `az functionapp log tail`
- **GitHub repo**: https://github.com/dokuczacz/CV-generator-repo
- **Azure Portal**: cv-generator-6695 Function App

---

**Status**: ✅ **LIVE AND OPERATIONAL**  
**Last Updated**: 2026-01-19  
**Endpoints**: 5/5 active  
**Uptime**: Running
