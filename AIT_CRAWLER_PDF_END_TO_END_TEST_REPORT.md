# AIT Crawler + PDF End-to-End Test Report

**Date:** 2026-11-03  
**Outcome:** Crawler, upload, worker and launcher defects were repaired and 15 targeted regressions pass. The User/Admin APIs and portals are now responding on their expected ports. Live AIT crawl attempts exposed a second legacy worker consuming the same queue; that process was stopped and unsuccessful jobs were marked failed. No AIT pages were committed by these attempts. The task worker is stopped pending a clean single-worker launch. PDF extraction and browser review remain unverified; synthetic PDF values were not published.

## Environment and safety

- Project: `C:\Users\HP\OneDrive\Desktop\chatbot 4`.
- Existing AIT tenant: id 1, `col-ait-001`, approved; official site `https://www.aitindia.in/` (HTTP 200 verified).
- Requested PDF: `C:\Users\HP\Downloads\AIT_Smart_Upload_Test_Document_With_Course_Fees.pdf`; 30,405 bytes; 2 pages; SHA-256 `822C05E68235EDB3A15BFF6CF6014433537BB9E6B5781D689852A9CDA056BE57`.
- The existing matching document record (`id=1`) remains pending review. It contains explicitly synthetic sample facts. It was not approved, published, reset, or re-uploaded.
- No existing account, password, or database record was reset or altered.

## Crawl results and root cause

- Earlier historical job 1 had zero successful pages and 15 failures; stale jobs were retained and explicitly marked failed when their dispatch/runtime was known to have failed.
- Job 6 discovered the sitemap but made no page progress. After the initial worker was stopped, job 8 was dispatched while the API and worker broker settings differed; it remained queued. Job 9 was dispatched after aligning them.
- Process inspection then found two Celery workers: the new workspace virtual-environment worker and a legacy worker launched with a separate `uv` Python runtime. The legacy process consumed the same filesystem queue, producing multiple in-progress URL rows without saved pages. Both worker processes were stopped and job 9 was marked failed. Jobs 6, 8, and 9 have zero saved AIT pages from these attempts.
- The single-job atomic claim, added to `backend/app/crawler.py`, prevents duplicate delivery from running the same job concurrently in the updated code. It cannot protect against a legacy process running old code, so the stale worker must remain stopped and the new single worker must be started cleanly before the next crawl.

## Implemented changes

- `backend/app/crawler.py`: validated crawl dispatch; atomic queued-to-running claim; correct crawl completion/error states and timestamps; transaction rollback before error persistence; robust hidden HTML, JSON-LD, tables and definition-list extraction; required table metadata; safe media/document downloads and metadata; job-scoped crawl URL history; encoded URL paths; DOM-ready navigation.
- `backend/app/main.py`: upload queue failures now mark extraction failed and return service unavailable; crawl errors map to clear validation/queue responses.
- `backend/app/worker.py`: filesystem broker support for local development without Redis.
- `backend/requirements.txt`: conditional Windows `pywin32` dependency.
- `server_manager.py`: development broker detection and shared worker lifecycle.
- `AIT_CRAWLER_PDF_END_TO_END_TEST_REPORT.md`: this report.

## Verification

| Check | Result |
|---|---|
| Crawler, table, FAQ, document approval, tenant isolation tests | **PASS** — 15 passed, 1 skipped |
| Python syntax compilation of crawler, API, worker and manager | **PASS** |
| User/Admin API health (`8000`, `8001`) | **PASS** — HTTP 200 after restart |
| User/Admin portal (`3000`, `3001`) | **PASS** — HTTP 200 after restart |
| Official AIT site reachability | **PASS** — HTTP 200 |
| Crawl pages saved | **FAIL** — jobs 6, 8, 9 failed safely; zero AIT pages saved |
| PDF extraction and staged fee mappings | **NOT TESTED** — clean single worker unavailable at final check |
| Synthetic facts kept pending/unpublished | **PASS** |
| Browser login, tenant security, admin review UI, and user retrieval | **NOT TESTED** |

## Remaining action

Before the next crawl or PDF staging run, ensure only one worker process is running from `backend\\.venv\\Scripts\\python.exe` with `REDIS_URL=filesystem://` (or start Redis and configure both API and worker to use it). Then dispatch a new crawl, verify pages/media in the database, stage document 1 and inspect its fee mappings while leaving every synthetic fact pending review. Do not approve the sample values.
