# Operations and production checklist

## Run and recover

`docker compose up --build` starts web, API, Postgres/pgvector, Redis, ClamAV, the daily backup worker and Celery. The backup worker stores compressed dumps under `./backups` and keeps 14 days. Restore into a clean database with `docker compose exec -T db pg_restore -U chatbot -d chatbot --clean --if-exists < backup.dump`. Test restores in a separate environment before production and move backups to encrypted off-site storage for production.

## Before production

- Set strong secrets, HTTPS, secure cookies, strict CORS and a real SMTP provider.
- Configure private S3-compatible storage with `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_REGION`; object URLs are short-lived signed URLs. Verify bucket encryption and lifecycle policies with the storage provider.
- Keep the Celery scheduler service running for college weekly crawl schedules. The scheduler checks daily page/crawl quotas before enqueuing jobs.
- Crawl jobs enforce an 8-level link depth, a 30-minute time budget, and a 20 MiB maximum per fetched page or document. An oversized resource is recorded as a failed frontier item and can be retried from crawl history after the source is corrected.
- Sitemap indexes are expanded through up to three levels; same-domain page URLs from URL sets enter the persisted crawl frontier and still pass robots, domain, and public-IP checks.
- HTML table rows and definition-list label/value pairs are indexed as tenant-scoped catch-all facts alongside raw page chunks. Re-crawls update changed entries, retain prior values in fact history, and deactivate extracted entries removed from the source page.
- Use managed encrypted database/object storage in the required India region; define retention and deletion policies.
- Use a non-owner application role for database connections. Initial Alembic migration enables PostgreSQL RLS policies on college-scoped tables and conversation ownership; verify the configured role and policy behavior in staging.
- Compose provisions Prometheus and Grafana with API request, server-error, and chat P95 latency charts. Prometheus evaluates API availability, elevated 5xx rate, chat latency, Redis availability, recent crawl failures, and repeated AI-provider failures; configure an Alertmanager receiver for email or paging delivery in production.
- Set `MAINTENANCE_MODE=true` in the API environment to show the localized maintenance banner to signed-in users and admins. The health endpoint reports the mode; the setting displays a banner and does not block API requests.
- CI runs Gitleaks, Python/Node dependency audits, Trivy scans of the API and web container images, and emits an SPDX SBOM. Dependabot proposes dependency updates. Production still requires penetration testing, 500-user load/crawl runs, backups with restore drills, and configured external monitoring and alerts.
- Configure Gemini/xKiro adapters, provider health/circuit breakers, per-tenant quotas and budget alerts before enabling general AI answers.
- Add malware scanning, OCR and isolated parsing for uploads before accepting documents.
- OCR and ClamAV scanning are wired for uploads; production must provide a healthy ClamAV service and isolated document parsing.
- Complete the [penetration-test checklist](penetration-test-checklist.md), including cross-tenant RLS checks, crawler SSRF tests, widget abuse, and load testing.
- For deployment verification, run `node infra/crawl-smoke-test.mjs` with a college-admin account and registered `CRAWL_URL`, then run `k6 run infra/load-test.js` with `TEST_EMAIL`, `TEST_PASSWORD`, `BASE_URL`, and `ORIGIN` set. Use a staging tenant; the k6 scenario sends up to 500 concurrent chats.

## Incident response

Disable affected college access, preserve audit and crawl job records, rotate exposed credentials, inspect access logs and data exports, restore from a verified backup if needed, and notify affected institutions according to the approved incident process.
