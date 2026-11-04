import socket
import httpx
import pytest

from app import crawler


def _dns_result(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_safe_url_rejects_host_outside_registered_domain():
    assert not crawler.safe_url("https://other.example.edu/page", "college.example.edu")


def test_safe_url_rejects_private_resolved_address(monkeypatch):
    monkeypatch.setattr(crawler.socket, "getaddrinfo", lambda *args, **kwargs: _dns_result("10.0.0.8"))
    assert not crawler.safe_url("https://college.example.edu/page", "college.example.edu")


def test_safe_url_accepts_public_resolved_address(monkeypatch):
    monkeypatch.setattr(crawler.socket, "getaddrinfo", lambda *args, **kwargs: _dns_result("93.184.216.34"))
    assert crawler.safe_url("https://college.example.edu/page", "college.example.edu")


def test_normalize_removes_tracking_and_fragments():
    assert crawler.normalize("https://college.example.edu/admissions/?utm_source=mail&year=2026#dates") == (
        "https://college.example.edu/admissions?year=2026"
    )


def test_parse_sitemap_index_and_url_set():
    is_index, locations = crawler.parse_sitemap(
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://college.example.edu/pages.xml</loc></sitemap></sitemapindex>'
    )
    assert is_index
    assert locations == ["https://college.example.edu/pages.xml"]
    is_index, locations = crawler.parse_sitemap(
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://college.example.edu/admissions</loc></url></urlset>'
    )
    assert not is_index
    assert locations == ["https://college.example.edu/admissions"]


def test_fetch_bounded_rejects_oversized_stream(monkeypatch):
    monkeypatch.setattr(crawler, "MAX_CRAWL_RESOURCE_BYTES", 4)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError, match="20 MiB limit"):
            crawler.fetch_bounded(client, "https://college.example.edu/large.pdf")


def test_fetch_bounded_accepts_body_at_limit(monkeypatch):
    monkeypatch.setattr(crawler, "MAX_CRAWL_RESOURCE_BYTES", 4)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"1234"))
    with httpx.Client(transport=transport) as client:
        status, host, _, body = crawler.fetch_bounded(client, "https://college.example.edu/file.pdf")
    assert (status, host, body) == (200, "college.example.edu", b"1234")
