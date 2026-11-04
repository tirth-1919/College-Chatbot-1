# Data model

```mermaid
erDiagram
  COLLEGES ||--o{ USERS : owns
  COLLEGES ||--o{ COLLEGE_SOURCES : configures
  COLLEGES ||--o{ CRAWL_JOBS : runs
  COLLEGES ||--o| CRAWL_SCHEDULES : schedules
  COLLEGES ||--o{ CRAWL_FRONTIER : queues
  COLLEGES ||--o{ CRAWLED_PAGES : ingests
  CRAWL_JOBS ||--o{ CRAWL_FRONTIER : discovers
  CRAWL_JOBS ||--o{ CRAWLED_PAGES : produces
  CRAWLED_PAGES ||--o{ PAGE_CHUNKS : splits
  COLLEGES ||--o{ OTHER_FACTS : contains
  CRAWLED_PAGES ||--o{ OTHER_FACTS : supports
  OTHER_FACTS ||--o| KNOWLEDGE_CATALOG : indexes
  OTHER_FACTS ||--o{ OTHER_FACTS_HISTORY : versions
  COLLEGES ||--o{ ANSWER_CACHE : caches
  USERS ||--o{ CONVERSATIONS : owns
  COLLEGES ||--o{ CONVERSATIONS : scopes
  CONVERSATIONS ||--o{ MESSAGES : contains
  MESSAGES ||--o{ FEEDBACK : receives
  COLLEGES ||--o{ QUESTION_LOG : observes
  COLLEGES ||--o{ KNOWLEDGE_GAPS : tracks
  COLLEGES ||--o{ ENQUIRIES : receives
  COLLEGES ||--o{ COLLEGE_MEMBERS : grants
  USERS ||--o{ COLLEGE_MEMBERS : joins
```

`other_facts` is the flexible evidence store. Each fact points to its source page when available, receives a catalog entry through SQLAlchemy insert/update/delete listeners, and keeps prior values in `other_facts_history`. Tenant-owned tables carry `college_id`; conversation access additionally checks the authenticated user. PostgreSQL RLS is enabled by the initial migration as a second tenant boundary.
