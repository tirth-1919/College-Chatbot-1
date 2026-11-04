from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Integer, Float, JSON, UniqueConstraint, func, event, insert, update, delete
import re
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from .db import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", "role", name="uq_users_email_role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    login_version: Mapped[int] = mapped_column(Integer, default=1)
    locked_until: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class OneTimeCode(Base):
    __tablename__ = "one_time_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)

# Alias for compatibility with existing code
EmailVerification = OneTimeCode

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    device: Mapped[str] = mapped_column(String(240), default="")
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

# Alias for compatibility with existing code
SessionToken = UserSession

class College(Base):
    __tablename__ = "colleges"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    website: Mapped[str] = mapped_column(String(500), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str] = mapped_column(String(100), default="India")
    affiliation: Mapped[str] = mapped_column(String(240), default="")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    highlights: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="approved", index=True)
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    widget_key: Mapped[str] = mapped_column(String(64), default="")
    allowed_domains: Mapped[list] = mapped_column(JSON, default=list)
    quotas: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_flags: Mapped[dict] = mapped_column(JSON, default=dict)

class CollegeSource(Base):
    __tablename__ = "college_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(40), default="main site")
    priority: Mapped[int] = mapped_column(Integer, default=1)
    campus: Mapped[str] = mapped_column(String(180), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class MediaAsset(Base):
    __tablename__ = "media_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int | None] = mapped_column(ForeignKey("crawled_pages.id"))
    source_url: Mapped[str] = mapped_column(String(1000))
    object_key: Mapped[str] = mapped_column(String(1000), default="")
    alt_text: Mapped[str] = mapped_column(String(500), default="")
    thumbnail_key: Mapped[str] = mapped_column(String(1000), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(50))
    source_page: Mapped[str | None] = mapped_column(String(1000))
    is_lazy_loaded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Registration(Base):
    __tablename__ = "college_registrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    code: Mapped[str] = mapped_column(String(48), default="")
    website: Mapped[str] = mapped_column(String(500))
    email: Mapped[str] = mapped_column(String(320))
    contact_name: Mapped[str] = mapped_column(String(160))
    contact_email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(120))
    affiliation: Mapped[str] = mapped_column(String(240), default="")
    country: Mapped[str] = mapped_column(String(100), default="India")
    designation: Mapped[str] = mapped_column(String(120), default="")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    verification_document: Mapped[str] = mapped_column(String(1000), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    highlights: Mapped[str] = mapped_column(Text, default="")
    verification_token: Mapped[str] = mapped_column(String(64), default="")
    verification_file_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

# Alias for compatibility with existing code
CollegeRegistration = Registration

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    title: Mapped[str] = mapped_column(String(240), default="New chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    last_entity: Mapped[str] = mapped_column(String(240), default="")
    last_table: Mapped[str] = mapped_column(String(80), default="")
    last_year: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    source_badge: Mapped[str] = mapped_column(String(48), default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    target_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    pages_found: Mapped[int] = mapped_column(Integer, default=0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    max_depth: Mapped[int] = mapped_column(Integer, default=10)
    time_budget_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=2048)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    stopped_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sitemap_urls: Mapped[int] = mapped_column(Integer, default=0)
    failed_urls: Mapped[int] = mapped_column(Integer, default=0)
    skipped_urls: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_urls: Mapped[int] = mapped_column(Integer, default=0)
    blocked_urls: Mapped[int] = mapped_column(Integer, default=0)
    robots_blocked_urls: Mapped[int] = mapped_column(Integer, default=0)
    out_of_domain_urls: Mapped[int] = mapped_column(Integer, default=0)
    images_found: Mapped[int] = mapped_column(Integer, default=0)
    images_stored: Mapped[int] = mapped_column(Integer, default=0)
    documents_found: Mapped[int] = mapped_column(Integer, default=0)
    documents_parsed: Mapped[int] = mapped_column(Integer, default=0)
    tables_found: Mapped[int] = mapped_column(Integer, default=0)
    faqs_found: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str] = mapped_column(Text, default="")
    coverage_report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CrawlSchedule(Base):
    __tablename__ = "crawl_schedules"
    __table_args__ = (UniqueConstraint("college_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    interval_days: Mapped[int] = mapped_column(Integer, default=7)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    next_run_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

class CrawlFrontier(Base):
    __tablename__ = "crawl_frontier"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id"), index=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    depth: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    status_reason: Mapped[str] = mapped_column(String(200), default="")
    parent_url: Mapped[str | None] = mapped_column(String(1000))
    discovered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    queued_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Page(Base):
    __tablename__ = "crawled_pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    url: Mapped[str] = mapped_column(String(1000), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    final_url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500), default="")
    raw_text: Mapped[str] = mapped_column(Text)
    raw_html: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(10))
    screenshot_key: Mapped[str | None] = mapped_column(String(1000))
    meta_description: Mapped[str | None] = mapped_column(String(500))
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    breadcrumbs: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_version_id: Mapped[int | None] = mapped_column(Integer)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    has_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    indexed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PageHistory(Base):
    __tablename__ = "page_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(Integer, index=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_html: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    changed_via: Mapped[str] = mapped_column(String(32), default="crawl")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PageChunk(Base):
    __tablename__ = "page_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id",ondelete="CASCADE"), index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768).with_variant(JSON(),"sqlite"))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Fact(Base):
    __tablename__ = "other_facts"
    __table_args__ = (UniqueConstraint("college_id", "category", "title", "source_page_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    value: Mapped[str] = mapped_column(Text)
    source_page_id: Mapped[int | None] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class KnowledgeCatalog(Base):
    __tablename__ = "knowledge_catalog"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("other_facts.id", ondelete="CASCADE"), unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    canonical_name: Mapped[str] = mapped_column(String(300), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    searchable_text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class FactHistory(Base):
    __tablename__ = "other_facts_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    fact_id: Mapped[int] = mapped_column(Integer, index=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    category: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    value: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_via: Mapped[str] = mapped_column(String(32), default="admin")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PageSection(Base):
    __tablename__ = "page_sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    heading_level: Mapped[int] = mapped_column(Integer)
    heading_text: Mapped[str] = mapped_column(String(500))
    section_text: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class NavigationItem(Base):
    __tablename__ = "navigation_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    label: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("navigation_items.id"))
    level: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer)
    nav_type: Mapped[str] = mapped_column(String(50), default="main")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class StructuredData(Base):
    __tablename__ = "structured_data"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    format: Mapped[str] = mapped_column(String(50))
    schema_type: Mapped[str | None] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ExtractedTable(Base):
    __tablename__ = "extracted_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    table_number: Mapped[int] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(String(500))
    headers: Mapped[list] = mapped_column(JSON)
    rows: Mapped[list] = mapped_column(JSON)
    row_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class FAQ(Base):
    __tablename__ = "faqs"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Link(Base):
    __tablename__ = "links"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    href: Mapped[str] = mapped_column(String(1000))
    anchor_text: Mapped[str | None] = mapped_column(String(500))
    link_type: Mapped[str] = mapped_column(String(50), default="internal")
    is_nofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int | None] = mapped_column(ForeignKey("crawled_pages.id"))
    source_url: Mapped[str] = mapped_column(String(1000))
    object_key: Mapped[str] = mapped_column(String(1000))
    file_type: Mapped[str] = mapped_column(String(50))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    contact_type: Mapped[str] = mapped_column(String(50))
    contact_value: Mapped[str] = mapped_column(String(500))
    label: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Program(Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Fee(Base):
    __tablename__ = "fees"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Faculty(Base):
    __tablename__ = "faculty"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Hostel(Base):
    __tablename__ = "hostel"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Placement(Base):
    __tablename__ = "placements"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Scholarship(Base):
    __tablename__ = "scholarships"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Library(Base):
    __tablename__ = "library"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_sections: Mapped[list] = mapped_column(JSON, default=list)
    admin_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class QuestionLog(Base):
    __tablename__ = "question_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    raw_question: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(80), default="")
    answer_found: Mapped[bool] = mapped_column(Boolean, default=False)
    response_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CrawlUrl(Base):
    __tablename__ = "crawl_urls"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    status_reason: Mapped[str | None] = mapped_column(String(200))
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    discovered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    queued_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Alias(Base):
    __tablename__ = "aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("other_facts.id"), index=True)
    alias: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AnswerCache(Base):
    __tablename__ = "answer_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id", ondelete="CASCADE"), index=True)
    question_hash: Mapped[str] = mapped_column(String(64), index=True)
    answer: Mapped[str] = mapped_column(Text)
    source_badge: Mapped[str] = mapped_column(String(48), default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    data_version: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CollegeMember(Base):
    __tablename__ = "college_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="viewer")

class CollegeInvitation(Base):
    __tablename__ = "college_invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(24), default="editor")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)

class WidgetRequest(Base):
    __tablename__ = "widget_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    domain: Mapped[str] = mapped_column(String(500))
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CustomField(Base):
    __tablename__ = "custom_fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    table_name: Mapped[str] = mapped_column(String(80))
    field_name: Mapped[str] = mapped_column(String(80))
    field_type: Mapped[str] = mapped_column(String(24), default="text")

class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="open")
    priority_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(200))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Enquiry(Base):
    __tablename__ = "enquiries"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text, default="")
    target: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    email_sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

