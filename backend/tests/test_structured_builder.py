"""Test structured data builder from extracted data"""
import pytest
from app.db import SessionLocal
from app.models import College, CrawlJob, Page, ExtractedTable, PageSection, Program, Fee, Faculty, Department, Fact
from app.structured_builder import build_from_table, build_from_sections
from sqlalchemy import select


def test_build_from_table_programs():
    """Test building programs from table data"""
    db = SessionLocal()
    try:
        college = College(name="Test College", code="TEST", website="https://example.com")
        db.add(college)
        db.flush()
        
        page = Page(college_id=college.id, url="https://example.com/test", title="Test", raw_text="Content", content_hash="abc")
        db.add(page)
        db.flush()
        
        table = ExtractedTable(
            college_id=college.id,
            page_id=page.id,
            source_url="https://example.com/test",
            table_number=1,
            headers=["Program Name", "Duration", "Fee"],
            rows=[["B.Tech", "4 Years", "100000"], ["M.Tech", "2 Years", "150000"]],
            row_count=2
        )
        db.add(table)
        db.flush()
        
        build_from_table(db, college.id, page.id, table)
        
        # Check that program was created
        programs = db.scalars(select(Program).where(Program.college_id == college.id, Program.source_page_id == page.id)).all()
        assert len(programs) == 2
        
        db.rollback()
    finally:
        db.close()


def test_build_from_sections_fees():
    """Test building fees from section headings"""
    db = SessionLocal()
    try:
        college = College(name="Test College", code="TEST", website="https://example.com")
        db.add(college)
        db.flush()
        
        page = Page(college_id=college.id, url="https://example.com/test", title="Test", raw_text="Content", content_hash="abc")
        db.add(page)
        db.flush()
        
        sections = [
            PageSection(college_id=college.id, page_id=page.id, source_url="https://example.com/test", heading_level=2, heading_text="Tuition Fees", section_text="B.Tech: 100000", position=0)
        ]
        db.add_all(sections)
        db.flush()
        
        build_from_sections(db, college.id, page.id, sections)
        
        # Check that fee was created
        fees = db.scalars(select(Fee).where(Fee.college_id == college.id, Fee.source_page_id == page.id)).all()
        assert len(fees) == 1
        
        db.rollback()
    finally:
        db.close()


def test_unknown_table_goes_to_other_facts():
    """Test that unknown table types go to other_facts"""
    db = SessionLocal()
    try:
        college = College(name="Test College", code="TEST", website="https://example.com")
        db.add(college)
        db.flush()
        
        page = Page(college_id=college.id, url="https://example.com/test", title="Test", raw_text="Content", content_hash="abc")
        db.add(page)
        db.flush()
        
        table = ExtractedTable(
            college_id=college.id,
            page_id=page.id,
            source_url="https://example.com/test",
            table_number=1,
            headers=["Unknown Column", "Data"],
            rows=[["Item 1", "Value 1"]],
            row_count=1
        )
        db.add(table)
        db.flush()
        
        build_from_table(db, college.id, page.id, table)
        
        # Check that it went to other_facts
        facts = db.scalars(select(Fact).where(Fact.college_id == college.id, Fact.source_page_id == page.id, Fact.category == "website table")).all()
        assert len(facts) == 1
        
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
