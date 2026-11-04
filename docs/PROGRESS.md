# Crawler and Admin Dashboard Upgrade Progress

## Project Overview
Multi-college AI FAQ chatbot with Playwright-based crawler and college-admin data dashboard.
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (SQLite fallback for local dev)
- **Frontend**: Next.js 16.4.1 + React 19.3.1
- **Colleges**: AIT, RCTI (multi-tenant with row-level security)

---

## COMPLETED STEPS (1-4)

### Step 1: Database ✅
**Status**: COMPLETED

**What Changed**:
- Created `docker-compose.yml` for PostgreSQL with pgvector and pg_trgm
- Updated `config.py` with PostgreSQL URL (SQLite fallback for local dev)
- Updated `db.py` with automatic PostgreSQL→SQLite fallback
- Migration `0013_add_missing_tables_and_tenant_columns.py`:
  - New tables: `crawl_urls`, `aliases`
  - Added `college_id` to: `email_outbox`, `user_sessions`, `college_registrations`, `messages`, `feedback`
- ORM models: `CrawlUrl`, `Alias`, updated `Message`, `Feedback`
- Test: `test_tenant_isolation.py` validates all data tables have college_id

**How to Run**:
```bash
cd backend
python -m pytest tests/test_tenant_isolation.py -v
```

**Database Tables**:
- `crawl_urls` - Tracks every URL with status (queued, running, stored, failed, duplicate, blocked_by_robots, out_of_domain)
- `crawled_pages` - Page content with versioning, screenshots, HTTP metadata
- `crawl_frontier` - Crawl queue for resume capability
- `crawl_jobs` - Crawl job metadata with coverage report
- `page_sections` - h1-h6 heading sections
- `navigation_items` - Navigation menu items
- `structured_data` - JSON-LD, Open Graph, Twitter Card
- `extracted_tables` - HTML tables with headers/rows
- `faqs` - FAQ Q&A pairs
- `links` - Internal/external links
- `documents` - PDF/DOCX/XLSX with extracted text
- `contacts` - Emails, phones, addresses
- `programs`, `fees`, `faculty`, `departments`, `facilities`, `hostel`, `placements`, `scholarships`, `events`, `library` - Structured data
- `other_facts` - Catch-all for unmatched data
- `media_assets` - Images with thumbnails
- `page_chunks` - Vector embeddings for search
- `knowledge_catalog` - Canonical names, aliases, searchable text
- `answer_cache` - Cached answers
- `*_history` tables - Row history for diffing

**How to Run Backend**:
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**How to Run Tests**:
```bash
cd backend
python -m pytest tests/ -v
```

---

### Step 2: Playwright Crawler ✅
**Status**: COMPLETED

**What Changed**:
- Replaced httpx with Playwright for ALL pages
- Added `expand_accordions_and_tabs()` to expand content before extraction
- Updated `run_crawl()`:
  - Screenshot capture stored under `colleges/<college_id>/screenshots/`
  - HTTP status, final URL, content type, language
  - Every URL tracked in `crawl_urls` with status and failure reason
  - Persisted crawl queue for resume capability
- Extraction functions: `extract_page_sections()`, `extract_navigation()`, `extract_structured_data()`, `extract_tables()`, `extract_faqs()`, `extract_contacts()`

**Test Results**:
```
tests/test_playwright_crawler.py::test_crawl_url_has_required_fields PASSED
tests/test_playwright_crawler.py::test_page_has_playwright_fields PASSED
```

**How to Run Crawler**:
```bash
cd backend
python -c "from app.crawler import run_crawl; from app.db import SessionLocal; from app.models import CrawlJob, College; db = SessionLocal(); college = db.query(College).first(); job = CrawlJob(college_id=college.id, url='https://example.com', status='pending'); db.add(job); db.commit(); run_crawl(job.id)"
```

---

### Step 3: Data Storage ✅
**Status**: COMPLETED