class CollegeDocument(Base):
    __tablename__ = "college_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(50))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(String(1000))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    rows_created: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class DocumentStagedRow(Base):
    __tablename__ = "document_staged_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_document_id: Mapped[int] = mapped_column(ForeignKey("college_documents.id"), index=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    target_table: Mapped[str] = mapped_column(String(80))
    target_column: Mapped[str | None] = mapped_column(String(80))
    page_number: Mapped[int | None] = mapped_column(Integer)
    snippet: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    row_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class DocumentStagedChange(Base):
    __tablename__ = "document_staged_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_document_id: Mapped[int] = mapped_column(ForeignKey("college_documents.id"), index=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    change_type: Mapped[str] = mapped_column(String(32))
    table_name: Mapped[str | None] = mapped_column(String(80))
    column_name: Mapped[str | None] = mapped_column(String(80))
    column_type: Mapped[str | None] = mapped_column(String(24))
    proposed_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CustomTable(Base):
    __tablename__ = "custom_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    table_slug: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)
    schema: Mapped[dict] = mapped_column(JSON, default=dict)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CustomTableRow(Base):
    __tablename__ = "custom_table_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    custom_table_id: Mapped[int] = mapped_column(ForeignKey("custom_tables.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("college_documents.id"))
    row_data: Mapped[dict] = mapped_column(JSON, default=dict)
    page_number: Mapped[int | None] = mapped_column(Integer)
    snippet: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

