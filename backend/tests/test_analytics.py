"""Test Stage 2 analytics endpoints."""
import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from app.db import SessionLocal, set_tenant_scope
from app.models import User, College, QuestionLog, KnowledgeGap
from app.security import hash_password


def test_knowledge_gap_prioritization():
    db = SessionLocal()
    try:
        c = College(name="Test College", code="TEST", status="approved")
        db.add(c); db.flush()
        u = User(name="Admin", email="admin@test.com", password_hash=hash_password("password"), role="college_admin", college_id=c.id, email_verified=True)
        db.add(u); db.flush()
        set_tenant_scope(db, c.id, "college_admin", u.id)
        
        week_ago = datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(days=7)
        week_start = week_ago.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        
        gap1 = KnowledgeGap(college_id=c.id, question="old question", count=2, status="open")
        gap1.created_at = week_start - timedelta(days=10)
        db.add(gap1)
        
        gap2 = KnowledgeGap(college_id=c.id, question="new popular question", count=10, status="open")
        gap2.created_at = week_start + timedelta(hours=1)
        db.add(gap2)
        
        gap3 = KnowledgeGap(college_id=c.id, question="recent question", count=3, status="open")
        gap3.created_at = week_start + timedelta(hours=5)
        db.add(gap3)
        
        db.commit()
        
        from app.main import gaps
        result = gaps(db, u)
        
        assert len(result) == 3
        assert result[0]["priority"] == "high"
        assert result[0]["question"] == "new popular question"
        assert result[1]["priority"] in ("high", "medium")
    finally:
        db.rollback()
        db.query(KnowledgeGap).delete()
        db.query(User).delete()
        db.query(College).delete()
        db.commit()
        db.close()
