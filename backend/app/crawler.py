"""Crawler with Playwright and local file storage for media/documents"""
import hashlib, io, logging, os, re, socket, urllib.parse, ipaddress, json, urllib.request, urllib.robotparser
from datetime import datetime, timedelta, timezone
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, func, update
from app.db import SessionLocal
from app.models import (
    CrawlJob, College, CrawlFrontier, CrawlUrl, Page, PageHistory, AnswerCache,
    PageSection, NavigationItem, StructuredData, ExtractedTable,
    FAQ, Contact, Link, MediaAsset, Document, Fact, FactHistory
)
from app.config import settings
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)
MAX_CRAWL_RESOURCE_BYTES = 20 * 1024 * 1024


def crawl_college(college_id: int, url: str) -> int:
    """Create and enqueue a crawl for an approved tenant, preserving failed dispatches."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A valid HTTP(S) crawl URL is required")

    db = SessionLocal()
    try:
        college = db.scalar(select(College).where(College.id == college_id))
        if not college:
            raise ValueError("College not found")
        if college.status != "approved":
            raise ValueError("Only approved colleges can be crawled")

        active_job = db.scalar(select(CrawlJob).where(
            CrawlJob.college_id == college_id,
            CrawlJob.url == url,
            CrawlJob.status.in_(("queued", "running")),
        ))
        if active_job:
            if active_job.status == "running":
                raise ValueError(f"A crawl for this URL is already running (job {active_job.id})")
            created_at = active_job.created_at
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            is_stale = (
                created_at is not None
                and datetime.now(timezone.utc) - created_at > timedelta(minutes=5)
                and active_job.started_at is None
                and (active_job.pages_done or 0) == 0
            )
            if not is_stale:
                raise ValueError(f"A crawl for this URL is already queued (job {active_job.id})")
            active_job.status = "failed"
            active_job.finished_at = datetime.now(timezone.utc)
            active_job.error_log = ((active_job.error_log or "") + "Queued job was not dispatched; superseded by a fresh crawl.\n")[-20000:]
            db.commit()

        job = CrawlJob(
            college_id=college_id,
            url=url,
            target_url=url,
            status="queued",
            version=(college.data_version or 0) + 1,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        try:
            from .worker import crawl_task
            crawl_task.delay(job_id)
        except Exception as error:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error_log = f"Task dispatch failed: {type(error).__name__}: {error}"[:20000]
            db.commit()
            raise RuntimeError(f"Crawl job {job_id} was recorded as failed because the worker queue is unavailable") from error
        return job_id
    finally:
        db.close()


def invalidate_college_answer_cache(db, college):
    db.query(AnswerCache).filter(AnswerCache.college_id == college.id).delete(
        synchronize_session=False
    )
    college.data_version = (college.data_version or 0) + 1
    db.commit()


def extract_urls_from_json(value):
    """Return supported file URLs embedded anywhere in JSON data."""
    extensions = {".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
    urls = []
    if isinstance(value, dict):
        for child in value.values():
            urls.extend(extract_urls_from_json(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(extract_urls_from_json(child))
    elif isinstance(value, str):
        path = urllib.parse.urlparse(value).path.lower()
        if os.path.splitext(path)[1] in extensions:
            urls.append(value)
    return urls


def file_extension(url: str) -> str:
    return os.path.splitext(urllib.parse.urlparse(url).path.lower())[1]


def parse_sitemap(content: bytes) -> tuple[bool, list[str]]:
    """Parse sitemap or sitemap-index XML and return its locations."""
    soup = BeautifulSoup(content, "xml")
    root = soup.find(["sitemapindex", "urlset"])
    if root is None:
        return False, []
    is_index = root.name == "sitemapindex"
    tag_name = "sitemap" if is_index else "url"
    locations = []
    for entry in root.find_all(tag_name, recursive=False):
        loc = entry.find("loc", recursive=False)
        if loc and loc.get_text(strip=True):
            locations.append(loc.get_text(strip=True))
    return is_index, locations


def fetch_bounded(client: httpx.Client, url: str, max_bytes: int | None = None):
    """Fetch one resource while enforcing a strict streamed response size limit."""
    limit = MAX_CRAWL_RESOURCE_BYTES if max_bytes is None else max_bytes
    response = client.get(url, follow_redirects=False)
    if response.is_redirect:
        response.close()
        raise ValueError("Redirects must be validated before following")
    body = bytearray()
    try:
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > limit:
                raise ValueError("Response exceeds the 20 MiB limit")
        status = response.status_code
        host = urllib.parse.urlparse(str(response.url)).hostname or ""
        headers = response.headers
        return status, host, headers, bytes(body)
    finally:
        response.close()


def safe_url(url: str, root_host: str, allowed_hosts=None):
    """Allow public HTTP(S) URLs on the college host or explicitly trusted API hosts."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    normalize_host = lambda value: value.lower().removeprefix("www.").rstrip(".")
    permitted = {normalize_host(root_host)}
    permitted.update(normalize_host(host) for host in (allowed_hosts or set()) if host)
    if normalize_host(parsed.hostname) not in permitted:
        return False
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, ValueError) as error:
        logger.warning("URL safety check failed for %s: %s: %s", url, type(error).__name__, error)
        return False


class _CheckedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, root_host, allowed_hosts):
        super().__init__()
        self.root_host = root_host
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, request, response, code, message, headers, new_url):
        if not safe_url(new_url, self.root_host, self.allowed_hosts):
            raise ValueError(f"Unsafe redirect to {new_url}")
        return super().redirect_request(request, response, code, message, headers, new_url)