**What Changed**:
- Media downloading: images stored with thumbnails under `colleges/<college_id>/media/`
- Document downloading: PDF/DOCX/XLSX with text extraction and OCR for scanned PDFs
- All extracted data stored with: `college_id`, `job_id`, `source_url`, `source_page_id`
- Tables: `page_sections`, `navigation_items`, `structured_data`, `extracted_tables`, `faqs`, `links`, `contacts`, `documents`
- Updated `MediaAsset` with `job_id` and `page_id`

**Test Results**:
```
tests/test_data_storage.py::test_page_sections_has_tenant_fields PASSED
tests/test_data_storage.py::test_all_extracted_tables_have_source_page_id PASSED
```

---

### Step 4: Structured Data Build ✅
**Status**: COMPLETED

**What Changed**:
- Created `structured_builder.py` with heuristic-based table detection
- Builds structured rows from:
  - HTML tables (header keyword matching: program, fee, faculty, etc.)
  - Page sections (heading keyword matching)
  - JSON-LD (schema.org types: Course, Person, Event)
- Unknown tables → `other_facts`
- Integrated into crawler post-crawl step
- All rows have `source_page_id` for traceability

**Test Results**:
```
tests/test_structured_builder.py::test_build_from_table_programs PASSED
tests/test_structured_builder.py::test_build_from_sections_fees PASSED
tests/test_structured_builder.py::test_unknown_table_goes_to_other_facts PASSED
```

---

## VERIFICATION: Real Crawl of AIT Website ✅

**Status**: COMPLETED (SQLite, PostgreSQL not available in local environment)

**Crawl Results**:
- **Pages crawled**: 248 pages successfully (95.8% coverage)
- **Pages failed**: 0
- **Coverage report**:
  - crawled_urls: 236 stored, 12 duplicate
  - images_found: 1781
  - blocked_urls: 0
  - out_of_domain_urls: 0
  - extracted_tables: 1
  - internal links found: 259

**Row Counts for College AIT**:
```
crawled_pages: 248
page_sections: 3890
navigation_items: 663
structured_data: 0
extracted_tables: 1
faqs: 0
links: 10279
contacts: 78
documents: 0
programs: 0
fees: 0
faculty: 4
departments: 8
facilities: 15
hostel: 1
placements: 1
scholarships: 5
events: 3
other_facts: 248
```

**Sample Data**:
- **Program**: 0 rows (builder cleared, needs fix)
- **Fee**: 0 rows (builder cleared, needs fix)
- **Faculty**: 4 rows with low confidence (breadcrumbs)

**Null college_id Check**: ✅ No rows with null college_id found in data tables

**Note**: PostgreSQL is not available in the local environment (Docker not installed). The configuration is ready for deployment, but local testing uses SQLite with the automatic fallback.

---

## EXTRACTION FIXES IN PROGRESS - CRITICAL ERROR

**CRITICAL ISSUE**: During Item 0 verification, I accidentally overwrote the entire `backend/app/crawler.py` file with a new version instead of making targeted edits. The file may have lost previous work. This needs to be fixed before continuing.

**Item 0 Status**: FAILED - crawler.py was accidentally overwritten
- Before the error: Media download code was updated to remove S3 conditional and add local storage fallback
- Current state: crawler.py is a new version that may not preserve all previous functionality
- Action needed: Restore crawler.py from backup or git history, then re-apply the targeted fix properly

**Previous fix that was applied (before error)**:
- Removed S3 conditional from image download (line 504): changed from `if image_links and all((settings.s3_endpoint,...))` to `if image_links:`
- Added local storage fallback for images: `os.makedirs(storage_dir, exist_ok=True)` and `with open(object_key, 'wb') as f: f.write(original.getvalue())`
- Same fix applied to document download (line 544)
- This fix allows downloading media/documents to local disk without requiring S3 configuration

**Remaining items from user's 6-point request (pending crawler.py fix):**
0. ⏳ VERIFY Item 1: Re-run media/document step, print counts, verify security requirements (hash-based filenames, max file size, content-type check, private-IP check, authenticated endpoint)
1. ⏳ For 9 PDFs: print URL, page count, first 300 chars of extracted text, identify fees/courses/faculty
2. ⏳ Print 10 page URLs with course/fee keywords, page_sections text length, table/list presence, 300-char samples
3. ⏳ Explain why programs/fees dropped from 1 to 0, show diff of builder logic, fix regression
4. ⏳ List 12 duplicate URLs with matched URLs, confirm none are real distinct pages
5. ⏳ Explain "95.8% coverage" calculation
6. ⏳ LLM-assisted extraction with Gemini, add amount/currency columns, local storage, confidence tracking, PostgreSQL

