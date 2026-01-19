# CV Generator - Custom GPT Integration Package

## 📋 Alignment Analysis: Custom GPT ↔ Azure Backend

### Current State vs. Target State

| Feature | Custom GPT Spec (v4.2) | Backend Status | Action Required |
|---------|------------------------|----------------|-----------------|
| **Photo extraction** | ✅ Detect & extract from DOCX/PDF | ✅ Implemented (`src/docx_photo.py`) | Update GPT prompt to call backend |
| **PDF generation** | ✅ Premium template rendering | ✅ WeasyPrint (`src/render.py`) | Expose via Actions |
| **Multi-language** | ✅ EN/DE/PL support | ⚠️ Template only (no i18n) | Add language parameter + translations |
| **Job offer alignment** | ✅ Parse & align skills | ❌ Not implemented | Add NLP matching endpoint |
| **DOCX export** | ✅ Optional output | ❌ Only PDF currently | Add python-docx renderer |
| **ATS compliance** | ✅ Strict formatting rules | ✅ Deterministic template | Already compliant |
| **6-phase pipeline** | ✅ Defined workflow | ⚠️ Partial (missing phases 2-4) | Add analysis/structuring endpoints |
| **Backend integration** | ✅ Actions placeholder | ✅ Azure Functions deployed | Connect via OpenAPI schema |

---

## 🎯 Proposed Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Custom GPT (CV_Dopasowywacz v4.2)             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Phase 1: INGEST (Code Interpreter)                        │  │
│  │  - Extract text from uploaded PDF/DOCX                     │  │
│  │  - Detect photo presence                                   │  │
│  │  - Send to backend: /extract-photo                         │  │
│  └────────────────┬───────────────────────────────────────────┘  │
│                   │                                              │
│  ┌────────────────▼───────────────────────────────────────────┐  │
│  │  Phase 2: ANALYSIS (GPT-4o + Code Interpreter)             │  │
│  │  - Parse job offer (if provided)                           │  │
│  │  - Extract skills from CV                                  │  │
│  │  - Optional: /match-job-offer (future)                     │  │
│  └────────────────┬───────────────────────────────────────────┘  │
│                   │                                              │
│  ┌────────────────▼───────────────────────────────────────────┐  │
│  │  Phase 3: STRUCTURE (GPT-4o)                               │  │
│  │  - Build ATS-compliant JSON                                │  │
│  │  - Validate with: /validate-cv                             │  │
│  └────────────────┬───────────────────────────────────────────┘  │
│                   │                                              │
│  ┌────────────────▼───────────────────────────────────────────┐  │
│  │  Phase 4: GENERATION (GPT-4o)                              │  │
│  │  - Generate professional summary                           │  │
│  │  - Format experience with bullets                          │  │
│  │  - Apply language (EN/DE/PL)                               │  │
│  └────────────────┬───────────────────────────────────────────┘  │
│                   │                                              │
│  ┌────────────────▼───────────────────────────────────────────┐  │
│  │  Phase 5: RENDER (Backend API)                             │  │
│  │  - POST /api/generate-cv-action                            │  │
│  │  - Receive base64 PDF                                      │  │
│  └────────────────┬───────────────────────────────────────────┘  │
│                   │                                              │
│  ┌────────────────▼───────────────────────────────────────────┐  │
│  │  Phase 6: EXPORT (Code Interpreter)                        │  │
│  │  - Decode base64 → PDF file                                │  │
│  │  - Save to /mnt/data/CV_[timestamp].pdf                    │  │
│  │  - Provide download link                                   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                           │
                           │ HTTPS (Actions)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│           Azure Functions (cv-generator-6695)                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  POST /api/extract-photo                                   │  │
│  │  → Input: {docx_base64}                                    │  │
│  │  → Output: {photo_data_uri}                                │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  POST /api/validate-cv                                     │  │
│  │  → Input: {cv_data}                                        │  │
│  │  → Output: {is_valid, errors[], warnings[]}               │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  POST /api/generate-cv-action                              │  │
│  │  → Input: {cv_data, source_docx_base64?, language?}       │  │
│  │  → Output: {success, pdf_base64}                           │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  POST /api/preview-html                                    │  │
│  │  → Input: {cv_data}                                        │  │
│  │  → Output: HTML (for debugging)                            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📁 Required Files Package

### 1. Custom GPT Instructions (`cv_dopasowywacz_v4.2_instructions.md`)
Updated prompt with backend integration hooks

### 2. Custom GPT Actions Schema (`openapi_cv_actions.json`)
OpenAPI 3.0 spec pointing to Azure Functions

### 3. Backend Endpoints (New)
- `POST /api/extract-photo` — Photo extraction only
- `POST /api/validate-cv` — Validation only
- `POST /api/match-job-offer` — Job skills matching (future)
- `POST /api/translate-sections` — Section i18n (future)

