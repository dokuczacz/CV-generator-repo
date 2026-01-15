# 🏗️ PHASED IMPLEMENTATION PLAN

**DoD (Definition of Done)**: Custom GPT can generate CVs with different content but same professional style, supporting multiple languages (EN/DE/PL).

---

## 📋 IMPLEMENTATION PHASES

### **PHASE 1: Generate Original 1:1**
Generate Aline Keller CV exactly as in DOCX template

**Deliverables:**
- [ ] Extract all Aline Keller data from DOCX
- [ ] Create test data file: `aline_keller_cv_data.py`
- [ ] Generate HTML/PDF from template
- [ ] Verify 100% match with original DOCX
- [ ] Playwright tests pass (new baselines)
- [ ] Verify visually: section order, spacing, fonts all correct

**Definition of Success:**
- PDF looks identical to original DOCX
- All 12 Playwright tests passing
- No visual differences from original

---

### **PHASE 2: Generate with Mariusz Data**
Same perfect template, but with Mariusz Horodecki's real CV data

**Deliverables:**
- [ ] Map Mariusz data to new section structure:
  - Education (instead of Profil)
  - Work Experience
  - Further Experience (instead of Trainings)
  - Languages
  - IT/AI Skills
  - Interests
- [ ] Create: `mariusz_horodecki_cv_data.py`
- [ ] Generate HTML/PDF
- [ ] Verify formatting and spacing
- [ ] Playwright tests pass
- [ ] Visual verification

**Definition of Success:**
- Professional-looking 2-page CV
- Same style as Aline example
- All data properly formatted
- No truncation

---

### **PHASE 3: GPT Flexibility & Multi-Language**
Make template flexible for GPT to customize

**Deliverables:**
- [ ] Create configurable section titles (language-based)
- [ ] Document section customization options
- [ ] Update validator to support language variants
- [ ] Create: `GPT_CUSTOMIZATION_GUIDE.md`
- [ ] Update OpenAPI schema for flexibility
- [ ] Document how GPT can:
  - Change section titles (EN/DE/PL)
  - Add/remove sections (optional sections)
  - Customize field labels
  - Generate in any language

**Definition of Success:**
- Template supports EN, DE, PL section titles
- GPT can override section names
- Validator accepts custom fields
- OpenAPI schema documented

---

### **PHASE 4: Single Source of Truth (SoT)**
Consolidate all documentation into one master document

**Current Redundant Documents:**
- GOLDEN_RULES.md
- VIOLATIONS_AND_FIXES.md
- DETAILED_PLANNING.md
- PLANNING_SUMMARY.md
- SYSTEM_SUMMARY.md
- DEPLOYMENT_GUIDE.md
- TESTING_STRATEGY.md
- GPT_SYSTEM_PROMPT.md
- IMPROVEMENT_PLAN.md

**Consolidation Plan:**
- [ ] Create `MASTER_SPECIFICATION.md` - Single SoT with all requirements
- [ ] Create `ARCHITECTURE.md` - Technical overview
- [ ] Create `IMPLEMENTATION_GUIDE.md` - Step-by-step for developers
- [ ] Create `GPT_INTEGRATION_GUIDE.md` - For GPT configuration
- [ ] Keep only essential docs, delete redundant ones
- [ ] Add cross-references between documents
- [ ] Version the SoT

**Definition of Success:**
- One master document defines all rules
- All other docs reference it
- No contradictions
- Easy to maintain

---

## 📊 IMPLEMENTATION SEQUENCE

```
PHASE 1: Extract Aline Data → Generate 1:1 → Test & Verify
         ↓
PHASE 2: Map Mariusz Data → Generate CV → Test & Verify
         ↓
PHASE 3: Add GPT Flexibility → Multi-language → Update Validator
         ↓
PHASE 4: Consolidate Docs → Create SoT → Final Review
```

---

## 🎯 SPECIFIC TASKS PER PHASE

### PHASE 1 CHECKLIST

