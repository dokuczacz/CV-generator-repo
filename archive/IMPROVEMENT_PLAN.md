# 📋 CV Generator - Improvement Plan

**Date:** January 14, 2026  
**Status:** Planning Phase  
**Goal:** Optimize for Swiss market (max 2 pages) with deterministic GPT integration

---

## 🎯 Identified Issues

### 1. **Visual Pagination Issue**
- **Problem:** No visual separator when content flows to page 2
- **Impact:** Aesthetically unpleasing, hard to distinguish pages
- **Priority:** HIGH

### 2. **Date Column Too Wide**
- **Problem:** Tabulation between dates and position (42.5mm) creates excessive whitespace
- **Source:** Template spec says ~37.5mm effective width, but we're using 42.5mm
- **Priority:** MEDIUM

### 3. **No Character Limit Enforcement**
- **Problem:** Custom GPT has no constraints → can generate 3+ page CVs
- **Impact:** Violates Swiss market standard (max 2 pages)
- **Priority:** CRITICAL

### 4. **GPT Integration Lacks Deterministic Rules**
- **Problem:** GPT is "blind" to layout, needs strict numerical limits
- **Impact:** Cannot guarantee 2-page output
- **Priority:** CRITICAL

---

## 📐 Space Calculation (A4 2-Page Layout)

### Available Space Analysis

**Page Dimensions:**
- A4: 210mm × 297mm
- Usable area per page: (210-25-22.4) × (297-20-20) = **162.6mm × 257mm**

**Page 1:**
- Header (name + contact + photo): ~55mm height
- Remaining space: ~202mm

**Page 2:**
- Full content space: ~257mm

**Total Content Space:** ~459mm vertical height

### Space Consumption by Element Type

**Fixed Elements (non-negotiable):**
- Section title: ~6mm (3mm title + 3mm margin)
- Entry head (date + title): ~5mm
- Bullet point: ~4mm per line
- Paragraph line: ~4.5mm (11pt × 1.3 line-height)
- Section margin: ~6mm

**Example Section Breakdown:**

```
BERUFSERFAHRUNG (Work Experience)
├─ Section title: 6mm
├─ Entry 1:
│  ├─ Header (date + title): 5mm
│  ├─ 4 bullets × 4mm: 16mm
│  └─ Entry margin: 3mm
├─ Entry 2: ~24mm
├─ Entry 3: ~24mm
├─ Entry 4: ~24mm
└─ Entry 5: ~24mm
TOTAL: ~127mm for 5 work entries
```

### Estimated Space Budget (2 pages)

| Section | Est. Height | Max Entries | Max Chars/Entry |
|---------|-------------|-------------|-----------------|
| Header | 55mm | - | - |
| Profil | 35mm | 1 paragraph | ~500 chars |
| Berufserfahrung | 130mm | 5 entries × 4 bullets | 80 chars/bullet |
| Ausbildung | 45mm | 2-3 entries | 120 chars/entry |
| Sprachen | 25mm | 3-5 items | 40 chars/item |
| Fähigkeiten & KI | 40mm | 6-8 items | 60 chars/item |
| Weiterbildungen | 60mm | 6-8 items | 100 chars/item |
| Interessen | 30mm | 1 paragraph | ~300 chars |
| Datenschutz | 20mm | 1 paragraph | ~150 chars |
| **TOTAL** | **~440mm** | | |

**Buffer:** ~19mm (4% safety margin)

---

## 🔧 Technical Solutions

### Solution 1: Page Break Handling

**Approach:** Add visual page breaks in CSS for better aesthetics

```css
/* Add page break styling */
@media print {
  .page-break {
    page-break-after: always;
    margin-bottom: 0;
  }
  
  .page {
    page-break-after: always;
  }
  
  .page:last-child {
    page-break-after: auto;
  }
}

/* Visual indicator for screen preview */
@media screen {
  .page-break::after {
    content: "";
    display: block;
    height: 2mm;
    background: linear-gradient(to bottom, transparent, #e0e0e0, transparent);
    margin: 10mm 0;
  }
}
```

**Implementation:**
1. Add CSS rules for page breaks
2. Inject `<div class="page-break"></div>` between logical page sections
3. Calculate optimal break point (after ~200mm of content)

---

### Solution 2: Optimize Date Column Width

**Current:** `grid-template-columns: 42.5mm 1fr`  
**Template spec:** ~37.5mm effective width  
**Proposed:** `grid-template-columns: 35mm 1fr`

**Rationale:**
- Swiss CVs use compact date format: "2020-01 – 2025-04"
- 35mm = ~13 characters at 11pt Arial
- Reduces whitespace, more modern look
- Matches original DOCX template closer

**Change:**
```css
.entry-head {
  display: grid;
  grid-template-columns: 35mm 1fr;  /* Changed from 42.5mm */
  column-gap: 3mm;  /* Reduced from 4mm */
  align-items: baseline;
  font-weight: 400;
}
```

