import uuid

from app.crawler import invalidate_college_answer_cache
from app.db import SessionLocal
from app.models import AnswerCache, College


def test_crawl_cache_invalidation_clears_old_answers_and_bumps_version():
    db = SessionLocal()
    college = College(
        name="Cache Test College",
        code=f"CACHE-{uuid.uuid4().hex[:12].upper()}",
    )
    try:
        db.add(college)
        db.flush()
        initial_version = college.data_version or 1
        db.add(AnswerCache(
            college_id=college.id,
            question_hash=uuid.uuid4().hex * 2,
            answer="old cached answer",
            data_version=initial_version,
        ))
        db.commit()

        invalidate_college_answer_cache(db, college)

        assert college.data_version == initial_version + 1
        assert db.query(AnswerCache).filter(
            AnswerCache.college_id == college.id
        ).count() == 0
    finally:
        db.delete(college)
        db.commit()
        db.close()
