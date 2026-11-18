"""Fetch a website and extract clean, LLM-ready content.

Steps: SSRF-validate the URL, fetch with a manual redirect loop (each
hop re-validated, max 5), require an HTML response, parse with
BeautifulSoup, drop script/style/nav/footer/aside, keep title, meta
description, headings, nav link text and visible body text, dedupe
repeated lines, and truncate to ``max_content_chars`` so the LLM prompt
stays small (spec section 6C: clean content before sending it).
"""

import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.utils.validators import UnsafeUrlError, validate_url_safe

USER_AGENT = "DxoraLinkAnalysis/1.0 (practical test; +https://github.com/hariomgupta70427)"

# Tags whose text is never business content.
DROP_TAGS = {"script", "style", "noscript", "nav", "footer", "aside", "svg"}
MAX_BODY_CHARS_FALLBACK = 4000


class FetchError(Exception):
    """The site could not be fetched (network, status, content type)."""


@dataclass
class ExtractedContent:
    url: str
    final_url: str
    title: str = ""
    meta_description: str = ""
    headings: list[str] = field(default_factory=list)
    nav_links: list[str] = field(default_factory=list)
    text: str = ""
    truncated: bool = False


def _clean_lines(raw: str) -> list[str]:
    """Split on newlines, strip, drop empties and dedupe (order kept)."""
    seen: set[str] = set()
    out: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 3 or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def extract_from_html(html: str, url: str, final_url: str) -> ExtractedContent:
    """Parse *html* into cleaned, structured content (no network)."""
    soup = BeautifulSoup(html, "html.parser")

    # Collect navigation link text BEFORE dropping <nav>/<footer>: the
    # drop pass below removes those tags entirely.
    nav_links = _clean_lines(
        "\n".join(
            a.get_text(" ", strip=True)
            for a in soup.find_all("a", href=True)
            if a.get_text(strip=True)
        )
    )[:40]

    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    meta_description = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if meta and meta.get("content"):
        meta_description = str(meta["content"]).strip()

    headings = _clean_lines(
        "\n".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"]))
    )[:30]

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = "\n".join(_clean_lines(main.get_text("\n")))
    truncated = False
    if len(text) > settings.max_content_chars:
        text = text[: settings.max_content_chars]
        truncated = True
    if not text and soup.title:
        text = title
    return ExtractedContent(
        url=url,
        final_url=final_url,
        title=title,
        meta_description=meta_description,
        headings=headings,
        nav_links=nav_links,
        text=text,
        truncated=truncated,
    )


async def fetch_website(url: str) -> ExtractedContent:
    """Validate, fetch and extract *url*. Raises UnsafeUrlError / FetchError."""
    validate_url_safe(url)
    current = url.strip()
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout_seconds,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        follow_redirects=False,
    ) as client:
        for _ in range(settings.max_redirects + 1):
            try:
                response = await client.get(current)
            except httpx.TimeoutException as exc:
                raise FetchError(f"timed out fetching {current}") from exc
            except httpx.RequestError as exc:
                raise FetchError(f"could not reach {current}: {exc}") from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError(f"redirect from {current} has no target")
                nxt = httpx.URL(location)
                if not nxt.is_absolute_url:
                    nxt = response.url.join(location)
                try:
                    validate_url_safe(str(nxt))
                except UnsafeUrlError as exc:
                    raise FetchError(
                        f"redirect target blocked by SSRF check: {exc}"
                    ) from exc
                current = str(nxt)
                continue

            if response.status_code != 200:
                raise FetchError(
                    f"website returned HTTP {response.status_code} for {current}"
                )
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower() and "<html" not in response.text[:2000].lower():
                raise FetchError(
                    f"URL did not return an HTML page (content-type: {content_type})"
                )
            return extract_from_html(response.text, url.strip(), current)
        raise FetchError(f"too many redirects (>{settings.max_redirects}) for {url}")