---

### Solution 3: Character Limit Calculator

**Create deterministic validation tool:**

```python
# Character limits based on space calculations
CV_LIMITS = {
    "full_name": {
        "max_chars": 50,
        "reason": "Header, 16pt font, ~80mm width"
    },
    "profile": {
        "max_chars": 500,
        "max_lines": 7,
        "reason": "~35mm height, 11pt, 1.3 line-height"
    },
    "work_experience": {
        "max_entries": 5,
        "per_entry": {
            "date_range": 20,
            "employer": 50,
            "location": 40,
            "title": 80,
            "bullets": {
                "max_count": 4,
                "max_chars_per_bullet": 80
            }
        },
        "total_height_mm": 130
    },
    "education": {
        "max_entries": 3,
        "per_entry": {
            "date_range": 20,
            "institution": 60,
            "title": 80,
            "details": 120
        },
        "total_height_mm": 45
    },
    "languages": {
        "max_items": 5,
        "max_chars_per_item": 40,
        "total_height_mm": 25
    },
    "it_ai_skills": {
        "max_items": 8,
        "max_chars_per_item": 60,
        "total_height_mm": 40
    },
    "trainings": {
        "max_items": 8,
        "max_chars_per_item": 100,
        "total_height_mm": 60
    },
    "interests": {
        "max_chars": 300,
        "max_lines": 6,
        "total_height_mm": 30
    },
    "data_privacy": {
        "max_chars": 150,
        "max_lines": 3,
        "total_height_mm": 20
    }
}
```

**Features:**
- Pre-flight validation before PDF generation
- Returns specific error messages if limits exceeded
- Suggests which sections to trim
- Estimates resulting page count

---

### Solution 4: GPT Prompt Engineering

**Create strict JSON schema with embedded limits:**

```json
{
  "type": "object",
  "required": ["full_name", "email"],
  "properties": {
    "full_name": {
      "type": "string",
      "maxLength": 50,
      "description": "Full name (max 50 characters)"
    },
    "profile": {
      "type": "string",
      "maxLength": 500,
      "description": "Professional summary (max 500 chars, ~7 lines)"
    },
    "work_experience": {
      "type": "array",
      "maxItems": 5,
      "description": "Maximum 5 work experiences",
      "items": {
        "type": "object",
        "properties": {
          "date_range": {
            "type": "string",
            "maxLength": 20,
            "pattern": "^\\d{4}-\\d{2}( – \\d{4}-\\d{2}|Present)?$"
          },
          "title": {
            "type": "string",
            "maxLength": 80
          },
          "bullets": {
            "type": "array",
            "maxItems": 4,
            "items": {
              "type": "string",
              "maxLength": 80,
              "description": "Max 80 chars per bullet"
            }
          }
        }
      }
    }
  }
}
```

**GPT System Prompt Addition:**

```
STRICT 2-PAGE LIMIT FOR SWISS MARKET CVs:

You must adhere to these character limits to ensure the CV fits exactly 2 A4 pages:

LIMITS:
- Profile: 500 characters max (not words!)
- Work Experience: MAX 5 entries, each with MAX 4 bullets of 80 chars each
- Education: MAX 3 entries
- Languages: MAX 5 items, 40 chars each
- IT/AI Skills: MAX 8 items, 60 chars each
- Trainings: MAX 8 items, 100 chars each
- Interests: 300 characters max
- Data Privacy: 150 characters max

RULES:
1. Count characters, NOT words
2. Prioritize recent/relevant experience
3. Be concise: use strong action verbs
4. If content exceeds limits, TRIM older/less relevant entries
5. NEVER exceed these limits - the PDF generator will reject it

VALIDATION:
Before submitting, verify each section stays within limits.
If over limit, you MUST reduce content.
```

---

## 📋 Implementation Plan

### Phase 1: CSS & Layout Fixes (1-2 hours)

**Tasks:**
1. ✅ Reduce date column width from 42.5mm → 35mm
2. ✅ Add page break styling (CSS)
3. ✅ Add visual page separator for screen preview
4. ✅ Test with current sample data
5. ✅ Update Playwright tests for new snapshots

**Files to modify:**
- `templates/html/cv_template_2pages_2025.css`
- `templates/html/cv_template_2pages_2025.html`

---

### Phase 2: Character Limit Validator (2-3 hours)

**Tasks:**
1. ✅ Create `src/validator.py` with CV_LIMITS
2. ✅ Implement character counting logic
3. ✅ Add height estimation algorithm
4. ✅ Return detailed validation errors
5. ✅ Integrate into `api.py` (pre-flight check)
6. ✅ Add unit tests

**Files to create:**
- `src/validator.py`
- `tests/test_validator.py`

