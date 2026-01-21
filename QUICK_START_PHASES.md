# Quick Start: Phase 1-3 Session-Based CV Generator

**TL;DR:** Schema validation + session storage + orchestration workflow implemented. Deploy → Update OpenAI tools → Test.

---

## What Changed

### For Users
- **No more empty PDFs** from schema errors
- **No more data loss** across conversation turns  
- **Faster workflow** (1 call vs. 3-5 calls)

### For Agents
- **Schema errors guide you** with examples when you send wrong format
- **Session storage** eliminates need to maintain CV JSON in context
- **Single orchestrated call** option for streamlined workflow

---

## Deployment (5 minutes)

### 1. Install Dependencies

```powershell
pip install azure-data-tables
```

### 2. Deploy

```powershell
git add -A
git commit -m "Phase 1-3: Schema validation + sessions + orchestration"
git push origin main
```

GitHub Actions deploys automatically to `cv-generator-6695.azurewebsites.net`.

### 3. Update OpenAI Dashboard

Go to: https://platform.openai.com/assistants

**Add 5 new tools** (copy from [TOOLS_CONFIG.md](TOOLS_CONFIG.md)):
1. `extract_and_store_cv` → `https://cv-generator-6695.azurewebsites.net/api/extract-and-store-cv`
2. `get_cv_session` → `https://cv-generator-6695.azurewebsites.net/api/get-cv-session`
3. `update_cv_field` → `https://cv-generator-6695.azurewebsites.net/api/update-cv-field`
4. `generate_cv_from_session` → `https://cv-generator-6695.azurewebsites.net/api/generate-cv-from-session`
5. `process_cv_orchestrated` → `https://cv-generator-6695.azurewebsites.net/api/process-cv-orchestrated`

**Upload instructions:** [PROMPT_INSTRUCTIONS_SESSION_BASED.md](PROMPT_INSTRUCTIONS_SESSION_BASED.md)

---

## Test (2 minutes)

```powershell
# Test health
curl https://cv-generator-6695.azurewebsites.net/api/health

# Test session creation
python -c "
import requests, base64

with open('sample.docx', 'rb') as f:
    docx = base64.b64encode(f.read()).decode()

r = requests.post(
    'https://cv-generator-6695.azurewebsites.net/api/extract-and-store-cv',
    json={'docx_base64': docx, 'language': 'en'}
)

print('Status:', r.status_code)
print('Session ID:', r.json().get('session_id'))
"
```

---

## Quick Reference

### Session Workflow

```
1. Upload → extract_and_store_cv → session_id
2. Edit → update_cv_field(session_id, field_path, value)
3. Generate → generate_cv_from_session(session_id) → PDF
```

### Orchestrated Workflow

```
1. process_cv_orchestrated(docx, edits=[...]) → PDF + session_id
```

### Legacy Workflow (Still Works)

```
1. extract_photo → photo URI
2. validate_cv → check structure
3. generate_cv_action → PDF (now with schema validation)
```

---

## Key Features

| Feature | Benefit |
|---------|---------|
| **Schema Validation** | Rejects wrong keys (personal_info, employment_history) with helpful errors |
| **Session Storage** | CV data persists 24h, no re-extraction needed |
| **Nested Field Updates** | `work_experience[0].employer` paths supported |
| **Orchestration** | Single call handles extract → edit → validate → generate |
| **Backward Compatible** | Legacy tools still work |

---

## Files Reference

| File | Purpose |
|------|---------|
| [PHASE_1_2_3_IMPLEMENTATION.md](PHASE_1_2_3_IMPLEMENTATION.md) | Full implementation details |
| [PROMPT_INSTRUCTIONS_SESSION_BASED.md](PROMPT_INSTRUCTIONS_SESSION_BASED.md) | Agent workflow instructions |
| [TOOLS_CONFIG.md](TOOLS_CONFIG.md) | Tool definitions for OpenAI |
| [src/session_store.py](src/session_store.py) | Azure Table Storage implementation |
| [src/schema_validator.py](src/schema_validator.py) | Schema validation logic |

---

## Troubleshooting

**Import error: `No module named 'azure.data'`**
```powershell
pip install azure-data-tables
```

**Session not found:**
- Check session_id is correct UUID
- Sessions expire after 24 hours
- Create new session if expired

**Schema validation error:**
- Check cv_data uses canonical keys (full_name, email, phone, work_experience, education)
- Avoid wrong keys (personal_info, employment_history, cv_source)
- Error response shows correct schema example

---

## Monitor

Watch logs for:
```
✅ Created session abc-123, expires at...
✅ Updated session abc-123, version 2
✅ Generated PDF from session abc-123: 15234 bytes

❌ WRONG KEYS DETECTED: ['personal_info']
❌ Session abc-123 not found or expired
```

---

## Next Steps

1. Deploy (commit + push)
2. Update OpenAI tools
3. Test with real CV
4. Monitor for 24h
5. Schedule daily cleanup: `/api/cleanup-expired-sessions`

---

**Full docs:** [PHASE_1_2_3_IMPLEMENTATION.md](PHASE_1_2_3_IMPLEMENTATION.md)