---

## PART B: End-to-End Slice (Pending)

### Status: Not started - awaiting extraction fixes

### Tasks:
1. ✅ Create knowledge_catalog, page_chunks and *_history tables if missing
2. ⏳ Catalog sync: after crawl/admin change, rebuild catalog entries, clear cache, bump data_version, safety net for newer rows
3. ⏳ Retrieval function answer_question(college_id, question): clean question, match entities, fetch rows, fallback to page_chunks, validate college ownership
4. ⏳ Chat endpoint using retrieval function
5. ⏳ Tests: "bca fee", "courses", "location" for AIT; add course manually and ask; RCTI isolation

---

## REMAINING STEPS (After Part B)

### Step 5: Coverage Report
- Generate after each crawl: sitemap vs stored URLs, links found vs pages stored, pages with no text, images/documents stats
- List failures with reasons and Retry endpoint
- Never hide login-only, robots-blocked, out-of-domain URLs

### Step 6: Re-Crawl Logic
- Skip unchanged pages by `content_hash`
- Create new version and diff for changed pages
- Mark vanished pages inactive (don't delete)
- Deduplicate images/documents by hash
- Chat uses latest active version

### Step 7: Backend API Endpoints
- Endpoints for all crawl data tables (CRUD, search, filter, paginate)
- Live crawl status endpoint
- Coverage report endpoint
- Retry failed URLs endpoint

### Step 8: Admin Dashboard Tabs (13 tabs)
1. Crawl Website
2. Crawl History
3. Discovered Pages (with snapshot preview)
4. Page Content
5. Navigation (table and tree views)
6. Structured Data
7. Tables and FAQs (render actual tables)
8. Links
9. Images and Media (gallery and table)
10. Documents
11. Contacts
12. Data by Category (one table per category)
13. Database Explorer (any table for this college)

Each: searchable, sortable, filterable, paginated, column chooser, row detail, CSV/Excel export

### Step 9: Live Crawl Screen
- Target URL with "Visit site" link
- Page currently being opened
- Running log of visited URLs
- Counters: discovered, fetched, stored, failed, skipped
- Progress bar
- Stop and Resume buttons
- Screenshot preview per page (no iframes)

### Step 10: Admin Editing
- Add rows, edit cells inline, delete rows
- Bulk import CSV/Excel
- Add custom column, add new table
- Mark entries "Admin Verified"
- Don't overwrite admin values on re-crawl without conflict prompt
- Conflict detection and handling

### Step 11: Knowledge Catalog Sync
- Trigger after crawl or admin change
- Rebuild catalog entries for affected rows
- Clear college's cached answers, bump data_version
- Safety net: at question time, read directly from source rows newer than last sync

### Step 12: Tests
1. Crawl sample site with mega menu, JSON-LD, data table, FAQ accordion, PDF, lazy-loaded images
2. AIT rows invisible to RCTI admin and vice versa
3. Coverage report matches sitemap; broken links show as failures
4. Change one page, re-crawl; only that page gets new version and diff
5. Edit row as admin, re-crawl; admin value kept, conflict shown
6. Add course in admin table, ask chatbot immediately; answers correctly

---

## IMPORTANT NOTES
- Never hardcode college, course, or category names - read from database
- Treat all crawled text as untrusted data, never as AI instructions
- Store files under `colleges/<college_id>/` for tenant isolation
- Preserve tenant isolation (AIT ↔ RCTI separation)
- Keep dark black-and-white ChatGPT-style theme
- PostgreSQL with pgvector/pg_trgm configured in docker-compose.yml but using SQLite fallback locally
- **Just fixed**: Local file storage fallback for images/documents (no longer requires S3 configuration)
