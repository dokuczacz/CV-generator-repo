# Headless CI/CD Integration

Claude Code programmatic invocation for automated workflows.

**Phase:** 3 (Advanced Features)
**Status:** Exploratory (CLI `-p` flag support varies)

---

## Overview

**Headless mode** runs Claude Code programmatically without interactive chat:
- Invoke Claude from scripts/CI pipelines
- Process tasks autonomously
- Output structured results
- Integrate with existing automation

**Use cases:**
- Automated code review in GitHub Actions
- PR validation (linting, testing, security checks)
- Scheduled maintenance tasks
- Batch processing

---

## Basic Headless Invocation

### Command Structure
```bash
claude -p "<prompt>" --headless --output <output-file>
```

**Parameters:**
- `-p "<prompt>"`: Task description (single string)
- `--headless`: Run without interactive mode
- `--output <file>`: Save results to file (optional)
- `--model <model>`: Specify model (sonnet, haiku, opus)
- `--max-tokens <N>`: Limit token usage

**Example:**
```bash
claude -p "Run tests and report failures" \
  --headless \
  --output test-results/claude-report.md
```

---

## GitHub Actions Integration

### Workflow: Automated Code Review

**.github/workflows/claude-review.yml**
```yaml
name: Claude Code Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  claude-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          npm install
          pip install -r requirements.txt

      - name: Run Claude Code Review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Review all changed files in this PR for security issues, type safety, and code quality. Focus on: $(git diff --name-only origin/main)" \
            --headless \
            --output pr-review.md \
            --model sonnet

      - name: Comment PR with review
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const review = fs.readFileSync('pr-review.md', 'utf8');

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Claude Code Review\n\n${review}`
            });

      - name: Upload review artifact
        uses: actions/upload-artifact@v3
        with:
          name: claude-review
          path: pr-review.md
```

### Workflow: Visual Regression Tests

**.github/workflows/visual-regression.yml**
```yaml
name: Visual Regression Tests

on:
  pull_request:
    paths:
      - 'templates/html/**'
      - 'tests/**'

jobs:
  visual-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup environment
        run: |
          npm install
          npx playwright install chromium

      - name: Generate test artifacts
        run: npm run pretest

      - name: Run Claude-driven visual tests
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Run visual regression tests and analyze failures. For each failing test, determine if the change is intentional (design update) or a regression. Output analysis to visual-regression-report.md" \
            --headless \
            --output visual-regression-report.md \
            --model sonnet

      - name: Run Playwright tests
        run: npm test

      - name: Upload test results
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: visual-diffs
          path: |
            test-results/
            visual-regression-report.md
```

---

## Automated Tasks

### Task 1: Nightly CV Validation
**Purpose:** Validate all sample CVs in repository

**.github/workflows/nightly-validation.yml**
```yaml
name: Nightly CV Validation

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

jobs:
  validate-samples:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Validate all sample CVs
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Validate all CV JSON files in samples/ directory. Report any schema violations or size constraint issues. Output summary to validation-report.md" \
            --headless \
            --output validation-report.md \
            --model haiku  # Cheaper model for routine checks

      - name: Email report if failures
        if: failure()
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: smtp.gmail.com
          server_port: 465
          username: ${{ secrets.EMAIL_USERNAME }}
          password: ${{ secrets.EMAIL_PASSWORD }}
          subject: CV Validation Failures
          body: file://validation-report.md
          to: team@example.com
```

### Task 2: Dependency Update Review
**Purpose:** Review dependency updates for breaking changes

```yaml
name: Dependency Update Review

on:
  pull_request:
    paths:
      - 'package.json'
      - 'requirements.txt'

jobs:
  review-deps:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 2  # Need previous commit for diff

      - name: Review dependency changes
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Analyze dependency changes in this commit. For each updated package, check: 1) Breaking changes in changelog, 2) Security advisories, 3) Impact on our codebase. Output findings to dep-review.md" \
            --headless \
            --output dep-review.md \
            --model sonnet

      - name: Comment on PR
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const review = fs.readFileSync('dep-review.md', 'utf8');

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Dependency Update Review\n\n${review}`
            });
```

---

## Local Automation Scripts

### Script: Batch CV Generation
**Purpose:** Generate PDFs for multiple CVs

**scripts/batch_generate_pdfs.sh**
```bash
#!/bin/bash

# Generate PDFs for all CVs in samples/ directory

for cv_file in samples/*.json; do
  echo "Processing $cv_file..."

  claude -p "Generate PDF for CV at $cv_file. Validate first, then generate for all languages (EN/DE/PL). Save outputs to tmp/$(basename $cv_file .json)_*.pdf" \
    --headless \
    --output tmp/$(basename $cv_file .json)_report.md \
    --model haiku

  if [ $? -ne 0 ]; then
    echo "Failed to process $cv_file"
  fi
done

echo "Batch generation complete. See tmp/ for outputs."
```

**Usage:**
```bash
./scripts/batch_generate_pdfs.sh
```

### Script: Code Quality Check
**Purpose:** Pre-commit code quality validation