**Files to modify:**
- `api.py` (add validation before rendering)

---

### Phase 3: GPT Integration Schema (1 hour)

**Tasks:**
1. ✅ Create OpenAPI schema with maxLength constraints
2. ✅ Add detailed descriptions with character limits
3. ✅ Create example valid payload
4. ✅ Document GPT system prompt requirements
5. ✅ Add validation examples

**Files to create:**
- `openapi_schema.json`
- `GPT_INTEGRATION.md`

---

### Phase 4: Testing & Validation (2 hours)

**Tasks:**
1. ✅ Test with edge cases (max length content)
2. ✅ Test with over-limit content (should reject)
3. ✅ Verify 2-page constraint holds
4. ✅ Visual comparison with DOCX template
5. ✅ Update Playwright tests
6. ✅ Document validated limits

---

## 🎯 Success Criteria

### Must Have (P0)
- ✅ CV never exceeds 2 pages (A4)
- ✅ API rejects content exceeding character limits
- ✅ Date column optimized (~35mm)
- ✅ Page breaks handled gracefully
- ✅ GPT receives strict JSON schema with limits

### Should Have (P1)
- ✅ Visual page separator in HTML preview
- ✅ Validation error messages specify which section/field exceeded limit
- ✅ Character counter utility for manual testing
- ✅ Height estimation within 5% accuracy

### Nice to Have (P2)
- ⭕ Auto-trimming suggestions for over-limit content
- ⭕ Interactive character counter UI
- ⭕ Visual "space remaining" indicator

---

## 📊 Validation Examples

### Example 1: Valid CV (Within Limits)
```json
{
  "profile": "Experienced engineer with..." (485 chars),
  "work_experience": [
    {
      "bullets": [
        "Led team of 5 developers" (25 chars),
        "Reduced deployment time by 50%" (32 chars),
        "Implemented CI/CD pipeline" (27 chars)
      ]
    }
    // ... 4 more entries
  ]
}
```
**Result:** ✅ PASS - Estimated 1.92 pages

### Example 2: Over Limit
```json
{
  "profile": "Very long profile text exceeding 500 characters..." (650 chars),
  "work_experience": [
    {
      "bullets": [
        "Very detailed bullet point that goes on and on exceeding the 80 character limit significantly" (95 chars)
      ]
    }
  ]
}
```
**Result:** ❌ REJECT
```
{
  "error": "Validation failed",
  "errors": [
    {
      "field": "profile",
      "current": 650,
      "limit": 500,
      "excess": 150,
      "suggestion": "Reduce by 150 characters (30%)"
    },
    {
      "field": "work_experience[0].bullets[0]",
      "current": 95,
      "limit": 80,
      "excess": 15,
      "suggestion": "Reduce bullet to max 80 chars"
    }
  ],
  "estimated_pages": 2.4
}
```

---

## 🔄 Iterative Refinement

**After initial implementation:**
1. Generate 10 test CVs with varying content lengths
2. Measure actual PDF page counts
3. Adjust limits if consistently under/over 2 pages
4. Update GPT schema based on findings

**Calibration targets:**
- 90% of CVs: exactly 2 pages
- 10% of CVs: 1.8-1.99 pages (acceptable)
- 0% of CVs: > 2 pages

---

## 📅 Timeline

| Phase | Duration | Start | End |
|-------|----------|-------|-----|
| Phase 1: CSS Fixes | 2 hours | Now | +2h |
| Phase 2: Validator | 3 hours | +2h | +5h |
| Phase 3: GPT Schema | 1 hour | +5h | +6h |
| Phase 4: Testing | 2 hours | +6h | +8h |
| **TOTAL** | **8 hours** | | |

**Target completion:** Same day

---

## 🎓 Key Principles

1. **Deterministic Over Heuristic**
   - Hard character limits, not "approximate"
   - Reject invalid input, don't auto-adjust

2. **GPT-Friendly Constraints**
   - Clear numerical limits (not "brief" or "concise")
   - Character counts, not word counts
   - Explicit maxItems/maxLength in schema

3. **Fail Fast**
   - Validate before rendering
   - Return specific error messages
   - Guide user to fix exact issues

4. **Swiss Market Standards**
   - Max 2 pages (A4)
   - Professional formatting
   - Concise, achievement-focused content

---

## ✅ Next Steps

**Immediate actions:**
1. Approve this plan
2. Begin Phase 1 (CSS fixes)
3. Create validator with character limits
4. Test with real data
5. Iterate based on measurements

**Questions for you:**
1. Are the character limits reasonable? (e.g., 80 chars/bullet)
2. Should we auto-trim or reject over-limit content?
3. Any specific Swiss CV conventions to enforce?

---

**Plan Status:** 📋 READY FOR IMPLEMENTATION  
**Estimated Effort:** 8 hours  
**Risk Level:** LOW (well-defined scope)