def download_checked_file(url: str, root_host: str, allowed_hosts=None, max_bytes=8 * 1024 * 1024):
    """Download a supported public file with redirect, size, and content-type checks."""
    extension = file_extension(url)
    expected = {
        ".pdf": {"application/pdf", "application/x-pdf"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".gif": {"image/gif"}, ".webp": {"image/webp"},
    }
    if extension not in expected or not safe_url(url, root_host, allowed_hosts):
        raise ValueError(f"Unsupported or unsafe file URL: {url}")
    opener = urllib.request.build_opener(_CheckedRedirectHandler(root_host, allowed_hosts or set()))
    request = urllib.request.Request(url, headers={"User-Agent": "AI-FAQ-Crawler/1.0"})
    with opener.open(request, timeout=20) as response:
        if not safe_url(response.geturl(), root_host, allowed_hosts):
            raise ValueError(f"Unsafe final file URL: {response.geturl()}")
        content_type = response.headers.get_content_type().lower()
        if content_type not in expected[extension]:
            raise ValueError(f"Unexpected content type {content_type} for {url}")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"File exceeds {max_bytes} byte limit: {url}")
        return data, extension[1:]


def strip_hidden_content(soup: BeautifulSoup):
    """Remove hidden/ignored tags and styles before extraction."""
    hidden_classes = {"hidden", "d-none", "sr-only", "visually-hidden", "ad", "advertisement", "sidebar"}
    for tag in soup.find_all(True):
        if getattr(tag, "attrs", None) is None:
            continue
        style = re.sub(r"\s+", "", tag.get("style", "").lower())
        classes = set(tag.get("class", []))
        hidden = (
            tag.has_attr("hidden")
            or tag.get("aria-hidden", "").lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
            or "opacity:0" in style
            or bool(classes & hidden_classes)
            or bool(re.search(r"(?:^|;)display:none(?:;|$)|(?:^|;)visibility:hidden(?:;|$)|(?:^|;)opacity:0(?:;|$)", style))
        )
        if hidden:
            tag.decompose()
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()


def extract_html_tables(soup: BeautifulSoup, page_title: str) -> list[dict[str, str]]:
    """Convert rendered HTML tables to generic facts without assuming college categories."""
    extracted: list[dict[str, str]] = []
    for table_number, table in enumerate(soup.find_all("table"), start=1):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        caption = table.find("caption")
        category_suffix = (caption.get_text(" ", strip=True) if caption else "") or page_title or f"table {table_number}"
        category = f"website table {table_number}: {category_suffix}"[:100]
        explicit_header = table.select_one("thead tr")
        first_row = explicit_header or rows[0]
        header_cells = first_row.find_all(["th", "td"], recursive=False)
        headers = [cell.get_text(" ", strip=True) for cell in header_cells]
        if not headers or all(not h for h in headers):
            continue
        title_counts: dict[str, int] = {}
        data_rows = rows[1:]
        for row_number, row in enumerate(data_rows, start=1):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) == len(headers):
                values = [cell.get_text(" ", strip=True) for cell in cells]
                if not any(values):
                    continue
                label = values[0] or f"Row {row_number}"
                title_counts[label] = title_counts.get(label, 0) + 1
                title = label if title_counts[label] == 1 else f"{label} · row {row_number}"
                value = " | ".join(f"{header}: {cell}" for header, cell in zip(headers, values) if header or cell)
                extracted.append({"category": category, "title": title, "value": value})
    return extracted


def extract_html_structured_facts(soup: BeautifulSoup, page_title: str) -> list[dict[str, str]]:
    """Extract labeled values from definition lists without inventing a schema."""
    facts: list[dict[str, str]] = []
    for list_number, definition_list in enumerate(soup.find_all("dl"), start=1):
        category = f"website definition list {list_number}: {page_title}"[:100]
        current_label = ""
        for item in definition_list.find_all(["dt", "dd"], recursive=False):
            value = item.get_text(" ", strip=True)
            if item.name == "dt":
                current_label = value
            elif current_label and value:
                facts.append({"category": category, "title": current_label[:300], "value": value[:50000]})
                current_label = ""
    return facts


def extract_page_sections(soup: BeautifulSoup, page_id: int, source_url: str) -> list[dict]:
    """Extract h1-h6 heading sections with text content."""
    sections = []
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    for i, heading in enumerate(heading_tags):
        level = int(heading.name[1])
        heading_text = heading.get_text(" ", strip=True)
        content_parts = []
        sibling = heading.next_sibling
        while sibling:
            if sibling.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                break
            if sibling.name:
                content_parts.append(sibling.get_text(" ", strip=True))
            sibling = sibling.next_sibling
        sections.append({
            "heading_text": heading_text,
            "heading_level": level,
            "section_text": " ".join(content_parts)
        })
    return sections


