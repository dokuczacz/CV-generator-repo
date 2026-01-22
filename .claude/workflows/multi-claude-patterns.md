# Multi-Claude Workflow Patterns

Advanced parallel Claude Code workflows for code review, testing, and development.

**Phase:** 3 (Advanced Features)
**Status:** Exploratory (CLI support may vary)

---

## Overview

**Multi-Claude workflows** leverage multiple Claude Code instances running in parallel to:
- Review code while continuing development
- Generate tests while implementing features
- Validate architecture while designing
- Monitor for regressions while refactoring

**Benefits:**
- Non-blocking reviews (don't wait for feedback)
- Parallel perspectives (one codes, one critiques)
- Faster iteration cycles
- Better code quality through dual oversight

**Trade-offs:**
- 2x token costs for reviewed code
- Manual coordination required
- Git worktree management overhead

---

## Pattern 1: Code Review While Developing

**Use case:** Implement feature while background Claude reviews for security/performance

### Setup
```bash
# Terminal 1 (Main Claude - Development)
claude  # Continue normal conversation

# Terminal 2 (Background Claude - Review)
claude --background \
  --task "Review src/blob_store.py for security and performance issues" \
  --output tmp/review_blob_store_$(date +%s).md \
  --model sonnet
```

### Main Claude (Development)
```
User: "Refactor blob_store.py to add session pooling"

Claude Main:
1. Create tmp/refactor_plan.md
2. Launch background review:
   /multi-claude-review src/blob_store.py --focus="security,performance"
3. Continue with refactoring:
   - Extract SessionPool class
   - Implement connection pooling
   - Update tests
4. Periodically check tmp/review_*.md for feedback
```

### Background Claude (Review)
**Autonomous task:**
```
Read src/blob_store.py
Focus on: security issues, performance bottlenecks
Output: tmp/review_blob_store_<timestamp>.md

Format:
# Code Review: src/blob_store.py

## Security Issues
1. [HIGH] SQL injection risk at line 45
   - Issue: User input not sanitized
   - Fix: Use parameterized queries

## Performance Concerns
1. [MEDIUM] N+1 query pattern at line 102
   - Issue: Loops over DB calls
   - Fix: Batch queries

## Recommendations
- Add input validation layer
- Implement connection pooling (aligns with refactor goal!)
```

### Merge Workflow
```
Main Claude:
1. Refactoring complete
2. Read tmp/review_blob_store_<timestamp>.md
3. Address HIGH priority issues immediately
4. Create follow-up tasks for MEDIUM issues
5. Run tests
6. Commit with review reference:
   git commit -m "refactor: add session pooling to blob_store

   Addresses performance concerns from code review.
   Implements connection pooling to reduce DB overhead.

   Review: tmp/review_blob_store_1737543210.md
   Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
   Co-Authored-By: Claude Sonnet 4.5 (Review) <noreply@anthropic.com>"
```

---

## Pattern 2: Test Generation While Implementing

**Use case:** Write tests in parallel with feature implementation

### Setup Using Git Worktrees
```bash
# Create separate worktree for test development
git worktree add ../cv-generator-tests main
cd ../cv-generator-tests
code .  # Open in new VSCode window
```

### Main Claude (Feature Implementation)
```
User: "Add WebP support to photo extraction"

Claude Main (in main worktree):
1. Implement WebP extraction in src/extract_photo.py
2. Update schema to accept image/webp MIME type
3. Save progress commits
```

### Background Claude (Test Development)
```
Claude Background (in tests worktree):
1. Read src/extract_photo.py (main worktree via git)
2. Generate test cases for WebP support:
   - Valid WebP → extract successfully
   - Invalid WebP → handle gracefully
   - Large WebP → compress to <32KB
   - Animated WebP → extract first frame
3. Write tests in tests/test_docx_prefill.py
4. Commit tests (may fail initially - TDD approach)
```

### Merge Workflow
```bash
# In main worktree
git pull ../cv-generator-tests main  # Pull test commits
npm test  # Run new tests (should fail)

# Iterate feature until tests pass
npm test  # Green!

# Cleanup
git worktree remove ../cv-generator-tests
```

---

## Pattern 3: Architecture Validation

**Use case:** Design architecture while background Claude validates scalability

### Main Claude (Design)
```
User: "Design session storage with Redis caching"

Claude Main:
1. Create tmp/session_redis_design.md:
   - Architecture diagram
   - Data flow
   - API contracts
   - Migration plan
2. Launch background validation:
   /multi-claude-review tmp/session_redis_design.md --focus="scalability,cost,complexity"
```

### Background Claude (Validation)
```
Autonomous analysis of tmp/session_redis_design.md:

## Scalability Analysis
✅ Redis handles 100K+ ops/sec (sufficient)
⚠️ Single Redis instance = single point of failure
Recommendation: Redis Cluster or failover setup

## Cost Analysis
💰 Azure Cache for Redis Basic: ~$15/month
💰 Alternative (CosmosDB): ~$25/month but globally distributed
Recommendation: Start with Redis Basic, upgrade if needed

## Complexity Analysis
⚠️ HIGH: Introduces new dependency (Redis)
⚠️ MEDIUM: Cache invalidation strategy needed
✅ LOW: Well-documented, mature technology

## Overall Recommendation
Proceed with design, but:
1. Add failover plan (fallback to direct storage if Redis down)
2. Document cache invalidation rules
3. Budget for Redis Cluster upgrade path
```

---

## Pattern 4: Refactor with Safety Net

**Use case:** Refactor code while background Claude monitors for behavioral equivalence

### Setup
```bash
# Save current behavior baseline
git commit -m "checkpoint: before blob_store refactor"
BEFORE_SHA=$(git rev-parse HEAD)

# Launch monitoring Claude
claude --background \
  --task "Monitor blob_store.py refactor for behavioral equivalence with $BEFORE_SHA" \
  --output tmp/refactor_monitor.md
```

### Main Claude (Refactoring)
```
Refactor src/blob_store.py:
1. Extract SessionStore class
2. Separate connection logic
3. Add type hints
4. Commit incrementally
```

### Background Claude (Monitoring)
```
After each commit:
1. git diff $BEFORE_SHA src/blob_store.py
2. Analyze changes:
   - Are all original code paths still present?
   - Are return values identical?
   - Are error conditions handled the same?
3. Run tests: pytest tests/test_blob_store.py -v
4. Report regressions immediately

Example alert:
⚠️ REGRESSION DETECTED in commit abc123
- Old: Returns None on error
- New: Raises exception
- Impact: Breaking change for callers
- Recommendation: Add exception handling or revert
```

---

## Git Worktree Management

### Create Review Worktree
```bash
git worktree add ../cv-generator-review main
cd ../cv-generator-review
code .  # New VSCode window with separate Claude instance
```

### List Worktrees
```bash
git worktree list
# main         /path/to/cv-generator        [main]
# review       /path/to/cv-generator-review [main]
```

### Remove Worktree
```bash
git worktree remove ../cv-generator-review
```

### Best Practices
- **One branch per worktree:** Avoid confusion
- **Sync frequently:** `git pull` in both worktrees
- **Clean up:** Remove worktrees when done
- **Commit often:** Small commits easier to merge

---

## Cost Management

### Token Usage Estimation
- Main Claude: Normal conversation (~10K tokens)
- Background Claude: Full file read + analysis (~5K tokens per file)
- **Total:** 1.5-2x normal cost

### Optimization Strategies
1. **Review critical files only:** Not every file needs review
2. **Batch reviews:** Review multiple files in one background task
3. **Set token limits:** `--max-tokens 20000` to cap costs
4. **Use Haiku for simple reviews:** `--model haiku` (faster, cheaper)

### When to Use Multi-Claude
**High value:**
- Large refactors (>500 lines)
- Security-critical code (auth, payments)
- Performance-sensitive paths
- Pre-PR reviews

**Low value:**
- Small fixes (<50 lines)
- Documentation updates
- Formatting changes
- Low-risk experiments

---

## Limitations & Future Enhancements

### Current Limitations (2026-01)
- CLI `--background` flag may not be available yet
- Manual coordination between instances
- No automatic merging of feedback
- Git worktree requires manual VSCode management

### Planned Enhancements
- Automatic review streaming (real-time feedback)
- Integrated diff view in main Claude
- One-click review approval
- Background task status in main conversation
- Auto-merge non-conflicting fixes

---

## Alternative: Sequential Review (Simpler)

If multi-instance support unavailable, use sequential review:

```
User: "Review my changes before committing"

Claude:
1. git diff HEAD
2. Analyze changes for issues
3. Report findings
4. Wait for fixes
5. Re-review
6. Approve for commit

Drawback: Blocks development during review
Benefit: Simpler, no worktree management
```

---

## Related Documentation

- [/multi-claude-review](../.claude/commands/multi-claude-review.md) - Slash command for parallel review
- [CLAUDE.md](../CLAUDE.md) - Auto-context with git etiquette
- [../../../.github/copilot-instructions.md](../../../.github/copilot-instructions.md) - Copilot review patterns (different approach)