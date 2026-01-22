# Multi-Claude Review Command

Launches a parallel Claude instance for code review while continuing main development work.

**Note:** This is a Phase 3 advanced feature. Requires Claude Code CLI with multi-instance support.

---

## Usage

```
/multi-claude-review <target> [focus-areas]
```

**Examples:**
```
/multi-claude-review src/blob_store.py --focus="security,performance"
/multi-claude-review ui/app/api/process-cv/route.ts --focus="type-safety,error-handling"
/multi-claude-review function_app.py --focus="all"
```

---

## Workflow

### Step 1: Save Current Context
Preserve main Claude's work state:

```bash
# Create handoff document
cat > tmp/multi_claude_handoff_$(date +%s).md <<EOF
# Multi-Claude Review Handoff

## Main Task (Claude A)
Currently working on: $CURRENT_TASK

## Review Request (Claude B)
Target: $ARGUMENTS
Focus areas: $FOCUS_AREAS

## Expected Deliverables
- Security audit
- Performance bottlenecks
- Type safety issues
- Error handling gaps
- Code style violations

## Handoff Timestamp
$(date -Iseconds)
EOF
```

### Step 2: Launch Background Claude
Spawn parallel Claude instance:

```bash
# Option 1: CLI (requires Claude Code CLI)
claude --background \
  --task "Review $ARGUMENTS focusing on $FOCUS_AREAS" \
  --output tmp/review_$(date +%s).md \
  --model sonnet

# Option 2: Git Worktree (manual alternative)
git worktree add ../cv-generator-review
cd ../cv-generator-review
# Open in new VSCode window
code .
```

### Step 3: Continue Main Work
Main Claude (you) continues development:
- Don't block on review completion
- Periodically check `tmp/review_*.md` for updates
- Use `/task-status` to monitor background Claude

### Step 4: Merge Review Feedback
When background Claude completes:

**Review file structure:**
```markdown
# Code Review: src/blob_store.py

## Summary
Found 3 security issues, 2 performance concerns, 1 type safety gap.

## Security Issues

### 1. SQL Injection Risk (HIGH)
**Location:** src/blob_store.py:45
**Issue:** User input not sanitized in table name
**Fix:**
```python
# Before
table_name = f"sessions_{user_id}"

# After
table_name = f"sessions_{sanitize_table_name(user_id)}"
```

### 2. Connection String Exposure (MEDIUM)
...

## Performance Concerns

### 1. Unnecessary Blob Listing (MEDIUM)
**Location:** src/blob_store.py:102
**Issue:** Lists all blobs instead of using prefix filter
**Fix:**
...

## Type Safety

### 1. Missing Return Type Annotation (LOW)
...

## Recommendations
1. Add input validation layer
2. Implement connection pooling
3. Add comprehensive type hints

## Test Coverage Gaps
- Missing tests for error conditions
- No integration tests for blob operations
```

### Step 5: Apply Fixes
Address review findings:

1. **Prioritize by severity:** HIGH → MEDIUM → LOW
2. **Create test for each issue** (TDD approach)
3. **Implement fixes** with tests green
4. **Commit incrementally:**
   ```bash
   git commit -m "security: sanitize user input in table names

   Addresses code review finding #1 from multi-claude-review.
   Prevents potential SQL injection via user-controlled table names.

   Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
   Co-Authored-By: Claude Sonnet 4.5 (Review) <noreply@anthropic.com>"
   ```

---

## Focus Areas

### Security
- SQL injection, XSS, CSRF
- Secrets exposure
- Authentication/authorization gaps
- Input validation
- Output encoding

### Performance
- N+1 queries
- Unnecessary loops
- Missing caching
- Inefficient algorithms
- Memory leaks

### Type Safety
- Missing type annotations
- `any` types
- Unchecked casts
- Optional chaining

### Error Handling
- Unhandled exceptions
- Silent failures
- Missing logging
- Improper error propagation

### Code Style
- PEP 8 (Python)
- ESLint rules (TypeScript)
- Naming conventions
- Documentation gaps

### All
Comprehensive review covering all areas above.

