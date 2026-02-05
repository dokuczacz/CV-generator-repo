# Scenario Pack: Prompts + Product Config Refactor

**Scenario ID**: `refactor_prompts_config_2026_02_04`

**Date**: February 4, 2026

**Type**: Deterministic refactor (zero behavior change)

## Goal
Extract inline prompts and product config from `function_app.py` (9261 lines) into dedicated modules without changing runtime behavior. Reduce environment variables to only deployment-specific settings.

## Planning Inputs
- **Scenario source**: Latest session (Azurite empty, using manual artifacts instead).
- **Requirement classification**: Deterministic (no semantic changes).
- **DoD**: Behavior unchanged, PDF generates successfully.
- **Verification method**: Generate PDF from CV data.

## Artifacts

**CV Source**: [cv_source.txt](cv_source.txt)
- Key achievements from work history
- All English content
- Target: project manager engineering role (Swiss)

**Job Posting**: https://www.jobs.ch/en/vacancies/detail/faa45fb1-e562-43b3-a4dd-be9717ed2074/
- Project Manager Engineering (M/F) – 100%
- Dietrich Engineering Consultants, Ecublens, Switzerland
- Full job description available at URL

**Template**: [templates/html/cv_template_2pages_2025.html](../../../templates/html/cv_template_2pages_2025.html)
- 2-page A4 PDF template
- Used for all PDF generation

## Definition of Done

### Commands
```bash
cd c:\AI memory\CV-generator-repo
python -m py_compile function_app.py      # Must pass (no syntax errors)
python -m py_compile src/prompt_registry.py
python -m py_compile src/product_config.py
```

### Thresholds
- ✅ No syntax errors in refactored code
- ✅ No inline prompt strings remain in `function_app.py`
- ✅ All magic numbers moved to `product_config.py`
- ✅ PDF generation works end-to-end (golden flow)

### Fallback
If any test fails or behavior changes:
- Revert refactor (git checkout function_app.py)
- Diagnose in isolated branch

## Golden Flow (Verification)

**Scenario**: Generate 2-page PDF from tailored CV

**Input**:
- CV data with work_experience (4+ roles), it_ai_skills, education, contact
- Job posting context applied
- All validations passing

**Process**:
1. Load CV data from scenario artifacts
2. Apply job tailoring (work experience + skills)
3. Validate against hard limits (200 chars/bullet, 2 pages)
4. Generate PDF via WeasyPrint template
5. Check output: 2 pages, no truncation

**Expected Output**:
- PDF file (2 pages, <2MB)
- No validation errors
- All content preserved

**Success Criterion**:
- PDF downloads successfully
- PDF contains all work experience bullets
- Page count = 2

## Next Steps
1. Create `src/prompt_registry.py` with prompt loading.
2. Create `src/product_config.py` with limits/flags.
3. Extract prompts from `function_app.py` to text files.
4. Replace inline strings with registry lookups.
5. Run golden flow test.
6. Merge changes.
