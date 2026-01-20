# 📋 DETAILED PLANNING - CV TEMPLATE CORRECTION

**Status**: PLANNING PHASE - NO IMPLEMENTATION YET  
**Date**: January 15, 2026

---

## 🔍 ANALYSIS: ORIGINAL DOCX vs CURRENT HTML

### ORIGINAL DOCX STRUCTURE (From Aline Keller CV)

```
1. HEADER (Name + Contact Info)
   - Name: ALINE KELLER
   - Address, Phone, Email
   - Birth Date, Nationality

2. EDUCATION (SECTION 1 - COMES FIRST!)
   - Major/Degree info
   - Bachelor thesis details
   - High school info

3. WORK EXPERIENCE (SECTION 2)
   - Current job (40%)
   - Previous jobs
   - Part-time work

4. FURTHER EXPERIENCE / COMMITMENT (SECTION 3)
   - Board positions
   - Volunteer work
   - Travel/Teaching

5. LANGUAGE SKILLS (SECTION 4)
   - List of languages with levels

6. IT & AI SKILLS (SECTION 5)
   - List of technical skills

7. INTERESTS (SECTION 6)
   - Hobbies/interests paragraph

8. REFERENCES (SECTION 7 - OPTIONAL)
   - "Will be announced on request"
```

### CURRENT HTML TEMPLATE STRUCTURE

```
1. HEADER ✅ Correct
   - Name, Contact, Photo

2. Berufserfahrung (Work Experience) ❌ WRONG - Should be 3rd!
   - Currently in position 2

3. Ausbildung (Education) ❌ WRONG - Should be 1st!
   - Currently in position 3

4. Sprachen (Languages) ✅ Position OK (4th)

5. Fähigkeiten & KI (IT/AI Skills) ✅ Position OK (5th)

6. Weiterbildungen (Trainings) ❌ EXTRA - Not in original!
   - Should be removed or replaced

7. Interessen (Interests) ✅ Position OK (6th)

8. Datenschutzerklärung (Data Privacy) ❌ EXTRA - Not in original!
   - Should be removed
```

---

## ❌ CRITICAL ERRORS IDENTIFIED

### Error 1: SECTION ORDER IS COMPLETELY WRONG
```
Current:  Header → Work → Education → Languages → Skills → Trainings → Interests → Privacy
Correct:  Header → Education → Work → Further Experience → Languages → Skills → Interests → References
```

### Error 2: MISSING SECTIONS
```
Missing: "Further Experience / Commitment" section
This is a key section in the original template!
```

### Error 3: EXTRA SECTIONS (NOT IN ORIGINAL)
```
Extra: "Weiterbildungen" (Trainings)
Extra: "Datenschutzerklärung" (Data Privacy)
These are NOT in the original DOCX template.
```

### Error 4: WRONG SECTION NAMES
```
Current: "Berufserfahrung" ✅ (Correct name)
Current: "Ausbildung" ✅ (Correct name)
Current: "Sprachen" ✅ (Correct name)
Current: "Fähigkeiten & KI" ✅ (Correct name)
Current: "Weiterbildungen" ❌ (Not in original - should be removed)
Current: "Interessen" ✅ (Correct name)
Current: "Datenschutzerklärung" ❌ (Not in original - should be removed)
```

---

## 🎯 CORRECTION PLAN

### Phase 1: Analyze Character Limits for NEW Structure
Need to calculate new character limits since section order changed:
- Education first = more prominent
- New "Further Experience / Commitment" section needed
- Remove "Weiterbildungen" and "Datenschutzerklärung"

### Phase 2: Update HTML Template

**Changes needed:**
1. Reorder sections in `cv_template_2pages_2025.html`:
   - Header
   - Education (MOVE TO POSITION 2)
   - Work Experience (MOVE TO POSITION 3)
   - NEW: Further Experience / Commitment
   - Languages
   - IT & AI Skills
   - Interests
   - REMOVE: Weiterbildungen
   - REMOVE: Datenschutzerklärung

2. Update section titles to match original:
   - Keep German names as shown
   - Add "Further Experience / Commitment" section

### Phase 3: Update Validator

1. Remove limits for:
   - `trainings` field
   - `data_privacy` field

2. Add/update limits for:
   - `further_experience` field (new)
   - Recalculate total height estimates

3. Adjust character limits:
   - Education might have more space now (comes first)
   - Work experience needs adjustment
   - New section for further experience

### Phase 4: Update Test Data

1. Update `extracted_cv_data.py` to use NEW structure:
   ```python
   CV_DATA = {
       "full_name": "...",
       "address_lines": [...],
       "email": "...",
       "education": [...],          # FIRST
       "work_experience": [...],    # SECOND
       "further_experience": [...], # NEW SECTION
       "languages": [...],
       "it_ai_skills": [...],
       "interests": "...",
       # REMOVED: "trainings", "data_privacy"
   }
   ```

2. Populate with either:
   - Original Aline Keller data (from DOCX)
   - OR Mariusz Horodecki data (mapped to new structure)

### Phase 5: Regenerate & Test

1. Generate new test artifacts
2. Verify section order matches original
3. Run Playwright tests
4. Visual verification

---

## 📊 NEW CHARACTER LIMITS (PRELIMINARY)

Based on new section order and removing 2 sections:

```
Profile Section: REMOVED ✅
└─ Frees up ~36mm

Available space (adjusted):
  Header:                 ~70mm
  Education:              ~80mm (more space, first section)
  Work Experience:        ~150mm
  Further Experience:     ~50mm (new section)
  Languages:              ~30mm
  IT & AI Skills:         ~30mm
  Interests:              ~30mm
  Footer/margins:         ~70mm
  ─────────────────────────────
  Total estimate:         ~510mm (fits in 594mm/2 pages) ✅
```

---

## ✅ APPROVAL CHECKLIST BEFORE IMPLEMENTATION

Before I proceed, please confirm:

- [ ] Section order is correct: Header → Education → Work → Further Exp → Languages → Skills → Interests
- [ ] Remove "Weiterbildungen" section entirely?
- [ ] Remove "Datenschutzerklärung" section entirely?
- [ ] Add new "Further Experience / Commitment" section?
- [ ] Use Aline Keller's original data for test, OR use Mariusz data mapped to new structure?
- [ ] Recalculate all character limits (validator)?
- [ ] Golden rules apply to new structure?

---

## 🔒 IMPLEMENTATION APPROACH (When approved)

**Step 1**: Update HTML template (section order + remove extra sections)  
**Step 2**: Update validator (new character limits)  
**Step 3**: Update test data  
**Step 4**: Generate new artifacts  
**Step 5**: Run tests  
**Step 6**: Visual verification  

**One pass, no corrections, done right.**

---

## 📝 TECHNICAL REQUIREMENTS

### Changes Required In:
1. `templates/html/cv_template_2pages_2025.html` - Reorder sections
2. `src/validator.py` - Update character limits & field definitions
3. `tests/extracted_cv_data.py` - Update data structure
4. CSS - No changes (styling stays same)

### Files NOT Touched:
- CSS (styling remains golden rules compliant)
- render.py (PDF generation unchanged)
- API (endpoint unchanged)

### Backward Compatibility:
- Old data format will NOT work
- Need migration path or update all test data

---

**READY FOR YOUR APPROVAL BEFORE IMPLEMENTATION**