**Step 1.1: Extract Aline Keller Data**
```python
# From DOCX, create aline_keller_cv_data.py
CV_DATA = {
    "full_name": "ALINE KELLER",
    "address_lines": ["Berghofstrasse 15", "8006 Zurich"],
    "phone": "078 345 66 77",
    "email": "aline.keller@uzh.ch",
    "birth_date": "14 October 2002",
    "nationality": "Switzerland",
    
    "education": [
        {
            "date_range": "08/2015 – 07/2021",
            "institution": "Cantonal school Zug",
            "title": "Bilingual Matura (DE/EN)",
            "details": ["New language profile"]
        },
        {
            "date_range": "Expected 07/2026",
            "institution": "University of Zurich",
            "title": "Bachelor of Science - History",
            "details": [
                "Major: History",
                "Minor: Media and Communication Studies",
                "Focus: migration, diversity, history of Southeastern Europe",
                "Bachelor's thesis: 'The influence of Italian migrants on the Swiss population in the 1950s' (Grade 5.5)"
            ]
        }
    ],
    
    "work_experience": [
        {
            "date_range": "06/2023 – Present",
            "employer": "Zuger Zeitung",
            "location": "Zug",
            "title": "Member of the editorial team (40%)",
            "bullets": [
                "Writing and editing newspaper articles on culture and history",
                "Processing texts in CMS (website maintenance)",
                "Accredited journalist at the Solothurn Literature Days"
            ]
        },
        # ... more entries
    ],
    
    "further_experience": [
        {
            "date_range": "Since 01/2024",
            "title": "History Student Council, University of Zurich",
            "role": "Member of the Board",
            "bullets": [
                "Representation of students at faculty meetings",
                "Organisation of events such as alumni events and HS Bar",
                "Editing the newsletter",
                "Supervision of the FVhist website"
            ]
        },
        # ... more entries
    ],
    
    "languages": [
        "German - Mother tongue",
        "English - C1 (Cambridge Certificate of Advanced, 2024)",
        "French - B2"
    ],
    
    "it_ai_skills": [
        "AI literacy and critical thinking",
        "Prompt Engineering",
        "Collaboration tools: Teams, Zoom, padlet, trello",
        "CMS Magnolia",
        "Canva",
        "MS Office"
    ],
    
    "interests": "Cooking (Southeast Asian), reading (English literature, daily newspapers), dancing (salsa, flamenco)"
}
```

**Step 1.2: Update HTML Template**
- Reorder sections: Header → Education → Work → Further Experience → Languages → Skills → Interests
- Remove: Weiterbildungen, Datenschutzerklärung
- No CSS changes (styling stays same)

**Step 1.3: Update Validator**
- Remove: trainings, data_privacy
- Add: further_experience (max 4 entries, 120 chars per bullet)
- Recalculate space estimates

**Step 1.4: Generate Artifacts**
```bash
python tests/generate_test_artifacts.py
```

**Step 1.5: Run Tests**
```bash
npx playwright test --update-snapshots
npx playwright test
```

**Step 1.6: Verify**
- Open PDF: `tests/test-output/preview.pdf`
- Compare with: `wzory/CV_template_2pages_2025.docx`
- Check: section order, spacing, fonts, appearance

---

### PHASE 2 CHECKLIST

**Step 2.1: Map Mariusz Data to New Structure**
```python
# Create mariusz_horodecki_cv_data.py
# Existing extracted_cv_data.py but mapped to:
# - education (instead of profile)
# - work_experience (existing)
# - further_experience (new - from trainings)
# - languages (existing)
# - it_ai_skills (existing)
# - interests (existing)
```

**Step 2.2: Generate with Mariusz Data**
```bash
# Modify generate_test_artifacts.py to accept data source parameter
python tests/generate_test_artifacts.py --data mariusz
```

**Step 2.3: Visual Verification**
- Open generated PDF
- Verify: 2 pages, professional appearance
- Check: Section order, spacing, alignment
- Confirm: Same style as Aline template

**Step 2.4: Tests Pass**
```bash
npx playwright test
# Should pass (same baselines from Phase 1)
```

---

### PHASE 3 CHECKLIST

**Step 3.1: Create Language Configuration**
```python
# In templates/html/cv_template_2pages_2025.html
# Add language support:

SECTION_TITLES = {
    "EN": {
        "education": "Education",
        "work_experience": "Work Experience",
        "further_experience": "Further Experience & Commitment",
        "languages": "Languages",
        "it_ai_skills": "IT & AI Skills",
        "interests": "Interests"
    },
    "DE": {
        "education": "Ausbildung",
        "work_experience": "Berufserfahrung",
        "further_experience": "Weitere Erfahrung & Engagement",
        "languages": "Sprachen",
        "it_ai_skills": "Fähigkeiten & KI",
        "interests": "Interessen"
    },
    "PL": {
        "education": "Edukacja",
        "work_experience": "Doświadczenie zawodowe",
        "further_experience": "Dalsze doświadczenie i zaangażowanie",
        "languages": "Języki",
        "it_ai_skills": "Umiejętności IT & AI",
        "interests": "Zainteresowania"
    }
}
```

**Step 3.2: Update Template to Use Language Config**
```html
<!-- Instead of hardcoded "Ausbildung" -->
<div class="section-title">{{ section_titles.education }}</div>
```

**Step 3.3: Update Validator**
- Accept custom section titles
- Validate that all required sections present
- Allow optional sections

