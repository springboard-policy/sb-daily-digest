"""
Scraper for sources that don't publish RSS feeds.

Uses a generic approach: fetches each source's news page, finds article
title+link pairs from common HTML patterns, and returns them in the standard
article dict format.  Relies on previous_items.json to surface only new items.
"""

import re
import sys
from datetime import datetime, timedelta, timezone

import urllib3
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date

from sources import SOURCES, SOURCE_TYPE_MAP

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; sb-digest-bot/1.0; for internal research)"
    )
}

TIMEOUT = 20

# Minimum title length to treat a link as an article (vs navigation).
MIN_TITLE_LEN = 20


def _get_soup(url: str) -> BeautifulSoup | None:
    try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=True)
        except requests.exceptions.SSLError:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"    [warning] Could not fetch {url}: {e}", file=sys.stderr)
        return None


LOOKBACK_HOURS = 24

# Date patterns to search for near each article on a scraped page
_DATE_PATTERN = re.compile(
    r"\b(\d{4}[-/]\d{2}[-/]\d{2}"              # 2026-03-06
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"  # March 6, 2026
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})"   # 6 March 2026
    r"\b",
    re.IGNORECASE,
)


def _extract_date_from_text(text: str) -> datetime | None:
    """Try to find and parse a date in a block of text. Returns UTC-aware datetime or None."""
    for m in _DATE_PATTERN.finditer(text):
        try:
            dt = parse_date(m.group(0), dayfirst=False)
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, OverflowError):
            continue
    return None


def _make_absolute(href: str, base_url: str) -> str:
    """Turn a relative href into an absolute URL."""
    if href.startswith("http"):
        return href
    from urllib.parse import urljoin
    return urljoin(base_url, href)


def _find_articles(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Extract article title+URL+nearby_text tuples from a news page.
    nearby_text is used for date extraction in the caller.
    Tries several strategies in order, returns the best result.
    """
    candidates = []  # list of (title, url, nearby_text)

    # Strategy 1: <article> elements
    for article in soup.find_all("article"):
        a = article.find("a", href=True)
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) >= MIN_TITLE_LEN:
            candidates.append((title, _make_absolute(a["href"], base_url), article.get_text(" ")))

    if candidates:
        return [{"title": t, "url": u, "nearby_text": tx} for t, u, tx in candidates]

    # Strategy 2: elements whose class suggests a news listing
    news_classes = re.compile(
        r"(news|post|article|item|entry|story|release|update|card)",
        re.IGNORECASE,
    )
    for el in soup.find_all(class_=news_classes):
        a = el.find("a", href=True)
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) >= MIN_TITLE_LEN:
            candidates.append((title, _make_absolute(a["href"], base_url), el.get_text(" ")))

    if candidates:
        seen = set()
        unique = []
        for t, u, tx in candidates:
            if u not in seen:
                seen.add(u)
                unique.append({"title": t, "url": u, "nearby_text": tx})
        return unique

    # Strategy 3: heading tags with links
    for tag in soup.find_all(["h2", "h3", "h4"]):
        a = tag.find("a", href=True)
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) >= MIN_TITLE_LEN:
            nearby = tag.get_text(" ") + " " + (tag.find_next_sibling() or tag).get_text(" ")
            candidates.append((title, _make_absolute(a["href"], base_url), nearby))

    seen = set()
    unique = []
    for t, u, tx in candidates:
        if u not in seen:
            seen.add(u)
            unique.append({"title": t, "url": u, "nearby_text": tx})
    return unique


CURRENT_YEAR = str(datetime.now(timezone.utc).year)


def _fetch_wordpress(src: dict) -> list[dict] | None:
    """
    Fetch recent posts via WordPress REST API.
    Returns a list of article dicts, or None if the API is unavailable.
    """
    base_url    = src.get("base_url", "").rstrip("/")
    source_type  = src.get("source_type", "National news")
    article_type = SOURCE_TYPE_MAP.get(source_type, "discussion")
    after = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%S")

    api_url = f"{base_url}/wp-json/wp/v2/posts"
    params  = {"after": after, "per_page": 20, "_fields": "title,link,date,excerpt"}

    try:
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=TIMEOUT, verify=False)
        resp.raise_for_status()
        posts = resp.json()
        if not isinstance(posts, list):
            return None
    except Exception as e:
        print(f"    [warning] WordPress API unavailable for {src['name']}: {e}", file=sys.stderr)
        return None

    articles = []
    for post in posts:
        title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", "")).strip()
        url   = post.get("link", "")
        if not title or not url:
            continue

        date_str = post.get("date", "")
        try:
            pub_dt  = datetime.fromisoformat(date_str)
            pub_str = pub_dt.strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            pub_str = ""

        excerpt = re.sub(r"<[^>]+>", " ", post.get("excerpt", {}).get("rendered", ""))
        excerpt = re.sub(r"\s+", " ", excerpt).strip()[:400]

        articles.append({
            "title":          title,
            "url":            url,
            "source_name":    src["name"],
            "source_type":    source_type,
            "article_type":   article_type,
            "published_date": pub_str,
            "summary":        excerpt,
        })

    return articles


def fetch_all_scraped() -> list[dict]:
    """
    Fetch all scraped (non-RSS, non-manual) sources and return article dicts.

    For sources with wordpress=True, tries the WordPress REST API first
    (clean dates, proper excerpts) and falls back to HTML scraping.
    For HTML-scraped items, requires the current year to appear in nearby
    text if no parseable date is found — filtering out old archived content.
    """
    scraped_sources = [
        s for s in SOURCES
        if not s.get("has_rss")
        and s.get("scrape")
        and s.get("scrape_module") is None  # hoc/senate handled separately
        and s.get("news_url")
    ]

    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    for src in scraped_sources:
        source_type  = src.get("source_type", "National news")
        article_type = SOURCE_TYPE_MAP.get(source_type, "discussion")
        print(f"  Fetching: {src['name']} ...")

        # ── WordPress REST API path ───────────────────────────────────────────
        if src.get("wordpress"):
            wp_articles = _fetch_wordpress(src)
            if wp_articles is not None:
                articles.extend(wp_articles)
                print(f"    {src['name']}: {len(wp_articles)} item(s) via WordPress API")
                continue
            # fall through to HTML scraping if API failed

        # ── HTML scraping path ────────────────────────────────────────────────
        news_url = src["news_url"]
        soup = _get_soup(news_url)
        if soup is None:
            continue

        found = _find_articles(soup, news_url)
        kept  = 0

        for item in found:
            nearby = item.get("nearby_text", "")
            pub_dt = _extract_date_from_text(nearby)

            if pub_dt:
                # Date found — skip if older than cutoff
                if pub_dt < cutoff:
                    continue
                pub_str = pub_dt.strftime("%B %d, %Y")
            else:
                # No parseable date — require current year to appear in nearby text
                if CURRENT_YEAR not in nearby:
                    continue
                pub_str = ""

            articles.append({
                "title":          item["title"],
                "url":            item["url"],
                "source_name":    src["name"],
                "source_type":    source_type,
                "article_type":   article_type,
                "published_date": pub_str,
                "summary":        "",
            })
            kept += 1

        print(f"    {src['name']}: {kept} item(s) (of {len(found)} on page)")

    return articles
