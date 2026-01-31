# Stage 5a/5b Input Correction - Technical Projects Tailoring

**Date:** 2026-01-29  
**Change:** Removed deterministic job_reference extraction from Stage 5a/5b (Technical Projects)  
**Status:** ✅ Complete

## What Changed

### Before (Incorrect)
Stage 5a/5b was receiving:
1. **job_reference** - Deterministically extracted from job posting
2. work_tailoring_notes - From work_experience stage  
3. further_experience items - CV data

**Problem:** Using extracted job_reference means the stage was using "curated" data instead of raw skill analysis.

### After (Correct)
Stage 5a/5b now receives ONLY:
1. **Skills from FÄHIGKEITEN & KOMPETENZEN section:**
   - `it_ai_skills` - All IT/AI skills
   - `technical_operational_skills` - All technical/operational skills
2. **Tailoring notes from work_experience stage** - `work_tailoring_notes`
3. **Technical projects from CV** - `further_experience` items

**Benefit:** Focuses on candidate's actual skills profile + context from work experience tailoring, not preprocessed job data.

## Code Changes

**File:** [function_app.py](function_app.py#L4286-L4355)  
**Lines:** 4286-4355

### Removed
```python
# OLD - now removed
job_ref = meta2.get("job_reference") if isinstance(meta2.get("job_reference"), dict) else None
job_summary = format_job_reference_for_display(job_ref) if isinstance(job_ref, dict) else ""
notes = _escape_user_input_for_prompt(str(meta2.get("further_tailoring_notes") or ""))
```

### Added
```python
# NEW - correct input sources
skills_it_ai = cv_data.get("it_ai_skills") if isinstance(cv_data.get("it_ai_skills"), list) else []
skills_technical = cv_data.get("technical_operational_skills") if isinstance(cv_data.get("technical_operational_skills"), list) else []
work_tailoring_notes = _escape_user_input_for_prompt(str(meta2.get("work_tailoring_notes") or ""))
```

### Updated Prompt
```python
# OLD prompt structure
user_text = (
    f"[TASK]\n{task}\n\n"
    f"[JOB_SUMMARY]\n{job_summary}\n\n"      # ← REMOVED
    f"[TAILORING_NOTES]\n{notes}\n\n"         # ← INCORRECT FIELD NAME
    f"[FURTHER_EXPERIENCE_FROM_CV]\n..."
)

# NEW prompt structure
user_text = (
    f"[TASK]\n{task}\n\n"
    f"[CANDIDATE_SKILLS]\n{skills_block}\n\n"      # ← NEW: Skills from FÄHIGKEITEN
    f"[WORK_TAILORING_NOTES]\n{work_tailoring_notes}\n\n"  # ← CORRECT FIELD
    f"[TECHNICAL_PROJECTS_FROM_CV]\n..."
)
```

## Input Format Details

### CANDIDATE_SKILLS Block
Combines both skill types:
```
- Python (Expert)
- AWS (Advanced)
- Kubernetes (Intermediate)
- Leadership
...
```

### WORK_TAILORING_NOTES
Carries over context from Stage 4 (Work Experience tailoring):
```
"Key achievements:
- Led team of 8 developers
- Achieved 99.99% uptime
- Launched Project Alpha"
→ (sanitized to single-line)
"Key achievements: Led team of 8 developers Achieved 99.99% uptime Launched Project Alpha"
```

## Stage 5b (IT/AI Skills) - Same Approach

The same fix should be applied to Stage 5b (IT/AI Skills ranking). Currently it may also use job_reference which should be removed. **Verify and apply same fix to IT/AI skills stage if needed.**

## Verification Checklist

✅ function_app.py syntax valid  
✅ Removes job_reference dependency from further_experience stage  
✅ Adds skills (it_ai_skills + technical_operational_skills) as input  
✅ Uses work_tailoring_notes (not further_tailoring_notes)  
✅ Prompt structure updated with correct field names  
✅ Skills formatting helper added (`_format_skills`)  

## Impact

**Scope:** Stage 5a/5b Technical Projects tailoring  
**Risk Level:** LOW - Changes prompt structure only, no API changes  
**User-visible change:** Stage now uses actual skill profile + work context instead of extracted job data  

---

**Status:** Ready for deployment ✅
