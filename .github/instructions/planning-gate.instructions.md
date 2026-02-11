---
applyTo: "**"
name: Planning Gate Procedure
description: Stop-the-line gate for non-trivial work requiring stable scenario pack and DoD
---

# Planning Gate Procedure

This file defines the mandatory planning gate that must be passed **before** executing non-trivial work.

## When to Apply

Use the planning gate when:
- Work involves >3 steps or spans multiple files/modules
- Work touches critical paths (authentication, payment, data loss scenarios)
- Work involves LLM integration or orchestration changes
- Work requires coordination between UI, backend, and tests
- Unclear requirements or multiple valid interpretations exist

**Do NOT skip** the gate for "small" changes that touch critical logic or introduce new external dependencies.

## Gate Requirements

Before proceeding, you **must** have:

### 1. Stable Scenario Pack

A **scenario pack** defines the happy path and key edge cases for the feature/change.

**Format:** Use scenario template from `docs/scenarios/SCENARIO_TEMPLATE.md`

**Required elements:**
- **Scenario name:** Clear, descriptive (e.g., "CV Generation - Normal Wizard Flow")
- **Preconditions:** What must be true before starting
- **Steps:** Numbered steps describing user actions or system behavior
- **Expected outcomes:** What should happen (success criteria)
- **Edge cases:** At least 2 edge cases (error, boundary, empty state)

**Example:**

```markdown
## Scenario: CV Generation - Normal Wizard Flow

### Preconditions
- User has a valid DOCX CV file
- OpenAI API key is configured
- Backend is running

### Steps
1. User uploads CV file (DOCX)
2. System extracts text and photo
3. System validates required fields (name, email, phone)
4. System enters wizard mode (stage: personal_info_review)
5. User confirms personal info → stage: work_experience_review
6. User confirms work experience → stage: skills_review
7. User confirms skills → stage: complete
8. System generates CV PDF (2 pages)
9. System provides download link

### Expected Outcomes
- PDF generated successfully
- PDF is exactly 2 pages
- All sections from source CV are present
- Photo is included in PDF
- Download link is functional

### Edge Cases
1. **Missing photo:** System generates CV without photo, shows warning
2. **Invalid email:** System shows error at stage 1, prevents progression
3. **Large work history:** System truncates to fit 2 pages, shows notice
```

### 2. Definition of Done (DoD)

A **DoD** specifies the concrete verification steps that prove the work is complete.

**Required elements:**
- **Functional criteria:** What must work (testable)
- **Test coverage:** What tests must pass
- **Non-functional criteria:** Performance, security, accessibility
- **Documentation:** What must be updated
- **Review:** Who/what must approve

**Example:**

```markdown
## Definition of Done: CV Generation Wizard

### Functional Criteria
- [ ] User can upload DOCX and see wizard stages
- [ ] User can navigate through all wizard stages
- [ ] System generates 2-page PDF at completion
- [ ] Download link works and serves correct PDF
- [ ] Error states show appropriate messages

### Test Coverage
- [ ] Tier 0: Schema validation passes (stage transitions)
- [ ] Tier 1: Mocked orchestration tests pass (all stages)
- [ ] Tier 2: E2E test with replayed LLM outputs passes
- [ ] Visual regression: PDF screenshot matches baseline

### Non-Functional Criteria
- [ ] CV generation completes within 30 seconds
- [ ] No prompt injection vulnerabilities (validated with test cases)
- [ ] Mobile-responsive UI (tested on 375px viewport)

### Documentation
- [ ] Update ORCHESTRATION.md with new stages
- [ ] Update API schema docs with new fields
- [ ] Add example payload to README

### Review
- [ ] Code review approved
- [ ] Security scan (CodeQL) passes
- [ ] Playwright E2E tests pass in CI
```

### 3. Deterministic Constraints with Fallback

For each LLM call or non-deterministic operation, define:
- **Constraint:** What must be true (structural, not exact phrasing)
- **Fallback:** What happens if constraint is violated

**Example:**

```markdown
## Deterministic Constraints: Skills Extraction

### Constraint 1: Skills Array
- **What:** Response must include `skills` array
- **Type:** Array of objects with `{ skill: string, category: string }`
- **Fallback:** If missing or invalid, return error to user: "Could not extract skills"

### Constraint 2: Skill Count
- **What:** Must extract 1-50 skills
- **Fallback:** If 0 skills, return error. If >50, truncate to top 50 and log warning.

### Constraint 3: No Fabrication
- **What:** All skills must appear in source CV text
- **Fallback:** Cross-check each skill against source text; remove any not found.
```