def _catalog_aliases(name):
    words=re.findall(r"[A-Za-z0-9]+",name or "")
    vals={name.lower(),"".join(words).lower()," ".join(words).lower()} if name else set()
    if words:
        vals.add("".join(word[0] for word in words).lower())
        vals.add(".".join(word[0] for word in words).lower()+".")
        if len(words[-1])>1: vals.add(" ".join(words[:-1]+[words[-1][:-1]]).lower())
        vals.add(" ".join(words[:-1]+[words[-1]+"s"]).lower())
    return sorted(v for v in vals if v)

def _catalog_values(fact):
    return {"college_id":fact.college_id,"fact_id":fact.id,"entity_type":fact.category,"canonical_name":fact.title,"aliases":_catalog_aliases(fact.title),"searchable_text":" ".join([fact.category or "",fact.title or "",fact.value or "",str(fact.extra or {})])}

@event.listens_for(Fact,"after_insert")
def _catalog_insert(mapper,connection,fact):
    connection.execute(insert(KnowledgeCatalog).values(**_catalog_values(fact)))

@event.listens_for(Fact,"after_update")
def _catalog_update(mapper,connection,fact):
    values=_catalog_values(fact); values.pop("fact_id")
    connection.execute(update(KnowledgeCatalog).where(KnowledgeCatalog.fact_id==fact.id).values(**values))

@event.listens_for(Fact,"after_delete")
def _catalog_delete(mapper,connection,fact):
    connection.execute(delete(KnowledgeCatalog).where(KnowledgeCatalog.fact_id==fact.id))
