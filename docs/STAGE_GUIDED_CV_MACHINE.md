# Stage-Guided CV Machine: Complete Architecture & Implementation Plan

**Status:** Master Blueprint (Final Baseline)  
**Date:** 2026-01-28  
**Philosophy Origin:** User insight - "AI is a cognitive execution engine controlled by deterministic process"

---

## I. EXECUTIVE SUMMARY

### The Paradigm Shift

**Old Model (Chat-Based):**
```
User → Chat → LLM Interprets → ???  (infers state) → Backend Action (maybe)
```
Problem: LLM controls flow. Free-text ambiguity. State not persisted.

**New Model (Stage-Guided):**
```
User → [Structured UI] → Backend State Machine → [Call AI for scoped task] → [Lock stage]
```
Philosophy: Backend owns process. UI owns choices. AI executes bounded work.

### Why This Works

1. **Deterministic:** Each stage has clear entry condition, exit condition, success criterion
2. **Testable:** 5 stages × 3-4 per-stage actions = ~20 test paths (vs 1000+ conversation paths)
3. **Scalable:** Today = explicit confirmations. Tomorrow = auto-complete stages with confidence threshold
4. **Clear Responsibility:** Backend (state), UI (choices), AI (content)
5. **Production-Ready:** No "I don't understand what happened" — every action is explicit

### Problem It Solves

| Issue | Symptom | Fix |
|-------|---------|-----|
| FSM state inferred | Stage field missing from metadata | Stage = output of each UI action, persisted immediately |
| Agent hallucination | "Done" without tool calls | Agent never owns flow, only executes section tasks |
| Confirmation loops | User: "yes" 3×, Agent: "Done" 3× | Structured buttons eliminate ambiguity |
| Long context degrades determinism | Session grows to 20+ turns | Each stage clears context, starts fresh |
| Unclear progress | User: "Am I done?" | UI shows: "Stage 2/5: Education" |

---

## II. ARCHITECTURE: THE 5-STAGE PIPELINE

### Stage Definition Template

Each stage has:
- **Goal:** What user accomplishes
- **Entry Condition:** Backend validates readiness
- **User Action:** Explicit structured choices (buttons, forms)
- **AI Invocation:** Only if stage intent is clear
- **Exit Validation:** What must be true to proceed
- **State Persisted:** What metadata is locked

---

### Stage 1: CONTACT_INFO

**Goal:** Confirm or update personal and contact data

**Entry Condition:**
- Session created
- Initial CV data available (extracted from upload or prefill)
- Contact section parsed and available

**User Sees:**
```
┌─────────────────────────────────────────┐
│ Stage 1/5: Contact Information          │
├─────────────────────────────────────────┤
│ ✓ Name: John Smith                      │
│   Email: john@example.com               │
│   Phone: +1-555-1234                    │
│   Location: San Francisco, CA           │
│                                         │
│ [ Edit ] or [ Next ]                    │
└─────────────────────────────────────────┘
```

**User Actions:**
- `[Edit]` → Open inline form, update fields, save
- `[Next]` → Proceed to EDUCATION stage

**AI Invocation (Optional):**
- If Edit triggered: Normalize phone, validate email, standardize location format
- Task: `normalize_contact_data(contact_dict) → contact_dict`

**State Persisted After User Clicks [Next]:**
```python
{
  "cv_stage": "CONTACT_INFO",
  "stage_status": "COMPLETED",
  "contact_data": {
    "name": "John Smith",
    "email": "john@example.com",
    "phone": "+1-555-1234",
    "location": "San Francisco, CA"
  },
  "stage_locked": true,
  "stage_exit_timestamp": "2026-01-28T10:00:00Z"
}
```

**Exit Validation:**
- Contact data has: name, email (or phone)
- Location is not empty
- If validation fails: Show error, stay on stage, allow re-edit

**Backend State Transition:**
```python
if (contact_data has required fields):
    cv_stage = "CONTACT_INFO" → "EDUCATION"
    next_stage_display = get_stage_display("EDUCATION")
    return {
        "stage_status": "READY_FOR_NEXT",
        "next_stage": "EDUCATION",
        "ui_action": build_education_stage_ui()
    }
else:
    return {
        "stage_status": "VALIDATION_FAILED",
        "message": "Contact information incomplete",
        "ui_action": build_contact_stage_ui(errors=[...])
    }
```

---

### Stage 2: EDUCATION

**Goal:** Build a clear and standardized education history

**Entry Condition:**
- CONTACT_INFO stage completed and locked
- Education entries extracted from CV

