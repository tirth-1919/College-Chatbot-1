"""Baseline schema matching current models.py."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # We'll use create_all since this is a fresh baseline
    # Import Base and models after op.get_bind() is available
    from app.db import Base
    from app import models

    # Enable pgvector extension for PostgreSQL
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Create all tables from models
    Base.metadata.create_all(bind=op.get_bind())

    # PostgreSQL-specific setup (row level security, indexes)
    if op.get_bind().dialect.name == "postgresql":
        tenant_tables = [
            "crawl_jobs", "crawl_schedules", "crawl_frontier", "crawled_pages",
            "page_chunks", "other_facts", "knowledge_catalog", "answer_cache",
            "other_facts_history", "custom_fields", "knowledge_gaps", "enquiries",
            "college_sources", "college_members", "college_invitations",
            "widget_requests", "media_assets"
        ]
        for table in tenant_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_guard ON {table} USING (current_setting('app.user_role', true) = 'super_admin' OR college_id::text = current_setting('app.tenant_id', true)) WITH CHECK (current_setting('app.user_role', true) = 'super_admin' OR college_id::text = current_setting('app.tenant_id', true))")

        op.execute("CREATE INDEX IF NOT EXISTS ix_other_facts_title_trgm ON other_facts USING gin (title gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_page_chunks_text_search ON page_chunks USING gin (to_tsvector('simple', chunk_text))")

        op.execute("ALTER TABLE question_log ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE question_log FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY question_guard ON question_log USING (current_setting('app.user_role', true) = 'super_admin' OR college_id::text = current_setting('app.tenant_id', true) OR (college_id IS NULL AND user_id::text = current_setting('app.user_id', true))) WITH CHECK (current_setting('app.user_role', true) = 'super_admin' OR college_id::text = current_setting('app.tenant_id', true) OR (college_id IS NULL AND user_id::text = current_setting('app.user_id', true)))")

        op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE conversations FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY owner_guard ON conversations USING (current_setting('app.user_role', true) = 'super_admin' OR user_id::text = current_setting('app.user_id', true)) WITH CHECK (current_setting('app.user_role', true) = 'super_admin' OR user_id::text = current_setting('app.user_id', true)))")

        op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE messages FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY owner_guard ON messages USING (current_setting('app.user_role', true) = 'super_admin' OR conversation_id IN (SELECT id FROM conversations WHERE user_id::text = current_setting('app.user_id', true))) WITH CHECK (current_setting('app.user_role', true) = 'super_admin' OR conversation_id IN (SELECT id FROM conversations WHERE user_id::text = current_setting('app.user_id', true)))")


def downgrade():
    from app.db import Base

    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS owner_guard ON messages")
        op.execute("ALTER TABLE messages DISABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS owner_guard ON conversations")
        op.execute("ALTER TABLE conversations DISABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS question_guard ON question_log")
        op.execute("ALTER TABLE question_log DISABLE ROW LEVEL SECURITY")

        for table in [
            "crawl_jobs", "crawl_schedules", "crawl_frontier", "crawled_pages",
            "page_chunks", "other_facts", "knowledge_catalog", "answer_cache",
            "other_facts_history", "custom_fields", "knowledge_gaps", "enquiries",
            "college_sources", "college_members", "college_invitations",
            "widget_requests", "media_assets"
        ]:
            op.execute(f"DROP POLICY IF EXISTS tenant_guard ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    Base.metadata.drop_all(bind=op.get_bind())
