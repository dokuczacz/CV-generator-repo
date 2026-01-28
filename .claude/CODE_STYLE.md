# Code Style Guidelines

## TypeScript

- Strict mode enabled
- Explicit return types for functions
- No `any` types unless absolutely necessary
- Use functional components with hooks
- Only use emojis if user explicitly requests

## Python

- Type hints for function signatures
- Docstrings for public functions (not private helpers)
- Use pathlib for file operations
- Follow Azure Functions patterns
- Only use emojis if user explicitly requests

## General

- Keep functions small and focused
- Prefer composition over inheritance
- Write self-documenting code (clear names > comments)
- Add comments only for "why", not "what"
- No emojis unless explicitly requested by user

## Security

- No command injection, XSS, SQL injection vulnerabilities
- Validate only at system boundaries (user input, external APIs)
- Trust internal code and framework guarantees
- No secrets in code (use environment variables)

## Avoid Over-Engineering

- Only make changes that are directly requested
- Don't add extra features, refactoring, or "improvements" beyond what was asked
- Don't add docstrings, comments, or type annotations to code you didn't change
- Don't add error handling for scenarios that can't happen
- Don't create helpers/utilities for one-time operations
- Three similar lines is better than a premature abstraction
- No backwards-compatibility hacks (unused `_vars`, re-exports, `// removed` comments)
- If something is unused, delete it completely