### 4. Enhanced `function_app.py`
Add missing endpoints + language support

### 5. Language Support (`src/i18n/`)
- `translations.json` — Section headers in EN/DE/PL
- `language_detector.py` — Auto-detect CV language

### 6. Template Variants (`templates/`)
- `zurich_en.html` — English headers
- `zurich_de.html` — German headers
- `zurich_pl.html` — Polish headers

---

## 🔧 Implementation Phases

### Phase 1: Immediate (Backend Endpoints) ✅
**Status**: Mostly complete
- ✅ Photo extraction (`/api/extract-photo` — via existing logic)
- ✅ PDF generation (`/api/generate-cv-action`)
- ✅ HTML preview (`/api/preview-html`)
- ⚠️ Validation endpoint (merge into `/validate-cv`)

### Phase 2: Quick Wins (1-2 hours)
**Add missing API endpoints**:
```python
@app.route(route="extract-photo", methods=["POST"])
def extract_photo_only(req):
    """Standalone photo extraction"""
    
@app.route(route="validate-cv", methods=["POST"])
def validate_cv_only(req):
    """Standalone validation"""
```

### Phase 3: Language Support (2-3 hours)
**Add i18n layer**:
- Template variants with translated headers
- Language parameter in API
- Section translation mapping

### Phase 4: Custom GPT Integration (1 hour)
**Configure Actions**:
- Update OpenAPI schema
- Add authentication (function key)
- Test with Custom GPT

### Phase 5: Job Matching (Future, 4-6 hours)
**NLP-based skill alignment**:
- Parse job offer text
- Extract required skills
- Match against CV skills
- Suggest additions

---

## 📄 File Deliverables

### File 1: `custom_gpt_instructions.md`
Complete Custom GPT system prompt with:
- Backend API integration hooks
- Phase-by-phase workflow
- Error handling
- Example JSON payloads

### File 2: `openapi_actions_schema.json`
OpenAPI 3.0 spec for Custom GPT Actions:
```json
{
  "openapi": "3.0.0",
  "servers": [{
    "url": "https://cv-generator-6695.azurewebsites.net/api"
  }],
  "paths": {
    "/extract-photo": {...},
    "/validate-cv": {...},
    "/generate-cv-action": {...}
  }
}
```

### File 3: `enhanced_function_app.py`
Updated Azure Functions with:
- Standalone photo extraction
- Standalone validation
- Language parameter support
- Enhanced error handling

### File 4: `translations.json`
Section headers in 3 languages:
```json
{
  "en": {
    "profile": "Professional Summary",
    "experience": "Work Experience",
    ...
  },
  "de": {
    "profile": "Berufsprofil",
    "experience": "Berufserfahrung",
    ...
  },
  "pl": {...}
}
```

### File 5: `deployment_guide.md`
Step-by-step Custom GPT setup:
1. Copy instructions to Custom GPT
2. Import Actions schema
3. Add function key authentication
4. Test with sample CV

---

## 🎯 Immediate Next Steps

### Option A: Full Package (Recommended)
Generate all 5 files + deploy enhanced backend

### Option B: Minimal Viable Integration
1. Update Custom GPT instructions only
2. Point to existing `/generate-cv-action` endpoint
3. Add photo extraction in GPT code interpreter
4. Test end-to-end flow

### Option C: Incremental
1. Start with Custom GPT instructions
2. Test with current backend
3. Add missing endpoints based on actual usage

---

## 📊 Integration Checklist

- [ ] Custom GPT instructions updated with backend URLs
- [ ] OpenAPI schema imported to Custom GPT Actions
- [ ] Function key added to GPT authentication
- [ ] Photo extraction endpoint tested
- [ ] Validation endpoint tested
- [ ] PDF generation tested with base64 response
- [ ] Language parameter working (EN/DE/PL)
- [ ] End-to-end test: Upload CV → Get PDF download
- [ ] Error handling tested (invalid JSON, missing fields)
- [ ] Performance validated (<10s total pipeline)

---

## 🚀 Recommendation

**Start with Option B (Minimal Viable Integration)**:

1. I'll create Custom GPT instructions that work with current backend
2. You test the flow manually
3. We iterate based on real usage patterns
4. Add advanced features (job matching, DOCX export) later

**Advantages**:
- ✅ Works immediately with deployed backend
- ✅ Validates architecture before building more
- ✅ Identifies missing pieces through real usage
- ✅ Faster time-to-production

**Ready to proceed?**

Choose:
- **A**: Generate full package now (5 files)
- **B**: Start minimal, iterate (Custom GPT instructions only)
- **C**: Review specific file first (which one?)