**.git/hooks/pre-commit**
```bash
#!/bin/bash

# Run Claude code quality check before commit

echo "Running Claude code quality check..."

claude -p "Review staged changes for: 1) Code style violations, 2) Missing tests, 3) TODO comments without issues, 4) Potential bugs. Exit with non-zero if critical issues found." \
  --headless \
  --output tmp/pre-commit-review.md \
  --model haiku

if [ $? -ne 0 ]; then
  echo "❌ Code quality check failed. See tmp/pre-commit-review.md"
  echo "Fix issues or use 'git commit --no-verify' to skip (not recommended)."
  exit 1
fi

echo "✅ Code quality check passed"
exit 0
```

---

## Structured Output Formats

### Markdown Report Template
```markdown
# Claude Headless Task Report

**Task:** <task description>
**Model:** <sonnet|haiku|opus>
**Timestamp:** <ISO 8601>
**Duration:** <seconds>

---

## Summary
<1-3 sentence overview>

## Findings
1. **[SEVERITY]** Finding 1
   - Details
   - Location
   - Recommendation

2. **[SEVERITY]** Finding 2
   ...

## Statistics
- Files reviewed: N
- Issues found: N (HIGH: N, MEDIUM: N, LOW: N)
- Lines changed: +N / -N

## Recommendations
1. Recommendation 1
2. Recommendation 2

## Next Steps
- [ ] Action item 1
- [ ] Action item 2

---

**Exit code:** 0 (success) | 1 (failure)
```

### JSON Output (for programmatic consumption)
```json
{
  "task": "Validate CV samples",
  "model": "haiku",
  "timestamp": "2026-01-22T12:00:00Z",
  "duration_seconds": 15.3,
  "summary": "Validated 10 CV samples, found 2 issues",
  "findings": [
    {
      "severity": "HIGH",
      "file": "samples/cv_german.json",
      "issue": "photo_url exceeds 32KB",
      "recommendation": "Compress photo or use blob storage"
    }
  ],
  "statistics": {
    "files_reviewed": 10,
    "issues_high": 1,
    "issues_medium": 1,
    "issues_low": 0
  },
  "exit_code": 1
}
```

---

## Error Handling

### Timeout Management
```bash
# Set timeout for headless execution (prevent hanging)
timeout 300 claude -p "Long-running task" --headless --output report.md

if [ $? -eq 124 ]; then
  echo "Claude task timed out after 300 seconds"
  exit 1
fi
```

### Retry Logic
```bash
# Retry up to 3 times on failure
MAX_RETRIES=3
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  claude -p "Task" --headless --output report.md

  if [ $? -eq 0 ]; then
    echo "Success!"
    exit 0
  fi

  RETRY_COUNT=$((RETRY_COUNT + 1))
  echo "Retry $RETRY_COUNT/$MAX_RETRIES..."
  sleep 5
done

echo "Failed after $MAX_RETRIES retries"
exit 1
```

### Graceful Degradation
```bash
# Fall back to simple linting if Claude fails
claude -p "Advanced code review" --headless --output review.md

if [ $? -ne 0 ]; then
  echo "Claude review failed, falling back to ESLint"
  cd ui && npm run lint
  exit $?
fi
```

---

## Cost Optimization

### Use Appropriate Models
```bash
# Simple tasks: Use Haiku (cheap, fast)
claude -p "Lint check" --headless --model haiku

# Complex tasks: Use Sonnet (balanced)
claude -p "Architecture review" --headless --model sonnet

# Critical tasks: Use Opus (best quality)
claude -p "Security audit" --headless --model opus
```

### Token Limiting
```bash
# Cap token usage to prevent cost overruns
claude -p "Review large file" \
  --headless \
  --max-tokens 10000 \
  --output review.md

# Claude will stop at 10K tokens (approx $0.15 cost for Sonnet)
```

### Caching Strategies
```bash
# Cache validation results to avoid re-running
CACHE_FILE="tmp/validation_cache_$(date +%Y%m%d).md"

if [ -f "$CACHE_FILE" ]; then
  echo "Using cached validation from today"
  cat "$CACHE_FILE"
  exit 0
fi

# Run validation, cache result
claude -p "Validate samples" --headless --output "$CACHE_FILE"
```

---

## Limitations

**Current limitations (2026-01):**
- `-p` flag may not be available in all Claude Code versions
- Limited to text-based output (no interactive approval)
- Cannot handle user prompts mid-execution
- File access requires explicit paths in prompt

**Workarounds:**
- Use explicit file paths in prompts
- Pre-stage all required files
- Structure prompts for autonomous execution
- Parse output files programmatically

---

## Best Practices

1. **Explicit prompts:** Be very specific in task description
2. **Output files:** Always use `--output` for CI integration
3. **Model selection:** Match model to task complexity
4. **Timeouts:** Set reasonable limits (5-10 min max)
5. **Error handling:** Always check exit codes
6. **Cost monitoring:** Track token usage with `--max-tokens`
7. **Caching:** Avoid redundant Claude invocations
8. **Testing:** Test headless scripts locally before CI

---

## Related Documentation

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Claude Code CLI Guide](https://code.claude.com/docs/cli)
- [multi-claude-patterns.md](multi-claude-patterns.md) - Parallel workflows
- [visual-iteration.md](visual-iteration.md) - Visual testing automation
