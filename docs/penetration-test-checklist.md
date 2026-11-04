# Pre-production security verification

Run these checks against an isolated staging deployment with synthetic accounts and tenant data. Record the build revision, database migration revision, tester, date, evidence, and remediation for every item.

## Identity and sessions

- Verify password hashing, email verification, password reset expiry, login lockout, optional email two-step sign-in, and refresh-token rotation.
- Confirm refresh tokens are HttpOnly, Secure in HTTPS deployments, SameSite=Lax, stored only as hashes, and revoked on password change and sign-out.
- Attempt replay of used, expired, and superseded verification, reset, and two-step codes.
- Test CSRF using hostile and missing `Origin` headers for browser cookie-authenticated state changes.
- Confirm role checks for super admin, college admin, editor, viewer, and student endpoints.

## Tenant isolation and privacy

- With at least two tenants, try cross-tenant fact IDs, page IDs, job IDs, uploads, enquiries, conversations, messages, exports, histories, conflicts, cache keys, and widget requests.
- Repeat with the PostgreSQL application role to verify RLS blocks rows when application filters are omitted.
- Verify users can export or delete only their own account data and that college offboarding removes tenant facts, pages, chunks, catalog rows, cache, messages, and related feedback.
- Check backup encryption, retention, restore access, and deletion workflows.

## Crawler and uploads

- Test redirects, DNS changes, IPv4/IPv6 loopback and private ranges, encoded IPs, alternate ports, subdomains, cross-host links, sitemap entries, and Playwright subresources for SSRF.
- Verify robots rules, retry/frontier recovery, time and depth bounds, and safe behavior after a partially failed crawl.
- Upload oversized, malformed, polyglot, encrypted, and malware test documents. Confirm ClamAV is required in production and OCR runs with resource limits.
- Confirm crawled text cannot override system instructions or cause unsupported values to be returned.

## Widget, providers, and operations

- Test missing, invalid, and leaked widget keys; disallowed origins; allowed origins; and per-widget rate limits.
- Simulate provider timeouts, invalid responses, fallback, circuit-open recovery, token-budget exhaustion, and secret redaction in logs and browser bundles.
- Exercise dependency and container scanning, secret scanning, backup restore, health and metrics endpoints, and alert delivery.
- Run a representative crawl and 500-concurrent-chat load test; verify the agreed latency targets and monitor database, Redis, storage, and provider costs.

Do not mark production approval complete until findings are fixed or explicitly accepted by the security owner.