---

## Output Format

**Main Claude (during review):**
```
🔄 Background review in progress...
   Target: src/blob_store.py
   Focus: security, performance
   Output: tmp/review_1737543210.md

Continuing with main task...
```

**Background Claude completion:**
```
✅ Review complete: tmp/review_1737543210.md

Summary:
- 3 HIGH priority issues
- 2 MEDIUM priority issues
- 1 LOW priority issue

Top recommendation: Add input sanitization layer

View full review: [tmp/review_1737543210.md](tmp/review_1737543210.md)
```

---

## Advanced Patterns

### Pattern 1: Parallel Feature Development
**Use case:** Implement feature while background Claude writes tests

```bash
# Main Claude: Implement feature
/implement-feature src/extract_photo.py --new-format=webp

# Background Claude: Write tests
/multi-claude-review tests/test_docx_prefill.py --focus="test-coverage" --task="Add tests for WebP support"
```

### Pattern 2: Architecture Review
**Use case:** Propose architecture while background Claude validates

```bash
# Main Claude: Design new session flow
/plan-architecture "Session pooling with Redis cache"

# Background Claude: Review design
/multi-claude-review tmp/session_pooling_plan.md --focus="scalability,cost,complexity"
```

### Pattern 3: Refactor with Safety Net
**Use case:** Refactor code while background Claude monitors for regressions

```bash
# Main Claude: Refactor
/refactor src/blob_store.py --extract-class=SessionStore

# Background Claude: Monitor
/multi-claude-review src/blob_store.py --focus="behavioral-equivalence" --compare-with=HEAD~1
```

---

## Git Worktree Alternative (Manual)

If Claude Code CLI not available, use git worktrees:

### Setup
```bash
# Create review worktree
git worktree add ../cv-generator-review main

# Open in new VSCode window
cd ../cv-generator-review
code .
```

### Review Process
In new VSCode window:
1. Open Claude Code (separate instance)
2. Run review task manually
3. Save review to `tmp/review_<timestamp>.md`
4. Commit review file

### Cleanup
```bash
# After merging review feedback
git worktree remove ../cv-generator-review
```

---

## Limitations

**Current limitations (Phase 3 exploration):**
- Requires Claude Code CLI with `--background` flag (may not be available yet)
- No automatic merging of review feedback
- Manual coordination between instances
- Git worktree requires manual VSCode window management

**Future enhancements:**
- Auto-merge non-conflicting fixes
- Real-time review streaming
- Integrated diff view
- Review approval workflow

---

## Cost Considerations

**Token usage:**
- Main Claude: Normal conversation flow
- Background Claude: Full file read + analysis
- **Total:** ~2x token cost for reviewed file

**Optimization:**
- Use background review for critical files only
- Combine multiple small files into one review
- Set token limits with `--max-tokens` flag

**When to use:**
- Large refactors (>500 lines)
- Security-critical code
- Performance-sensitive paths
- Pre-PR reviews

**When NOT to use:**
- Small fixes (<50 lines)
- Simple formatting changes
- Documentation updates
- Low-risk changes

---

## Related Commands

- `/code-review` - Single-instance review (blocks main task)
- `/security-audit` - Security-focused review
- `/performance-profile` - Performance analysis

---

## Integration with PR Workflow

**Pre-PR checklist:**
```bash
# 1. Run multi-Claude review
/multi-claude-review src/ --focus="all"

# 2. Apply critical fixes
# (Address HIGH priority issues)

# 3. Run tests
npm test && cd ui && npm run lint

# 4. Create PR with review summary
gh pr create --title "feat: session pooling" \
  --body "$(cat tmp/review_1737543210.md)"
```

**Review summary in PR description:**
```markdown
## Code Review Summary

Pre-PR review by Claude Sonnet 4.5 (multi-instance):

✅ Security: No high-priority issues
✅ Performance: Caching implemented
⚠️ Type Safety: 2 minor annotations missing
✅ Error Handling: Comprehensive coverage

Full review: [tmp/review_1737543210.md](tmp/review_1737543210.md)
```