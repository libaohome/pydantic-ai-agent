# Security Review Checklist

## OWASP Top 10 (2025)

| # | Category | Key Checks |
|---|----------|------------|
| A01 | Broken Access Control | IDOR, missing auth checks, privilege escalation |
| A02 | Cryptographic Failures | Hardcoded keys, weak algorithms, missing TLS |
| A03 | Injection | SQL injection, XSS, command injection |
| A04 | Insecure Design | Missing rate limiting, no input validation |
| A05 | Security Misconfiguration | Default credentials, verbose errors, CORS |
| A06 | Vulnerable Components | Outdated dependencies, known CVEs |
| A07 | Auth Failures | Weak passwords, no MFA, session fixation |
| A08 | Data Integrity Failures | No integrity checks, insecure deserialization |
| A09 | Logging Failures | Missing audit logs, sensitive data in logs |
| A10 | SSRF | Unvalidated URLs, internal network access |

## Language-Specific Checks

### Python
- `pickle.loads()` on untrusted data
- `subprocess` with `shell=True`
- `yaml.load()` without `SafeLoader`
- `eval()` / `exec()` on user input
- SQL string concatenation

### TypeScript / Node.js
- `eval()` / `new Function()`
- `child_process.exec()` with user input
- Prototype pollution vectors
- `innerHTML` assignment
- Unvalidated redirect URLs