**User Sees:**
```
┌─────────────────────────────────────────┐
│ Stage 2/5: Education                    │
├─────────────────────────────────────────┤
│ ✓ Bachelor of Science in CS             │
│   University of California, Berkeley     │
│   Graduated: May 2015                    │
│   [ Edit ]                              │
│                                         │
│   Master of Science in AI               │
│   Carnegie Mellon University            │
│   Graduated: May 2017                   │
│   [ Edit ]                              │
│                                         │
│ [ + Add Another ] [ Skip ] [ Next ]     │
└─────────────────────────────────────────┘
```

**User Actions:**
- `[Edit]` on any entry → Inline form edit
- `[+ Add Another]` → New education entry form
- `[Skip]` → No education entries, proceed
- `[Next]` → Confirm and proceed to WORK_EXPERIENCE

**AI Invocation (Per Entry):**
- Task: `standardize_education_entry(entry_dict) → entry_dict`
  - Standardize degree titles ("BS" → "Bachelor of Science")
  - Validate university names
  - Format dates (YYYY-MM format)
  - Capitalize properly

**State Persisted After [Next]:**
```python
{
  "cv_stage": "EDUCATION",
  "stage_status": "COMPLETED",
  "education": [
    {
      "degree": "Bachelor of Science",
      "field": "Computer Science",
      "institution": "University of California, Berkeley",
      "graduation_date": "2015-05",
      "gpa": "3.8"
    },
    ...
  ],
  "stage_locked": true
}
```

**Exit Validation:**
- If education is provided: At least 1 valid entry
- If skipped: Mark `has_education: false`
- Date validation: graduation_date is valid YYYY-MM

---

### Stage 3: WORK_EXPERIENCE

**Goal:** Construct impactful, achievement-oriented work history

**Entry Condition:**
- EDUCATION stage completed
- Work experience entries extracted and available

**User Sees:**
```
┌──────────────────────────────────────────┐
│ Stage 3/5: Work Experience               │
├──────────────────────────────────────────┤
│ Company: Acme Corp                       │
│ Title: Senior Software Engineer          │
│ Duration: Jan 2020 - Present             │
│ Current Bullets:                         │
│ • Developed microservices architecture   │
│ • Led team of 5 engineers                │
│ • Improved performance by 40%            │
│                                          │
│ [ Review & Enhance ] [ Edit ] [ Remove ] │
│                                          │
│ Company: TechStart Inc                   │
│ Title: Software Engineer                 │
│ Duration: Jun 2017 - Dec 2019            │
│ [ Review & Enhance ] [ Edit ] [ Remove ] │
│                                          │
│ [ + Add New Role ] [ Skip ] [ Next ]     │
└──────────────────────────────────────────┘
```

**User Actions:**
- `[Review & Enhance]` → AI rewrites bullets to be metric-driven, concise, ATS-optimized
- `[Edit]` → Edit role details (title, company, dates, bullets)
- `[Remove]` → Delete this entry
- `[+ Add New Role]` → Add another work entry
- `[Skip]` → No work experience
- `[Next]` → Confirm all roles, proceed

**AI Invocation (Per Role):**
- Task: `enhance_work_bullets(role_dict, job_title, industry) → enhanced_bullets`
  - Input: Current bullets, role title, industry context
  - Output: 3-5 ATS-optimized bullets with metrics
  - Rules:
    - Start with strong action verbs (Developed, Led, Improved)
    - Include quantifiable results (40%, $2M, 5×)
    - Remove fluff ("responsible for", "helped with")
    - Highlight impact (business, technical, team)
  
- Example:
  ```
  Input:  "Worked on backend stuff, made it faster"
  Output: "Optimized backend infrastructure, reducing query latency by 60% and improving API throughput to 10K req/s"
  ```

**State Persisted After [Next]:**
```python
{
  "cv_stage": "WORK_EXPERIENCE",
  "stage_status": "COMPLETED",
  "work_experience": [
    {
      "company": "Acme Corp",
      "title": "Senior Software Engineer",
      "start_date": "2020-01",
      "end_date": null,
      "is_current": true,
      "bullets": [
        "Developed microservices architecture serving 2M+ users...",
        "Led team of 5 engineers through 3 major product launches...",
        "Improved system performance by 40%, reducing infrastructure costs by $500K annually"
      ]
    },
    ...
  ],
  "stage_locked": true
}
```

**Exit Validation:**
- At least 1 work entry, OR explicitly skipped
- Each entry has: company, title, dates, at least 1 bullet
- Dates are valid and logical (start < end or end is null)

---

### Stage 4: PROFILE_AND_SKILLS

**Goal:** Synthesize a coherent professional narrative and skill summary

**Entry Condition:**
- WORK_EXPERIENCE stage completed
- Previous contact + education + work all locked

