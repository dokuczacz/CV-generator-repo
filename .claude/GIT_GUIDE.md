# Git Workflow Guide

## Before Committing

```bash
# Check status
git status -sb

# Lint frontend
cd ui && npm run lint

# Run tests
npm test

# Verify no secrets
git diff --cached | grep -i "api_key\|secret\|password\|connection"
```

## Commit Messages

Use conventional commits style:

```
feat: add photo URL size validation

Validate that photo URLs don't exceed 32KB to prevent
Azure Table Storage property limit errors.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

Format: `<type>: <description>`

Types:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring
- `test`: Test additions/changes
- `docs`: Documentation only
- `chore`: Tooling, dependencies

## Branch Workflow

- Main branch: `main`
- No force push to main
- Create feature branches for new work
- Run tests before creating PRs

## Git Safety Protocol

**NEVER:**
- Update git config
- Run destructive commands (push --force, reset --hard, clean -f) without explicit user request
- Skip hooks (--no-verify, --no-gpg-sign)
- Force push to main/master
- Commit sensitive files (.env, credentials.json)

**ALWAYS:**
- Create NEW commits (avoid --amend unless explicitly requested)
- Stage specific files by name (avoid `git add -A` which can include secrets)
- Only commit when user explicitly asks

## When Pre-commit Hooks Fail

If commit fails due to pre-commit hook:
1. Fix the issue
2. Re-stage the files
3. Create a NEW commit (don't use --amend)

The hook failure means the commit didn't happen - using --amend would modify the PREVIOUS commit and destroy work.

## Creating Pull Requests

Use the `gh` CLI:

```bash
# Check current state
git status
git diff main...HEAD

# Push to remote
git push -u origin <branch-name>

# Create PR
gh pr create --title "Title" --body "$(cat <<'EOF'
## Summary
- Bullet point summary

## Test plan
- [ ] Test item 1
- [ ] Test item 2

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
