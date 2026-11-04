"""Check that all models used in crawler.py exist in app.models"""
import sys
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

from app import models

required_models = [
    "CrawlJob",
    "College",
    "CrawlFrontier",
    "CrawlUrl",
    "Page",
    "PageHistory",
    "PageSection",
    "NavigationItem",
    "StructuredData",
    "ExtractedTable",
    "FAQ",
    "Contact",
    "Link",
    "MediaAsset",
    "Document",
    "Fact",
    "FactHistory",
]

missing = []
for model_name in required_models:
    if not hasattr(models, model_name):
        missing.append(model_name)

if missing:
    print("MISSING:")
    for m in missing:
        print(f"  {m}")
else:
    print("MISSING:")
    print("  (empty list)")
