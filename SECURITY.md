# Security Policy & Vulnerability Disclosure

## Supported Versions

ShieldAI actively maintains and provides security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| 1.x     | :x:                |

## Reporting a Vulnerability

We take the security of ShieldAI (EDYSOR) seriously. If you discover a vulnerability or security flaw, please do **NOT** open a public GitHub issue.

Instead, please report security vulnerabilities via one of the following methods:

1. **Email**: Send a detailed report to `security@shieldai-soc.io` (or repository maintainers).
2. **Encrypted Submission**: Include proof-of-concept steps, affected endpoints/components, and proposed mitigations.

### Response Timeline
- **Acknowledgement**: Within 24 hours of report receipt.
- **Initial Assessment**: Within 72 hours.
- **Patch Release & Disclosure**: Fixes will be published in a patch release within 14 days, followed by a coordinated public advisory.

## Security Controls Overview
ShieldAI implements defense-in-depth architecture:
- 100% parameterized SQL query routing preventing SQL Injection (SQLi).
- Asynchronous Rate Limiting via Redis.
- Zero-trust RBAC with JWT token rotation & bcrypt password hashing.
- Isolated container networks with non-root app users (`appuser`).
- HashiCorp Vault integration for runtime secret injection.