**User Sees:**
```
┌──────────────────────────────────────────┐
│ Stage 4/5: Profile & Skills              │
├──────────────────────────────────────────┤
│ Professional Focus:                      │
│ [ ] Technical Leadership                 │
│ [ ] Individual Contributor               │
│ [x] Hybrid (Technical + Team Mgmt)       │
│                                          │
│ Generated Profile Summary:                │
│ ┌────────────────────────────────────┐   │
│ │ Results-driven Senior Software     │   │
│ │ Engineer with 8+ years building    │   │
│ │ scalable systems and leading       │   │
│ │ high-performing teams. Proven      │   │
│ │ expertise in cloud architecture,   │   │
│ │ performance optimization, and      │   │
│ │ product delivery. Track record...  │   │
│ └────────────────────────────────────┘   │
│ [ Edit ] [ Regenerate ]                  │
│                                          │
│ Skills (Auto-extracted from experience): │
│ Architecture Design, Python, AWS, Kubernetes,
│ Team Leadership, Agile, Performance Tuning,
│ Mentoring, System Design, TypeScript     │
│                                          │
│ [ Edit ] [ Auto-group ] [ Next ]         │
└──────────────────────────────────────────┘
```

**User Actions:**
- Select professional focus (Technical, Managerial, Hybrid)
- `[Regenerate]` → AI regenerates profile summary for different focus
- `[Edit]` → Manually edit profile text
- `[Edit]` skills → Add/remove skills
- `[Auto-group]` → AI groups skills by category (Languages, Infrastructure, etc.)
- `[Next]` → Confirm and proceed to FINAL_CV_GENERATION

**AI Invocations:**

1. **Generate Profile Summary:**
   - Task: `generate_profile_summary(contact, work_exp, education, focus) → profile_text`
   - Input: Name, key achievements, years of experience, professional focus
   - Output: 3-4 sentences, compelling, ATS-friendly
   - Length: 150-200 words

2. **Auto-Group Skills:**
   - Task: `group_skills_by_category(skills_list) → {category: [skills]}`
   - Output:
     ```python
     {
       "Languages": ["Python", "TypeScript", "Go"],
       "Cloud & Infrastructure": ["AWS", "Kubernetes", "Docker"],
       "Domains": ["System Design", "Performance Optimization"],
       "Soft Skills": ["Team Leadership", "Mentoring"]
     }
     ```

**State Persisted After [Next]:**
```python
{
  "cv_stage": "PROFILE_AND_SKILLS",
  "stage_status": "COMPLETED",
  "professional_focus": "HYBRID",
  "profile_summary": "Results-driven Senior Software Engineer...",
  "skills": {
    "Languages": ["Python", "TypeScript", "Go"],
    "Cloud & Infrastructure": ["AWS", "Kubernetes", "Docker"],
    ...
  },
  "stage_locked": true
}
```

**Exit Validation:**
- Profile summary exists and is 100-300 words
- At least 5 skills provided
- Professional focus is one of: TECHNICAL, MANAGERIAL, HYBRID

---

### Stage 5: FINAL_CV_GENERATION

**Goal:** Produce the final CV document

**Entry Condition:**
- All 4 previous stages completed and locked
- All exit validations passed

**User Sees:**
```
┌──────────────────────────────────────────┐
│ Stage 5/5: Generate Final CV             │
├──────────────────────────────────────────┤
│ ✓ Contact Information    [Complete]     │
│ ✓ Education              [Complete]     │
│ ✓ Work Experience        [Complete]     │
│ ✓ Profile & Skills       [Complete]     │
│                                          │
│ All sections ready. Generate your CV.   │
│                                          │
│ [ Generate PDF ]                         │
│                                          │
│ Status: Initializing PDF render...      │
└──────────────────────────────────────────┘
```

**User Actions:**
- `[Generate PDF]` → Backend generates final PDF using template

**AI Invocation:** None (pure rendering)

**Backend Operation:**
```python
if all_stages_locked and all_validations_passed:
    pdf = render_cv_from_locked_sections(cv_data)
    return {
        "stage_status": "CV_GENERATED",
        "pdf_url": "s3://bucket/cv_<session_id>.pdf",
        "download_link": "/api/download-cv/<session_id>"
    }
else:
    return {
        "stage_status": "GENERATION_FAILED",
        "reason": "Not all sections complete"
    }
```

**State Persisted After [Generate PDF]:**
```python
{
  "cv_stage": "FINAL_CV_GENERATION",
  "stage_status": "COMPLETED",
  "pdf_generated": true,
  "pdf_url": "s3://bucket/cv_<session_id>.pdf",
  "pdf_generated_timestamp": "2026-01-28T10:15:00Z",
  "session_status": "DONE"
}
```

---

## III. ROLE SEPARATION BLUEPRINT

### Backend (State & Flow Owner)

**Responsibilities:**
- Owns current `cv_stage` and persists it in session metadata
- Computes valid next stages based on current state + exit validations
- Validates user input before accepting state transitions
- Determines which stage UI to render
- Calls AI functions for bounded tasks only (never for flow control)
- Enforces data contracts (what must be true to exit each stage)
- Returns explicit response with `ui_action` describing user's next choices

