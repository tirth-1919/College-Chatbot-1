"""Test that extracted data is stored with college_id, job_id, source_url, source_page_id"""
import pytest
from app.db import SessionLocal
from app.models import College, CrawlJob, Page, PageSection, NavigationItem, StructuredData, ExtractedTable, FAQ, Link, Contact, Document
from sqlalchemy import select


def test_page_sections_has_tenant_fields():
    """Test page_sections has college_id, job_id, source_url"""
    db = SessionLocal()
    try:
        college = College(name="Test College", code="TEST", website="https://example.com")
        db.add(college)
        db.flush()
        
        job = CrawlJob(college_id=college.id, url="https://example.com", status="pending")
        db.add(job)
        db.flush()
        
        page = Page(college_id=college.id, url="https://example.com/test", title="Test", raw_text="Content", content_hash="abc")
        db.add(page)
        db.flush()
        
        section = PageSection(
            college_id=college.id,
            job_id=job.id,
            page_id=page.id,
            source_url="https://example.com/test",
            heading_level=1,
            heading_text="Test Heading",
            section_text="Test content",
            position=0
        )
        db.add(section)
        db.flush()
        
        assert section.college_id == college.id
        assert section.job_id == job.id
        assert section.page_id == page.id
        assert section.source_url == "https://example.com/test"
        
        db.rollback()
    finally:
        db.close()


def test_all_extracted_tables_have_source_page_id():
    """Test that all extracted data tables have source_page_id"""
    db = SessionLocal()
    try:
        college = College(name="Test College", code="TEST", website="https://example.com")
        db.add(college)
        db.flush()
        
        job = CrawlJob(college_id=college.id, url="https://example.com", status="pending")
        db.add(job)
        db.flush()
        
        page = Page(college_id=college.id, url="https://example.com/test", title="Test", raw_text="Content", content_hash="abc")
        db.add(page)
        db.flush()
        
        # Test each table
        tables_to_test = [
            (NavigationItem, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test", "label": "Nav", "url": "https://example.com/test",
                "nav_type": "main", "level": 0, "position": 0
            }),
            (StructuredData, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test", "format": "json-ld", "data": {}
            }),
            (ExtractedTable, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test", "table_number": 1, "headers": [], "rows": [], "row_count": 0
            }),
            (FAQ, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test", "question": "Q?", "answer": "A", "position": 0
            }),
            (Link, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test", "href": "https://example.com/test", "link_type": "internal"
            }),
            (Contact, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test", "contact_type": "email", "contact_value": "test@example.com"
            }),
            (Document, {
                "college_id": college.id, "job_id": job.id, "page_id": page.id,
                "source_url": "https://example.com/test.pdf", "object_key": "test.pdf", "file_type": "pdf", "file_size_bytes": 1000
            }),
        ]
        
        for model_class, data in tables_to_test:
            obj = model_class(**data)
            db.add(obj)
            db.flush()
            assert obj.college_id == college.id
            assert obj.job_id == job.id
            assert obj.page_id == page.id
            assert obj.source_url.startswith("https://example.com")
            db.delete(obj)
        
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
