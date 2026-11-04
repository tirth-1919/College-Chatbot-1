"""Check crawl job status"""
import sys
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

from app.db import SessionLocal
from app.models import CrawlJob, CrawlFrontier
from sqlalchemy import select, func

db = SessionLocal()
try:
    job = db.scalar(select(CrawlJob).where(CrawlJob.id == 1))
    print(f"Job status: {job.status}")
    print(f"Pages done: {job.pages_done}")
    print(f"Pages failed: {job.pages_failed}")

    statuses = db.execute(select(CrawlFrontier.status, func.count(CrawlFrontier.id)).where(CrawlFrontier.job_id == 1).group_by(CrawlFrontier.status)).all()
    print("\nFrontier status:")
    for s, c in statuses:
        print(f"  {s}: {c}")
finally:
    db.close()
