"""Check AIT site with Playwright to understand rendering behavior"""
from playwright.sync_api import sync_playwright
import time

def check_ait_site():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # Track network responses with JSON content type
        json_responses = []

        def handle_response(response):
            content_type = response.header_value("content-type") or ""
            if "application/json" in content_type:
                try:
                    json_responses.append({
                        "url": response.url,
                        "size": len(response.body())
                    })
                except Exception:
                    pass

        page.on("response", handle_response)

        print("Loading https://www.aitindia.in/ ...")
        page.goto("https://www.aitindia.in/", wait_until="networkidle", timeout=30000)

        # Extra wait for lazy loading
        print("Waiting 5 seconds for lazy loading...")
        time.sleep(5)

        # Scroll to bottom to trigger lazy loading
        print("Scrolling to bottom...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        # Check sitemap.xml
        print("\nChecking /sitemap.xml ...")
        try:
            sitemap_page = context.new_page()
            sitemap_response = sitemap_page.goto("https://www.aitindia.in/sitemap.xml", timeout=10000)
            sitemap_status = sitemap_response.status if sitemap_response else 0
            sitemap_page.close()
        except Exception as e:
            sitemap_status = f"Error: {e}"

        # Get rendered content
        text = page.inner_text("body")
        html = page.content()

        # Extract navigation links
        nav_links = []
        for selector in ["nav a", "header a"]:
            for link in page.locator(selector).all():
                href = link.get_attribute("href")
                text_content = link.inner_text()
                if href and text_content:
                    nav_links.append({
                        "text": text_content.strip()[:100],
                        "href": href
                    })
                    if len(nav_links) >= 40:
                        break
            if len(nav_links) >= 40:
                break

        # Print results
        print("\n" + "="*60)
        print("SITE CHECK RESULTS")
        print("="*60)
        print(f"Rendered text length: {len(text)} characters")
        print(f"Link count: {len(page.locator('a').all())}")
        print(f"Image count: {len(page.locator('img').all())}")
        print(f"\nFirst 500 characters of text:")
        print(text[:500])
        print(f"\nNavigation links (up to 40):")
        for i, link in enumerate(nav_links, 1):
            print(f"  {i}. {link['text'][:60]} -> {link['href']}")
        print(f"\nSitemap.xml status: {sitemap_status}")
        print(f"\nJSON network responses during page load:")
        if json_responses:
            for resp in json_responses:
                print(f"  - {resp['url']} ({resp['size']} bytes)")
        else:
            print("  (none)")
        print("="*60)

        browser.close()

if __name__ == "__main__":
    check_ait_site()
