"""
Generic RSS / Atom feed fetcher.

Fetches all RSS-enabled sources from sources.py, filters to items published
in the last 48 hours (or includes undated items), and returns a flat list
of article dicts in a standard format.
"""

import sys
import time
from datetime import datetime, timezone, timedelta

import urllib3
import feedparser
import requests

from sources import SOURCES, SOURCE_TYPE_MAP

# Suppress SSL warnings — some government/org sites have cert issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; sb-digest-bot/1.0; for internal research)"
    )
}

# Include items published within this many hours.
LOOKBACK_HOURS = 24

# Per-feed timeout in seconds.
FEED_TIMEOUT = 20


def _parse_time(entry) -> datetime | None:
    """Extract a timezone-aware datetime from a feedparser entry, or None."""
    for field in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


def _get_summary(entry) -> str:
    """Return the best available summary text from a feedparser entry."""
    for field in ("summary", "description", "content"):
        val = getattr(entry, field, None)
        if val:
            if isinstance(val, list):
                val = val[0].get("value", "")
            # Strip HTML tags crudely
            import re
            text = re.sub(r"<[^>]+>", " ", val)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text[:600]
    return ""


def fetch_all_rss() -> list[dict]:
    """
    Fetch all RSS-enabled sources and return a list of article dicts.
    Articles older than LOOKBACK_HOURS are skipped.
    Each dict contains: title, url, source_name, source_type, article_type,
                        published_date, summary.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    articles = []

    rss_sources = [s for s in SOURCES if s.get("has_rss")]
    print(f"  Fetching {len(rss_sources)} RSS feeds ...")

    for src in rss_sources:
        feed_url = src["rss_url"]
        try:
            # Try with SSL verification first; fall back to verify=False on SSL errors.
            try:
                resp = requests.get(feed_url, headers=HEADERS, timeout=FEED_TIMEOUT, verify=True)
            except requests.exceptions.SSLError:
                resp = requests.get(feed_url, headers=HEADERS, timeout=FEED_TIMEOUT, verify=False)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            print(f"    [warning] {src['name']}: {e}", file=sys.stderr)
            continue

        if not feed.entries:
            continue

        source_type = src.get("source_type", "National news")
        article_type = SOURCE_TYPE_MAP.get(source_type, "discussion")
        count = 0

        for entry in feed.entries:
            title = (getattr(entry, "title", "") or "").strip()
            url   = (getattr(entry, "link",  "") or "").strip()
            if not title or not url:
                continue

            pub = _parse_time(entry)
            if pub and pub < cutoff:
                continue  # too old

            summary = _get_summary(entry)
            pub_str = pub.strftime("%B %d, %Y") if pub else ""

            articles.append({
                "title":        title,
                "url":          url,
                "source_name":  src["name"],
                "source_type":  source_type,
                "article_type": article_type,
                "published_date": pub_str,
                "summary":      summary,
            })
            count += 1

        print(f"    {src['name']}: {count} item(s)")

    print(f"  RSS total: {len(articles)} items across all feeds")
    return articles
