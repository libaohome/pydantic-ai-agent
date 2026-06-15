---
name: code-review
description: >
  Review source code for bugs, security vulnerabilities, and style issues.
  Use when the user asks to review, audit, or check code quality.
  Supports Python, TypeScript, and Go code review.
version: 1.0.0
author: system
category: development
tags: [code-review, security, quality]
---

# Code Review Skill

## When to Use This Skill

Use this skill when you need to:

- Review code for bugs and potential issues
- Audit code for security vulnerabilities
- Check code style and best practices
- Suggest improvements and refactoring

## Instructions

1. Read the target source file(s) using the `read_file` tool
2. Analyze the code against the following criteria:
   - **Correctness**: Logic errors, off-by-one, null handling
   - **Security**: Injection, XSS, hardcoded secrets, insecure APIs
   - **Performance**: N+1 queries, unnecessary allocations, blocking I/O
   - **Style**: Naming conventions, code organization, documentation
3. Generate a structured review report

## Output Format

```json
{
  "summary": "Brief overall assessment",
  "severity": "high|medium|low",
  "issues": [
    {
      "type": "bug|security|performance|style",
      "location": "file:line",
      "description": "What the issue is",
      "suggestion": "How to fix it"
    }
  ]
}
```

## Review Checklist

### Python
- [ ] Type hints present on public functions
- [ ] No bare `except:` clauses
- [ ] f-strings used over `.format()` or `%`
- [ ] No mutable default arguments
- [ ] `with` statement for file/DB operations

### TypeScript
- [ ] No `any` types without justification
- [ ] Proper null/undefined handling
- [ ] Async/await over raw promises
- [ ] No console.log in production code

### Security (All Languages)
- [ ] No hardcoded credentials or API keys
- [ ] Input validation on all user-facing endpoints
- [ ] Parameterized queries for database access
- [ ] Proper error handling without leaking internals

## When NOT to Use

- General coding questions (not reviewing specific code)
- Writing new code from scratch
- Debugging runtime errors (use debugging skill instead)