## Gate Checklist

Before proceeding, verify:

- [ ] **Scenario pack exists** (at least 1 happy path + 2 edge cases)
- [ ] **DoD is written** (functional, tests, non-functional, docs, review)
- [ ] **Deterministic constraints defined** (for all LLM/non-deterministic operations)
- [ ] **Fallbacks specified** (for all constraints)
- [ ] **Smallest verification step identified** (what to test first)

## If Gate Fails

If any requirement is missing, **STOP** and use the **stall-escalation pattern**:

### Stall-Escalation Pattern

Output only the following (do NOT proceed with implementation):

#### 1. Blocker
One sentence describing what is missing.

**Example:** "No stable scenario pack exists for the edit intent fast-path."

#### 2. Option A - Split
1-3 smallest next steps to unblock (ask operator to provide missing artifact).

**Example:**
1. Operator provides scenario pack for edit intent (happy path + 2 edge cases)
2. Operator provides DoD checklist
3. Agent proceeds with implementation

#### 3. Option B - Escalate
What extra input/tool is needed to proceed.

**Example:** "Need operator to confirm: Should edit intent bypass wizard or run wizard in background?"

#### 4. Operator Question
Yes/no question for operator to decide.

**Example:** "Proceed with Option A (wait for scenario pack) or Option B (escalate to confirm design)?"

## Example: Gate Passed

```markdown
## Planning Gate: Skills Proposal UI Actions

### Scenario Pack
✅ Documented in `docs/scenarios/skills-proposal-ui-actions.md`
- Happy path: User reorders skills
- Edge case 1: User removes all skills
- Edge case 2: User adds duplicate skill

### DoD
✅ Documented in issue description
- Functional: Reorder/remove actions work
- Tests: Tier 0+1 tests pass
- Non-functional: No UI jank
- Docs: Update ORCHESTRATION.md
- Review: Code review + CI green

### Deterministic Constraints
✅ Defined for all actions
- Reorder: Array must remain 1-50 items, same skills
- Remove: Array must have ≥1 item remaining
- Fallback: Reject action if constraint violated

### Smallest Verification Step
✅ Test reorder action in isolation (mock backend, assert new order)

**Gate status: PASSED ✅**
Proceeding with implementation...
```

## Example: Gate Failed

```markdown
## Planning Gate: Edit Intent Fast-Path

### Scenario Pack
❌ Missing

### DoD
❌ Missing

### Deterministic Constraints
❌ Not defined

**Gate status: FAILED ❌**

### Stall-Escalation

#### 1. Blocker
No stable scenario pack exists for edit intent fast-path.

#### 2. Option A - Split
1. Operator provides scenario pack (happy path: user edits name; edge cases: empty field, invalid email)
2. Operator provides DoD (tests, constraints, fallbacks)
3. Agent implements fast-path with deterministic validation

#### 3. Option B - Escalate
Need operator to confirm: Should edit intent skip all other stages, or validate at each stage?

#### 4. Operator Question
Proceed with Option A (wait for scenario pack) or Option B (escalate design question)?
```

## Unknown Sea Protocol

If during execution you encounter:
- Missing evidence
- Multiple valid interpretations
- Scope explosion
- Need to touch auth/secrets

**Stop immediately** and invoke the **Unknown Sea** script:

### Unknown Sea Script

1. **"We are about to work on an unknown sea; be careful."**
2. **State the top 1-2 assumptions and what evidence is missing.**
3. **Offer the smallest safe verification step (command/file) before proceeding.**

**Example:**

> We are about to work on an unknown sea; be careful.
> 
> **Assumptions:**
> 1. Edit intent should bypass wizard stages entirely
> 2. Edit intent should validate all fields before applying changes
> 
> **Missing Evidence:**
> - No specification for what happens if edit validation fails
> - No fixture showing expected edit intent JSON structure
> 
> **Smallest Safe Verification Step:**
> Check `docs/scenarios/` for any edit intent documentation OR ask operator to confirm the two assumptions above.

## Efficiency Guard

Before starting work that will take >2 minutes (broad scans, long test suites, destructive ops):

1. **Check if a cheaper L0/L1 verification exists** (unit test, schema check, single function test)
2. **Ask operator:** "This will take ~X minutes. Should I proceed or use cheaper check Y first?"

## References

- Agent operating rules: `AGENTS.md`
- LLM orchestration: `.github/instructions/llm-orchestration.instructions.md`
- Scenario template: `docs/scenarios/SCENARIO_TEMPLATE.md`
