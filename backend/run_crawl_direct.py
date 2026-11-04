"""Direct crawl test for college_id=1 without Redis/Celery"""
import sys
import traceback
import os
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

# Set page limit for testing
os.environ["CRAWL_PAGE_LIMIT"] = "1"

from app.db import SessionLocal
from app.models import College, CrawlJob
from app.crawler import run_crawl
from sqlalchemy import select, func, delete

db = SessionLocal()

try:
    # Get college
    college = db.scalar(select(College).where(College.id == 1))
    if not college:
        print("ERROR: College with id=1 not found")
        sys.exit(1)

    print(f"College: {college.name} ({college.website})")

    # Clean up existing data for college_id=1 before test
    print("Cleaning up existing data for college_id=1...")
    from app.models import (
        Page, PageSection, NavigationItem, StructuredData, ExtractedTable,
        FAQ, Contact, Link, MediaAsset, Document, Fact, CrawlUrl, CrawlFrontier,
        CrawlJob, KnowledgeCatalog, FactHistory
    )
    # Delete in order of dependencies
    db.execute(delete(KnowledgeCatalog).where(KnowledgeCatalog.college_id == 1))
    db.execute(delete(FactHistory).where(FactHistory.college_id == 1))
    db.execute(delete(Fact).where(Fact.college_id == 1))
    db.execute(delete(PageSection).where(PageSection.college_id == 1))
    db.execute(delete(NavigationItem).where(NavigationItem.college_id == 1))
    db.execute(delete(StructuredData).where(StructuredData.college_id == 1))
    db.execute(delete(ExtractedTable).where(ExtractedTable.college_id == 1))
    db.execute(delete(FAQ).where(FAQ.college_id == 1))
    db.execute(delete(Contact).where(Contact.college_id == 1))
    db.execute(delete(Link).where(Link.college_id == 1))
    db.execute(delete(MediaAsset).where(MediaAsset.college_id == 1))
    db.execute(delete(Document).where(Document.college_id == 1))
    db.execute(delete(Page).where(Page.college_id == 1))
    db.execute(delete(CrawlUrl).where(CrawlUrl.college_id == 1))
    db.execute(delete(CrawlFrontier).where(CrawlFrontier.college_id == 1))
    db.execute(delete(CrawlJob).where(CrawlJob.college_id == 1))
    db.commit()
    print("Cleanup complete")

    # Create crawl job with page limit (we'll check in crawler)
    job = CrawlJob(
        college_id=college.id,
        url="https://www.aitindia.in/",
        status="queued",
        version=college.data_version + 1,
        max_depth=10,
        time_budget_seconds=1800
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    print(f"Created crawl job: {job.id}")
    print("Note: Crawl will process up to 15 pages for testing")

    # Run crawl directly
    print("\nRunning crawl...")
    try:
        result = run_crawl(job.id)
        print(f"\nCrawl completed: {result}")
    except Exception as e:
        print(f"\nCrawl failed with error:")
        traceback.print_exc()
        db.refresh(job)
        print(f"Job status: {job.status}")
        print(f"Job error: {job.error_log}")
        sys.exit(1)

    # Print crawl_urls by status
    print("\n" + "="*60)
    print("CRAWL_URLS BY STATUS")
    print("="*60)
    from app.models import CrawlUrl
    crawl_urls = db.execute(select(CrawlUrl.status, func.count(CrawlUrl.id)).where(CrawlUrl.job_id == job.id).group_by(CrawlUrl.status)).all()
    for status, count in crawl_urls:
        print(f"  {status}: {count}")

    # Print row counts for college_id=1
    print("\n" + "="*60)
    print("ROW COUNTS FOR COLLEGE_ID=1")
    print("="*60)
    from app.models import (
        Page, PageSection, NavigationItem, StructuredData, ExtractedTable,
        FAQ, Contact, Link, MediaAsset, Document, Fact
    )

    counts = {
        "crawled_pages": db.scalar(select(func.count(Page.id)).where(Page.college_id == 1)),
        "page_sections": db.scalar(select(func.count(PageSection.id)).where(PageSection.college_id == 1)),
        "navigation_items": db.scalar(select(func.count(NavigationItem.id)).where(NavigationItem.college_id == 1)),
        "structured_data": db.scalar(select(func.count(StructuredData.id)).where(StructuredData.college_id == 1)),
        "extracted_tables": db.scalar(select(func.count(ExtractedTable.id)).where(ExtractedTable.college_id == 1)),
        "faqs": db.scalar(select(func.count(FAQ.id)).where(FAQ.college_id == 1)),
        "contacts": db.scalar(select(func.count(Contact.id)).where(Contact.college_id == 1)),
        "links": db.scalar(select(func.count(Link.id)).where(Link.college_id == 1)),
        "media": db.scalar(select(func.count(MediaAsset.id)).where(MediaAsset.college_id == 1)),
        "documents": db.scalar(select(func.count(Document.id)).where(Document.college_id == 1)),
        "facts": db.scalar(select(func.count(Fact.id)).where(Fact.college_id == 1)),
        "other_facts": db.scalar(select(func.count(Fact.id)).where(Fact.college_id == 1)),
    }

    for table, count in counts.items():
        print(f"  {table}: {count}")

    # Structured data by format
    print("\nSTRUCTURED_DATA BY FORMAT:")
    sd_formats = db.execute(select(StructuredData.format, func.count(StructuredData.id)).where(StructuredData.college_id == 1).group_by(StructuredData.format)).all()
    for fmt, count in sd_formats:
        print(f"  {fmt}: {count}")

    # 5 stored page URLs with titles
    print("\n" + "="*60)
    print("5 STORED PAGE URLs WITH TITLES")
    print("="*60)
    pages = db.execute(select(Page.url, Page.title).where(Page.college_id == 1).limit(5)).all()
    for url, title in pages:
        print(f"  {url}")
        print(f"    {title[:80]}")

    # Verify no stored URL is outside aitindia.in
    print("\n" + "="*60)
    print("DOMAIN VERIFICATION")
    print("="*60)
    from urllib.parse import urlparse
    all_urls = db.execute(select(Page.url).where(Page.college_id == 1)).all()
    outside_urls = []
    for (url,) in all_urls:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not any(host in hostname for host in ["aitindia.in", "www.aitindia.in"]):
            outside_urls.append(url)

    if outside_urls:
        print(f"ERROR: Found {len(outside_urls)} URLs outside aitindia.in:")
        for url in outside_urls[:10]:
            print(f"  {url}")
    else:
        print("SUCCESS: All stored URLs are within aitindia.in")

    # Verify no row has another college_id
    print("\n" + "="*60)
    print("COLLEGE_ID VERIFICATION")
    print("="*60)
    tables_to_check = [
        Page, PageSection, NavigationItem, StructuredData, ExtractedTable,
        FAQ, Contact, Link, MediaAsset, Document, Fact
    ]

    wrong_college = []
    for table in tables_to_check:
        count = db.scalar(select(func.count(table.id)).where(table.college_id != 1))
        if count > 0:
            wrong_college.append((table.__tablename__, count))

    if wrong_college:
        print(f"ERROR: Found rows with college_id != 1:")
        for table_name, count in wrong_college:
            print(f"  {table_name}: {count}")
    else:
        print("SUCCESS: All rows have college_id=1")

    print("\n" + "="*60)
    print("DIRECT CRAWL TEST COMPLETE")
    print("="*60)

finally:
    db.close()
