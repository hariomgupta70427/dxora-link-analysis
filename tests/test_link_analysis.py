"""Tests for the Link Analysis API.

Run from the project root with the venv active:
    NO_PROXY=localhost,127.0.0.1 TEST_MODE=1 PYTHONPATH=. .venv/bin/pytest tests/ -q
TEST_MODE=1 makes the LLM service return a deterministic mock, so the
endpoint tests need no API key and no network (except the SSRF tests,
which resolve hostnames, and the unresolvable-host test, which expects
DNS to fail fast on the .invalid TLD).
NO_PROXY is set because httpx 0.28.1 chokes on the IPv6 entries
(::1, [::1]) in this sandbox's default NO_PROXY (same quirk as test 1).
PYTHONPATH=. is required: without it the suite fails collection with
"No module named 'app'" (same invocation detail as test 1).
"""

import os

os.environ["TEST_MODE"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.website_extractor import extract_from_html
from app.utils.validators import UnsafeUrlError, validate_url_safe

client = TestClient(app)

SAMPLE_HTML = """
<html><head><title>Acme Widgets</title>
<meta name="description" content="Acme sells durable widgets for small factories.">
</head><body>
<nav><a href="/home">Home</a><a href="/pricing">Pricing</a></nav>
<h1>Widgets that last</h1><h2>Our services</h2>
<main><p>Acme Widgets makes industrial widgets, custom widget design and
widget repair for factories across India.</p>
<p>Acme Widgets makes industrial widgets, custom widget design and
widget repair for factories across India.</p></main>
<script>var x = 1;</script>
</body></html>
"""


# --- Endpoint: request validation -------------------------------------------

def test_root_and_health():
    assert client.get("/").json()["endpoint"] == "POST /link-analysis"
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "url",
    ["", "not a url", "ftp://example.com", "example.com", "http://", "https://"],
)
def test_invalid_url_returns_422(url):
    response = client.post("/link-analysis", json={"url": url})
    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:4000/",
        "http://localhost/",
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://192.168.1.1/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://[::1]/",
        "http://user:pass@example.com/",
        "http://example.com:8443/",
    ],
)
def test_ssrf_blocked_urls_return_422(url):
    response = client.post("/link-analysis", json={"url": url})
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_unresolvable_host_rejected_by_validator(monkeypatch):
    # DNS fails, so the SSRF check cannot verify the host is public.
    # (Tested at the validator level: this sandbox's resolver answers
    # every hostname, so an endpoint-level .invalid test is not
    # deterministic here.)
    import socket

    def fake_getaddrinfo(*args, **kwargs):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="could not be resolved"):
        validate_url_safe("http://nonexistent.invalid/")


def test_fetch_failure_returns_502(monkeypatch):
    from app.services.website_extractor import FetchError

    async def failing_fetch(url: str):
        raise FetchError("could not reach https://example.com: boom")

    monkeypatch.setattr("app.main.fetch_website", failing_fetch)
    response = client.post("/link-analysis", json={"url": "https://example.com/"})
    assert response.status_code == 502
    assert response.json()["success"] is False


# --- Endpoint: happy path (TEST_MODE mock LLM, mocked fetch) -----------------

def test_happy_path_returns_all_five_sections(monkeypatch):
    async def fake_fetch(url: str):
        return extract_from_html(SAMPLE_HTML, url, url)

    monkeypatch.setattr(
        "app.main.fetch_website", fake_fetch
    )
    response = client.post("/link-analysis", json={"url": "https://acme.example/"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["website"] == "https://acme.example/"
    assert body["brand"]["name"] == "Acme Widgets"  # mock takes title from prompt
    analysis = body["analysis"]
    assert len(analysis["competitor_analysis"]["competitors"]) >= 3
    assert all(
        c["source"] == "ai_generated_suggestion"
        for c in analysis["competitor_analysis"]["competitors"]
    )
    assert len(analysis["target_search_queries"]) == 5
    assert len(analysis["top_services"]) == 5
    assert analysis["seo_improvements"]["primary_keyword"]
    assert analysis["target_audience"]["primary_audience"]
    assert body["meta"]["mock"] is True


def test_docs_endpoint_available():
    assert client.get("/docs").status_code == 200


# --- Validators (unit) ------------------------------------------------------

def test_validate_url_safe_accepts_public_host():
    assert validate_url_safe("https://example.com/path") == "https://example.com/path"


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost/"])
def test_validate_url_safe_rejects_private(url):
    with pytest.raises(UnsafeUrlError):
        validate_url_safe(url)


# --- Extractor (unit) -------------------------------------------------------

def test_extract_from_html_cleans_and_dedupes():
    content = extract_from_html(SAMPLE_HTML, "https://acme.example/", "https://acme.example/")
    assert content.title == "Acme Widgets"
    assert "durable widgets" in content.meta_description
    assert "Widgets that last" in content.headings
    assert "var x = 1;" not in content.text  # script dropped
    assert "Home" in content.nav_links
    # duplicated paragraph appears once
    assert content.text.count("industrial widgets") == 1


def test_extract_truncates_long_pages(monkeypatch):
    monkeypatch.setattr("app.services.website_extractor.settings.max_content_chars", 100)
    long_html = "<html><body><p>" + ("word " * 500) + "</p></body></html>"
    content = extract_from_html(long_html, "https://x.example/", "https://x.example/")
    assert content.truncated is True
    assert len(content.text) == 100
