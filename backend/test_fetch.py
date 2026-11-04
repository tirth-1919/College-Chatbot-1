"""Test fetcher on AIT site pages"""
import sys
import hashlib
import time
sys.path.insert(0, "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend")

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import urllib.parse
import json

def test_fetch(url):
    print(f"\n{'='*60}")
    print(f"Testing: {url}")
    print('='*60)

    api_responses = []
    excluded_hosts = {"googleapis.com", "gstatic.com", "iconify.design", "google-analytics.com", "googletagmanager.com", "google.com"}

    def handle_response(response):
        content_type = response.header_value("content-type") or ""
        resp_url = response.url
        p = urllib.parse.urlparse(resp_url)
        if "application/json" in content_type and not any(host in p.hostname for host in excluded_hosts):
            try:
                body = response.body()
                if len(body) > 50:
                    api_responses.append({
                        "url": resp_url,
                        "body": body
                    })
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, user_agent="Mozilla/5.0 (compatible; Crawler/1.0)")
        page = context.new_page()
        page.on("response", handle_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Scroll
            for i in range(3):
                scroll_y = int((i + 1) * 0.3 * page.evaluate("() => document.body.scrollHeight"))
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                time.sleep(0.5)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)

            # Expand accordions
            for summary in page.locator("summary").all():
                try:
                    summary.click(timeout=1000)
                except Exception:
                    pass
            for tab in page.locator("[role='tab'], .tab, .accordion-header").all():
                try:
                    tab.click(timeout=1000)
                except Exception:
                    pass

            html = page.content()
            text = page.inner_text("body")
            soup = BeautifulSoup(html, "html.parser")

            # Links
            links = [a.get("href") for a in soup.select("a[href]")]
            # Images
            images = [img.get("src") or img.get("data-src") for img in soup.select("img[src],img[data-src]")]
            # Headings
            headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

            print(f"Text length: {len(text)} characters")
            print(f"Links found: {len(links)}")
            print(f"Images found: {len(images)}")
            print(f"Headings found: {len(headings)}")
            print(f"API responses captured: {len(api_responses)}")
            for api in api_responses:
                print(f"  - {api['url']}")
            print(f"\nFirst 200 characters of text:")
            print(text[:200])
            print(f"\nHeadings:")
            for h in headings[:10]:
                print(f"  {h.name}: {h.get_text(' ', strip=True)[:80]}")

            return text, links, images, api_responses

        finally:
            browser.close()

if __name__ == "__main__":
    urls = [
        "https://www.aitindia.in/",
        "https://www.aitindia.in/departments/computer-eng",
        "https://www.aitindia.in/placement/cell"
    ]

    results = []
    for url in urls:
        text, links, images, api = test_fetch(url)
        results.append((text, links, images, api))

    # Verify texts differ
    print(f"\n{'='*60}")
    print("VERIFICATION: Texts must differ")
    print('='*60)
    hashes = [hashlib.sha256(t.encode()).hexdigest() for t, _, _, _ in results]
    print(f"Home page hash: {hashes[0][:16]}...")
    print(f"Computer eng hash: {hashes[1][:16]}...")
    print(f"Placement cell hash: {hashes[2][:16]}...")

    if len(set(hashes)) == 3:
        print("\nSUCCESS: All three pages have different content")
    else:
        print("\nFAILURE: Some pages have identical content")
        sys.exit(1)
