"""Test that table rows are stored as Facts and don't duplicate on re-run"""
import sys
import hashlib
import json
import time
import os
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

# Use a temporary in-memory database for this test
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.db import SessionLocal, engine, Base
from app.models import College, Page, Fact, CrawlJob
from sqlalchemy import select, delete, func

# Create tables in memory
Base.metadata.create_all(bind=engine)

# Create a test database session
db = SessionLocal()

try:
    # Create test college and page
    import time
    unique_suffix = str(int(time.time() * 1000))
    college_code = f"TEST_TABLE_ROW_{unique_suffix}"
    college = College(code=college_code, name="Test College for Table Rows", status="approved")
    db.add(college)
    db.flush()

    # No cleanup needed since this is a brand new college

    # Create test page
    page = Page(
        college_id=college.id,
        url="https://test.example/table",
        title="Test Table Page",
        raw_text="Test content",
        content_hash=hashlib.sha256("Test content".encode()).hexdigest(),
        version=1
    )
    db.add(page)
    db.flush()

    # Simulate extract_html_tables output for a table with 5 rows
    structured_tables = []
    for i in range(5):
        row_dict = {"header1": f"value{i}", "header2": f"data{i}"}
        struct = {
            "category": f"website table 1: Test Table",
            "title": "",
            "value": json.dumps(row_dict)
        }
        structured_tables.append(struct)

    # Simulate the crawler's structured facts storage logic
    job_id = 999
    url = "https://test.example/table"

    for row_index, struct in enumerate(structured_tables):
        value_hash = hashlib.sha256(struct["value"].encode()).hexdigest()[:12]
        title = f"Row {row_index}: {value_hash}"
        existing = db.scalar(select(Fact).where(
            Fact.college_id == college.id,
            Fact.source_page_id == page.id,
            Fact.category == struct["category"],
            Fact.title == title
        ))
        if not existing:
            db.add(Fact(
                college_id=college.id,
                category=struct["category"],
                title=title,
                value=struct["value"],
                source_page_id=page.id,
                confidence=0.85,
                extra={"job_id": job_id, "source_url": url, "origin": "html_table"}
            ))

    db.commit()

    # Check how many Facts were created
    fact_count = db.scalar(select(func.count()).select_from(Fact).where(Fact.college_id == college.id, Fact.category.like("website table%")))
    print(f"First run: {fact_count} Fact rows created")

    # Run the same logic again (simulate re-crawl)
    for row_index, struct in enumerate(structured_tables):
        value_hash = hashlib.sha256(struct["value"].encode()).hexdigest()[:12]
        title = f"Row {row_index}: {value_hash}"
        existing = db.scalar(select(Fact).where(
            Fact.college_id == college.id,
            Fact.source_page_id == page.id,
            Fact.category == struct["category"],
            Fact.title == title
        ))
        if not existing:
            db.add(Fact(
                college_id=college.id,
                category=struct["category"],
                title=title,
                value=struct["value"],
                source_page_id=page.id,
                confidence=0.85,
                extra={"job_id": job_id, "source_url": url, "origin": "html_table"}
            ))

    db.commit()

    # Check how many Facts exist after second run
    fact_count_after = db.scalar(select(func.count()).select_from(Fact).where(Fact.college_id == college.id, Fact.category.like("website table%")))
    print(f"Second run: {fact_count_after} Fact rows exist (should still be 5)")

    # Verify details
    facts = list(db.scalars(select(Fact).where(Fact.college_id == college.id, Fact.category.like("website table%"))))
    print(f"Fact titles: {[f.title for f in facts]}")
    print(f"Fact confidence values: {[f.confidence for f in facts]}")
    print(f"Fact extra.origin values: {[f.extra.get('origin') for f in facts]}")

    if fact_count == 5 and fact_count_after == 5:
        print("\nSUCCESS: 5 Fact rows created on first run, still 5 after second run (no duplicates)")
        # Clean up
        db.execute(delete(Fact).where(Fact.college_id == college.id))
        db.execute(delete(Page).where(Page.college_id == college.id))
        db.execute(delete(College).where(College.id == college.id))
        db.commit()
    else:
        print(f"\nFAILURE: Expected 5 rows, got {fact_count} on first run and {fact_count_after} on second run")
        # Clean up on failure too
        db.execute(delete(Fact).where(Fact.college_id == college.id))
        db.execute(delete(Page).where(Page.college_id == college.id))
        db.execute(delete(College).where(College.id == college.id))
        db.commit()
        sys.exit(1)

finally:
    db.close()
