"""Test that all data tables (except users/colleges) have college_id for tenant isolation"""
import pytest
from sqlalchemy import inspect
from app.db import engine, SessionLocal
from app.config import settings


def test_all_data_tables_have_college_id():
    """Verify that every table except specific system tables has college_id column"""
    tables_without_college_id_allowed = {
        "alembic_version",  # Migration metadata
        "colleges",  # Tenant table itself
        "one_time_codes",  # Auth codes cross-tenant
    }

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    missing_college_id = []
    for table in tables:
        if table in tables_without_college_id_allowed:
            continue
        columns = [col["name"] for col in inspector.get_columns(table)]
        if "college_id" not in columns:
            missing_college_id.append(table)

    if missing_college_id:
        pytest.fail(f"Tables missing college_id column: {missing_college_id}")


def test_postgresql_vector_extensions():
    """Test that PostgreSQL has pgvector and pg_trgm extensions if using PostgreSQL"""
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Not using PostgreSQL")

    db = SessionLocal()
    try:
        result = db.execute("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
        extensions = {row[0] for row in result}
        assert "vector" in extensions, "pgvector extension not installed"
        assert "pg_trgm" in extensions, "pg_trgm extension not installed"
    finally:
        db.close()


def test_required_tables_exist():
    """Test that all required tables exist"""
    required_tables = {
        "crawl_urls", "media_assets", "other_facts", "knowledge_catalog",
        "aliases", "page_chunks", "other_facts_history"
    }

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    missing = required_tables - tables
    if missing:
        pytest.fail(f"Required tables missing: {missing}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