def extract_navigation(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Extract navigation from main menu, footer, sidebar."""
    nav_items = []
    nav_selectors = ["nav", "footer", ".menu", ".sidebar", ".navigation"]
    for selector in nav_selectors:
        for nav in soup.select(selector):
            for link in nav.find_all("a", href=True):
                href = link.get("href")
                if href:
                    nav_items.append({
                        "label": link.get_text(" ", strip=True),
                        "url": urllib.parse.urljoin(source_url, href),
                        "parent": nav.get("id", "") or nav.get("class", [""])[0]
                    })
    return nav_items


def extract_structured_data(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Extract JSON-LD, Open Graph, Twitter Card."""
    structured = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
            data_items = data if isinstance(data, list) else [data]
            for item in data_items:
                if isinstance(item, dict):
                    structured.append({"format": "json-ld", "schema_type": str(item.get("@type", "")), "data": item})
        except Exception as error:
            logger.warning("JSON-LD parse failed for %s: %s: %s", source_url, type(error).__name__, error)
    for meta in soup.find_all("meta", property=True):
        if meta.get("property", "").startswith(("og:", "twitter:")):
            structured.append({"format": "meta", "schema_type": meta.get("property", ""), "data": {meta.get("property", ""): meta.get("content", "")}})
    return structured


def extract_tables(soup: BeautifulSoup, page_id: int, source_url: str) -> list[dict]:
    """Extract HTML tables with headers and rows."""
    tables = []
    for table_number, table in enumerate(soup.find_all("table"), start=1):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_row = rows[0]
        headers = [cell.get_text(" ", strip=True) for cell in header_row.find_all(["th", "td"])]
        data_rows = []
        for row in rows[1:]:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if cells:
                data_rows.append(cells)
        if headers and data_rows:
            caption = table.find("caption")
            tables.append({
                "table_number": table_number,
                "caption": caption.get_text(" ", strip=True)[:500] if caption else None,
                "headers": headers,
                "rows": data_rows,
            })
    return tables


def extract_faqs(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Extract FAQ accordions."""
    faqs = []
    for accordion in soup.select("details, .accordion, .faq-item"):
        question = accordion.select_one("summary, h3, h4, .question")
        answer = accordion.select_one("p, .answer, .content")
        if question and answer:
            faqs.append({"question": question.get_text(" ", strip=True), "answer": answer.get_text(" ", strip=True)})
    return faqs


def extract_contacts(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Extract emails, phones, addresses, social links."""
    contacts = []
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    for email in email_pattern.finditer(soup.get_text()):
        contacts.append({"contact_type": "email", "contact_value": email.group(), "label": ""})
    phone_pattern = re.compile(r'\+?\d{10,15}')
    for phone in phone_pattern.finditer(soup.get_text()):
        contacts.append({"contact_type": "phone", "contact_value": phone.group(), "label": ""})
    return contacts


def normalize(url):
    """Normalize URL: remove UTM params, trailing slash."""
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    q = [(k, v) for k, v in q if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    path = urllib.parse.quote(p.path.rstrip("/"), safe="/%:@!$&'()*+,;=-._~%")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, urllib.parse.urlencode(q), ""))


def expand_accordions_and_tabs(page):
    """Click on common accordion/tab patterns to expand content."""
    try:
        # Click on details/summary
        for summary in page.locator("summary").all():
            try:
                summary.click(timeout=1000)
            except Exception as error:
                logger.warning("Accordion expansion failed at %s: %s: %s", page.url, type(error).__name__, error)
        # Click on common tab patterns
        for tab in page.locator("[role='tab'], .tab, .accordion-header").all():
            try:
                tab.click(timeout=1000)
            except Exception as error:
                logger.warning("Tab expansion failed at %s: %s: %s", page.url, type(error).__name__, error)
    except Exception as error:
        logger.warning("Interactive control expansion failed at %s: %s: %s", page.url, type(error).__name__, error)


def run_crawl(job_id: int):
    """Run a crawl job with Playwright, local file storage, and detailed extraction."""
    db = SessionLocal()
    job = None
    try:
        claimed_at = datetime.now(timezone.utc)
        claim = db.execute(
            update(CrawlJob)
            .where(CrawlJob.id == job_id, CrawlJob.status == "queued")
            .values(status="running", started_at=claimed_at)
        )
        db.commit()
        if claim.rowcount != 1:
            # Duplicate queue deliveries must not crawl the same tenant/job concurrently.
            return None
        job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id))
        
        college = db.scalar(select(College).where(College.id == job.college_id))
        url = job.url
        host = urllib.parse.urlparse(url).hostname
        
        seen = set()
        start_time = 0

        # Track API responses
        api_responses = []
        api_hosts = set()
        current_page_url = [None]
        crawl_errors = []
        robots_parsers = {}
        excluded_hosts = ("googleapis.com", "gstatic.com", "iconify.design", "google-analytics.com", "googletagmanager.com", "google.com", "mapbox.com", "fonts.googleapis.com", "fonts.gstatic.com")

        def record_error(stage, error, target_url, row=None):
            message = f"{stage} {target_url}: {type(error).__name__}: {error}"[:500]
            logger.error("%s", message)
            crawl_errors.append(message)
            job.error_log = ((job.error_log or "") + message + "\n")[-20000:]
            if row is not None:
                row.status_reason = message[:200]

        def robots_for(target_url):
            parsed = urllib.parse.urlparse(target_url)
            origin = f"{parsed.scheme}://{parsed.hostname.lower().removeprefix('www.')}"
            if origin not in robots_parsers:
                parser = urllib.robotparser.RobotFileParser()
                robots_url = urllib.parse.urljoin(origin, "/robots.txt")
                parser.set_url(robots_url)
                if not safe_url(robots_url, host):
                    record_error("robots.txt rejected", ValueError("robots URL failed public-host checks"), robots_url)
                    robots_parsers[origin] = None
                else:
                    try:
                        request = urllib.request.Request(robots_url, headers={"User-Agent": "AI-FAQ-Crawler/1.0"})
                        opener = urllib.request.build_opener(_CheckedRedirectHandler(host, set()))
                        with opener.open(request, timeout=10) as response:
                            body = response.read(1024 * 1024).decode("utf-8", errors="replace")
                        parser.parse(body.splitlines())
                        robots_parsers[origin] = parser
                    except Exception as error:
                        record_error("robots.txt fetch failed; allowing URL", error, robots_url)
                        robots_parsers[origin] = None
            return robots_parsers[origin]

        def handle_response(response):
            content_type = response.header_value("content-type") or ""
            response_url = response.url
            parsed_response = urllib.parse.urlparse(response_url)
            hostname = (parsed_response.hostname or "").lower()
            # Check if JSON and not from excluded hosts
            if current_page_url[0] and "application/json" in content_type.lower() and hostname and not any(hostname == excluded or hostname.endswith("." + excluded) for excluded in excluded_hosts):
                api_hosts.add(hostname)
                try:
                    body = response.body()
                    if len(body) > 8 and current_page_url[0]:
                        api_responses.append({
                            "url": response_url,
                            "body": body,
                            "page_url": current_page_url[0]
                        })
                except Exception as error:
                    record_error("API response capture failed", error, response_url)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True, user_agent="Mozilla/5.0 (compatible; Crawler/1.0)")
            page_view = context.new_page()
            page_view.on("response", handle_response)

            # Fetch and parse sitemap.xml
            sitemap_url = f"{urllib.parse.urlparse(url).scheme}://{host}/sitemap.xml"
            try:
                sitemap_response = page_view.goto(sitemap_url, wait_until="domcontentloaded", timeout=10000)
                if sitemap_response and sitemap_response.status == 200:
                    sitemap_content = page_view.content()
                    sitemap_soup = BeautifulSoup(sitemap_content, "xml")
                    # Check for sitemap index
                    sitemaps = sitemap_soup.find_all("sitemap")
                    for sitemap in sitemaps:
                        loc = sitemap.find("loc")
                        if loc:
                            try:
                                index_page = context.new_page()
                                index_response = index_page.goto(loc.text, wait_until="domcontentloaded", timeout=10000)
                                if index_response and index_response.status == 200:
                                    index_content = index_page.content()
                                    index_soup = BeautifulSoup(index_content, "xml")
                                    for url_elem in index_soup.find_all("url"):
                                        url_loc = url_elem.find("loc")
                                        if url_loc:
                                            normalized = normalize(url_loc.text)
                                            if normalized not in seen and safe_url(normalized, host):
                                                seen.add(normalized)
                                                db.add(CrawlFrontier(job_id=job.id, college_id=college.id, url=normalized, depth=0, status="queued"))
                                                db.add(CrawlUrl(college_id=college.id, job_id=job.id, url=normalized, status="queued"))
                                index_page.close()
                            except Exception as error:
                                record_error("nested sitemap fetch failed", error, loc.text)
                    # Check for direct URLs in sitemap
                    for url_elem in sitemap_soup.find_all("url"):
                        url_loc = url_elem.find("loc")
                        if url_loc:
                            normalized = normalize(url_loc.text)
                            if normalized not in seen and safe_url(normalized, host):
                                seen.add(normalized)
                                db.add(CrawlFrontier(job_id=job.id, college_id=college.id, url=normalized, depth=0, status="queued"))
                                db.add(CrawlUrl(college_id=college.id, job_id=job.id, url=normalized, status="queued"))
                    job.sitemap_urls = (job.sitemap_urls or 0) + len(sitemap_soup.find_all("url"))
                    db.commit()
            except Exception as error:
                record_error("sitemap fetch failed", error, sitemap_url)

            # Add to frontier
            db.add(CrawlFrontier(job_id=job.id, college_id=college.id, url=url, depth=0, status="queued"))
            db.commit()
            
            start_time = __import__('time').time()
            
            while True:
                if __import__('time').time() - start_time > job.time_budget_seconds:
                    job.status = "failed"
                    job.error_log = ((job.error_log or "") + "Crawl time budget exhausted; remaining URLs are saved in the frontier.\n")[-20000:]
                    db.commit()
                    raise RuntimeError("Crawl time budget exhausted; retrying from saved frontier")

                # Page limit for testing (can be overridden via environment)
                page_limit = int(os.environ.get("CRAWL_PAGE_LIMIT", "0"))
                if page_limit > 0 and job.pages_done >= page_limit:
                    break
                
                frontier = db.scalar(select(CrawlFrontier).where(CrawlFrontier.job_id == job.id, CrawlFrontier.status == "queued"))
                if not frontier:
                    break
                
                frontier.status = "running"
                db.commit()
                
                # Keep crawl URL history scoped to this job. Earlier completed
                # crawls must not cause a fresh job to skip the page.
                crawl_url = db.scalar(select(CrawlUrl).where(
                    CrawlUrl.job_id == job.id,
                    CrawlUrl.college_id == college.id,
                    CrawlUrl.url == frontier.url,
                ))
                if not crawl_url:
                    crawl_url = CrawlUrl(college_id=college.id, job_id=job.id, url=frontier.url, status="running")
                    db.add(crawl_url)
                else:
                    crawl_url.status = "running"
                db.commit()
                
                api_responses.clear()
                current_page_url[0] = frontier.url
                try:
                    # Check robots.txt once per host; an unavailable file allows crawling.
                    parser = robots_for(frontier.url)
                    if parser is not None and not parser.can_fetch("*", frontier.url):
                        crawl_url.status = "blocked_by_robots"
                        crawl_url.status_reason = "Disallowed by robots.txt"
                        frontier.status = "blocked_by_robots"
                        job.robots_blocked_urls = (job.robots_blocked_urls or 0) + 1
                        db.commit()
                        continue

                    # Go to page
                    api_responses.clear()
                    response = page_view.goto(frontier.url, wait_until="domcontentloaded", timeout=30000)
                    final_url = page_view.url
                    http_status = response.status if response else 0
                    content_type = response.header_value("content-type") if response else ""
                    language = page_view.evaluate("() => document.documentElement.lang") or ""

                    # Extra wait for lazy-loaded content
                    __import__('time').sleep(3)

                    # Scroll to bottom in steps to trigger lazy loading
                    try:
                        scroll_height = page_view.evaluate("() => document.body.scrollHeight")
                        for i in range(3):
                            scroll_y = int((i + 1) * 0.3 * scroll_height)
                            page_view.evaluate(f"window.scrollTo(0, {scroll_y})")
                            __import__('time').sleep(0.5)
                        page_view.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        __import__('time').sleep(1)
                        page_view.evaluate("window.scrollTo(0, 0)")
                        __import__('time').sleep(0.5)
                    except Exception as error:
                        record_error("page scrolling failed", error, frontier.url, crawl_url)

                    # Expand accordions/tabs
                    expand_accordions_and_tabs(page_view)
                    
                    # Get content
                    html = page_view.content()
                    text = page_view.inner_text("body")
                    title = page_view.title()
                    
                    # Screenshot
                    screenshot_dir = f"colleges/{college.id}/screenshots"
                    os.makedirs(screenshot_dir, exist_ok=True)
                    screenshot_hash = hashlib.sha256(frontier.url.encode()).hexdigest()[:32]
                    screenshot_key = f"{screenshot_dir}/{screenshot_hash}.png"
                    page_view.screenshot(path=screenshot_key, full_page=True)
                    
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    strip_hidden_content(soup)
                    
                    # Extract data
                    structured_tables = (
                        extract_html_tables(soup, title or url)
                        + extract_html_structured_facts(soup, title or url)
                    )
                    page_sections = extract_page_sections(soup, 0, url)
                    navigation = extract_navigation(soup, url)
                    structured_data = extract_structured_data(soup, url)
                    tables = extract_tables(soup, 0, url)
                    faqs = extract_faqs(soup, url)
                    contacts = extract_contacts(soup, url)
                    links = [urllib.parse.urljoin(url, a.get("href")) for a in soup.select("a[href]")]
                    image_links = [(urllib.parse.urljoin(url, img.get("src") or img.get("data-src") or ""), str(img.get("alt", ""))) for img in soup.select("img[src],img[data-src]")]
                    image_links.extend((urllib.parse.urljoin(url, meta.get("content")), str(meta.get("property", ""))) for meta in soup.select('meta[property="og:image"][content]'))

                    digest = hashlib.sha256(text.encode()).hexdigest()
                    page = db.scalar(select(Page).where(Page.college_id == college.id, Page.url == frontier.url))
                    was_active = page.active if page else False
                    previous_hash = page.content_hash if page else None
                    
                    if not page:
                        page = Page(college_id=college.id, url=frontier.url, source_url=url, final_url=final_url, title=title, raw_text=text, raw_html=html, content_hash=digest, job_id=job.id, http_status=http_status, content_type=content_type, language=language, screenshot_key=screenshot_key, version=1)
                        db.add(page)
                        db.flush()
                    elif page.content_hash != digest:
                        db.add(PageHistory(page_id=page.id, college_id=college.id, url=page.url, title=page.title, raw_text=page.raw_text, raw_html=page.raw_html, content_hash=page.content_hash, version=page.version, changed_via="crawl"))
                        page.raw_text = text
                        page.raw_html = html
                        page.content_hash = digest
                        page.version += 1
                        page.final_url = final_url
                        page.http_status = http_status
                        page.content_type = content_type
                        page.language = language
                        page.screenshot_key = screenshot_key
                        page.job_id = job.id
                        db.flush()

                    # Store API data only after the saved Page row and rendered-page image queue exist.
                    api_file_payloads = {}
                    for api_resp in api_responses:
                        try:
                            api_json = json.loads(api_resp["body"])
                            existing = db.scalar(select(StructuredData).where(
                                StructuredData.page_id == page.id,
                                StructuredData.format == "api_json",
                                StructuredData.schema_type == api_resp["url"][:100]
                            ))
                            if not existing:
                                db.add(StructuredData(
                                    college_id=college.id,
                                    job_id=job.id,
                                    page_id=page.id,
                                    source_url=api_resp["page_url"],
                                    format="api_json",
                                    schema_type=api_resp["url"][:100],
                                    data={"api_url": api_resp["url"], "page_url": api_resp["page_url"], "json": api_json}
                                ))
                            for file_url in extract_urls_from_json(api_json):
                                full_url = urllib.parse.urljoin(api_resp["url"], file_url)
                                if not safe_url(full_url, host, api_hosts):
                                    continue
                                try:
                                    file_data, kind = download_checked_file(full_url, host, api_hosts)
                                    api_file_payloads[full_url] = (file_data, kind)
                                    if kind in {"jpg", "jpeg", "png", "gif", "webp"} and full_url not in [item[0] for item in image_links]:
                                        image_links.append((full_url, ""))
                                except Exception as error:
                                    record_error("API file validation/download failed", error, full_url, crawl_url)
                        except Exception as error:
                            record_error("API response storage or file queue failed", error, api_resp.get("url", frontier.url), crawl_url)
                    
                    job.pages_done = (job.pages_done or 0) + 1
                    
                    # Store page sections
                    for i, section in enumerate(page_sections):
                        existing = db.scalar(select(PageSection).where(PageSection.page_id == page.id, PageSection.heading_text == section["heading_text"]))
                        if not existing:
                            db.add(PageSection(college_id=college.id, job_id=job.id, page_id=page.id, source_url=url, heading_text=section["heading_text"], heading_level=section["heading_level"], section_text=section["section_text"], position=i))
                    
                    # Store navigation
                    for i, nav in enumerate(navigation):
                        existing = db.scalar(select(NavigationItem).where(NavigationItem.page_id == page.id, NavigationItem.label == nav["label"]))
                        if not existing:
                            db.add(NavigationItem(college_id=college.id, job_id=job.id, page_id=page.id, source_url=url, label=nav["label"], url=nav["url"], position=i))
                    
                    # Store structured data
                    for sd in structured_data:
                        existing = db.scalar(select(StructuredData).where(StructuredData.page_id == page.id, StructuredData.format == sd["format"], StructuredData.schema_type == sd["schema_type"]))
                        if not existing:
                            db.add(StructuredData(college_id=college.id, job_id=job.id, page_id=page.id, source_url=url, format=sd["format"], schema_type=sd["schema_type"], data=sd["data"]))
                    
                    # Store tables
                    for table in tables:
                        existing = db.scalar(select(ExtractedTable).where(
                            ExtractedTable.page_id == page.id,
                            ExtractedTable.table_number == table["table_number"],
                        ))
                        if not existing:
                            db.add(ExtractedTable(
                                college_id=college.id,
                                job_id=job.id,
                                page_id=page.id,
                                source_url=url,
                                table_number=table["table_number"],
                                caption=table["caption"],
                                headers=table["headers"],
                                rows=table["rows"],
                                row_count=len(table["rows"]),
                            ))
                    
                    # Store FAQs
                    for faq in faqs:
                        existing = db.scalar(select(FAQ).where(FAQ.page_id == page.id, FAQ.question == faq["question"]))
                        if not existing:
                            db.add(FAQ(college_id=college.id, job_id=job.id, page_id=page.id, source_url=url, question=faq["question"], answer=faq["answer"]))
                    
                    # Store contacts
                    for contact in contacts:
                        existing = db.scalar(select(Contact).where(Contact.page_id == page.id, Contact.contact_value == contact["contact_value"]))
                        if not existing:
                            db.add(Contact(college_id=college.id, job_id=job.id, page_id=page.id, source_url=url, contact_type=contact["contact_type"], contact_value=contact["contact_value"], label=contact["label"]))
                    
                    # Store links
                    for link in links:
                        link_url = normalize(link)
                        is_internal = urllib.parse.urlparse(link_url).hostname == host
                        existing_link = db.scalar(select(Link).where(Link.page_id == page.id, Link.href == link_url))
                        if not existing_link:
                            anchor = next((a for a in soup.select("a[href]") if urllib.parse.urljoin(url, a.get("href", "")) == link), None)
                            rel = anchor.get("rel", []) if anchor else []
                            is_nofollow = "nofollow" in (rel if isinstance(rel, list) else str(rel).split())
                            db.add(Link(
                                college_id=college.id,
                                job_id=job.id,
                                page_id=page.id,
                                source_url=url,
                                href=link_url,
                                anchor_text=anchor.get_text(" ", strip=True)[:500] if anchor else "",
                                link_type="internal" if is_internal else "external",
                                is_nofollow=is_nofollow,
                            ))
                    
                    # Download and store media (images) - use local storage if S3 not configured
                    if image_links:
                        from .storage import put_image
                        from PIL import Image, ImageOps
                        use_s3 = all((settings.s3_endpoint, settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key))
                        for image_url, alt_text in image_links[:20]:
                            if not image_url or not safe_url(image_url, host, api_hosts):
                                continue
                            existing_media = db.scalar(select(MediaAsset).where(MediaAsset.college_id == college.id, MediaAsset.source_url == image_url))
                            try:
                                payload = api_file_payloads.get(image_url)
                                if payload:
                                    image_data = payload[0]
                                else:
                                    image_data, _image_kind = download_checked_file(
                                        image_url, host, api_hosts, max_bytes=8 * 1024 * 1024
                                    )
                                if len(image_data) > 8 * 1024 * 1024:
                                    continue
                                media_hash = hashlib.sha256(image_data).hexdigest()
                                if existing_media and existing_media.content_hash == media_hash:
                                    continue
                                image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_data))).convert("RGB")
                                image_width, image_height = image.size
                                image.thumbnail((1800, 1800))
                                original = io.BytesIO()
                                image.save(original, format="WEBP", quality=84, method=5)
                                thumbnail_image = image.copy()
                                thumbnail_image.thumbnail((640, 640))
                                thumbnail = io.BytesIO()
                                thumbnail_image.save(thumbnail, format="WEBP", quality=76, method=4)
                                media_size = len(original.getvalue()) + len(thumbnail.getvalue())
                                image_id = hashlib.sha256(image_url.encode()).hexdigest()[:32]
                                if use_s3:
                                    object_key = existing_media.object_key if existing_media else f"colleges/{college.id}/media/{image_id}.webp"
                                    thumb_key = existing_media.thumbnail_key if existing_media else f"colleges/{college.id}/media/{image_id}-thumb.webp"
                                    put_image(object_key, original.getvalue())
                                    put_image(thumb_key, thumbnail.getvalue())
                                else:
                                    storage_dir = f"colleges/{college.id}/media"
                                    os.makedirs(storage_dir, exist_ok=True)
                                    object_key = existing_media.object_key if existing_media else f"{storage_dir}/{image_id}.webp"
                                    thumb_key = existing_media.thumbnail_key if existing_media else f"{storage_dir}/{image_id}-thumb.webp"
                                    with open(object_key, 'wb') as f:
                                        f.write(original.getvalue())
                                    with open(thumb_key, 'wb') as f:
                                        f.write(thumbnail.getvalue())
                                if existing_media:
                                    existing_media.content_hash = media_hash
                                    existing_media.alt_text = alt_text[:500]
                                    existing_media.size_bytes = media_size
                                    existing_media.job_id = job.id
                                    existing_media.page_id = page.id
                                    existing_media.width = image_width
                                    existing_media.height = image_height
                                    existing_media.media_type = "image/webp"
                                    existing_media.source_page = url
                                else:
                                    db.add(MediaAsset(
                                        college_id=college.id,
                                        source_url=image_url,
                                        object_key=object_key,
                                        thumbnail_key=thumb_key,
                                        alt_text=alt_text[:500],
                                        content_hash=media_hash,
                                        size_bytes=media_size,
                                        width=image_width,
                                        height=image_height,
                                        media_type="image/webp",
                                        source_page=url,
                                        job_id=job.id,
                                        page_id=page.id,
                                    ))
                                job.images_stored = (job.images_stored or 0) + 1
                            except Exception as error:
                                record_error("media download/store failed", error, image_url, crawl_url)
                    
                    # Download and store documents (PDF, DOCX, XLSX) - use local storage if S3 not configured
                    from .storage import put_image
                    for link in soup.select("a[href]"):
                        href = link.get("href", "")
                        if file_extension(href) in {".pdf", ".docx", ".xlsx"}:
                            full_url = urllib.parse.urljoin(url, href)
                            if not safe_url(full_url, host):
                                continue
                            existing_doc = db.scalar(select(Document).where(Document.college_id == college.id, Document.source_url == full_url))
                            if existing_doc:
                                continue
                            try:
                                doc_data, file_type = download_checked_file(full_url, host)
                                doc_hash = hashlib.sha256(doc_data).hexdigest()
                                use_s3 = all((settings.s3_endpoint, settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key))
                                if use_s3:
                                    object_key = f"colleges/{college.id}/documents/{doc_hash[:32]}.{file_type}"
                                    put_image(object_key, doc_data)
                                else:
                                    storage_dir = f"colleges/{college.id}/documents"
                                    os.makedirs(storage_dir, exist_ok=True)
                                    object_key = f"{storage_dir}/{doc_hash[:32]}.{file_type}"
                                    with open(object_key, 'wb') as f:
                                        f.write(doc_data)
                                extracted_text = ""
                                ocr_used = False
                                if file_type == "pdf":
                                    from pypdf import PdfReader
                                    pdf = PdfReader(io.BytesIO(doc_data))
                                    extracted_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                                    if not extracted_text.strip():
                                        try:
                                            from pdf2image import convert_from_bytes
                                            import pytesseract
                                            ocr_pages = []
                                            for page_number in range(1, min(len(pdf.pages) + 1, 5)):
                                                rendered = convert_from_bytes(doc_data, first_page=page_number, last_page=page_number, thread_count=1, timeout=30, dpi=120, size=2000)
                                                if rendered:
                                                    ocr_pages.append(pytesseract.image_to_string(rendered[0], timeout=30))
                                            extracted_text = "\n".join(ocr_pages)
                                            ocr_used = True
                                        except Exception as error:
                                            record_error("document OCR failed", error, full_url, crawl_url)
                                elif file_type == "docx":
                                    from docx import Document as DocxDocument
                                    extracted_text = "\n".join(p.text for p in DocxDocument(io.BytesIO(doc_data)).paragraphs)
                                elif file_type == "xlsx":
                                    from openpyxl import load_workbook
                                    wb = load_workbook(io.BytesIO(doc_data), read_only=True, data_only=True)
                                    extracted_text = "\n".join(" | ".join(str(v) for v in row if v is not None) for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
                                db.add(Document(college_id=college.id, job_id=job.id, page_id=page.id, source_url=full_url, object_key=object_key, file_type=file_type, file_size_bytes=len(doc_data), extracted_text=extracted_text[:100000], ocr_used=ocr_used, content_hash=doc_hash))
                                job.documents_found = (job.documents_found or 0) + 1
                                if extracted_text:
                                    job.documents_parsed = (job.documents_parsed or 0) + 1
                            except Exception as error:
                                record_error("document download/store failed", error, full_url, crawl_url)
                            if safe_url(url, host):
                                page_view.goto(url, wait_until="domcontentloaded", timeout=10000)

                    # Store checked document payloads discovered in captured API JSON.
                    for full_url, (doc_data, file_type) in api_file_payloads.items():
                        if file_type not in {"pdf", "docx", "xlsx"}:
                            continue
                        try:
                            existing_doc = db.scalar(select(Document).where(Document.college_id == college.id, Document.source_url == full_url))
                            if existing_doc:
                                continue
                            doc_hash = hashlib.sha256(doc_data).hexdigest()
                            use_s3 = all((settings.s3_endpoint, settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key))
                            if use_s3:
                                object_key = f"colleges/{college.id}/documents/{doc_hash[:32]}.{file_type}"
                                put_image(object_key, doc_data)
                            else:
                                storage_dir = f"colleges/{college.id}/documents"
                                os.makedirs(storage_dir, exist_ok=True)
                                object_key = f"{storage_dir}/{doc_hash[:32]}.{file_type}"
                                with open(object_key, 'wb') as f:
                                    f.write(doc_data)
                            extracted_text = ""
                            ocr_used = False
                            if file_type == "pdf":
                                from pypdf import PdfReader
                                pdf = PdfReader(io.BytesIO(doc_data))
                                extracted_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                            elif file_type == "docx":
                                from docx import Document as DocxDocument
                                extracted_text = "\n".join(p.text for p in DocxDocument(io.BytesIO(doc_data)).paragraphs)
                            elif file_type == "xlsx":
                                from openpyxl import load_workbook
                                wb = load_workbook(io.BytesIO(doc_data), read_only=True, data_only=True)
                                extracted_text = "\n".join(" | ".join(str(v) for v in row if v is not None) for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
                            db.add(Document(college_id=college.id, job_id=job.id, page_id=page.id, source_url=full_url, object_key=object_key, file_type=file_type, file_size_bytes=len(doc_data), extracted_text=extracted_text[:100000], ocr_used=ocr_used, content_hash=doc_hash))
                            job.documents_found = (job.documents_found or 0) + 1
                            if extracted_text:
                                job.documents_parsed = (job.documents_parsed or 0) + 1
                        except Exception as error:
                            record_error("API document store failed", error, full_url, crawl_url)

                    # Update counters
                    job.images_found = (job.images_found or 0) + len(image_links)
                    
                    # Store facts
                    fact = db.scalar(select(Fact).where(Fact.college_id == college.id, Fact.category == "website page", Fact.title == title[:300], Fact.source_page_id == page.id))
                    if not fact:
                        try:
                            fact = Fact(college_id=college.id, category="website page", title=(title or url)[:300], value=text[:50000], source_page_id=page.id, confidence=.75)
                            db.add(fact)
                        except Exception as error:
                            db.rollback()
                            record_error("website fact store failed", error, frontier.url, crawl_url)
                    elif previous_hash != digest or not was_active:
                        try:
                            db.add(FactHistory(fact_id=fact.id, college_id=fact.college_id, category=fact.category, title=fact.title, value=fact.value, extra=fact.extra or {}, changed_via="crawl"))
                            fact.title = (title or url)[:300]
                            fact.value = text[:50000]
                            fact.confidence = .75
                        except Exception as error:
                            db.rollback()
                            record_error("fact history store failed", error, frontier.url, crawl_url)
                    
                    # Store structured facts
                    for row_index, struct in enumerate(structured_tables):
                        value_hash = hashlib.sha256(struct["value"].encode()).hexdigest()[:12]
                        title = f"Row {row_index}: {value_hash}"
                        existing = db.scalar(select(Fact).where(Fact.college_id == college.id, Fact.source_page_id == page.id, Fact.category == struct["category"], Fact.title == title))
                        if not existing:
                            try:
                                db.add(Fact(college_id=college.id, category=struct["category"], title=title, value=struct["value"], source_page_id=page.id, confidence=0.85, extra={"job_id": job_id, "source_url": url, "origin": "html_table"}))
                            except Exception as error:
                                db.rollback()
                                record_error("table fact store failed", error, frontier.url, crawl_url)
                    
                    # Update crawl_url status
                    crawl_url.status = "stored"
                    frontier.status = "stored"
                    try:
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        # If it's a KnowledgeCatalog constraint error, it's not critical for the crawl
                        if "knowledge_catalog" in str(e):
                            db.commit()  # Try again without the problematic insert
                        else:
                            raise
                    
                    # Add new links to frontier
                    for link in links:
                        normalized_link = normalize(link)
                        if normalized_link not in seen and safe_url(normalized_link, host):
                            seen.add(normalized_link)
                            exists = db.scalar(select(CrawlFrontier).where(CrawlFrontier.job_id == job.id, CrawlFrontier.url == normalized_link))
                            if not exists:
                                db.add(CrawlFrontier(job_id=job.id, college_id=college.id, url=normalized_link, depth=frontier.depth + 1, status="queued"))
                                db.add(CrawlUrl(college_id=college.id, job_id=job.id, url=normalized_link, status="queued"))
                    db.commit()
                    
                except Exception as e:
                    frontier_id = frontier.id
                    crawl_url_id = crawl_url.id if crawl_url else None
                    # A failed SQLAlchemy flush leaves the session unusable
                    # until rollback. Roll back page writes, then persist the
                    # failed URL and continue with the remaining frontier.
                    db.rollback()
                    frontier = db.get(CrawlFrontier, frontier_id)
                    job = db.get(CrawlJob, job_id)
                    crawl_url = db.get(CrawlUrl, crawl_url_id) if crawl_url_id else None
                    if not crawl_url:
                        crawl_url = CrawlUrl(college_id=college.id, job_id=job.id, url=frontier.url, status="failed")
                        db.add(crawl_url)
                    logger.exception("page crawl failed url=%s", frontier.url)
                    record_error("page crawl failed", e, frontier.url, crawl_url)
                    crawl_url.status = "failed"
                    crawl_url.status_reason = str(e)[:200]
                    frontier.status = "failed"
                    job.pages_failed = (job.pages_failed or 0) + 1
                    db.commit()
                finally:
                    api_responses.clear()
                    current_page_url[0] = None
            
            browser.close()
        
        job.pages_found = db.scalar(select(func.count(CrawlFrontier.id)).where(CrawlFrontier.job_id == job.id)) or 0
        if job.pages_done and job.pages_failed:
            job.status = "partial"
        elif job.pages_done:
            job.status = "completed"
        else:
            job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.coverage_report = {
            "sitemap_urls": 0,
            "crawled_urls": job.pages_done,
            "failed_urls": job.pages_failed,
            "blocked_urls": db.scalar(select(func.count(CrawlUrl.id)).where(CrawlUrl.job_id == job.id, CrawlUrl.status == "blocked_by_robots")),
            "out_of_domain_urls": db.scalar(select(func.count(CrawlUrl.id)).where(CrawlUrl.job_id == job.id, CrawlUrl.status == "out_of_domain")),
            "duplicate_urls": db.scalar(select(func.count(CrawlUrl.id)).where(CrawlUrl.job_id == job.id, CrawlUrl.status == "duplicate")),
            "images_found": job.images_found,
            "images_stored": job.images_stored,
            "documents_found": job.documents_found,
            "documents_parsed": job.documents_parsed,
            "tables_found": db.scalar(select(func.count(ExtractedTable.id)).where(ExtractedTable.job_id == job.id)),
            "faqs_found": db.scalar(select(func.count(FAQ.id)).where(FAQ.job_id == job.id)),
            "errors": crawl_errors
        }
        db.commit()
        
        # Run structured builder
        from app.structured_builder import build_structured_data
        build_structured_data(college.id, job.id)
        invalidate_college_answer_cache(db, college)
        
        return job.coverage_report
        
    except Exception as e:
        db.rollback()
        job = db.get(CrawlJob, job_id)
        if job:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error_log = ((job.error_log or "") + f"Crawl failed: {type(e).__name__}: {e}\n")[-20000:]
            db.commit()
        raise
    finally:
        db.close()