**No Authority Over:**
- How user perceives the flow
- What text to display
- How user enters data (UI's job)
- Whether to skip a stage (user choice, backend honors)

**Key Functions:**
```python
def resolve_next_stage(current_stage, user_action, cv_data):
    """Deterministic state transition logic."""
    if current_stage == CONTACT_INFO:
        if validate_contact_data(cv_data):
            return EDUCATION
        else:
            return CONTACT_INFO  # Stay, return validation errors
    elif current_stage == EDUCATION:
        if user_action == "SKIP" or validate_education_data(cv_data):
            return WORK_EXPERIENCE
        else:
            return EDUCATION

def build_stage_ui(stage, cv_data):
    """Returns UI action descriptor for frontend."""
    if stage == CONTACT_INFO:
        return {
            "stage": "CONTACT_INFO",
            "stage_number": 1,
            "total_stages": 5,
            "title": "Contact Information",
            "description": "Confirm or update your personal and contact data",
            "ui_elements": [
                {"type": "display", "label": "Name", "value": cv_data.contact.name},
                {"type": "display", "label": "Email", "value": cv_data.contact.email},
                ...
            ],
            "actions": [
                {"label": "Edit", "action_id": "EDIT_CONTACT"},
                {"label": "Next", "action_id": "PROCEED_NEXT"}
            ]
        }

def handle_user_action(session_id, stage, action_id, input_data):
    """Process explicit user action, update state, return next UI."""
    session = load_session(session_id)
    
    # Validate action is valid for current stage
    if action_id not in VALID_ACTIONS[stage]:
        return error_response("Invalid action for current stage")
    
    # Process action
    if action_id == "EDIT_CONTACT":
        # User edited contact, save changes
        session.cv_data.contact.update(input_data)
    
    # If user confirmed proceeding, validate + transition
    elif action_id == "PROCEED_NEXT":
        if not validate_stage_data(session.cv_data, stage):
            return build_validation_error_ui(stage, errors)
        session.cv_stage = resolve_next_stage(stage, action_id, session.cv_data)
        session.stage_locked = True
    
    # Persist and return next UI
    save_session(session)
    return {
        "session_id": session_id,
        "current_stage": session.cv_stage,
        "ui_action": build_stage_ui(session.cv_stage, session.cv_data)
    }
```

---

### Frontend UI (User Interaction & Choices)

**Responsibilities:**
- Renders stage-specific UI based on backend's `ui_action`
- Presents structured choices (buttons, forms, selections)
- Prevents free-text input when deterministic choices required
- Shows clear progress (Stage 2/5, [████░░░░░])
- Provides inline help/explanations for each stage
- Collects user input via structured form (not chat)
- Sends explicit `user_action` with typed payload to backend

**No Authority Over:**
- Stage transitions (backend owns this)
- Validations (backend owns this)
- AI invocations (backend owns this)
- Flow logic (backend owns this)

**Key Components:**

```typescript
// UIActionHandler.tsx
interface UIAction {
  stage: string;
  stage_number: number;
  total_stages: number;
  title: string;
  description: string;
  ui_elements: UIElement[];
  actions: UserAction[];
}

interface UIElement {
  type: "display" | "input" | "selector" | "form";
  label: string;
  value?: any;
  required?: boolean;
  validation?: RegExp;
  options?: {label: string, value: any}[];
}

interface UserAction {
  label: string;
  action_id: string;
  style?: "primary" | "secondary" | "tertiary";
  requires_input?: boolean;
}

export function StageContainer({ uiAction, onAction }: Props) {
  return (
    <div className="stage-container">
      <StageHeader 
        current={uiAction.stage_number}
        total={uiAction.total_stages}
        title={uiAction.title}
      />
      
      <StageContent 
        elements={uiAction.ui_elements}
        onUpdate={setFormData}
      />
      
      <StageActions>
        {uiAction.actions.map(action => (
          <button
            key={action.action_id}
            onClick={() => onAction(action.action_id, formData)}
            className={`action-${action.style}`}
          >
            {action.label}
          </button>
        ))}
      </StageActions>
    </div>
  );
}

// Key behavior: When action clicked
async function handleActionClick(actionId: string, inputData: any) {
  const response = await fetch("/api/process-stage-action", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      stage: currentStage,
      action_id: actionId,
      input_data: inputData
    })
  });
  
  const { current_stage, ui_action, errors } = await response.json();
  
  // Render next stage or show validation errors
  setUIAction(ui_action);
  setCurrentStage(current_stage);
}
```

---

### AI Agent (Bounded Content Execution)

**Responsibilities:**
- Executes well-defined, stage-scoped content transformation tasks ONLY
- Never owns or infers flow/state
- Never says "Done" or "I'm finished"
- Only called when stage intent is crystal clear
- Returns deterministic output typed to the stage contract
- Can be scaled (multiple instances, no state conflicts)

**No Authority Over:**
- When to be invoked (backend decides)
- Which stage is active (backend owns)
- Whether to proceed to next stage (backend owns)
- Confirming user actions (user decides, backend validates)

**Allowed Tasks:**

| Stage | Task | Input | Output |
|-------|------|-------|--------|
| CONTACT_INFO | `normalize_contact_data()` | `{name, email, phone, location}` | `{name, email, phone, location}` |
| EDUCATION | `standardize_education_entry()` | `{degree, field, institution, date, gpa}` | `{degree, field, institution, date, gpa}` |
| WORK_EXPERIENCE | `enhance_work_bullets()` | `{company, title, bullets[], context}` | `{bullets[]: enhanced}`  |
| PROFILE_AND_SKILLS | `generate_profile_summary()` | `{contact, work_exp, education, focus}` | `{profile_text}` |
| PROFILE_AND_SKILLS | `group_skills_by_category()` | `{skills[]}` | `{category: skills[]}` |
| FINAL_CV_GENERATION | (None) | N/A | N/A |

**Example Agent Function:**

```python
@app.function_route(route="ai/enhance-work-bullets", methods=["POST"])
def enhance_work_bullets(req: func.HttpRequest) -> func.HttpResponse:
    """
    Stage-scoped task: Rewrite work bullets to be ATS-optimized.
    NEVER called as general-purpose AI. Called ONLY when work experience stage
    needs enhancement and user explicitly clicked [Review & Enhance].
    """
    data = req.get_json()
    
    # Validate input contract
    if not all(k in data for k in ["company", "title", "bullets", "job_context"]):
        return func.HttpResponse(
            json.dumps({"error": "Missing required fields"}),
            status_code=400
        )
    
    # Call LLM with bounded, stage-specific prompt
    prompt = f"""
    You are an ATS-optimized CV writer. Your task: rewrite these work bullets.
    
    Company: {data['company']}
    Title: {data['title']}
    Current bullets: {json.dumps(data['bullets'])}
    Job context: {data['job_context']}
    
    Requirements:
    - 3-5 bullets total
    - Start with action verbs (Developed, Led, Optimized, etc.)
    - Include quantifiable metrics (%, $, count, time)
    - Each bullet ≤ 1 line
    - Focus on business/technical impact, not activities
    
    Return ONLY JSON:
    {{"bullets": ["bullet1", "bullet2", "bullet3"]}}
    """
    
    response = call_openai(prompt)
    bullets = json.loads(response.json()["choices"][0]["message"]["content"])
    
    # Validate output
    if len(bullets["bullets"]) < 1 or len(bullets["bullets"]) > 5:
        return func.HttpResponse(
            json.dumps({"error": "Invalid bullet count"}),
            status_code=400
        )
    
    # Return only the contract-specified output
    return func.HttpResponse(json.dumps(bullets))

# Key behavior: Bounded, typed, no side effects, no state
```

---

## IV. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Wave 1) — 8 hours

**Goal:** Build deterministic stage infrastructure. No more chat-based flow.

**Deliverables:**
1. New `CVStage` enum with 5 explicit stages
2. `handle_user_action()` function replacing chat handler
3. Hard fail old sessions (no migration)
4. UI contract with `ui_action` structure
5. Backend state machine with clear transitions
6. 5 stage validation schemas

**Tasks:**

| Task | Time | Details |
|------|------|---------|
| Add CVStage enum | 1h | CONTACT_INFO, EDUCATION, WORK_EXPERIENCE, PROFILE_AND_SKILLS, FINAL_CV_GENERATION |
| Add stage validation schemas | 2h | Pydantic models for each stage's exit conditions |
| Implement `handle_user_action()` | 2h | Orchestrates stage transitions, calls AI tasks, returns ui_action |
| Hard fail old sessions | 1h | Add version check, return 409 for stage=null |
| Add `build_stage_ui()` function | 1h | Generates ui_action descriptor for each stage |
| Backend tests: State transitions | 1h | Verify stage 1→2, validation failures, skips |

**Success Criteria:**
- ✅ New session → CONTACT_INFO stage
- ✅ Old session (no stage field) → 409 error
- ✅ [Next] on CONTACT_INFO (valid data) → EDUCATION
- ✅ [Skip] on EDUCATION → WORK_EXPERIENCE
- ✅ Validation failure → stays on stage, returns errors
- ✅ All 5 stages reachable in sequence

**Testing:** Backend unit tests + manual flow trace

---

### Phase 2: AI Integration (Wave 2) — 6 hours

**Goal:** Connect stage-scoped AI tasks to pipeline. Each stage calls AI only when needed.

**Deliverables:**
1. 5 AI function endpoints (one per stage)
2. Integration in `handle_user_action()` for [Review & Enhance], [Regenerate], [Auto-group]
3. AI response validation
4. Error handling if AI fails (fallback to user input)

**Tasks:**

| Task | Time | Details |
|------|------|---------|
| `normalize_contact_data()` | 1h | Standard formats, validation |
| `standardize_education_entry()` | 1h | Degree titles, date standardization |
| `enhance_work_bullets()` | 1.5h | Most complex, metric-driven rewrite |
| `generate_profile_summary()` | 1h | Focus-aware narrative |
| `group_skills_by_category()` | 0.5h | Simple categorization |
| Integration + error handling | 1h | Fallback to user input if AI fails |

**Success Criteria:**
- ✅ [Enhance] on work role → 3-5 metric-driven bullets returned
- ✅ [Regenerate] on profile → Different summary for different focus
- ✅ AI error → Show error, keep user data intact, allow manual edit
- ✅ Validated AI output matches stage contract

**Testing:** Test each AI function in isolation, then integration tests

---

### Phase 3: Frontend Implementation (Wave 3) — 5 hours

**Goal:** Build UI layer that renders stage-specific actions, disables free-text where needed.

**Deliverables:**
1. `UIActionHandler` component
2. Stage-specific input components (ContactForm, EducationList, WorkExperienceList, etc.)
3. Progress indicator (Stage 2/5)
4. Form validation (client-side check before submit)
5. Disable free-text when buttons required

**Tasks:**

| Task | Time | Details |
|------|------|---------|
| UIActionHandler component | 1h | Renders ui_action, dispatches user actions |
| Stage-specific forms | 2h | ContactForm, EducationList, WorkList, ProfileForm |
| Progress & navigation | 0.5h | Stage indicator, back button (read-only), status |
| Client-side validation | 0.5h | Show errors before submit, disable [Next] if invalid |
| Disable free-text logic | 1h | When ui_action.disable_free_text, hide chat input |

**Success Criteria:**
- ✅ Stage 1: See contact info, [Edit] works, [Next] disables if invalid
- ✅ Stage 2: Add education, [Skip] works, validation required before [Next]
- ✅ Stage 3: [Review & Enhance] calls backend, shows new bullets
- ✅ Stage 4: [Regenerate] switches focus, [Auto-group] categorizes skills
- ✅ Stage 5: [Generate PDF] initiates render, shows download link
- ✅ No free-text chat input visible during stage flow

**Testing:** E2E Playwright tests for all 5 stages

---

### Phase 4: Integration & Testing (Wave 4) — 4 hours

**Goal:** Full end-to-end testing, edge cases, production readiness.

**Deliverables:**
1. End-to-end test suite (fresh session → stage 5 → PDF)
2. Edge case tests (validation failures, AI errors, re-edits)
3. Performance tests (stage transitions < 500ms)
4. Production checklist

**Tasks:**

| Task | Time | Details |
|------|------|---------|
| E2E happy path test | 1h | Upload CV → all 5 stages → PDF download |
| Validation failure tests | 1h | Missing contact, invalid dates, empty bullets |
| AI error handling | 0.5h | AI timeout, malformed response, fallback |
| Re-edit middle stage | 1h | Go back, modify education, confirm, ensure work updated correctly |
| Performance baseline | 0.5h | Measure stage transitions, AI calls, PDF render |

**Success Criteria:**
- ✅ Full flow: Upload → Stage 1-5 → PDF generated < 5 minutes
- ✅ Validation errors caught before transition
- ✅ AI errors don't crash pipeline, fallback works
- ✅ No orphaned sessions or state corruption
- ✅ Stage transitions deterministic (same input → same output)

**Testing:** Playwright + backend unit tests

---

## V. DATA CONTRACTS

### Session Metadata Schema (Locked After Stage Completion)

```python
@dataclass
class SessionMetadata:
    session_id: str
    created_at: datetime
    schema_version: str = "2.0"  # New contract
    
    # Stage tracking
    current_stage: CVStage  # CONTACT_INFO | EDUCATION | ...
    stage_locked: bool = False  # True after [Next] → validation ✓
    
    # Locked stages (can't go back)
    completed_stages: list[CVStage] = field(default_factory=list)
    
    # Timestamps (for debugging + future analytics)
    stage_entered_at: datetime = None
    stage_exited_at: datetime = None
    
    # Session state
    session_status: str = "ACTIVE"  # ACTIVE | COMPLETED | ERROR | ABANDONED
    
    # AI context (optional, for future adaptive flows)
    ai_confidence_score: float = None
    auto_complete_eligible: bool = False
```

### UI Action Response Schema

```python
@dataclass
class UIAction:
    stage: str  # "CONTACT_INFO", "EDUCATION", ...
    stage_number: int  # 1, 2, 3, 4, 5
    total_stages: int = 5
    title: str  # "Contact Information"
    description: str
    
    ui_elements: list[UIElement]  # [display, input, form, selector]
    actions: list[UserAction]  # [button definitions]
    
    # Optional: disable free-text chat input for this stage
    disable_free_text: bool = False
    
    # Optional: if stage failed validation
    validation_errors: list[str] = field(default_factory=list)

@dataclass
class UIElement:
    type: str  # "display" | "input" | "selector" | "form"
    label: str
    value: Any = None
    required: bool = False
    placeholder: str = None
    options: list[dict] = None  # For selector
    validation: dict = None  # Regex, min/max, etc.

@dataclass
class UserAction:
    label: str  # "Edit", "Next", "Skip", "Regenerate"
    action_id: str  # "EDIT_CONTACT", "PROCEED_NEXT", "SKIP", "REGENERATE"
    style: str = "primary"  # "primary" | "secondary" | "tertiary"
    requires_input: bool = False
```

### AI Function Contract Example

```python
@dataclass
class EnhanceWorkBulletsRequest:
    company: str
    title: str
    current_bullets: list[str]
    job_context: str  # Industry, seniority level

@dataclass
class EnhanceWorkBulletsResponse:
    bullets: list[str]  # 3-5 ATS-optimized bullets
    ai_model: str  # "gpt-4"
    tokens_used: int  # For tracking costs
```

---

## VI. MAPPING: OLD ARCHITECTURE → NEW ARCHITECTURE

### Before (Chat-Based, Non-Deterministic)

```
Session Create → INGEST stage
         ↓
User: "Import prefill"
         ↓
Agent (LLM) interprets text → "OK, I'll do that" (says, not does)
         ↓
Function: _is_import_prefill_intent() → checks for keywords
         ↓
If matches: UPDATE_CV_FIELDS (maybe)
If doesn't match or ambiguous: Do nothing, say "Done"
         ↓
User confused: "Why is it still empty?"
         ↓
Session stuck: No stage field, can't compute next state
         ↓
PDF generation fails
```

**Problems:**
- ❌ Stage not persisted (inferred from events)
- ❌ Text parsing ambiguous
- ❌ Agent controls flow
- ❌ Not testable
- ❌ Long context degrades determinism

---

### After (Stage-Guided, Deterministic)

```
Session Create → CONTACT_INFO stage persisted in metadata
         ↓
[User clicks buttons, fills forms - no free text]
         ↓
Backend: handle_user_action(CONTACT_INFO, PROCEED_NEXT, {contact_data})
         ↓
Validation: validate_contact_data() → PASS/FAIL
         ↓
If PASS: stage = EDUCATION, persist, return ui_action(EDUCATION)
If FAIL: return validation_errors, stay on CONTACT_INFO
         ↓
[User sees EDUCATION stage]
         ↓
[User clicks [Review & Enhance] on work role]
         ↓
Backend: AI calls enhance_work_bullets(role_dict)
         ↓
AI returns: {bullets: [...]}
         ↓
[User sees enhanced bullets, clicks [Next]]
         ↓
Backend: validate_work_data() → PASS
         ↓
stage = PROFILE_AND_SKILLS, persist, return ui_action(PROFILE_AND_SKILLS)
         ↓
[Repeat for remaining stages]
         ↓
Stage 5: All sections locked, [Generate PDF]
         ↓
PDF rendered and ready
```

**Advantages:**
- ✅ Stage persisted at every step (can't get lost)
- ✅ User actions explicit (buttons, not text)
- ✅ Deterministic transitions (same input → same output)
- ✅ Fully testable (20 test paths vs 1000+)
- ✅ Clear responsibility (backend owns flow, UI owns choices, AI owns tasks)
- ✅ Future: Can add confidence scores, auto-complete stages

---

## VII. AUTOMATIO N PATH (Long-term Vision)

### Today (Manual Confirmations)

```
Stage 2 (EDUCATION):
  - User sees: Education list + [Skip] [Next] buttons
  - User action: Clicks [Next]
  - Backend validates: At least 1 entry → PASS → move to Stage 3
```

### Tomorrow (Confidence-Based Auto-Complete)

```
Stage 2 (EDUCATION):
  - Backend computes: education_confidence = 0.95 (high confidence, well-formed)
  - If auto_complete_eligible AND confidence > 0.9:
    - auto_skip = true
    - Proceed to Stage 3 without user confirmation
  - Otherwise: Show [Skip] [Next] buttons (manual)
  
Result: First time through: 5 stages with confirmations
        Subsequent refinements: Auto-skip confident stages, only re-edit others
```

### Future (Fully Automated Workflow)

```
User uploads CV:
  - Stage 1 (CONTACT_INFO): auto_confidence = 0.98 → auto-complete
  - Stage 2 (EDUCATION): auto_confidence = 0.92 → auto-complete
  - Stage 3 (WORK_EXPERIENCE): auto_confidence = 0.87 → auto-complete (AI enhance)
  - Stage 4 (PROFILE_AND_SKILLS): auto_confidence = 0.85 → auto-complete (AI generate)
  - Stage 5 (FINAL_CV_GENERATION): auto-complete
  
Total time: ~30 seconds
User still has ability to re-enter any stage if dissatisfied
```

**Key:** Confidence scores are computed but **not used today** (manual flow)
Foundation laid for future automation without re-architecting.

---

## VIII. SUCCESS CRITERIA & METRICS

### Determinism
- **Metric:** Same user input (same session, same CSV) → same output
- **Target:** 100% (deterministic or expected variation captured in logs)
- **Verification:** Replay session from event log, compare PDF byte-for-byte

### Pipeline Reliability
- **Metric:** % of sessions reaching Stage 5 successfully
- **Current (Chat-Based):** ~65% (estimated from session_1 failure)
- **Target (Stage-Guided):** 98%+
- **Verification:** Session logs, stage transitions, PDF generation success rate

### User Clarity
- **Metric:** User doesn't re-confirm same action 2+ times
- **Current:** 3-4 re-confirmations per session (from session_1)
- **Target:** 0 unnecessary re-confirmations
- **Verification:** Event log analysis, turn count per stage

### Performance
- **Metric:** Average time to reach Stage 5
- **Current (Chat):** 12-15 minutes (long context, multiple turns)
- **Target (Structured):** 5-8 minutes (focused tasks, clear transitions)
- **Verification:** Timestamp deltas in session metadata

### Testability
- **Metric:** % of code paths covered by automated tests
- **Target:** >85%
- **Verification:** Coverage report (pytest + Playwright)

---

## IX. PRODUCTION ROLLOUT STRATEGY

### Phase 1: Shadow Mode (Dev Env, 1 week)
- Deploy new code alongside old chat system
- New sessions only use stage-guided pipeline
- Old chat code still works (for rollback if needed)
- Collect metrics: stage transitions, validation failures, AI errors
- Success criteria: 0 critical bugs, >98% stage transitions successful

### Phase 2: Beta (Staging Env, 1 week)
- Deploy to staging, invite beta users
- Monitor: Session completion, PDF quality, user feedback
- Success criteria: 95%+ sessions reach Stage 5, no corruption

### Phase 3: Production Rollout (Gradual, 2 weeks)
- Week 1: 10% traffic
- Week 2: 50% traffic
- Week 3: 100% traffic
- Rollback plan: If stage transition failure rate > 5%, revert to old chat system

---

## X. FAQ

**Q: What about sessions created before this change?**
A: Hard fail with 409 error. Users must start fresh. Justification: Old sessions have no stage field, can't work with new system. Better to force new session than silently corrupt data.

**Q: Can users go back to a previous stage?**
A: No (for now). Stage-guided pipeline is forward-only. Future enhancement: Allow re-entry to earlier stages with data re-validation.

**Q: What if user wants to manually edit something in Stage 5?**
A: Not supported in first version. Workaround: Delete session, start over. Future: Allow "edit mode" to re-enter earlier stages.

**Q: What if AI fails to enhance bullets?**
A: Graceful fallback: Show error, keep original bullets, allow manual edit. User can still proceed to next stage.

**Q: Can I skip all stages and just generate the PDF?**
A: Some stages allow [Skip], others require data. Contact & Work Experience required, Education & Profile optional.

---

## XI. NEXT STEPS

### Before Implementation:
1. ✅ **Validate:** Agree this architecture solves the core problems
2. ✅ **Review:** Check data contracts, stage transitions, role separation
3. ✅ **Clarify:** Any questions on implementation phases?

### After Approval:
1. **Wave 1 Start:** Phase 1 (Foundation) — commit stage infrastructure
2. **Wave 2:** Phase 2 (AI Integration) — connect AI tasks
3. **Wave 3:** Phase 3 (Frontend) — build UI components
4. **Testing:** Phase 4 (E2E + Edge Cases)
5. **Rollout:** Staging → Production (gradual)

---

## Summary

**Old Model (Broken):** Chat → LLM Interprets → Maybe Acts → Stuck State  
**New Model (Deterministic):** UI Action → Backend Validates → State Transition → AI Task (if needed) → Next Stage

**Philosophy:** Backend owns flow. UI owns choices. AI owns content.  
**Result:** Boring interactions at start (clear buttons, simple forms) → Impressive outcome at end (beautiful PDF from chaos)

This is your CV Machine. 🚀

