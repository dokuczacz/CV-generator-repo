# ✅ Custom GPT Setup Guide - 5 Minute Deployment

Your Custom GPT is ready to deploy!

---

## Step 1: Copy System Prompt (8000 chars limit)

1. Open: [CUSTOM_GPT_INSTRUCTIONS_COMPACT.md](CUSTOM_GPT_INSTRUCTIONS_COMPACT.md)
2. Copy **everything EXCEPT the last 2 lines** (the ones saying "Paste the content above...")
3. Go to: https://chat.openai.com/gpts/editor
4. Create new GPT
5. **Paste into "Instructions" field**

✅ Character count: **~3,200 characters** (well under 8000 limit)

---

## Step 2: Upload Reference Files

In the same Custom GPT editor:

1. Click "⬆️ Upload files" or drag files to upload area
2. Upload these files:
   - `CUSTOM_GPT_API_REFERENCE.md`
   - `CUSTOM_GPT_PHASES_DETAILED.md`
3. Click "✓ Confirm"

These files are available for the GPT to reference during conversations.

---

## Step 3: Configure OpenAPI Schema

1. Scroll to "**Actions**" section
2. Click "**Create new action**"
3. Click "**Authenticate via API key**"
4. Paste this URL:
   ```
   https://cv-generator-6695.azurewebsites.net/api/openapi.json
   ```
   OR use YAML schema: Copy content from `openapi_cv_actions.yaml`

5. **Authentication Details**:
   - **Type**: API Key
   - **Auth Type**: API Key
   - **Location**: Header
   - **Header Name**: `x-functions-key`
   - **API Key Value**: 
     ```
     cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==
     ```

6. Click "**Save**"

---

## Step 4: Basic Settings

1. **Name**: CV_Dopasowywacz v4.2
2. **Description**: Professional CV generator with Azure backend
3. **Instructions**: ✅ Already pasted
4. **Capabilities**:
   - ✅ Enable "Code Interpreter" (for photo extraction from DOCX)
   - ❌ Disable "Web Browsing" (not needed)
   - ❌ Disable "DALL·E" (not needed)

5. **Profile Picture**: Optional (add CV icon or your logo)
6. Click "**Save**"

---

## Step 5: Test the GPT

1. Click "**Preview**" 
2. Start a new conversation
3. Upload a test CV (PDF or DOCX)
4. Type: "Please generate a CV for me"
5. Verify:
   - ✅ GPT extracts CV data
   - ✅ GPT calls backend API
   - ✅ Backend returns PDF
   - ✅ GPT provides download link

---

## Test Conversation Example

**User**: "I want to optimize my CV for a senior backend engineer role"

**Expected GPT Response**:
```
I'll help you optimize your CV for a senior backend engineer role.

📋 Phase 1: Analyzing your CV...
[User uploads CV.pdf]

✓ Extracted 1,200 words
✓ Photo detected
✓ Current role: Mid-level Developer

📊 Phase 2: Matching job requirements...
Key skills identified:
- Python ✓ (5 years)
- AWS ✓ (3 years)
- Team leadership ⚠️ (mentioned but brief)

🔧 Phase 3: Building optimized CV...
✓ Enhanced professional summary
✓ Highlighted leadership achievements
✓ Quantified AWS experience

🎨 Phase 5: Generating PDF...
✓ Backend processing
✓ PDF rendered

Your optimized CV is ready! [Download link]
```

---

## Troubleshooting

### "API key not working"
- ✅ Key is: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`
- ✅ Header name is: `x-functions-key` (lowercase, with hyphen)
- Check in Custom GPT Actions settings

### "PDF not generating"
- Verify backend is running: https://cv-generator-6695.azurewebsites.net/api/health
- Should return: `{"status": "healthy", ...}`
- If not, contact support

### "Photo not extracted from DOCX"
- This is normal - Code Interpreter limitations
- GPT will continue without photo
- Backend will use placeholder

### "CV validation failing"
- Check required fields in schema: full_name, email, address_lines, profile
- GPT will show which fields are missing
- User should provide more details

---

## File Checklist

Before deploying, ensure you have:

- ✅ `CUSTOM_GPT_INSTRUCTIONS_COMPACT.md` (System prompt)
- ✅ `CUSTOM_GPT_PHASES_DETAILED.md` (Reference guide)
- ✅ `CUSTOM_GPT_API_REFERENCE.md` (API docs)
- ✅ `openapi_cv_actions.yaml` (OpenAPI schema)
- ✅ Function key: `cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==`

---

## URLs You'll Need

| Purpose | URL |
|---------|-----|
| Custom GPT Editor | https://chat.openai.com/gpts/editor |
| Backend API | https://cv-generator-6695.azurewebsites.net/api |
| Health Check | https://cv-generator-6695.azurewebsites.net/api/health |
| Generate PDF | https://cv-generator-6695.azurewebsites.net/api/generate-cv-action |

---

## Support

**Backend Status**: ✅ Running (verified 2026-01-19)
**API Version**: v1.0
**OpenAPI Version**: 3.1.0
**Last Updated**: 2026-01-19

For issues, check [ENDPOINT_TESTING_REPORT.md](ENDPOINT_TESTING_REPORT.md)

---

## Next Steps After Deployment

1. ✅ Test with sample CV
2. ✅ Share GPT link: `https://chat.openai.com/g/g-YOUR_GPT_ID`
3. ✅ Monitor performance
4. ✅ Collect user feedback
5. ✅ Update instructions as needed

---

**Ready to deploy!** 🚀

Start at: https://chat.openai.com/gpts/editor
