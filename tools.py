"""
Tool implementations for the Springboard briefing agent.

Two tools:
  search_source(source_id)  — fetch recent articles from a named source
  fetch_article(url)        — fetch and clean the full text of a URL
"""

import re
import sys
from datetime import datetime, timedelta, timezone

import requests
import urllib3
from bs4 import BeautifulSoup

from sources import SOURCES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; sb-digest-bot/1.0; for internal research)"
}
TIMEOUT = 20
LOOKBACK_HOURS = 28  # slightly generous to catch early-morning posts


# ── search_source ─────────────────────────────────────────────────────────────

def _get_source(source_id: str) -> dict | None:
    """Look up a source by id or by name (case-insensitive)."""
    sid = source_id.lower().strip()
    for s in SOURCES:
        if s["id"] == sid or s["name"].lower() == sid:
            return s
    return None


def _fetch_rss(src: dict) -> list[dict]:
    """Return recent items from an RSS/Atom feed."""
    import feedparser
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    try:
        try:
            resp = requests.get(src["rss_url"], headers=HEADERS, timeout=TIMEOUT, verify=True)
        except requests.exceptions.SSLError:
            resp = requests.get(src["rss_url"], headers=HEADERS, timeout=TIMEOUT, verify=False)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as e:
        return []

    items = []
    for entry in feed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        url   = (getattr(entry, "link",  "") or "").strip()
        if not title or not url:
            continue
        for field in ("published_parsed", "updated_parsed"):
            t = getattr(entry, field, None)
            if t:
                try:
                    pub = datetime(*t[:6], tzinfo=timezone.utc)
                    if pub < cutoff:
                        title = None  # skip
                    break
                except Exception:
                    pass
        if not title:
            continue
        summary = ""
        for field in ("summary", "description"):
            val = getattr(entry, field, None)
            if val:
                summary = re.sub(r"<[^>]+>", " ", val)
                summary = re.sub(r"\s+", " ", summary).strip()[:300]
                break
        items.append({"title": title, "url": url, "summary": summary})
    return items


def _fetch_page_articles(src: dict) -> list[dict]:
    """Scrape article links from a news page."""
    news_url = src.get("news_url", "")
    if not news_url:
        return []
    try:
        try:
            resp = requests.get(news_url, headers=HEADERS, timeout=TIMEOUT, verify=True)
        except requests.exceptions.SSLError:
            resp = requests.get(news_url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return []

    items = []
    seen = set()
    # Try <article> elements first, then heading links
    candidates = []
    for article in soup.find_all("article"):
        a = article.find("a", href=True)
        if a:
            candidates.append(a)
    if not candidates:
        for tag in soup.find_all(["h2", "h3"]):
            a = tag.find("a", href=True)
            if a:
                candidates.append(a)

    for a in candidates:
        title = a.get_text(" ", strip=True)
        href  = a.get("href", "")
        if len(title) < 20 or not href:
            continue
        if href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(news_url, href)
        if href in seen:
            continue
        seen.add(href)
        items.append({"title": title, "url": href, "summary": ""})
        if len(items) >= 10:
            break
    return items


def _fetch_scrape_module(src: dict) -> list[dict]:
    """Call a dedicated scrape module (fetch_hoc or fetch_senate)."""
    module_name = src.get("scrape_module", "")
    try:
        if module_name == "fetch_hoc":
            import fetch_hoc
            raw = fetch_hoc.fetch()
        elif module_name == "fetch_senate":
            import fetch_senate
            raw = fetch_senate.fetch()
        else:
            return []
        return [
            {"title": a["title"], "url": a.get("url", ""), "summary": a.get("summary", "")}
            for a in raw
        ]
    except Exception as e:
        print(f"    [warning] scrape_module {module_name}: {e}", file=sys.stderr)
        return []


def _keyword_match(title: str, summary: str) -> bool:
    """Return True if the article matches any keyword across any category."""
    from keywords import match_article
    return bool(match_article(title, summary))


def search_source(source_id: str, keyword_filter: bool = False) -> str:
    """
    Fetch recent articles from a named source.
    Returns a plain-text formatted list of articles (title, URL, brief excerpt).
    If keyword_filter is True, only articles matching policy keywords are returned.
    If no recent articles are found, says so.
    """
    src = _get_source(source_id)
    if src is None:
        return f"Unknown source: '{source_id}'. Check the source ID."

    if src.get("manual"):
        return (
            f"{src['name']} must be checked manually.\n"
            f"URL: {src.get('url', 'N/A')}\n"
            f"Note: No automated feed available."
        )

    items = []
    if src.get("scrape_module"):
        items = _fetch_scrape_module(src)
    elif src.get("has_rss") and src.get("rss_url"):
        items = _fetch_rss(src)
    elif src.get("news_url"):
        items = _fetch_page_articles(src)

    if keyword_filter:
        items = [i for i in items if _keyword_match(i["title"], i.get("summary", ""))]

    paywall_note = " [PAYWALLED]" if src.get("paywalled") else ""
    header = f"=== {src['name']}{paywall_note} ===\n"

    if not items:
        return header + "No recent articles found in the last 28 hours.\n"

    lines = [header]
    for i, item in enumerate(items[:8], 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   URL: {item['url']}")
        if item.get("summary"):
            lines.append(f"   Excerpt: {item['summary']}")
        lines.append("")
    return "\n".join(lines)


# ── fetch_article ─────────────────────────────────────────────────────────────

def fetch_article(url: str) -> str:
    """
    Fetch and return the cleaned full text of an article at the given URL.
    Returns up to ~5000 characters of main body text.
    """
    try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=True)
        except requests.exceptions.SSLError:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        resp.raise_for_status()
    except Exception as e:
        return f"Could not fetch article: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove nav, footer, ads, scripts
    for tag in soup(["script", "style", "nav", "footer", "aside",
                     "header", "form", "noscript", "iframe"]):
        tag.decompose()

    # Try to find the article body
    body = None
    for selector in ("article", "[role='main']", "main", ".article-body",
                     ".story-body", ".post-content", ".entry-content"):
        body = soup.select_one(selector)
        if body:
            break

    text_source = body if body else soup.find("body") or soup
    text = text_source.get_text(" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"(\. )([A-Z])", r".\n\2", text)  # rough sentence breaks

    if len(text) > 5000:
        text = text[:5000] + "\n[... truncated]"

    return text or "No readable content found."
