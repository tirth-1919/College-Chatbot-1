"""Check that app.worker and app.crawler can be imported"""
import sys
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

try:
    from app import worker
    print("app.worker imported ok")
except Exception as e:
    print(f"app.worker import failed: {e}")
    sys.exit(1)

try:
    from app import crawler
    print("app.crawler imported ok")
except Exception as e:
    print(f"app.crawler import failed: {e}")
    sys.exit(1)

print("imports ok")
