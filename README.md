# Multi-college FAQ platform

Dark, multi-tenant college information platform. This repository is the runnable foundation for the three delivery stages: identity/tenant administration and evidence-backed chat; queued ingestion, analytics, feedback and knowledge gaps; and production operations, compliance, widget, voice and deployment hardening.

## Run locally

1. Run `python user.py` from the repository root. On first run it creates a git-ignored `.env` with a fresh secret key and a random one-time development super-admin password, then builds and starts the full Docker Compose stack.
2. Open http://localhost:3000. API docs are at http://localhost:8000/docs and health at http://localhost:8000/api/v1/health.

Use `python user.py logs` to follow service logs, `python user.py status` to see service status, and `python user.py down` to stop the stack. Use `python user.py up --foreground` to keep startup logs attached to the terminal. Grafana is at http://localhost:3001 and Prometheus at http://localhost:9090; the default Grafana dashboard charts API traffic, server errors, and chat P95 latency. The first-run credentials are printed once. To configure a specific super-admin email, SMTP, or production secrets, edit `.env` before starting the stack.

## Dependencies and services

- Python application and test dependencies are pinned in `backend/requirements.txt`; the API image installs them and installs Chromium for Playwright crawling.
- Frontend dependencies are pinned in `frontend/package.json`; the web image installs them before building Next.js.
- Docker Compose provides PostgreSQL with pgvector, Redis/Celery, ClamAV, daily PostgreSQL backups, Prometheus, and Grafana.
- The API image installs Tesseract and Poppler for scanned-document OCR. SMTP, Gemini, xKiro, OpenAI Whisper transcription, and S3-compatible storage are optional integrations configured in `.env`.

For local API development: `cd backend; pip install -r requirements.txt; alembic upgrade head; uvicorn app.main:app --reload`. The development default is SQLite; Compose uses PostgreSQL and Redis. The first boot seeds only the configured super-admin account. Register and approve actual colleges in the UI; no sample tenant or fabricated college data is seeded.

## Delivery stages

- **Stage 1 (MVP - Complete):** authentication, roles, college registration/review, tenant-scoped records, conversations, evidence-only chat, crawler ingestion, live catalog aliases, versioned cache, and searchable facts.
- **Stage 2 (Beta - Complete):** enhanced analytics dashboard, provider health monitoring with circuit breaker status, usage quota alerting (80% threshold), background queue visibility, knowledge gap prioritization (recency + frequency scoring), import/export validation with duplicate detection and format warnings, and provider fallback interface with automatic retry.
- **Stage 3 (Production - Complete):** operational monitoring endpoints (health check with Celery status), enhanced widget domain controls with origin validation, privacy/export/delete routes (GDPR compliant), voice affordances (browser Speech API + Whisper fallback), CSRF origin checks (middleware), security headers, backup script, and monitoring infrastructure (Prometheus/Grafana).

The MVP uses evidence-only retrieval for college facts. Gemini, xKiro, and optional Whisper transcription keys are server-side; Gemini is also used for optional Hindi/Gujarati question and answer translation, while the core chat interface has English, Hindi, and Gujarati strings. S3-compatible media and weekly crawl scheduling are implemented and require credentials plus a running scheduler. SMTP is required for production email and two-step sign-in. OCR and ClamAV require their runtime services. The interface dictionaries cover English, Hindi, and Gujarati, including the admin screens. Production load runs, clean-database migration checks, browser end-to-end checks, and external monitoring still require an environment with Docker, installed frontend dependencies, and configured service credentials.

For tenant acceptance runs, create an evaluation JSONL file from institution-verified questions and answers, then set `CHAT_EVAL_EMAIL` and `CHAT_EVAL_PASSWORD` and run `python infra/chat-eval.py path/to/verified-evaluation.jsonl`. The runner requires 100 questions per college by default; `--allow-small` is for smoke checks only.

CI runs backend tests, a frontend production build, Python and npm dependency audits, and a Gitleaks secret scan; pushes also publish an SPDX SBOM artifact. Install the staged secret hook locally with `pip install pre-commit` followed by `pre-commit install`.

See [docs/architecture.md](docs/architecture.md), [docs/er-diagram.md](docs/er-diagram.md), [docs/admin-guide.md](docs/admin-guide.md), [docs/operations.md](docs/operations.md), [docs/penetration-test-checklist.md](docs/penetration-test-checklist.md), and [docs/demo-script.md](docs/demo-script.md). API schemas are published via FastAPI OpenAPI.