**Step 3.4: Update OpenAPI Schema**
- Add `language` parameter (EN/DE/PL)
- Add `section_titles` optional override object
- Document customization options

**Step 3.5: Create GPT Customization Guide**
- How to change section titles
- How to add/remove sections
- How to customize for different languages
- Examples for EN, DE, PL CVs

---

### PHASE 4 CHECKLIST

**Step 4.1: Create MASTER_SPECIFICATION.md**
- Single source of truth
- All requirements consolidated
- Page setup, typography, structure, spacing
- Section definitions
- Character limits
- Language support

**Step 4.2: Create ARCHITECTURE.md**
- Technical overview
- Component interactions
- Data flow
- Validation flow
- Rendering pipeline

**Step 4.3: Create IMPLEMENTATION_GUIDE.md**
- For developers implementing changes
- File-by-file guide
- Testing procedures
- Common issues

**Step 4.4: Create GPT_INTEGRATION_GUIDE.md**
- For Custom GPT configuration
- System prompt (with language support)
- OpenAPI schema
- Example conversations
- Customization options

**Step 4.5: Delete Redundant Docs**
- Remove: GOLDEN_RULES.md
- Remove: VIOLATIONS_AND_FIXES.md
- Remove: DETAILED_PLANNING.md
- Remove: PLANNING_SUMMARY.md
- Remove: SYSTEM_SUMMARY.md
- Remove: DEPLOYMENT_GUIDE.md
- Remove: TESTING_STRATEGY.md
- Keep: Only essential, linked docs

**Step 4.6: Update README.md**
- Link to MASTER_SPECIFICATION.md as SoT
- Link to ARCHITECTURE.md for technical details
- Link to IMPLEMENTATION_GUIDE.md
- Link to GPT_INTEGRATION_GUIDE.md

---

## 🎓 MASTER SPECIFICATION (Phase 4 Output)

The new SoT will include:

1. **Requirements**
   - Original spec from DOCX
   - Golden rules
   - Character limits
   - Spacing rules

2. **Structure**
   - Section order: Header → Education → Work → Further Exp → Languages → Skills → Interests
   - Data fields for each section
   - Optional vs required sections

3. **Language Support**
   - EN, DE, PL section titles
   - Language-specific character limits (if needed)
   - Multi-language examples

4. **Customization for GPT**
   - What can be customized
   - What cannot be changed (styling)
   - Constraints and validation rules

5. **Testing & Verification**
   - How to test
   - Validation procedures
   - Visual verification

---

## 📝 FILES TO CREATE/MODIFY

### Phase 1 Files:
- `tests/aline_keller_cv_data.py` - NEW
- `templates/html/cv_template_2pages_2025.html` - MODIFY (reorder)
- `src/validator.py` - MODIFY (update fields)

### Phase 2 Files:
- `tests/mariusz_horodecki_cv_data.py` - CREATE (rename from extracted)
- `tests/generate_test_artifacts.py` - MODIFY (data parameter)

### Phase 3 Files:
- `templates/cv_section_titles.py` - NEW (language config)
- `src/validator.py` - MODIFY (language support)
- `api.py` - MODIFY (language parameter)
- `openapi_schema.json` - MODIFY (add language)
- `GPT_CUSTOMIZATION_GUIDE.md` - NEW

### Phase 4 Files:
- `MASTER_SPECIFICATION.md` - NEW (SoT)
- `ARCHITECTURE.md` - NEW
- `IMPLEMENTATION_GUIDE.md` - NEW
- `GPT_INTEGRATION_GUIDE.md` - NEW (from existing prompt)
- `README.md` - MODIFY (add links to SoT)
- DELETE: Old redundant docs

---

## ✅ DEFINITION OF DONE (Per Phase)

### Phase 1 Done When:
- [ ] Aline Keller PDF generated
- [ ] Visually identical to original DOCX
- [ ] All 12 tests passing
- [ ] Section order correct: Education first
- [ ] No visual differences from original

### Phase 2 Done When:
- [ ] Mariusz CV generated with new structure
- [ ] 2-page professional layout
- [ ] Same styling as Aline example
- [ ] All tests passing
- [ ] Visual verification complete

### Phase 3 Done When:
- [ ] Language configuration working
- [ ] GPT can request EN/DE/PL titles
- [ ] OpenAPI schema supports customization
- [ ] GPT customization guide written
- [ ] Multi-language examples tested

### Phase 4 Done When:
- [ ] SoT created and complete
- [ ] All docs consolidated
- [ ] No redundant documentation
- [ ] Cross-references working
- [ ] README points to SoT

---

Ready to proceed with Phase 1? Confirm and I'll execute!

