"""Check failed crawl URL"""
import sys
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

from app.db import SessionLocal
from app.models import CrawlFrontier, CrawlUrl
from sqlalchemy import select

db = SessionLocal()
try:
    failed = db.scalar(select(CrawlFrontier).where(CrawlFrontier.job_id == 1, CrawlFrontier.status == "failed"))
    if failed:
        print(f"Failed URL: {failed.url}")
        print(f"Status reason: {failed.status_reason}")
        print(f"Attempts: {failed.attempts}")

    failed_url = db.scalar(select(CrawlUrl).where(CrawlUrl.job_id == 1, CrawlUrl.status == "failed"))
    if failed_url:
        print(f"\nCrawlUrl failed: {failed_url.url}")
        print(f"Failure reason: {failed_url.status_reason}")
finally:
    db.close()
